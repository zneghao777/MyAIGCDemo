from copy import deepcopy
import math
from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select
from app.api.routers.resources import DB
from app.core.errors import AppError
from app.models import Project, Scene, uid
from app.schemas.creative import Edit, VideoInput
from app.services import creative as flow
from app.services.resources import children, require, ensure_idle, media_urls
from app.services.production_segments import segment_for, suggested_references, choose_take

router = APIRouter(prefix="/api/creative")


@router.get("/scenes/{id}/production")
async def production(id: str, db: DB):
    sc = await require(db, Scene, id)
    p = await require(db, Project, sc.project_id)
    group = segment_for(p, id)
    leader = await require(db, Scene, group["scene_ids"][0]) if group else sc
    from app.services.video_capabilities import CAPABILITIES
    return {"suggestions": await suggested_references(db, p, sc),
            "capabilities": CAPABILITIES,
            "segment": group, "leader_id": leader.id,
            "takes": media_urls((leader.creative or {}).get("video_takes", []))}


@router.post("/projects/{id}/segments")
async def group_shots(id: str, body: Edit, db: DB):
    p = await require(db, Project, id, True)
    flow.check_version(p.creative, body.expected)
    await ensure_idle(db, id)
    ids = body.data.get("scene_ids", [])
    rows = await children(db, Scene, id)
    positions = [i for i, row in enumerate(rows) if row.id in ids]
    if len(ids) != len(set(ids)) or len(positions) != len(ids) or not positions or positions != list(range(min(positions), max(positions)+1)):
        raise AppError("SEGMENT_ADJACENCY", "只能组合相邻且不重复的当前镜头", 422)
    ids = [rows[i].id for i in positions]
    groups = (p.creative or {}).get("production_segments", [])
    overlaps = [x for x in groups if set(x["scene_ids"]) & set(ids)]
    if any(not set(x["scene_ids"]) <= set(ids) for x in overlaps):
        raise AppError("SEGMENT_OVERLAP", "请先取消原片段组合，再重新组合相邻镜头", 409)
    updated = [x for x in groups if x not in overlaps]
    if body.data.get("action") != "split":
        if len(ids) < 2:
            raise AppError("SEGMENT_ADJACENCY", "请选择至少两个相邻镜头", 422)
        from app.services.video_capabilities import validate_duration
        validate_duration(sum(rows[i].duration_sec for i in positions))
        cursor, ranges = 0, []
        for i in positions:
            ranges.append({"scene_id": rows[i].id, "start_sec": cursor, "end_sec": cursor + rows[i].duration_sec})
            cursor += rows[i].duration_sec
        updated.append({"id": uid(), "scene_ids": ids, "shot_ranges": ranges, "cut_plan": "按各镜头设计切镜，时间仅作节奏引导"})
    await flow.save_state(db, p, {**p.creative, "production_segments": updated}, "project")
    await db.commit()
    return {"saved": True}


@router.post("/scenes/{id}/production-settings")
async def settings(id: str, body: Edit, db: DB):
    sc = await require(db, Scene, id)
    p = await require(db, Project, sc.project_id, True)
    flow.check_version(sc.creative, body.expected)
    inp = VideoInput.model_validate(body.data).model_dump()
    group = segment_for(p, id)
    if group and group["scene_ids"][0] != id:
        raise AppError("SEGMENT_MEMBER", "请在片段首镜设置制作方式", 409)
    if group and inp["mode"] not in ("references", "text"):
        raise AppError("SEGMENT_MODE", "多镜片段请选择多素材参考或纯文字预演", 422)
    shot = {**sc.creative["shot"], "video_input": inp}
    if inp["mode"] in ("references", "text"):
        shot.update(first_frame_asset_id=None, last_frame_asset_id=None, continuity_from=None)
    await flow.apply_shot(db, sc, await flow.validate_shot(db, p.id, shot, sc.creative.get("edit")))
    await db.commit()
    return {"saved": True}


@router.post("/scenes/{id}/select-video")
async def select_video(id: str, body: Edit, db: DB):
    leader = await require(db, Scene, id)
    p = await require(db, Project, leader.project_id, True)
    flow.check_version(leader.creative, body.expected)
    take = next((x for x in leader.creative.get("video_takes", []) if x.get("take") == body.data.get("take")), None)
    if not take:
        raise AppError("INVALID_CANDIDATE", "视频候选不存在", 404)
    await choose_take(db, p, leader, take)
    await db.commit()
    return {"selected": True}


@router.post("/scenes/{id}/edit-range")
async def edit_range(id: str, body: Edit, db: DB):
    sc = await require(db, Scene, id)
    p = await require(db, Project, sc.project_id, True)
    flow.check_version(sc.creative, body.expected)
    take = sc.creative.get("video") or {}
    start, end = body.data.get("in_sec"), body.data.get("out_sec")
    if not sc.video_key or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (start, end)) or not 0 <= start < end <= take.get("duration", 0) + .05:
        raise AppError("INVALID_EDIT_RANGE", "采用区间须位于当前实际视频范围内", 422)
    for other in await children(db, Scene, p.id):
        edit = (other.creative or {}).get("edit") or {}
        if other.id != id and other.video_key == sc.video_key and edit and max(start, edit["in_sec"]) < min(end, edit["out_sec"]) - .01:
            raise AppError("EDIT_OVERLAP", "同一视频的采用区间不能重叠；请先缩短相邻区间，再调整本镜", 422)
    await flow.save_state(db, sc, {**sc.creative, "edit": {"asset_id": take["asset_id"], "take": take["take"], "in_sec": start, "out_sec": end}}, "scene")
    await db.commit()
    return {"saved": True}


@router.post("/scenes/{id}/clean-video-audio")
async def clean_video_audio(id: str, body: Edit, db: DB):
    """Reversible local cleanup; a new previewable take, never an invisible mix."""
    import tempfile
    from pathlib import Path
    from app.providers import providers
    from app.services.locking import locked_scene
    from app.services.media import run_ffmpeg, probe_video
    from app.services.resources import save_asset
    from app.services.production_segments import members
    p, sc = await locked_scene(db, id)
    await members(db, p, sc)
    flow.check_version(sc.creative, body.expected)
    takes = sc.creative.get("video_takes", [])
    parent = next((x for x in takes if x.get("take") == body.data.get("take")), None)
    if not parent or parent.get("sound_strategy") != "model_audio":
        raise AppError("INVALID_AUDIO_SOURCE", "请选择本片段带原声的视频版本", 422)
    sound_take = next((x for x in takes if x.get("take") == body.data.get("audio_from_take", parent["take"])), None)
    if not sound_take or sound_take.get("sound_strategy") != "model_audio" or abs(sound_take.get("duration", 0) - parent.get("duration", 0)) > .1:
        raise AppError("INVALID_AUDIO_SOURCE", "复用声音须选择本片段时长相同的原声版本；不会自动拉伸或加速录音", 422)
    ranges = body.data.get("ranges", [])
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 20:
        raise AppError("INVALID_AUDIO_RANGE", "请选择要静音的原视频时间区间", 422)
    for span in ranges:
        if not isinstance(span, dict) or not all(isinstance(span.get(k), (float,int)) and math.isfinite(span[k]) for k in ("start", "end")) or not 0 <= span["start"] < span["end"] <= parent.get("duration", 0):
            raise AppError("INVALID_AUDIO_RANGE", "静音区间必须位于原视频实际时长内", 422)
    fingerprint = flow.digest({"take": parent["take"], "audio_from_take": sound_take["take"], "ranges": ranges})
    if any((take.get("audio_cleanup") or {}).get("fingerprint") == fingerprint for take in takes):
        return {"saved": True}
    async def checkpoint(): pass
    with tempfile.TemporaryDirectory() as folder:
        source, target = Path(folder)/"source.mp4", Path(folder)/"clean.mp4"
        source.write_bytes(await providers().storage.get(parent["key"]))
        sound_source = Path(folder)/"sound.mp4"
        sound_source.write_bytes(await providers().storage.get(sound_take["key"]))
        filters = ",".join(f"volume=0:enable='between(t,{span['start']},{span['end']})'" for span in ranges)
        await run_ffmpeg(["-i",str(source),"-i",str(sound_source),"-map","0:v:0","-map","1:a:0","-c:v","copy","-af",filters,"-c:a","aac","-b:a","192k","-t",str(parent["duration"]),"-movflags","+faststart",str(target)],checkpoint)
        meta = await probe_video(target)
        asset = await save_asset(db,p.id,"video",target.read_bytes(),"video/mp4","mp4",f"scenes/{sc.id}/video",duration_ms=round(meta["duration"]*1000))
        asset.width, asset.height = meta["width"], meta["height"]
    trace = {**deepcopy(parent), **meta, "key":asset.object_key,"asset_id":asset.id,"take":uid(),"accepted":False,
             "audio_cleanup":{"parent_take":parent["take"],"audio_from_take":sound_take["take"],"ranges":ranges,"fingerprint":fingerprint},
             "post_processing":[*parent.get("post_processing",[]),{"kind":"local_audio_mute","ranges":ranges}]}
    await flow.save_state(db,sc,{**sc.creative,"video_takes":[*takes,trace]},"scene")
    await db.commit()
    return {"saved":True}


@router.post("/projects/{id}/add-shot")
async def add_shot(id: str, body: Edit, db: DB):
    p = await require(db, Project, id, True)
    flow.check_version(p.creative, body.expected)
    await ensure_idle(db, id)
    rows = await children(db, Scene, id)
    if len(rows) >= 24:
        raise AppError("SHOT_LIMIT", "最多支持 24 镜", 422)
    from app.schemas.creative import Shot
    location = p.creative["plan"]["locations"][0]
    shot = Shot(title="新的镜头", location_id=location["id"], location_description=location["description"]).model_dump()
    sc = Scene(project_id=id, order_index=len(rows))
    db.add(sc)
    await db.flush()
    await flow.apply_shot(db, sc, shot)
    await flow.save_state(db, p, {**p.creative, "shots_confirmed": False}, "project")
    await db.commit()
    return {"scene_id": sc.id}


@router.post("/projects/{id}/reference-media")
async def upload_reference_media(id: str, db: DB, file: UploadFile = File(...)):
    import tempfile
    from pathlib import Path
    from app.services.resources import save_asset, inspect_image
    from app.services.media import probe, probe_video
    from app.services.video_capabilities import CAPABILITIES
    await require(db, Project, id)
    kind = (file.content_type or "").split("/")[0]
    if kind not in ("image", "audio", "video"):
        raise AppError("INVALID_MEDIA", "请选择图片、声音或视频参考", 422)
    limit = CAPABILITIES["max_file_mib"][kind] * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise AppError("PAYLOAD_TOO_LARGE", "参考素材超过当前渠道文件大小限制", 413)
    duration = None
    if kind == "image":
        fmt, _, _ = inspect_image(raw)
        mime, suffix = "image/" + fmt.lower().replace("jpg", "jpeg"), fmt.lower()
    else:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reference"
            path.write_bytes(raw)
            duration = await probe(path)
            if not 2 <= duration <= 15:
                raise AppError("REFERENCE_DURATION", "请上传 2–15 秒的音视频参考；已有项目素材可在参考清单中截取", 422)
            if kind == "video":
                await probe_video(path)
        mime = file.content_type
        suffix = Path(file.filename or "").suffix.lstrip(".") or ("mp4" if kind == "video" else "mp3")
    asset = await save_asset(db, id, "generation-reference", raw, mime, suffix, duration_ms=round(duration * 1000) if duration else None)
    await db.commit()
    from app.providers import providers
    return {"asset_id": asset.id, "kind": kind, "name": file.filename or "补充参考", "purpose": "补充参考", "url": providers().storage.url(asset.object_key)}


@router.post("/projects/{id}/reference-excerpt")
async def reference_excerpt(id: str, body: Edit, db: DB):
    import tempfile
    from pathlib import Path
    from app.models import Asset
    from app.providers import providers
    from app.services.media import probe, run_ffmpeg
    from app.services.resources import save_asset
    p = await require(db, Project, id, True)
    flow.check_version(p.creative, body.expected)
    asset = await require(db, Asset, body.data.get("asset_id", ""))
    kind = asset.content_type.split("/")[0]
    if asset.project_id != id or kind not in ("audio", "video"):
        raise AppError("INVALID_REFERENCE", "请选择当前项目的音视频参考", 422)
    if body.data.get("audio_only"):
        kind = "audio"
    start, end = body.data.get("start_sec"), body.data.get("end_sec")
    if not all(isinstance(x, (int,float)) and math.isfinite(x) for x in (start,end)) or not 0 <= start < end or not 2 <= end-start <= 15:
        raise AppError("REFERENCE_DURATION", "参考区间长度须为 2–15 秒", 422)
    async def checkpoint(): pass
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"source";path.write_bytes(await providers().storage.get(asset.object_key))
        duration=await probe(path)
        if end > duration + .05:
            raise AppError("REFERENCE_DURATION", "参考区间超过原素材时长", 422)
        target=Path(folder)/("excerpt.mp4" if kind=="video" else "excerpt.mp3")
        args=["-ss",str(start),"-i",str(path),"-t",str(end-start)]
        args += ["-c:v","libx264","-c:a","aac"] if kind=="video" else ["-vn","-c:a","libmp3lame"]
        await run_ffmpeg([*args,str(target)],checkpoint)
        result=await save_asset(db,id,"generation-reference",target.read_bytes(),"video/mp4" if kind=="video" else "audio/mpeg","mp4" if kind=="video" else "mp3",duration_ms=round((end-start)*1000))
    await db.commit()
    return {"asset_id":result.id,"kind":kind,"name":"参考节选","purpose":body.data.get("purpose","参考节选"),"url":providers().storage.url(result.object_key),"duration":end-start}

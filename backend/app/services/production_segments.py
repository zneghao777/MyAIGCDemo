"""Adjacent shot plans, paid takes and editorial ranges, without destructive migration."""
from copy import deepcopy
from sqlalchemy import select
from app.core.errors import AppError
from app.models import Scene, Asset, Character, Project
from app.services.resources import children, require


def segment_for(project, scene_id):
    return next((x for x in (getattr(project, "creative", None) or {}).get("production_segments", []) if scene_id in x["scene_ids"]), None)


async def members(db, project, scene):
    group = segment_for(project, scene.id)
    if not group:
        return [scene]
    if group["scene_ids"][0] != scene.id:
        raise AppError("SEGMENT_MEMBER", "本镜已编入相邻片段，请从片段首镜生成并选用", 409)
    rows = [await require(db, Scene, sid) for sid in group["scene_ids"]]
    if any(x.project_id != project.id or x.order_index < 0 for x in rows):
        raise AppError("SEGMENT_STALE", "片段包含已归档镜头，请重新组合当前镜头", 409)
    return rows


async def snapshot(db, project, scene):
    from .video import source
    group = segment_for(project, scene.id)
    if not group:
        return None
    rows = [await require(db, Scene, sid) for sid in group["scene_ids"]]
    plan, cursor, ranges = deepcopy(group), 0, []
    for row in rows:
        ranges.append({"scene_id": row.id, "start_sec": cursor, "end_sec": cursor + row.duration_sec})
        cursor += row.duration_sec
    plan["shot_ranges"] = ranges
    return {"plan": plan, "shots": {x.id: source(x, project.ratio) for x in rows}}


async def choose_take(db, p, leader, take):
    from .creative import save_state
    from .video import current_source, source
    current = await current_source(db, leader, p.ratio)
    if current != take.get("generation_source", take.get("source")):
        raise AppError("STALE_CANDIDATE", "视频基于旧设计，已保留供对比；请按当前内容重新生成", 409)
    rows = await members(db, p, leader)
    duration = take["duration"]
    planned = sum(x.duration_sec for x in rows)
    if len(rows) > 1 and duration < planned - .15:
        raise AppError("SEGMENT_TOO_SHORT", "实际视频短于设计，请先调整片段设计或重新生成，不能截断后续台词", 409)
    cursor = 0
    for i, sc in enumerate(rows):
        end = duration if i == len(rows) - 1 else cursor + sc.duration_sec
        trace = {**deepcopy(take), "source": source(sc, p.ratio), "segment_source": current.get("segment"),
                 "generation_source": current, "leader_id": leader.id}
        edit = {"take": take["take"], "asset_id": take["asset_id"], "in_sec": cursor, "out_sec": end}
        sc.video_key, sc.status = take["key"], "done"
        # Native dialogue may move between takes even when the written script
        # is unchanged. Keep editable cues, but never inherit their acceptance.
        shot = deepcopy((sc.creative or {}).get("shot") or {})
        if take.get("sound_strategy") == "model_audio":
            shot["subtitles_calibrated"] = False
        await save_state(db, sc, {**sc.creative, "shot": shot, "video": trace, "edit": edit}, "scene")
        cursor = end


async def suggested_references(db, p, scene):
    from app.providers import providers
    group = segment_for(p, scene.id)
    rows = [await require(db, Scene, sid) for sid in group["scene_ids"]] if group else [scene]
    assets = {x.object_key: x for x in await db.scalars(select(Asset).where(Asset.project_id == p.id))}
    options = {}
    def add(ref, kind, name, purpose):
        asset = assets.get((ref or {}).get("key"))
        if asset:
            options[asset.id] = {"asset_id": asset.id, "kind": kind, "name": name, "purpose": purpose,
                                 "url": providers().storage.url(asset.object_key), "duration": (asset.duration_ms or 0) / 1000}
    chars = {c.id: c for c in await children(db, Character, p.id)}
    for sc in rows:
        shot = (sc.creative or {}).get("shot") or {}
        for cid in shot.get("cast", {}):
            ch = chars.get(cid)
            if ch:
                add((ch.creative or {}).get("image"), "image", ch.name + "的形象", ch.name + "的身份、外貌与服装，保持同一人物")
        for cid in {x.get("speaker_id") for x in shot.get("lines", [])}:
            ch = chars.get(cid)
            if ch:
                voice = (ch.creative or {}).get("voice") or {}
                add(voice.get("reference") or voice, "audio", ch.name + "的声音", ch.name + "的音色参考；只参考音色，按本段新台词说话，不复述原音频内容")
        loc = (p.creative or {}).get("locations", {}).get(shot.get("location_id"), {})
        add(loc.get("image"), "image", (loc.get("location") or {}).get("name", "场景") + "的环境", "保持该场景的地标、光照与空间关系")
    return list(options.values())

"""Versioned H3 inputs shared by read-only quotes, submission and export."""

from copy import deepcopy
import math

from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Asset, Candidate, Scene, Character, Project
from app.providers.minimax import MiniMaxVideo
from app.services.creative import (
    current_input,
    digest,
    image_fingerprint_matches,
    pending_changes,
    shot_inputs,
)


def generative_shot(shot):
    omitted = {"acceptance", "issues", "review", "subtitle_cues", "subtitles_calibrated", "beat_indices"}
    if (shot.get("video_input") or {}).get("sound_strategy", "post_audio") == "post_audio":
        omitted.update(("sound_effects", "sound_notes"))
    result = {k: deepcopy(v) for k, v in shot.items() if k not in omitted}
    if not result.get("offscreen_cast"):
        result.pop("offscreen_cast", None)
    for line in result.get("lines", []) + result.get("narration", []):
        if line.get("delivery") == "on_screen":
            line.pop("delivery")
        if not line.get("continues_from"):
            line.pop("continues_from", None)
    return result


def source(scene, ratio):
    shot = (scene.creative or {}).get("shot") or {}
    mode = (shot.get("video_input") or {}).get("mode", "first_frame")
    data = {
        "first_frame_key": scene.first_frame_key if mode in ("first_frame", "first_last_frame") else None,
        "duration_sec": scene.duration_sec,
        "ratio": ratio,
        "video_prompt": scene.video_prompt,
        "action": shot.get("action") or scene.image_prompt,
        "camera_move": scene.camera_move,
        # Copy only generative inputs, not editorial acceptance/revision flags.
        "shot": generative_shot(shot),
    }
    segments = ((scene.creative or {}).get("audio") or {}).get("segments")
    if segments and (shot.get("video_input") or {}).get("sound_strategy", "post_audio") == "post_audio":
        data["audio_timing"] = [
            {
                "id": x.get("line", {}).get("id"),
                "key": x.get("key"),
                "duration_ms": x.get("duration_ms"),
                "pause_after": x.get("line", {}).get("pause_after", 0),
            }
            for x in segments
        ]
    return data


async def current_source(db, scene, ratio):
    data = source(scene, ratio)
    from .production_segments import snapshot
    project = await db.get(Project, scene.project_id)
    group = await snapshot(db, project, scene) if project else None
    if group:
        data["segment"] = group
    previous_id = data["shot"].get("continuity_from")
    if previous_id:
        previous = await db.get(Scene, previous_id)
        if (
            not previous
            or previous.project_id != scene.project_id
            or previous.order_index >= scene.order_index
        ):
            raise AppError("VIDEO_DEPENDENCY_INVALID", "尾帧依赖必须指向同项目的前序分镜", 422)
        data["dependency"] = {"scene_id": previous.id, "video_key": previous.video_key}
        if (getattr(previous, "creative", None) or {}).get("edit"):
            data["dependency"]["edit"] = previous.creative["edit"]
    return data


async def dependency_is_stale(db, scene):
    stored = ((scene.creative or {}).get("video") or {}).get("source") or {}
    from .production_segments import snapshot
    take = (scene.creative or {}).get("video") or {}
    if take.get("segment_source"):
        project = await db.get(Project, scene.project_id)
        if take["segment_source"] != await snapshot(db, project, scene):
            return True
    dependency = stored.get("dependency")
    if not dependency:
        return False
    previous = await db.get(Scene, dependency["scene_id"])
    return not previous or previous.video_key != dependency.get("video_key") or ((getattr(previous, "creative", None) or {}).get("edit") or None) != dependency.get("edit")


def organized_prompt(scene, materials, video_input, names=None, *, multi=False):
    from .story_pacing import estimated_line_seconds
    shot = (scene.creative or {}).get("shot") or {}
    names = names or {}
    native = video_input.get("sound_strategy") == "model_audio"
    counters = {"image": 0, "video": 0, "audio": 0}
    labels = {"image": "Picture", "video": "Video", "audio": "Audio"}
    uses = []
    for material in materials:
        if material["role"].startswith("reference_"):
            kind = material["kind"]
            counters[kind] += 1
            tag = f"<{labels[kind]} {counters[kind]}>"
        else:
            tag = "首帧" if material["role"] == "first_frame" else "尾帧"
        uses.append(f"{tag}：{material.get('purpose') or '以该素材定义画面'}")
    by_id = {x["id"]: x for x in shot.get("lines", []) + shot.get("narration", [])}
    measured = {x.get("line", {}).get("id"): x for x in ((scene.creative or {}).get("audio") or {}).get("segments", [])}
    if "lines" not in shot and "narration" not in shot:
        by_id = {lid: segment["line"] for lid, segment in measured.items()}
    timing, cursor = [], 0
    for lid in shot.get("audio_order") or list(by_id):
        line = by_id[lid]
        speaker = names.get(line.get("speaker_id"), "独立旁白" if not line.get("speaker_id") else "已设定角色")
        delivery = "画外音，不要求说话人入画" if line.get("delivery") == "off_screen" or line.get("speaker_id") in shot.get("offscreen_cast", {}) else "画内说话，嘴型匹配对白；嘴部清晰可见，每个字有相应开合，禁止闭嘴配音" if line.get("speaker_id") else "画外旁白"
        if line.get("continues_from"):
            timing.append(f"{speaker}：延续前镜同一句声音，不重新说一遍；切镜后{delivery}。")
            continue
        segment = measured.get(lid) if video_input.get("sound_strategy") != "model_audio" else None
        trigger = next((x.get("trigger_sec", x.get("start_sec", 0)) for x in shot.get("action_steps", []) if x.get("trigger_line_id") == lid), None)
        if trigger is not None:
            cursor = max(cursor, trigger)
        seconds = segment.get("duration_ms", 0) / 1000 if segment else estimated_line_seconds(line) - line.get("pause_after", .15)
        spoken = f"<d>[Chinese] {line['text']}</d>" if native else f"“{line['text']}”"
        timing.append(f"{'录音实测' if segment else '预计，非精确对齐'} {cursor:g}–{cursor + seconds:g}秒，{speaker}，{delivery}，{line.get('emotion', 'neutral')}：{spoken}")
        cursor += seconds + line.get("pause_after", .15)
    steps = []
    for x in shot.get("action_steps", []):
        trigger = by_id.get(x.get("trigger_line_id"), {}).get("text")
        steps.append(f"{x['start_sec']:g}–{x['end_sec']:g}秒：{x['description']}" + (f"（在说‘{trigger}’时触发）" if trigger else ""))
    spatial = "；".join(f"{names.get(cid, '画内角色')}：{position}" for cid, position in shot.get("spatial_relations", {}).items())
    parts = [
        "执行边界：只有“对白与旁白顺序”中对白标记内的台词允许被说出，其他所有文字都是拍摄指令，绝不能念出来。音色参考与原视频都不能带入额外对白。" if native else "后期配音模式：本次画面生成不合入任何人声。",
        "素材用途：" + ("；".join(uses) or ("沿用片段共同参考，按本镜出场名单入画" if multi else "纯文字预演，无人物身份参考")),
        "叙事目的：" + shot.get("purpose", ""),
        "画内角色：" + "、".join(names.get(cid, "已设定角色") for cid in shot.get("cast", {})),
        "场景与空间：" + shot.get("location_description", "") + "；" + spatial,
        "起始状态：" + shot.get("start_state", ""),
        "人物动作：" + (shot.get("action") or scene.image_prompt),
        "动作时序：" + ("；".join(steps) or "按上述动作自然完成"),
        "对白与旁白顺序：" + ("；".join(timing) or "无对白"),
        f"镜头要求：{shot.get('shot_type', '')}，{shot.get('composition', '')}，{shot.get('camera_angle', '')}，{scene.camera_move}。" + ("遵守本段切镜计划。" if multi else "本镜连续表演，不擅自切镜。") + "不添加画面文字、字幕、拼图或水印。",
        "结束状态：" + shot.get("end_state", ""),
        "承接要求：" + shot.get("continuity_requirements", ""),
        "声音方式：" + ("生成普通话原声对白，按上述顺序完整说出，不复述音色参考中的旧文案，不添加其他台词；保留环境音，口型与新对白一致。" if native else "交付静音视频；独立配音、环境音及混音由后期完成，按对白节奏表演，不宣称已完成口型同步。"),
        "声音设计：" + shot.get("sound_notes", ""),
    ]
    extra = video_input.get("prompt") or scene.video_prompt
    if extra:
        parts.append("补充要求：" + extra)
    return "\n".join(parts)


async def resolve_material(db, project_id, asset_id, kind, role, purpose):
    asset = await db.get(Asset, asset_id) if asset_id else None
    if not asset or asset.project_id != project_id:
        raise AppError("H3_REFERENCE_MISSING", "视频引用素材不存在或属于其他项目", 422)
    if not asset.content_type.startswith(kind + "/"):
        raise AppError("H3_REFERENCE_TYPE", "视频引用素材类型与用途不匹配", 422)
    from .video_capabilities import CAPABILITIES
    limits = CAPABILITIES["max_file_mib"]
    if asset.size_bytes > limits[kind] * 1024 * 1024:
        raise AppError("PAYLOAD_TOO_LARGE", f"H3 {kind} 素材超过 {limits[kind]} MiB", 413)
    return {
        "asset_id": asset.id,
        "key": asset.object_key,
        "kind": kind,
        "role": role,
        "purpose": purpose,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "duration_ms": asset.duration_ms,
    }


async def validate_derived_tail(db, project, scene, first, tail_asset_id):
    """Only generated derivatives carry a mandatory first-frame dependency."""
    selected = (scene.creative or {}).get("last_frame") or {}
    fingerprint = None
    reference = None
    if selected.get("asset_id") == tail_asset_id and selected.get("reference_mode") == "shot-first-frame":
        fingerprint = selected.get("fingerprint")
        reference = selected.get("first_frame_reference")
    else:
        candidates = await db.scalars(
            select(Candidate)
            .where(
                Candidate.project_id == project.id,
                Candidate.entity_id == scene.id,
                Candidate.kind == "shot_image",
            )
            .order_by(Candidate.created_at.desc())
        )
        candidate = next(
            (
                row
                for row in candidates
                if row.data.get("asset_id") == tail_asset_id
                and row.data.get("request", {}).get("frame") == "last"
                and row.data.get("source", "provider") == "provider"
            ),
            None,
        )
        if not candidate:
            return  # Explicitly uploaded frames retain their human-review workflow.
        fingerprint = candidate.fingerprint
        reference = (candidate.data.get("input") or {}).get("first_frame_reference")
    if not reference or not reference.get("key"):
        raise AppError("LAST_FRAME_STALE", "该生成尾帧未绑定本镜首帧，请基于当前首帧派生并选用尾帧", 409)
    value = await current_input(db, project, "shot_image", scene.id, frame="last")
    if fingerprint != digest(value) or reference["key"] != first["key"]:
        raise AppError(
            "LAST_FRAME_STALE", "尾帧依赖的首帧、机位或分镜输入已变化，请选用与当前首帧一致的尾帧", 409
        )


async def payload(db, project, scene):
    from .production_segments import members
    shots = await members(db, project, scene)
    shot = (scene.creative or {}).get("shot") or {}
    video_input = shot.get("video_input") or {}
    mode = video_input.get("mode", "first_frame")
    if len(shots) > 1 and mode not in ("references", "text"):
        raise AppError("SEGMENT_MODE", "多镜片段请选择多素材参考或文字预演；首尾帧适合单镜过渡", 422)
    materials = []
    # A continued line must refer to the same speaker's earlier line within this
    # generated segment. Separate post-dub clips cannot carry one recording across cuts.
    prior_lines = {}
    for member in shots:
        member_shot = (member.creative or {}).get("shot") or {}
        for line in member_shot.get("lines", []) + member_shot.get("narration", []):
            origin = line.get("continues_from")
            if origin:
                original = prior_lines.get(origin)
                if not original or original.get("speaker_id") != line.get("speaker_id") or video_input.get("sound_strategy") != "model_audio":
                    raise AppError("CROSS_SHOT_AUDIO", "跨镜延续需引用同一原声片段内前镜的同一发言人台词；请组合镜头，或将续句作为新的画外台词", 422)
        prior_lines.update({x["id"]: x for x in member_shot.get("lines", []) + member_shot.get("narration", [])})
    if project.creative and shot:
        if not project.creative.get("shots_confirmed"):
            raise AppError("PRECHECK_FAILED", "请先确认分镜", 409)
        from .creative import validate_shot
        await validate_shot(db, project.id, shot, (scene.creative or {}).get("edit"))
        if mode in ("first_frame", "first_last_frame") and not (video_input.get("first_frame_asset_id") or shot.get("first_frame_asset_id")):
            image, _ = await shot_inputs(db, scene, need_audio=False)
            pending_image, _ = await pending_changes(db, scene)
            if pending_image or not image_fingerprint_matches((scene.creative.get("image") or {}).get("fingerprint"), image):
                raise AppError("STALE_IMAGE", f"{scene.title}：分镜画面过期，请先选用当前画面", 409)
    if mode in ("first_frame", "first_last_frame"):
        if video_input.get("references"):
            raise AppError("H3_MODE_CONFLICT", "首尾帧不能与参考素材混用", 422)
        first_id = video_input.get("first_frame_asset_id") or shot.get("first_frame_asset_id")
        if first_id:
            materials.append(
                await resolve_material(db, project.id, first_id, "image", "first_frame", "镜头起始状态")
            )
        elif scene.first_frame_key:
            # Legacy selected frames remain usable and traceable by their object key.
            materials.append(
                {
                    "key": scene.first_frame_key,
                    "kind": "image",
                    "role": "first_frame",
                    "purpose": "镜头起始状态",
                }
            )
        else:
            raise AppError("FIRST_FRAME_REQUIRED", "请先选择分镜首帧", 409)
        if mode == "first_last_frame":
            last_id = video_input.get("last_frame_asset_id") or shot.get("last_frame_asset_id")
            if not last_id:
                raise AppError("LAST_FRAME_REQUIRED", "首尾帧模式需要明确选择尾帧", 409)
            await validate_derived_tail(db, project, scene, materials[0], last_id)
            materials.append(
                await resolve_material(db, project.id, last_id, "image", "last_frame", "镜头结束状态")
            )
    elif mode == "references":
        if video_input.get("first_frame_asset_id") or video_input.get("last_frame_asset_id"):
            raise AppError("H3_MODE_CONFLICT", "全能参考模式不能同时传首尾帧", 422)
        for ref in video_input.get("references") or []:
            kind = ref.get("kind")
            if kind not in ("image", "video", "audio"):
                raise AppError("H3_REFERENCE_TYPE", "不支持的 H3 素材类型", 422)
            materials.append(
                await resolve_material(
                    db, project.id, ref.get("asset_id"), kind, "reference_" + kind, ref.get("purpose", "")
                )
            )
        if not materials:
            raise AppError("H3_REFERENCE_MISSING", "全能参考模式至少需要一张图片或一个视频", 422)
    elif mode != "text":
        raise AppError("INVALID_VIDEO_INPUT", "不支持的 H3 输入模式", 422)
    for kind in ("audio", "video"):
        timed = [m for m in materials if m["kind"] == kind and m.get("duration_ms")]
        if any(not 2000 <= m["duration_ms"] <= 15000 for m in timed) or sum(m["duration_ms"] for m in timed) > 15000:
            raise AppError("REFERENCE_DURATION", "音视频参考单段需 2–15 秒，同类总长不超过 15 秒；请换用较短参考", 422)
    s = get_settings()
    inp = await current_source(db, scene, project.ratio)
    resolution = video_input.get("resolution") or s.minimax_video_resolution
    points = MiniMaxVideo.estimate_points(sum(x.duration_sec for x in shots), resolution)
    names = {c.id: c.name for c in await db.scalars(select(Character).where(Character.project_id == project.id))}
    prompt = organized_prompt(scene, materials, video_input) if not names else organized_prompt(scene, materials, video_input, names)
    if len(shots) > 1:
        blocks, cursor = [], 0
        for member in shots:
            blocks.append(f"第 {len(blocks)+1} 镜，计划 {cursor:g}–{cursor+member.duration_sec:g} 秒，{member.title}（以下动作及对白时间从本镜起点算起）：\n" + organized_prompt(member, [], video_input, names, multi=True))
            cursor += member.duration_sec
        material_header = "\n".join(prompt.split("\n")[:2])
        prompt = material_header + "\n片段内按下列计划切镜；时间码是节奏引导，跨镜延续台词只说一次，环境音保持连续。\n" + "\n".join(blocks)
    prompt = f"视觉风格：{project.style}。\n" + prompt
    if (
        sum((m.get("size_bytes", 0) + 2) // 3 * 4 for m in materials) + len(prompt.encode())
        > 71 * 1024 * 1024
    ):
        raise AppError("PAYLOAD_TOO_LARGE", "H3 多素材请求预计超过 72 MiB，请减少素材", 413)
    MiniMaxVideo.validate_content(
        [
            {"type": "text", "text": prompt},
            *[
                {"type": m["kind"] + "_url", m["kind"] + "_url": {"url": m["key"]}, "role": m["role"]}
                for m in materials
            ],
        ]
    )
    return {
        **inp,
        "duration_sec": math.ceil(sum(x.duration_sec for x in shots)),
        "scene_ids": [x.id for x in shots],
        "prompt": prompt,
        "video_prompt": prompt,
        "materials": materials,
        "input_mode": mode,
        "sound_strategy": video_input.get("sound_strategy", "post_audio"),
        "mute_audio": video_input.get("sound_strategy", "post_audio") == "post_audio",
        "use_context_ir": video_input.get("use_context_ir", False),
        "model": s.minimax_video_model,
        "resolution": resolution,
        "estimated_points": points,
        "video_source": inp,
    }


def is_stale(scene, ratio):
    video = (scene.creative or {}).get("video")
    if not (scene.video_key and video):
        return False
    stored = {k: v for k, v in (video.get("source") or {}).items() if k not in ("dependency", "segment")}
    if "shot" in stored:
        stored["shot"] = generative_shot(stored["shot"])
    current = source(scene, ratio)
    # Older exports remain playable; adding the new empty shot snapshot is compatible.
    new_fields = (
        "purpose",
        "start_state",
        "end_state",
        "action_steps",
        "spatial_relations",
        "video_input",
        "first_frame_asset_id",
        "last_frame_asset_id",
        "continuity_from",
    )
    if "shot" not in stored and not any(current["shot"].get(k) for k in new_fields):
        current.pop("shot")
        if "audio_timing" not in stored:
            current.pop("audio_timing", None)
    return stored != current


async def retake_payload(db, project, scene, body):
    value = await payload(db, project, scene)
    if body.modify:
        if not body.source_asset_id:
            raise AppError("VIDEO_EDIT_SOURCE", "请选择要修改的原片版本", 422)
        known = [scene.creative.get("video") or {}, *scene.creative.get("video_takes", [])]
        if not any(x.get("asset_id") == body.source_asset_id for x in known):
            raise AppError("VIDEO_EDIT_SOURCE", "原片必须是本镜当前或历史视频", 422)
        material = await resolve_material(db, project.id, body.source_asset_id, "video", "reference_video", "待修改的原视频")
        # Frame modes cannot mix frames and references. Reuse the frame as identity/composition reference.
        materials = deepcopy(value["materials"])
        for m in materials:
            if m["role"] in ("first_frame", "last_frame"):
                m["role"] = "reference_image"
        materials.append(material)
        number = sum(m["kind"] == "video" for m in materials)
        names = {c.id: c.name for c in await db.scalars(select(Character).where(Character.project_id == project.id))}
        inp = (scene.creative.get("shot") or {}).get("video_input") or {}
        header = next(line for line in organized_prompt(scene, materials, inp, names).split("\n") if line.startswith("素材用途："))
        value["prompt"] = "\n".join(header if line.startswith("素材用途：") and "沿用片段" not in line else line for line in value["prompt"].split("\n")) + f"\n基于 <Video {number}> 定向修改：{body.reason}。保留：{body.preserve or '未要求修改的人物、环境、动作和镜头节奏'}。修改结果需要回放验收，不保证逐帧一致。"
        timed = [m for m in materials if m["kind"] == "video" and m.get("duration_ms")]
        if any(not 2000 <= m["duration_ms"] <= 15000 for m in timed) or sum(m["duration_ms"] for m in timed) > 15000:
            raise AppError("REFERENCE_DURATION", "修改原视频需在 2–15 秒内，全部视频参考总长不超过 15 秒；请先选择较短片段", 422)
        value.update(materials=materials, input_mode="references", first_frame_key=None)
    else:
        value["prompt"] += "\n本次重拍要求：" + body.reason
    MiniMaxVideo.validate_content([{"type": "text", "text": value["prompt"]}, *[{"type": m["kind"] + "_url", m["kind"] + "_url": {"url": m["key"]}, "role": m["role"]} for m in value["materials"]]])
    value["video_prompt"] = value["prompt"]
    return value

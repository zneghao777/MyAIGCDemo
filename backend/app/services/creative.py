"""Creative workflow on the existing Project/Character/Scene/Task/Asset pipeline.

All expensive jobs retain candidates. Storyboards may opt into automatic application.
Fingerprints are dependency-specific, so a voice change cannot stale an image.
"""

import hashlib
import json
from copy import deepcopy

from sqlalchemy import func, select
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Asset, Candidate, Character, Project, Revision, Scene
from app.providers import providers
from app.schemas.creative import Location, Persona, Plan, Shot, Storyboard, VoiceMatches
from app.services import tts
from app.services.resources import children, require, save_asset
from app.services.storyboard_recovery import dependencies


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def check_version(state, expected):
    if state.get("version", 0) != expected:
        raise AppError("STALE_VERSION", "内容已更新，请刷新后再保存；旧版本已保留", 409)


async def revision(db, project_id, entity_id, kind, data):
    row = Revision(project_id=project_id, entity_id=entity_id, kind=kind, data=deepcopy(data))
    db.add(row)
    await db.flush()
    return row.id


async def save_state(db, row, data, kind):
    state = deepcopy(data)
    if kind == "project":
        state.pop("stage", None)
    state["version"] = (row.creative or {}).get("version", 0) + 1
    state.pop("revision", None)
    from app.services.workbench import creation_event

    state.pop("_event", None)
    if creation_event.get():
        state["_event"] = creation_event.get()
    state["revision"] = await revision(
        db, row.id if isinstance(row, Project) else row.project_id, row.id, kind, state
    )
    row.creative = state
    return state


def visual(persona):
    return {
        k: v
        for k, v in persona.items()
        if k
        not in (
            "voice_description",
            "voice_prompt",
            "base_speed",
            "base_pitch",
            "voice_mode",
            "variants",
            "role_kind",
        )
    }


def image_fingerprint(persona, style):
    return digest({"persona": visual(persona), "style": style})


def image_fingerprint_matches(fingerprint, image):
    if fingerprint == digest(image):
        return True
    # A schema upgrade alone must not invalidate selected historical pictures.
    # Preserve the original hash; only reproduce its original input contract.
    additions = {
        "purpose",
        "start_state",
        "end_state",
        "action_steps",
        "spatial_relations",
        "continuity_from",
        "continuity_requirements",
        "location_revision",
        "location_state",
        "character_views",
    }
    shot = image.get("shot", {})
    if (
        image.get("frame", "first") != "first"
        or image.get("location")
        or any(shot.get(k) not in (None, "", False, [], {}) for k in additions)
    ):
        return False
    legacy = {k: v for k, v in image.items() if k not in ("frame", "location")}
    legacy["shot"] = {k: v for k, v in shot.items() if k not in additions}
    return fingerprint == digest(legacy)


def variant_fingerprint(state, name, style):
    return digest(
        {
            "base": image_fingerprint(state["persona"], style),
            "main_key": (state.get("image") or {}).get("key"),
            "variant": state["persona"].get("variants", {}).get(name),
            "name": name,
        }
    )


def character_reference(state, variant, style):
    main = state.get("image")
    if not main or main.get("fingerprint") != image_fingerprint(state["persona"], style):
        raise AppError("IMAGE_REQUIRED", "角色主参考图缺失或与当前外貌、风格不一致，请重新选定", 409)
    if not variant:
        return main
    ref = state.get("references", {}).get(variant)
    if not ref or ref.get("fingerprint") != variant_fingerprint(state, variant, style):
        raise AppError(
            "VARIANT_REFERENCE_REQUIRED",
            f"造型「{variant}」参考图缺失或已过期，请基于当前主图重新生成并选用",
            409,
        )
    return ref


def view_fingerprint(state, view, style):
    return digest(
        {
            "base": image_fingerprint(state["persona"], style),
            "main_key": (state.get("image") or {}).get("key"),
            "view": view,
        }
    )


def selected_character_reference(state, variant, view, style):
    base = character_reference(state, variant, style)
    if not view or view in ("state", "main"):
        return base
    ref = state.get("views", {}).get(view)
    if not ref or not ref.get("confirmed") or ref.get("fingerprint") != view_fingerprint(state, view, style):
        raise AppError(
            "VIEW_REFERENCE_REQUIRED", f"角色 {view} 视图缺失、未确认或已过期，请先选择并检查", 409
        )
    return ref


async def location_state(db, p, location_id):
    location = next(
        (x for x in (p.creative.get("plan") or {}).get("locations", []) if x["id"] == location_id), None
    )
    if not location:
        raise AppError("INVALID_LOCATION", "地点不属于当前项目方案", 422)
    return deepcopy(
        p.creative.get("locations", {}).get(location_id)
        or {"version": 0, "location": Location.model_validate(location).model_dump(), "confirmed": False}
    )


def location_visual_inputs(state):
    location = state.get("location", {})

    def reference(ref):
        return {key: ref.get(key) for key in ("key", "asset_id", "candidate_id")}

    return {
        "location": {key: value for key, value in location.items() if key not in {"name", "description"}},
        "image": reference(state.get("image") or {}),
        "states": {name: reference(ref) for name, ref in state.get("states", {}).items()},
    }


async def save_location(db, p, location_id, state):
    st = deepcopy(state)
    old = p.creative.get("locations", {}).get(location_id, {})
    copy_only = (
        bool(old)
        and old.get("location") != st.get("location")
        and location_visual_inputs(old) == location_visual_inputs(st)
    )
    if copy_only:
        st["confirmed"] = old.get("confirmed", False)
        # The pixels remain the same; refresh their metadata fingerprint for the edited text.
        if st.get("image") and st["image"].get("fingerprint") == location_fingerprint(old, p.style):
            st["image"]["fingerprint"] = location_fingerprint(st, p.style)
        for name, reference in st.get("states", {}).items():
            if reference.get("fingerprint") == location_fingerprint(old, p.style, name):
                reference["fingerprint"] = location_fingerprint(st, p.style, name)
    visual_changed = (
        location_visual_inputs(old) != location_visual_inputs(st)
        or old.get("confirmed", False) != st.get("confirmed", False)
    )
    st["version"] = old.get("version", 0) + 1
    st["revision"] = await revision(db, p.id, location_id, "location", st)
    await save_state(
        db,
        p,
        {
            **p.creative,
            "locations": {**p.creative.get("locations", {}), location_id: st},
            "shots_confirmed": False if visual_changed else p.creative.get("shots_confirmed", False),
        },
        "project",
    )
    if not visual_changed:
        return st
    for sc in await children(db, Scene, p.id):
        shot = (sc.creative or {}).get("shot") or {}
        if shot.get("location_id") == location_id and shot.get("location_revision"):
            await save_state(
                db, sc, {**sc.creative, "dependency_stamp": digest({"location": st["revision"]})}, "scene"
            )
    return st


def location_fingerprint(state, style, state_name=""):
    return digest(
        {
            "location": state["location"],
            "style": style,
            "state": state_name,
            "main_key": (state.get("image") or {}).get("key") if state_name else None,
        }
    )


async def selected_location_reference(db, p, shot):
    rid = shot.get("location_revision")
    if not rid:
        return None  # Imported projects retain their historical text-only environments.
    r = await require(db, Revision, rid)
    if (
        r.project_id != p.id
        or r.entity_id != shot["location_id"]
        or r.kind != "location"
        or not r.data.get("confirmed")
    ):
        raise AppError("INVALID_LOCATION_REVISION", "场景必须引用本项目已确认的环境版本", 422)
    st = r.data
    name = shot.get("location_state", "")
    ref = st.get("states", {}).get(name) if name else st.get("image")
    if name and name not in st["location"].get("states", {}):
        raise AppError("INVALID_LOCATION_STATE", "场景状态不存在", 422)
    if not ref or ref.get("fingerprint") != location_fingerprint(st, p.style, name):
        raise AppError("LOCATION_REFERENCE_REQUIRED", "场景参考缺失或已过期，请选用当前环境素材", 409)
    return {"revision": rid, "location": st["location"], "state": name, "image": ref}


def review_fingerprint(sc):
    st = sc.creative or {}
    return digest(
        {
            "shot": st.get("shot"),
            "image": st.get("image"),
            "audio": st.get("audio"),
            "video": st.get("video"),
            "video_key": sc.video_key,
            "director": sc.director_data,
            "duration": sc.duration_sec,
            "dependency_stamp": st.get("dependency_stamp"),
            "edit": st.get("edit"),
        }
    )


def review_current(sc):
    review = (sc.creative or {}).get("review") or {}
    return bool(review.get("status") == "accepted" and review.get("fingerprint") == review_fingerprint(sc))


def preview_fingerprint(scenes):
    return digest(
        [
            {
                "id": sc.id,
                "order": sc.order_index,
                "shot": {
                    k: v
                    for k, v in ((sc.creative or {}).get("shot") or {}).items()
                    if k not in ("video_input", "first_frame_asset_id", "last_frame_asset_id")
                },
                "image": (sc.creative or {}).get("image"),
                "audio": (sc.creative or {}).get("audio"),
                "director": sc.director_data,
                "duration": sc.duration_sec,
                "dependency_stamp": (sc.creative or {}).get("dependency_stamp"),
            }
            for sc in sorted(scenes, key=lambda x: x.order_index)
        ]
    )


def render_fingerprint(scenes, ratio, style, static=False):
    return digest(
        {
            "preview": preview_fingerprint(scenes),
            "ratio": ratio,
            "style": style,
            "videos": []
            if static
            else [
                {
                    "id": sc.id,
                    "key": sc.video_key,
                    "video": (sc.creative or {}).get("video"),
                    "edit": (sc.creative or {}).get("edit"),
                    "video_input": ((sc.creative or {}).get("shot") or {}).get("video_input"),
                    "first_frame": ((sc.creative or {}).get("shot") or {}).get("first_frame_asset_id"),
                    "last_frame": ((sc.creative or {}).get("shot") or {}).get("last_frame_asset_id"),
                }
                for sc in sorted(scenes, key=lambda x: x.order_index)
            ],
        }
    )


def workflow_stage_confirmations(p, scenes):
    state = p.creative or {}
    locations = (state.get("plan") or {}).get("locations", [])
    confirmation = state.get("export_confirmation") or {}
    return {
        "plan": bool(state.get("plan_confirmed")),
        "cast": bool(state.get("cast_confirmed")),
        "locations": bool(locations) and all(
            (state.get("locations", {}).get(location["id"]) or {}).get("confirmed")
            for location in locations
        ),
        "shots": bool(state.get("shots_confirmed")),
        "export": bool(confirmation) and confirmation.get("status") == "accepted"
        and confirmation.get("fingerprint") == render_fingerprint(scenes, p.ratio, p.style),
    }


def workflow_stage_states(p, scenes, characters, revisions, confirmations):
    state = p.creative or {}
    return {
        key: "已确认" if confirmations[confirmation] else "需更新"
        if any(r.kind == "project" and r.data.get(flag) for r in revisions)
        else "待确认" if present else "未开始"
        for key, confirmation, flag, present in [
            ("plan", "plan", "plan_confirmed", bool(state.get("plan_draft") or state.get("plan"))),
            ("characters", "cast", "cast_confirmed", bool(characters)),
            ("storyboard", "shots", "shots_confirmed", bool(scenes)),
        ]
    }


async def workflow_readiness(db, p):
    scenes = await children(db, Scene, p.id)
    confirmation = (p.creative or {}).get("preview_confirmation") or {}
    issues = await check_project(db, p, media=False)
    pending = [await pending_changes(db, sc) for sc in scenes]
    return {
        **workflow_stage_confirmations(p, scenes),
        "structure_ready": bool(scenes) and not issues,
        "media_complete": bool(scenes) and all(sc.video_key for sc in scenes) and not await check_project(db, p),
        "materials_confirmed": bool((p.creative or {}).get("cast_confirmed"))
        and bool(scenes)
        and all(not image and not voice for image, voice in pending),
        "preview_confirmed": bool(confirmation)
        and confirmation.get("fingerprint") == preview_fingerprint(scenes),
        "video_accepted": bool(scenes) and all(review_current(sc) for sc in scenes),
        "scene_reviews": [
            {
                "id": sc.id,
                "accepted": review_current(sc),
                "status": ((sc.creative or {}).get("review") or {}).get("status", "pending"),
            }
            for sc in scenes
        ],
        "warnings": [
            f"{sc.title}：字幕时间待人工校准"
            for sc in scenes
            if ((sc.creative or {}).get("shot") or {}).get("lines")
            and not ((sc.creative or {}).get("shot") or {}).get("subtitles_calibrated")
        ],
    }


async def invalidate_character_dependents(db, c):
    for sc in await children(db, Scene, c.project_id):
        if c.id in ((sc.creative or {}).get("shot") or {}).get("cast", {}):
            image, voice = await pending_changes(db, sc)
            if image or voice:
                await save_state(
                    db,
                    sc,
                    {
                        **sc.creative,
                        "dependency_stamp": digest({"character": c.id, "revision": c.creative["revision"]}),
                    },
                    "scene",
                )


def voice_spec(persona):
    return {
        k: persona.get(k)
        for k in ("voice_description", "voice_prompt", "base_speed", "base_pitch", "voice_mode")
        if k in persona
    }


async def init_project(db, project):
    if project.creative:
        return
    await save_state(
        db,
        project,
        {
            "plan": None,
            "plan_confirmed": False,
            "cast_confirmed": False,
            "shots_confirmed": False,
            "narrator": {
                "provider": get_settings().tts_provider,
                "voice_id": get_settings().tts_voice_id,
                "speed": 1,
            },
        },
        "project",
    )
    for c in await children(db, Character, project.id):
        persona = Persona(
            name=c.name,
            age=c.age,
            identity=c.description,
            appearance=c.description,
            clothing=c.clothing,
            image_prompt=c.description + " " + c.clothing,
            voice_description=c.voice,
        ).model_dump()
        # Import old assets without making provider calls or inventing speaker mappings.
        await save_state(
            db,
            c,
            {
                "persona": persona,
                "image": {"key": c.image_key, "fingerprint": image_fingerprint(persona, project.style)}
                if c.image_key
                else None,
                "voice": {"voice_id": c.voice_id, "provider": "minimax", "mode": "legacy", "key": None},
                "confirmed": False,
            },
            "character",
        )
    for sc in await children(db, Scene, project.id):
        await save_state(
            db,
            sc,
            {
                "shot": None,
                "legacy_dialogue": sc.dialogue,
                "legacy_narration": sc.narration,
                "image": None,
                "audio": None,
                "needs_binding": True,
            },
            "scene",
        )


async def change_character(db, c, persona):
    state = deepcopy(c.creative or {})
    state.update(persona=Persona.model_validate(persona).model_dump(), confirmed=False)
    await save_state(db, c, state, "character")
    c.name = state["persona"]["name"]
    c.description = state["persona"]["identity"]
    c.clothing = state["persona"]["clothing"]
    await invalidate_character_dependents(db, c)
    await unconfirm(db, c.project_id, "cast")


async def unconfirm(db, project_id, scope):
    p = await require(db, Project, project_id)
    st = deepcopy(p.creative)
    if scope == "cast":
        st["cast_confirmed"] = False
    st["shots_confirmed"] = False
    await save_state(db, p, st, "project")


async def validate_shot(db, project_id, data, edit=None):
    # Subtitle timings describe the adopted clip, which can differ from design time.
    context = {"subtitle_duration": edit["out_sec"] - edit["in_sec"]} if edit else None
    try:
        shot = Shot.model_validate(data, context=context).model_dump()
    except ValidationError as exc:
        reason = (exc.errors()[0].get("ctx") or {}).get("error")
        raise AppError("INVALID_SHOT", str(reason) if reason else "分镜内容不完整，请检查人物、台词和时间设置", 422) from exc
    p = await require(db, Project, project_id)
    locations = (p.creative.get("plan") or {}).get("locations", [])
    if shot["location_id"] not in {x["id"] for x in locations}:
        raise AppError("INVALID_LOCATION", "分镜必须引用已确认方案中的场景", 422)
    if any(i < 0 or i >= len((p.creative.get("plan") or {}).get("beats", [])) for i in shot["beat_indices"]):
        raise AppError("INVALID_BEAT", "请选择当前故事的剧情节点", 422)
    for cid, rid in (shot["cast"] | shot["offscreen_cast"]).items():
        c = await require(db, Character, cid)
        if not rid:
            if c.project_id != project_id:
                raise AppError("INVALID_CAST", "角色必须属于当前项目", 422)
            continue
        r = await require(db, Revision, rid)
        if (
            c.project_id != project_id
            or r.project_id != project_id
            or r.entity_id != cid
            or r.kind != "character"
        ):
            raise AppError("INVALID_CAST", "角色引用必须是本项目已确认版本", 422)
        variant = shot["variants"].get(cid)
        if variant and variant not in r.data["persona"].get("variants", {}):
            raise AppError("INVALID_VARIANT", "造型版本不存在", 422)
        if (
            any(x["speaker_id"] == cid for x in shot["lines"])
            and r.data["persona"].get("role_kind") == "background"
        ):
            raise AppError("BACKGROUND_SPEAKER", "背景群体不能发言，请建立独立发言角色", 422)
    for field in ("first_frame_asset_id", "last_frame_asset_id"):
        if shot.get(field):
            asset = await require(db, Asset, shot[field])
            if asset.project_id != project_id or not asset.content_type.startswith("image/"):
                raise AppError("INVALID_FRAME", "首尾帧必须引用当前项目的图片素材", 422)
    if shot["continuity_from"]:
        previous = await require(db, Scene, shot["continuity_from"])
        if previous.project_id != project_id or previous.order_index < 0:
            raise AppError("INVALID_CONTINUITY", "承接镜头必须引用当前项目的活动镜头", 422)
    for effect in shot["sound_effects"]:
        asset = await db.get(Asset, effect["asset_id"])
        if not asset or asset.project_id != project_id or asset.kind != "sound-effect":
            raise AppError("INVALID_ASSET", "音效必须是本项目已上传的素材，不能引用未生成的音效", 422)
    return shot


async def shot_inputs(db, sc, *, need_image=True, need_audio=True):
    state = sc.creative or {}
    if not state.get("shot"):
        raise AppError("LEGACY_BINDING_REQUIRED", "请先将旧台词明确绑定角色，并保存结构化分镜", 409)
    shot = await validate_shot(db, sc.project_id, state["shot"], state.get("edit"))
    p = await require(db, Project, sc.project_id)
    cast = {}
    for cid, rid in (shot["cast"] | shot.get("offscreen_cast", {})).items():
        if not rid:
            if (need_image and cid in shot["cast"]) or (need_audio and any(x["speaker_id"] == cid for x in shot["lines"])):
                raise AppError("REFERENCE_REQUIRED", "请在制作前绑定所需的角色素材版本", 409)
            continue
        rev = await require(db, Revision, rid)
        cast[cid] = {**rev.data, "revision": rid}
    image = {
        "frame": "first",
        "model": get_settings().image_model,
        "quality": get_settings().image_quality,
        "style": p.style,
        "ratio": p.ratio,
        "shot": {
            k: v
            for k, v in shot.items()
            if k
            not in (
                "beat_indices",
                "offscreen_cast",
                "lines",
                "narration",
                "sound_notes",
                "cast",
                "duration",
                "audio_order",
                "sound_effects",
                "subtitle_cues",
                "subtitles_calibrated",
                "video_input",
                "first_frame_asset_id",
                "last_frame_asset_id",
            )
        },
        "cast": {
            cid: {
                "persona": visual(c["persona"]),
                "image": selected_character_reference(
                    c, shot["variants"].get(cid), shot["character_views"].get(cid), p.style
                ),
                "variant_description": c["persona"].get("variants", {}).get(shot["variants"].get(cid), ""),
            }
            for cid, c in cast.items() if cid in shot["cast"] and need_image
        },
        "director": sc.director_data,
        "location": await selected_location_reference(db, p, shot) if need_image else None,
    }
    lines = []
    by_id = {x["id"]: x for x in shot["lines"] + shot["narration"]}
    for lid in (shot["audio_order"] or list(by_id)) if need_audio else []:
        line = by_id[lid]
        c = cast.get(line["speaker_id"])
        voice = c.get("voice") if c else p.creative.get("narrator")
        if not voice or not voice.get("voice_id"):
            raise AppError("VOICE_REQUIRED", "发言人或旁白缺少独立音色配置", 409)
        persona = c["persona"] if c else {}
        stable = persona.get("voice_mode") == "stable"
        base_speed = persona.get("base_speed", 1) if c else voice.get("speed", 1)
        speed = base_speed if stable else min(2, max(0.5, line["speed"] * base_speed))
        audio_line = {k: v for k, v in line.items() if k not in ("delivery", "continues_from")}
        if line.get("continues_from"):
            continue
        inp = {
            "line": audio_line,
            "voice_id": voice["voice_id"],
            "provider": voice.get("provider", "minimax"),
            "speed": speed,
            "model": voice.get("model") or get_settings().tts_model,
            "audio_pipeline": "loudnorm-v1",
        }
        if inp["provider"] not in ("source-audio", get_settings().tts_provider):
            inp["active_tts_provider"] = get_settings().tts_provider
        if inp["provider"] == "mimo" and voice.get("reference"):
            inp["reference"] = deepcopy(voice["reference"])
        if stable or persona.get("base_pitch", 0):
            inp.update(
                emotion="calm" if stable else line["emotion"],
                pitch=persona.get("base_pitch", 0),
                voice_mode=persona.get("voice_mode", "expressive"),
            )
        lines.append({**inp, "fingerprint": digest(inp)})
    return image, lines


async def current_input(
    db, p, operation, target="", variant="", voice_id="", text="", view="", frame="first", use_reference=False
):
    if get_settings().tts_provider == "mimo" and operation == "role_audio":
        from app.providers.mimo import unsupported

        unsupported(operation)
    if operation == "role_audio":
        from .voice_continuity import role_input

        return await role_input(db, p, target)
    if operation == "plan":
        return {
            "idea": p.description,
            "style": p.style,
            "ratio": p.ratio,
            **p.creative.get("plan_settings", {}),
            "version": p.creative["version"],
        }
    if operation == "storyboard":
        if not p.creative.get("plan") or not await children(db, Character, p.id):
            raise AppError("CONFIRMATION_REQUIRED", "先保存故事和人物设定，即可设计文字分镜", 409)
        value = {
            "plan": p.creative["plan"],
            "cast": {c.id: c.creative for c in await children(db, Character, p.id)},
            "locations": p.creative.get("locations", {}),
            "render_style": p.style,
            "render_ratio": p.ratio,
            "version": p.creative["version"],
        }
        if target and target != p.id:
            candidate = await require(db, Candidate, target)
            if candidate.project_id != p.id or candidate.kind != "storyboard":
                raise AppError("INVALID_CANDIDATE", "只能纠错当前项目的分镜草稿", 422)
            from .storyboard_recovery import archived_text
            value["repair"] = {"candidate_id": candidate.id, "value": candidate.data.get("value"),
                               "raw_text": candidate.data.get("raw_text") or archived_text(candidate),
                               "issues": candidate.data.get("validation_issues", [])}
        return value
    if operation == "location_image":
        st = await location_state(db, p, target)
        if variant and variant not in st["location"].get("states", {}):
            raise AppError("INVALID_LOCATION_STATE", "请先定义环境状态", 422)
        if use_reference and not (st.get("image") or {}).get("key"):
            raise AppError("LOCATION_REFERENCE_REQUIRED", "请先选用当前场景参考图", 409)
        if variant and (not st.get("confirmed") or not st.get("image")):
            raise AppError("LOCATION_REFERENCE_REQUIRED", "请先选择并确认主环境图，再派生状态", 409)
        return {
            "location": st["location"],
            "style": p.style,
            "ratio": p.ratio,
            "state": variant,
            "reference": st.get("image") if variant or use_reference else None,
        }
    if operation.startswith("shot_"):
        sc = await require(db, Scene, target)
        if sc.project_id != p.id:
            raise AppError("INVALID_TARGET", "分镜不属于本项目", 422)
        image, lines = await shot_inputs(db, sc, need_image=operation == "shot_image", need_audio=operation == "shot_audio")
        if operation == "shot_image" and frame == "last":
            first = (sc.creative or {}).get("image") or {}
            pending_image, _ = await pending_changes(db, sc)
            if (
                not first.get("key")
                or pending_image
                or not image_fingerprint_matches(first.get("fingerprint"), image)
            ):
                raise AppError(
                    "FIRST_FRAME_REQUIRED",
                    "请先选用当前有效的本镜首帧，再基于同机位、景别和构图派生尾帧",
                    409,
                )
            reference = {key: first.get(key) for key in ("key", "asset_id", "candidate_id", "fingerprint")}
            return {
                **image,
                "frame": "last",
                "first_frame_reference": reference,
                "reference_policy": "shot-first-frame-only",
            }
        if operation == "shot_image":
            needed = len(image["cast"]) + bool(image.get("location"))
            limit = get_settings().image_max_references
            if needed > limit:
                raise AppError("REFERENCE_LIMIT", f"本镜需要 {needed} 张角色与环境参考图，当前上限为 {limit}。请减少同框角色、拆分镜头，或提高 IMAGE_MAX_REFERENCES。", 409)
        return {**image, "frame": frame} if operation == "shot_image" else {"lines": lines}
    c = await require(db, Character, target)
    if c.project_id != p.id or not c.creative:
        raise AppError("INVALID_TARGET", "角色不属于本项目或尚未升级", 422)
    persona = c.creative["persona"]
    if operation == "character":
        return {"persona": persona, "version": c.creative["version"]}
    if operation == "character_image":
        if (variant or view or use_reference) and not c.creative.get("image"):
            raise AppError("REFERENCE_REQUIRED", "先选定主参考图，再生成补充参考", 409)
        if variant or view:
            character_reference(c.creative, None, p.style)
        if variant:
            if variant not in persona.get("variants", {}):
                raise AppError("INVALID_VARIANT", "请先在造型设定中添加此造型或视角", 422)
        return {
            "persona": visual(persona),
            "style": p.style,
            "variant": variant,
            "view": view,
            "variant_description": persona.get("variants", {}).get(variant, ""),
            "reference": c.creative.get("image") if variant or view or use_reference else None,
        }
    reference = c.creative.get("voice_reference") if operation == "voice_clone" else None
    if operation == "voice_clone" and not reference:
        raise AppError("VOICE_REFERENCE_REQUIRED", "请先上传同一人的声音参考", 409)
    result = {
        **({"reference": {k: reference[k] for k in ("key", "asset_id", "duration_ms")}} if reference else {}),
        "voice": voice_spec(persona),
        "voice_id": voice_id,
        "text": text,
        "model": "original-audio" if operation == "voice_source" else get_settings().tts_model,
        "provider": get_settings().tts_provider,
    }
    if get_settings().tts_provider == "mimo":
        if operation == "voice_design":
            if not (persona.get("voice_prompt") or persona.get("voice_description") or "").strip():
                raise AppError("VOICE_DESCRIPTION_REQUIRED", "请先填写声音描述或音色设计提示词", 422)
            result["model"] = get_settings().mimo_tts_design_model
        elif operation == "voice_clone":
            result["model"] = get_settings().mimo_tts_clone_model
        elif operation == "voice_preview":
            selected = c.creative.get("voice") or {}
            if (
                selected.get("provider") == "mimo"
                and selected.get("reference")
                and voice_id == selected.get("voice_id")
            ):
                result.update(
                    model=get_settings().mimo_tts_clone_model,
                    reference=deepcopy(selected["reference"]),
                    voice_mode=selected["mode"],
                )
        if operation in ("voice_design", "voice_clone", "voice_preview") and not text.strip():
            raise AppError("VOICE_TEXT_REQUIRED", "请填写试听台词", 422)
    return result


async def stale(db, p, c):
    if c.kind == "video_correction":
        from .video_correction import is_stale

        return await is_stale(db, p, c)
    meta = c.data.get("request", {})
    try:
        value = await current_input(
            db,
            p,
            c.kind,
            c.entity_id,
            meta.get("variant", ""),
            meta.get("voice_id", ""),
            meta.get("text", ""),
            meta.get("view", ""),
            meta.get("frame", "first"),
            meta.get("use_reference", False),
        )
        if c.kind == "storyboard":
            from .storyboard_recovery import dependencies
            expected = digest(dependencies(value))
            if expected == c.fingerprint:
                return False
            # Older billed candidates used a project-wide version counter. Compare their
            # actual pinned inputs so unrelated saves do not make drafts unusable.
            from app.models import Task
            task = await db.get(Task, c.task_id) if c.task_id else None
            original = ((task.payload or {}).get("creative") or {}).get("input") if task and task.project_id == p.id else None
            return not original or c.fingerprint != digest(original) or digest(dependencies(original)) != expected
        return (
            not image_fingerprint_matches(c.fingerprint, value)
            if c.kind == "shot_image"
            else digest(value) != c.fingerprint
        )
    except AppError:
        return True


async def confirm_character(db, c, checks=None, notes=""):
    st = deepcopy(c.creative)
    p = await require(db, Project, c.project_id)
    character_reference(st, None, p.style)
    if st["persona"].get("role_kind") != "background" and (
        not st.get("voice")
        or not st["voice"].get("key")
        or st["voice"].get("fingerprint") != digest(voice_spec(st["persona"]))
    ):
        raise AppError("VOICE_REQUIRED", "请试听并选定当前音色候选", 409)
    st["confirmed"] = True
    if checks is not None:
        if (
            not isinstance(checks, dict)
            or set(checks) - {"clear_silhouette", "no_subtitles", "low_occlusion", "identity_consistent"}
            or any(not isinstance(v, bool) for v in checks.values())
        ):
            raise AppError(
                "INVALID_VISUAL_CHECKS", "角色人工检查项必须为轮廓、无字幕、少遮挡和身份一致的确认值", 422
            )
        st["visual_checks"] = {
            "checks": checks,
            "notes": notes,
            "image_fingerprint": (st.get("image") or {}).get("fingerprint"),
            "candidate_id": (st.get("image") or {}).get("candidate_id"),
            "source": "human",
        }
    await save_state(db, c, st, "character")
    # Project-local updates deliberately repin affected shots; global library never does this.
    for sc in await children(db, Scene, c.project_id):
        if sc.creative and sc.creative.get("shot") and c.id in sc.creative["shot"]["cast"]:
            ss = deepcopy(sc.creative)
            ss["shot"]["cast"][c.id] = c.creative["revision"]
            await save_state(db, sc, ss, "scene")
    await unconfirm(db, c.project_id, "cast")


async def scene_media_issues(db, p, sc, video=True):
    from app.services.video import is_stale, dependency_is_stale
    state = sc.creative or {}
    shot = await validate_shot(db, p.id, state.get("shot") or {}, state.get("edit"))
    issues = []
    if video and sc.video_key:
        if is_stale(sc, p.ratio) or await dependency_is_stale(db, sc):
            issues.append("视频与当前设计不一致，请重新选用或生成")
        native = (state.get("video") or {}).get("sound_strategy", (shot.get("video_input") or {}).get("sound_strategy")) == "model_audio"
        if not native:
            _, lines = await shot_inputs(db, sc, need_image=False)
            if lines and (state.get("audio") or {}).get("fingerprint") != digest({"lines": lines}):
                issues.append("配音缺失或过期")
        return issues
    image, lines = await shot_inputs(db, sc)
    if not state.get("image") or not image_fingerprint_matches(state["image"].get("fingerprint"), image):
        issues.append("画面缺失或过期")
    if lines and (state.get("audio") or {}).get("fingerprint") != digest({"lines": lines}):
        issues.append("配音缺失或过期")
    pending_image, pending_voice = await pending_changes(db, sc)
    if pending_image or pending_voice:
        issues.append("角色或场景素材有更新，请重新选择确认版本")
    return issues


async def check_project(db, p, media=True, video=True):
    issues = []
    if not p.creative:
        return ["旧项目：请进入创作流程补全角色与发言人绑定"]
    if not p.creative.get("plan_confirmed"):
        issues.append("故事方案尚未确认")
    scenes = await children(db, Scene, p.id)
    if not scenes:
        issues.append("尚无分镜")
    for sc in scenes:
        try:
            shot = await validate_shot(db, p.id, (sc.creative or {}).get("shot") or {}, (sc.creative or {}).get("edit"))
            if media:
                issues.extend(f"{sc.title}：{message}" for message in await scene_media_issues(db, p, sc, video))
            if shot.get("continuity_from"):
                previous = await require(db, Scene, shot["continuity_from"])
                if previous.order_index >= sc.order_index:
                    issues.append(f"{sc.title}：承接镜头顺序非法")
        except (AppError, ValueError) as exc:
            issues.append(f"{sc.title}：{getattr(exc, 'message', str(exc))}")
    return issues


async def execute_candidate(db, task, checkpoint, report):
    req = task.payload["creative"]
    op, inp = req["operation"], req["input"]
    result = {"request": req["request"]}
    package = op == "character_image" and not inp.get("view") and not inp.get("variant") and task.payload.get("billable_calls", 1) == 2
    saved_image_candidate = None
    if package:
        saved_image_candidate = await db.scalar(select(Candidate).where(
            Candidate.task_id == task.id, Candidate.kind == op, Candidate.fingerprint == digest(inp)
        ))
    await checkpoint()
    if op in ("plan", "character", "storyboard", "voice_match"):
        schemas = {"plan": Plan, "character": Persona, "storyboard": Storyboard, "voice_match": VoiceMatches}
        prompts = {
            "plan": "你是短剧编剧。从一句创意给出完整可编辑创作方案，四段起承转合、结局、人物关系动机变化、详细视觉与声音设定和地点。variants只记录服装或剧情阶段等视觉造型变体，不填声音表演要求。合理默认30秒、16:9。不要生成分镜。返回符合schema的JSON。",
            "character": "补全角色人物设定、外貌细节、形象提示词和音色描述，保留已有明确身份。返回JSON。",
            "storyboard": "根据已确认方案和cast生成分镜。不得改变角色身份外貌。cast键是角色ID，值必须逐字使用输入该角色的revision。地点ID引用plan.locations，locations里有已确认版本时必须填写其location_revision，并选择需要的location_state。角色对白仅放入lines，每句绑定有效speaker_id；旁白仅放入narration且speaker_id为null，不能放入lines；不在文本加发言人前缀。scene_count是建议数量，只有fixed_scene_count=true时严格遵守。完整覆盖plan.beats的开端发展转折结局，beat_indices填写实际覆盖节点的从0开始的序号。满足plan.duration时长目标，按每秒约3.5个中文字为台词留出动作停顿，必要时拆镜。角色尚无确认素材时cast值留空，不编造版本。画外发言放入offscreen_cast并设置delivery=off_screen，不强迫该角色入画。purpose写本镜目的；start_state描述动作发生前首帧状态，end_state给出可观察结果；action_steps为有稳定ID的可见动作、start_sec/end_sec和trigger_line_id，时间必须在duration内；spatial_relations的键只能是本镜cast中的角色ID，用来写左右位置、视线、朝向与装备；环境布局写入composition，不得把地点ID放入spatial_relations。动作要有原因和结果；起始画面不能已经完成本镜动作。相邻镜保持人物身份、位置、装备、环境事件状态；continuity_requirements写承接条件。无真实前镜尾帧依赖时不要填写continuity_from。sound_effects必须为空数组，声音创作描述写入sound_notes，不得编造音效资产ID。variants只允许选择角色references中已有且匹配的造型；character_views只用已有已确认views。audio_order包含本镜全部台词和旁白ID以安排穿插顺序。没有人工校准字幕时subtitle_cues为空且subtitles_calibrated=false，不编造自动对齐。first_frame_asset_id,last_frame_asset_id,video_input不编造。返回JSON。",
            "voice_match": "根据声音描述从catalog匹配最多3个预设音色。voice_ids必须完全来自catalog，说明匹配理由；这是预设匹配不是设计新音色。返回JSON。",
        }
        brief = deepcopy(inp)
        if op == "storyboard":
            prompts["storyboard"] += f" 每镜参考图预算为 {get_settings().image_max_references} 张，角色与环境参考图合计不得超过该值。预算不足以覆盖同框角色与环境时，减少同框角色数或拆分为单人镜头。"
            prompts["storyboard"] += (
                " location_state是已生成并确认的环境状态素材名称，不是自然语言描述。只允许从输入locations[地点ID].states中选取有图片key且confirmed=true的状态；没有这种状态素材时必须为空字符串。灯未亮、灯已亮等剧情描述请写start_state/end_state，不得猜测或编造location_state名称。"
            )
            prompts["storyboard"] += " 如果服装变体描述已经包含在角色基础clothing里，使用已确认主造型，不再填写同名variants；其他变体只选references中已有实际图片的条目。"
            if inp.get("repair"):
                prompts["storyboard"] += " 本次只纠错 repair 中已付费草稿：保留故事、镜头顺序、台词和动作，只按具体错误修正结构及当前角色/环境绑定；无法确定发言人时不要编造。返回完整可校验 JSON。本任务只调用一次，不自动循环付费重试。"
        if op == "voice_match":
            catalog = await providers().tts.voices()
            brief["catalog"] = catalog.get("system_voice", [])
        try:
            output = await providers().llm.structured(schemas[op], prompts[op], brief)
        except AppError as exc:
            if op != "storyboard" or exc.code != "PROVIDER_OUTPUT_INVALID" or "rawValue" not in exc.details:
                raise
            raw_issues = exc.details.get("validationIssues") or exc.details.get("errors") or []
            issues = [
                {
                    "code": issue.get("code") or issue.get("type") or "STRUCTURE_INVALID",
                    "message": issue.get("message") or issue.get("msg") or "模型输出未通过分镜结构校验",
                    "path": issue.get("path") or issue.get("loc") or [],
                }
                if isinstance(issue, dict)
                else {"code": "STRUCTURE_INVALID", "message": str(issue)}
                for issue in raw_issues
            ]
            result.update(
                value=deepcopy(exc.details["rawValue"]),
                validation_issues=issues or [{"code": "STRUCTURE_INVALID", "message": exc.message}],
                draft=True,
                validation_stage="schema",
                raw_text=exc.details.get("rawText", ""),
            )
            if exc.details.get("archivePath"):
                result["provider_archive"] = exc.details["archivePath"]
        else:
            result["value"] = output.model_dump()
        if op == "voice_match":
            legal = {v["voice_id"] for v in brief["catalog"]}
            if not set(result["value"]["voice_ids"]) <= legal:
                raise AppError("PROVIDER_OUTPUT_INVALID", "匹配结果包含不可用音色", 422)
        if op == "storyboard":
            from .storyboard_recovery import parse_text, validate
            original = deepcopy(result.get("value"))
            value = original
            formatting = []
            if value is None:
                value, formatting = parse_text(result.get("raw_text", ""))
            project = await require(db, Project, task.project_id)
            board, corrections, issues = await validate(db, project, value, inp)
            result.update(value=board, original_value=original, corrections=formatting + corrections,
                          validation_issues=issues, draft=bool(issues),
                          validation_stage="schema" if any(x.get("path") for x in issues) else "semantic" if issues else None)
            if inp.get("repair"):
                result["parent_candidate_id"] = inp["repair"]["candidate_id"]
                result["source"] = "ai-repair"
    elif op in ("character_image", "location_image", "shot_image"):
        refs, logs = [], []
        if op == "character_image":
            prompt = inp["style"] + "。角色设定：" + json.dumps(inp["persona"], ensure_ascii=False)
            if inp["reference"]:
                refs = [await providers().storage.get(inp["reference"]["key"])]
                prompt += (
                    "。严格保持参考图角色身份，补充视角/造型："
                    + inp["variant"]
                    + "，"
                    + inp.get("variant_description", "")
                )
                views = {
                    "full_body": "完整全身",
                    "front": "正面",
                    "side": "侧面",
                    "back": "背面",
                    "half_body": "半身",
                    "face": "面部特写",
                    "state": "状态变体",
                    "turnaround": "正面、侧面、背面并排的全身三视图，统一纯色背景与人物比例",
                }
                if inp.get("view"):
                    prompt += "。本次参考用途：" + views[inp["view"]] + "，沿用已确认主造型，不重新设计人物"
                elif not inp.get("variant"):
                    prompt += "。参考图用于固定人物身份与面部特征；服装、配饰和形象细节以本次角色设定为准，按新的描述调整。"
            prompt += "。固定身份特征与服装按设定保持；轮廓清楚，少遮挡，无文字、字幕、水印；姿势和情绪只是可变状态。"
            ratio = "16:9" if inp.get("view") == "turnaround" else "9:16"
        elif op == "location_image":
            prompt = (
                inp["style"]
                + "。无人环境参考图，不包含人物身份图，无字幕、水印。地点与地标、光照、色调、空间关系："
                + json.dumps(inp["location"], ensure_ascii=False)
            )
            if inp.get("reference"):
                refs = [await providers().storage.get(inp["reference"]["key"])]
                prompt += (
                    "。参考图1是已确认主环境，保持地标和空间结构，只改变状态："
                    + (inp["state"] or "基础环境，依据当前场景描述优化细节")
                    + "。"
                    + inp["location"].get("states", {}).get(inp["state"], "")
                )
            ratio = inp["ratio"]
        else:
            shot = inp["shot"]
            prompt = (
                inp["style"]
                + "。用途：分镜首帧，动作发生前的起始状态；不是高潮海报。"
                + "本镜目的："
                + shot.get("purpose", "")
                + "。起始状态："
                + shot.get("start_state", "")
                + "。构图："
                + shot.get("composition", "")
                + "。景别/机位："
                + shot.get("shot_type", "")
                + "、"
                + shot.get("camera_angle", "")
                + "。画面要求："
                + shot.get("image_prompt", "")
                + "。左右/视线："
                + json.dumps(shot.get("spatial_relations", {}), ensure_ascii=False)
            )
            if inp.get("frame") == "last":
                first = inp.get("first_frame_reference")
                if not first or not first.get("key"):
                    raise AppError(
                        "FIRST_FRAME_REQUIRED",
                        "尾帧任务缺少已选本镜首帧；旧尾帧请求请重新检查输入后提交",
                        409,
                    )
                refs = [await providers().storage.get(first["key"])]
                prompt = (
                    inp["style"]
                    + "。参考图1是本镜已选首帧，也是唯一画面派生参考。用途：从本镜首帧派生连续尾帧，不重新设计人物、环境或机位。必须保持首帧同一机位、相同景别、镜头视角、取景裁切、构图和道具；首帧只露出手部与按钮时尾帧也保持手部与按钮特写，不扩大成全身、远景或新场景。只改变本镜动作导致的可见结束状态："
                    + shot.get("end_state", "")
                    + "。相对于首帧允许的动作过程："
                    + shot.get("action", "")
                    + "。本镜景别/机位："
                    + shot.get("shot_type", "")
                    + "、"
                    + shot.get("camera_angle", "")
                    + "。必须呈现动作结果；保持原取景构图："
                    + shot.get("composition", "")
                    + "。禁止加入文字、字幕、水印或参考图未出现的新人物。"
                )
                logs.append("尾帧仅使用本镜已选首帧作为派生参考，人物/环境主素材不作为重新构图输入")
            limit = get_settings().image_max_references
            for i, (cid, c) in enumerate(inp["cast"].items() if inp.get("frame") != "last" else []):
                prompt += f"。角色 {cid} {c['persona']['name']}：" + json.dumps(
                    c["persona"], ensure_ascii=False
                )
                prompt += "。本镜造型：" + c.get("variant_description", "基础造型")
                if c.get("image") and len(refs) < limit:
                    refs.append(await providers().storage.get(c["image"]["key"]))
                    prompt += f"，对应参考图{len(refs)}"
                else:
                    raise AppError(
                        "REFERENCE_REQUIRED", f"{c['persona']['name']} 缺少参考图或超过上限，已停止生成", 409
                    )
            if inp.get("location") and inp.get("frame") != "last":
                environment = inp["location"]
                if len(refs) >= limit:
                    raise AppError(
                        "REFERENCE_LIMIT", f"本镜人物与环境参考超过当前上限 {limit} 张，请减少同框角色或拆分镜头。", 409
                    )
                refs.append(await providers().storage.get(environment["image"]["key"]))
                prompt += (
                    f"。参考图{len(refs)}用途是无人环境，保持地标、光照和空间关系："
                    + json.dumps(environment["location"], ensure_ascii=False)
                    + "；环境状态："
                    + environment["state"]
                )
            elif inp.get("frame") != "last":
                prompt += "。环境：" + shot.get("location_description", "")
            if inp.get("frame") != "last":
                prompt += (
                    "。导演台仅用于位置、走位、视线与机位轨迹，禁止根据对象名称改变人物身份。characterId绑定以上角色ID。导演台数据："
                    + json.dumps(inp["director"], ensure_ascii=False)
                )
            ratio = inp["ratio"]
        if saved_image_candidate:
            result = deepcopy(saved_image_candidate.data)
            raw = await providers().storage.get(result["key"])
        else:
            await report(20, "正在生成形象" if op == "character_image" else "正在生成画面")
            raw, provider_logs = await providers().image.generate(
                prompt, ratio, get_settings().image_quality, refs
            )
            await checkpoint()
            asset = await save_asset(db, task.project_id, "creative-image", raw, "image/png", "png")
            result.update(
                key=asset.object_key,
                asset_id=asset.id,
                logs=logs + provider_logs,
                reference_count=len(refs),
                reference_mode="shot-first-frame"
                if inp.get("frame") == "last"
                else "reference"
                if refs
                else "character-design",
                source="provider",
                parent_revision=(inp.get("first_frame_reference") or inp.get("reference") or {}).get(
                    "candidate_id"
                ),
                input=inp,
                prompt=prompt,
                parameters={
                    "model": get_settings().image_model,
                    "quality": get_settings().image_quality,
                    "ratio": ratio,
                },
            )
        if package:
            if not saved_image_candidate:
                result["package_pending"] = True
                saved_image_candidate = Candidate(project_id=task.project_id, entity_id=req["target"],
                    kind=op, fingerprint=digest(inp), task_id=task.id, data=deepcopy(result))
                db.add(saved_image_candidate)
                # Preserve paid portrait output even if the second image fails or is cancelled.
                await db.commit()
            await report(55, "正在生成正面、侧面、背面三视图")
            # A package contains a portrait and a matching turnaround, quoted as two calls.
            sheet_prompt = (
                inp["style"] + "。参考图为刚生成的主形象，严格保持同一人物的脸部、发型、服装、配饰与颜色。"
                "生成角色全身三视图设定图：从左到右依次为正面、侧面、背面，同一人物同一身高比例，"
                "站立中性姿势，头顶和鞋子完整入画，三个视角彼此分开，统一白色或浅灰背景，均匀柔光。"
                "不加文字、标签、字幕、水印、边框或其他人物。角色设定："
                + json.dumps(inp["persona"], ensure_ascii=False)
            )
            sheet, sheet_logs = await providers().image.generate(
                sheet_prompt, "16:9", get_settings().image_quality, [raw]
            )
            await checkpoint()
            sheet_asset = await save_asset(db, task.project_id, "character-turnaround", sheet, "image/png", "png")
            result["turnaround"] = {"key": sheet_asset.object_key, "asset_id": sheet_asset.id}
            result["logs"] += sheet_logs
            result.pop("package_pending", None)
    elif op in ("voice_preview", "voice_design", "voice_clone") and get_settings().tts_provider == "mimo":
        from .mimo_voice import generate

        result.update(await generate(db, task, inp, op, checkpoint))
    elif op in ("voice_preview", "voice_design", "voice_clone"):
        if op == "voice_design":
            voice, raw = await providers().tts.design(
                inp["voice"]["voice_prompt"] or inp["voice"]["voice_description"],
                inp["text"],
                "cineai" + task.id,
            )
            import tempfile
            from pathlib import Path

            from .media import probe

            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "voice.mp3"
                path.write_bytes(raw)
                duration = round(await probe(path) * 1000)
        else:
            if op == "voice_clone":
                voice = (
                    "cineai"
                    + digest({"target": task.payload["creative"]["target"], "reference": inp["reference"]})[
                        :32
                    ]
                )
                await report(20, "正在根据参考录音复刻角色音色")
                voice = await providers().tts.clone(
                    await providers().storage.get(inp["reference"]["key"]), voice
                )
            else:
                voice = inp["voice_id"]
            if not voice:
                raise AppError("VOICE_REQUIRED", "请选择预设音色", 422)
            if get_settings().tts_provider == "mimo":
                from app.providers.mimo import resolve_voice

                voice = resolve_voice(voice)
            raw, duration = await tts.synthesize(
                inp["text"],
                voice,
                checkpoint,
                {
                    "speed": inp["voice"].get("base_speed", 1),
                    "pitch": inp["voice"].get("base_pitch", 0),
                    "emotion": "calm" if inp["voice"].get("voice_mode") == "stable" else "neutral",
                    "model": inp["model"],
                },
            )
        await checkpoint()
        asset = await save_asset(
            db, task.project_id, "voice-preview", raw, "audio/mpeg", "mp3", duration_ms=duration
        )
        result.update(
            key=asset.object_key,
            asset_id=asset.id,
            voice_id=voice,
            model=inp["model"],
            provider=get_settings().tts_provider,
            mode="clone" if op == "voice_clone" else "design" if op == "voice_design" else "preset",
            duration_ms=duration,
        )
        if op == "voice_clone":
            result["reference"] = inp["reference"]
    elif op == "role_audio":
        from .voice_continuity import generate_role

        result.update(await generate_role(db, task, inp, checkpoint, report))
    elif op == "shot_audio":
        # Reuse exactly matching individual lines, including previously generated candidates.
        old = list(
            await db.scalars(
                select(Candidate)
                .where(
                    Candidate.project_id == task.project_id,
                    Candidate.entity_id == req["target"],
                    Candidate.kind.in_(["shot_audio", "line_audio"]),
                )
                .order_by(Candidate.created_at)
            )
        )
        cache = {x["fingerprint"]: x for c in old for x in c.data.get("segments", [])}
        scene = await require(db, Scene, req["target"])
        cache.update({x["fingerprint"]: x for x in (scene.creative.get("audio") or {}).get("segments", [])})
        forced = set(req["request"].get("regenerate_line_ids", []))
        take_id = req["request"].get("nonce", "")
        takes = {(x["fingerprint"], x.get("take_id")): x for c in old for x in c.data.get("segments", [])}
        segments = []
        offset = 0
        for i, line in enumerate(inp["lines"]):
            await report(
                10 + int(75 * i / max(1, len(inp["lines"]))), f"逐句配音 {i + 1}/{len(inp['lines'])}"
            )
            retake = line["line"]["id"] in forced
            seg = deepcopy(
                takes.get((line["fingerprint"], take_id)) if retake else cache.get(line["fingerprint"])
            )
            if not seg:
                if line["provider"] == "source-audio":
                    raise AppError(
                        "SOURCE_AUDIO_REQUIRED",
                        "该角色使用原声录音，请上传对应台词录音，或先选定可合成的音色",
                        409,
                    )
                raw, duration = await tts.synthesize(
                    line["line"]["text"],
                    line["voice_id"],
                    checkpoint,
                    {
                        "speed": line["speed"],
                        "emotion": line.get("emotion", line["line"]["emotion"]),
                        "pitch": line.get("pitch", 0),
                        "model": line["model"],
                        **({"reference": line["reference"]} if line.get("reference") else {}),
                    },
                )
                await checkpoint()
                asset = await save_asset(
                    db, task.project_id, "line-audio", raw, "audio/mpeg", "mp3", duration_ms=duration
                )
                seg = {
                    **line,
                    "key": asset.object_key,
                    "duration_ms": duration,
                    "take_id": take_id if retake else "",
                }
                # Persist each completed paid utterance so an explicit retry reuses it.
                partial = Candidate(
                    project_id=task.project_id,
                    entity_id=req["target"],
                    kind="line_audio",
                    fingerprint=line["fingerprint"],
                    task_id=task.id,
                    data={"segments": [seg]},
                )
                db.add(partial)
                await db.commit()
            seg["start_ms"] = offset
            offset += seg["duration_ms"] + round(seg["line"]["pause_after"] * 1000)
            segments.append(seg)
        result.update(segments=segments, duration_ms=offset)
    await checkpoint()
    if result.get("logs"):
        task.logs = [*task.logs, *[{"message": str(x)} for x in result["logs"]]]
    if saved_image_candidate:
        candidate = saved_image_candidate
        candidate.data = result
    else:
        candidate = Candidate(
            project_id=task.project_id,
            entity_id=req["target"] or task.project_id,
            kind=op,
            fingerprint=digest(dependencies(inp)) if op == "storyboard" else digest(inp),
            task_id=task.id,
            data=result,
        )
        db.add(candidate)
    await db.flush()
    applied = False
    if op == "storyboard" and req["request"].get("auto_apply") and not result.get("draft") and not result.get("validation_issues"):
        # Serialize with edits/selections and refresh the worker's cached project.
        p = (await db.execute(select(Project).where(Project.id == task.project_id)
                              .with_for_update().execution_options(populate_existing=True))).scalar_one()
        if p.creative.get("version", 0) == inp.get("version", 0) and not await stale(db, p, candidate):
            await apply_storyboard_candidate(db, p, candidate)
            applied = True
    return {
        "candidateId": candidate.id,
        "operation": op,
        "applied": applied,
        "message": "分镜已自动应用，可直接编辑镜头。" if applied else "分镜未完整生成，请重新生成。" if op == "storyboard" and result.get("draft") else "已保留为历史方案，可预览后使用。" if op == "storyboard" else "草稿已保存；还有需要确认的问题，可本地修复或选择 AI 纠错并先估算费用"
        if result.get("draft")
        else "候选已保存，请预览确认；不会覆盖当前版本",
        "validationIssues": result.get("validation_issues", []),
        "draft": result.get("draft", False),
    }


async def apply_shot(db, sc, shot):
    if shot.get("continuity_from"):
        previous = await require(db, Scene, shot["continuity_from"])
        if previous.id == sc.id or previous.order_index >= sc.order_index:
            raise AppError(
                "INVALID_CONTINUITY", "镜头只能承接时间线中较早的镜头，不能引用自身或形成循环", 422
            )
    st = {**(sc.creative or {}), "shot": shot, "needs_binding": False}
    if not shot["lines"] and not shot["narration"]:
        st["audio"] = {"segments": [], "duration_ms": 0, "fingerprint": digest({"lines": []})}
        sc.audio_duration_ms = 0
    await save_state(db, sc, st, "scene")
    sc.title, sc.shot_type, sc.camera_move = shot["title"], shot["shot_type"], shot["camera_move"]
    sc.image_prompt = shot["image_prompt"]
    audio = st.get("audio") or {}
    sc.duration_sec = max(
        shot["duration"], audio.get("duration_ms", 0) / 1000 + 0.3 if audio.get("segments") else 0
    )
    sc.dialogue = "\n".join(x["text"] for x in shot["lines"])
    sc.narration = "\n".join(x["text"] for x in shot["narration"])


async def validated_storyboard(db, p, value):
    board = Storyboard.model_validate(value).model_dump()
    count = (p.creative.get("plan") or {}).get("scene_count")
    if (p.creative.get("plan") or {}).get("fixed_scene_count") and count is not None and len(board["scenes"]) != count:
        raise AppError(
            "PROVIDER_OUTPUT_INVALID", "分镜数量必须与已确认方案一致，请先修改故事方案或修正草稿", 422
        )
    board["scenes"] = [await validate_shot(db, p.id, shot) for shot in board["scenes"]]
    return board


async def apply_storyboard_candidate(db, p, candidate):
    board = await validated_storyboard(db, p, candidate.data["value"])
    existing = await children(db, Scene, p.id)
    # Preserve previous scenes and media as history when switching storyboards.
    oldest_index = await db.scalar(select(func.min(Scene.order_index)).where(Scene.project_id == p.id))
    archive_start = min(oldest_index or 0, 0) - 1
    for i, sc in enumerate(existing):
        sc.order_index = archive_start - i
    await db.flush()
    for i, shot in enumerate(board["scenes"]):
        sc = Scene(project_id=p.id, order_index=i)
        db.add(sc)
        await db.flush()
        await apply_shot(db, sc, shot)
    await save_state(db, p, {**p.creative, "selected_storyboard": candidate.id, "shots_confirmed": False}, "project")


async def pending_changes(db, sc):
    """Show draft dependency changes immediately, while generation still uses confirmed pins."""
    visual_changed = voice_changed = False
    shot = (sc.creative or {}).get("shot") or {}
    speaking = {x["speaker_id"] for x in shot.get("lines", [])}
    p = await require(db, Project, sc.project_id)
    current_location = (p.creative or {}).get("locations", {}).get(shot.get("location_id"), {})
    if shot.get("location_revision") and current_location.get("revision") != shot["location_revision"]:
        pinned_location = await require(db, Revision, shot["location_revision"])
        visual_changed = location_visual_inputs(current_location) != location_visual_inputs(pinned_location.data) or not current_location.get("confirmed")
    for cid, rid in (shot.get("cast", {}) | shot.get("offscreen_cast", {})).items():
        if not rid:
            visual_changed = voice_changed = True
            continue
        c = await require(db, Character, cid)
        r = await require(db, Revision, rid)
        current = c.creative or {}
        if visual(current.get("persona", {})) != visual(r.data["persona"]) or current.get(
            "image"
        ) != r.data.get("image"):
            visual_changed = True
        variant = shot.get("variants", {}).get(cid)
        view = shot.get("character_views", {}).get(cid)
        if view and current.get("views", {}).get(view) != r.data.get("views", {}).get(view):
            visual_changed = True
        if variant and (
            current.get("references", {}).get(variant) != r.data.get("references", {}).get(variant)
            or current.get("persona", {}).get("variants", {}).get(variant)
            != r.data["persona"].get("variants", {}).get(variant)
        ):
            visual_changed = True
        if cid in speaking and (
            voice_spec(current.get("persona", {})) != voice_spec(r.data["persona"])
            or current.get("voice") != r.data.get("voice")
        ):
            voice_changed = True
    return visual_changed, voice_changed

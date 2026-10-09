from copy import deepcopy

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from sqlalchemy import select

from app.api.routers.jobs import finish_submit
from app.api.routers.resources import DB
from app.core.config import ROOT, get_settings
from app.core.errors import AppError
from app.models import (
    Asset,
    Candidate,
    Character,
    ExportJob,
    LibraryCharacter,
    Project,
    Revision,
    Scene,
    Task,
    now,
    uid,
)
from app.providers import providers
from app.schemas.creative import Edit, Generate, Location, Persona, Plan, Selection, Storyboard
from app.services import creative as flow
from app.services import workbench
from app.services.jobs import create_job, estimate_cost
from app.services.resources import bind_image, children, columns, media_urls, project_out, require, save_asset

router = APIRouter(prefix="/api/creative")


async def project(db, id):
    p = await require(db, Project, id, True)
    await flow.init_project(db, p)
    return p


@router.post("/projects/{id}/start")
async def start(id: str, db: DB):
    p = await project(db, id)
    await db.commit()
    return await project_out(db, p)


@router.get("/projects/{id}")
async def state(id: str, db: DB):
    p = await require(db, Project, id)
    candidates = []
    rows = await db.scalars(
        select(Candidate).where(Candidate.project_id == id).order_by(Candidate.created_at.desc())
    )
    for row in rows:
        data = media_urls(deepcopy(columns(row)))
        if row.data.get("segments"):
            data["data"]["segments"] = [
                {**x, "url": providers().storage.url(x["key"])} for x in row.data["segments"]
            ]
        data["stale"] = await flow.stale(db, p, row) if p.creative else True
        data["url"] = providers().storage.url(row.data.get("key"))
        data["selected"] = await selected(db, p, row)
        candidates.append(data)
    scenes = []
    for sc in await children(db, Scene, id):
        from app.services.video import is_stale, dependency_is_stale
        out = {
            "id": sc.id,
            "video_stale": bool(sc.video_key) and (is_stale(sc, p.ratio) or await dependency_is_stale(db, sc)),
            "image_stale": True,
            "audio_stale": True,
            "review_current": flow.review_current(sc),
            "review_stale": bool((sc.creative or {}).get("review")) and not flow.review_current(sc),
        }
        if sc.creative and sc.creative.get("shot"):
            try:
                image, lines = await flow.shot_inputs(db, sc)
                out["image_stale"] = not flow.image_fingerprint_matches(
                    (sc.creative.get("image") or {}).get("fingerprint"), image
                )
                out["audio_stale"] = bool(lines) and (sc.creative.get("audio") or {}).get(
                    "fingerprint"
                ) != flow.digest({"lines": lines})
                pending_image, pending_voice = await flow.pending_changes(db, sc)
                out["image_stale"] = out["image_stale"] or pending_image
                out["audio_stale"] = out["audio_stale"] or pending_voice
                out["segments"] = [
                    {**x, "url": providers().storage.url(x["key"])}
                    for x in (sc.creative.get("audio") or {}).get("segments", [])
                ]
            except AppError as exc:
                out["error"] = exc.message
        if sc.creative and sc.creative.get("shot"):
            from app.services.video import payload
            try:
                await payload(db, p, sc)
                out["video_ready"] = True
            except AppError as exc:
                out["video_ready"] = False
                out["video_block"] = exc.message
        scenes.append(out)
    revisions = list(
        await db.scalars(
            select(Revision).where(Revision.project_id == id).order_by(Revision.created_at.desc())
        )
    )
    from app.services.story_pacing import assess
    from app.services.video_capabilities import CAPABILITIES
    workflow = await flow.workflow_readiness(db, p)
    return {
        "pacing": assess((p.creative or {}).get("plan") or {}, await children(db, Scene, id)),
        "project": await project_out(db, p),
        "candidates": candidates,
        "scenes": scenes,
        "revisions": [columns(r) for r in revisions],
        "readiness": await workbench.readiness(db, p),
        "workflowReadiness": workflow,
        "stageStates": flow.workflow_stage_states(
            p, await children(db, Scene, id), await children(db, Character, id), revisions, workflow
        ),
        "issues": await flow.check_project(db, p),
        "capabilities": {
            "video": CAPABILITIES,
            "intro": (ROOT / "public/assets/intro.mp4").is_file(),
            "watermark": (ROOT / "public/assets/watermark.png").is_file(),
            "bgmPresets": any(file.is_file() and file.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"} for file in get_settings().bgm_dir.glob("*")),
            "voiceDesign": True,
            "voiceClone": True,
            "referenceVoiceLock": get_settings().tts_provider == "mimo",
            "roleAudio": get_settings().tts_provider == "minimax",
            "ttsProvider": get_settings().tts_provider,
            "ttsModel": get_settings().tts_model,
            "defaultVoice": get_settings().tts_voice_id,
            "presetMatching": True,
            "videoGeneration": get_settings().feature_video_generation,
            "maxImageReferences": get_settings().image_max_references,
        },
    }


@router.patch("/projects/{id}/plan")
async def edit_plan(id: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    plan = Plan.model_validate(body.data).model_dump()
    st = {**p.creative, "plan_draft": plan}
    if not st.get("plan_confirmed"):
        st["plan"] = plan
    await flow.save_state(db, p, st, "project")
    await db.commit()
    return media_urls(p.creative)


@router.patch("/projects/{id}/narrator")
async def narrator(id: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    voice = body.data.get("voice_id", "")
    speed = body.data.get("speed", 1)
    if (
        not isinstance(voice, str)
        or not voice
        or not isinstance(speed, (float, int))
        or not 0.5 <= speed <= 2
    ):
        raise AppError("INVALID_VOICE", "必须明确设置旁白音色 ID 和基础语速", 422)
    if get_settings().tts_provider == "mimo":
        from app.providers.mimo import resolve_voice

        voice = resolve_voice(voice)
    await flow.save_state(
        db,
        p,
        {
            **p.creative,
            "narrator": {
                "voice_id": voice,
                "provider": get_settings().tts_provider,
                "model": get_settings().tts_model,
                "speed": speed,
            },
        },
        "project",
    )
    await db.commit()
    return media_urls(p.creative)


@router.post("/projects/{id}/characters")
async def add_character(id: str, body: Persona, db: DB):
    p = await project(db, id)
    c = Character(project_id=id, name=body.name)
    db.add(c)
    await db.flush()
    await flow.change_character(db, c, body.model_dump())
    await db.commit()
    return await project_out(db, p)


@router.patch("/characters/{id}")
async def edit_character(id: str, body: Edit, db: DB):
    c = await require(db, Character, id)
    await project(db, c.project_id)
    flow.check_version(c.creative, body.expected)
    await flow.change_character(db, c, body.data)
    await db.commit()
    return media_urls(c.creative)


@router.post("/characters/{id}/reference")
async def upload_reference(id: str, body: Edit, db: DB):
    c = await require(db, Character, id)
    p = await project(db, c.project_id)
    flow.check_version(c.creative, body.expected)
    key = await bind_image(db, c.project_id, body.data.get("image", ""))
    if not key:
        raise AppError("IMAGE_REQUIRED", "请选择图片", 422)
    variant = body.data.get("variant", "")
    view = body.data.get("view", "")
    if view not in ("", "full_body", "front", "side", "back", "half_body", "face", "state", "turnaround"):
        raise AppError("INVALID_VIEW", "请选择可用参考视图", 422)
    inp = await flow.current_input(db, p, "character_image", c.id, variant, view=view)
    asset = await db.scalar(select(Asset).where(Asset.project_id == p.id, Asset.object_key == key))
    candidate = Candidate(
        project_id=p.id,
        entity_id=c.id,
        kind="character_image",
        fingerprint=flow.digest(inp),
        data={
            "key": key,
            "asset_id": asset.id if asset else None,
            "request": {"variant": variant, "view": view},
            "source": body.data.get("source", "upload"),
            "use": body.data.get("use", view or variant or "main"),
            "checks": body.data.get("checks", {}),
            "parent_revision": c.creative.get("revision") if variant or view else None,
            "logs": [],
        },
    )
    db.add(candidate)
    await db.commit()
    return {"candidateId": candidate.id}


@router.patch("/projects/{id}/locations/{location_id}")
async def edit_location(id: str, location_id: str, body: Edit, db: DB):
    p = await project(db, id)
    st = await flow.location_state(db, p, location_id)
    flow.check_version(st, body.expected)
    location = Location.model_validate(body.data).model_dump()
    if location["id"] != location_id:
        raise AppError("INVALID_LOCATION", "不能更改地点 ID", 422)
    st = await flow.save_location(db, p, location_id, {**st, "location": location, "confirmed": False})
    await db.commit()
    return media_urls(st)


@router.post("/projects/{id}/locations/{location_id}/reference")
async def upload_location_reference(id: str, location_id: str, body: Edit, db: DB):
    p = await project(db, id)
    st = await flow.location_state(db, p, location_id)
    flow.check_version(st, body.expected)
    key = await bind_image(db, id, body.data.get("image", ""))
    if not key:
        raise AppError("IMAGE_REQUIRED", "请选择无人环境图", 422)
    state_name = body.data.get("state", "")
    inp = await flow.current_input(db, p, "location_image", location_id, state_name)
    asset = await db.scalar(select(Asset).where(Asset.project_id == id, Asset.object_key == key))
    candidate = Candidate(
        project_id=id,
        entity_id=location_id,
        kind="location_image",
        fingerprint=flow.digest(inp),
        data={
            "key": key,
            "asset_id": asset.id if asset else None,
            "request": {"variant": state_name},
            "source": body.data.get("source", "upload"),
            "parent_revision": st.get("revision") if state_name else None,
            "logs": [],
        },
    )
    db.add(candidate)
    await db.commit()
    return {"candidateId": candidate.id}


@router.post("/projects/{id}/locations/{location_id}/confirm")
async def confirm_location(id: str, location_id: str, body: Edit, db: DB):
    p = await project(db, id)
    st = await flow.location_state(db, p, location_id)
    flow.check_version(st, body.expected)
    if not st.get("image") or st["image"].get("fingerprint") != flow.location_fingerprint(st, p.style):
        raise AppError("LOCATION_REFERENCE_REQUIRED", "请先选用与当前场景设定一致的环境图", 409)
    st = await flow.save_location(
        db,
        p,
        location_id,
        {**st, "confirmed": True, "checks": body.data.get("checks", {}), "notes": body.data.get("notes", "")},
    )
    await db.commit()
    return media_urls(st)


@router.post("/scenes/{id}/review")
async def review_scene(id: str, body: Edit, db: DB):
    sc = await require(db, Scene, id)
    p = await project(db, sc.project_id)
    await db.refresh(sc)
    flow.check_version(sc.creative or {}, body.expected)
    data = deepcopy(body.data)
    checks = data.get("checks", {})
    categories = {"character", "environment", "action", "sound", "subtitles", "transition"}
    if (
        data.get("status") not in ("accepted", "issues", "pending")
        or not isinstance(checks, dict)
        or set(checks) - categories
    ):
        raise AppError("INVALID_REVIEW", "请填写有效的逐镜验收结论和检查项", 422)
    if data["status"] == "accepted" and (
        not sc.video_key or not all(checks.get(x) is True for x in categories)
    ):
        raise AppError(
            "REVIEW_INCOMPLETE", "作品验收需有真实视频，并逐项人工确认人物、环境、动作、声音、字幕和衔接", 409
        )
    issues = data.get("issues", [])
    if not isinstance(issues, list) or any(
        not isinstance(x, dict) or x.get("category") not in categories or not x.get("note") for x in issues
    ):
        raise AppError("INVALID_REVIEW", "问题需包含检查类别和说明", 422)
    if data["status"] == "accepted" and issues:
        raise AppError("REVIEW_INCOMPLETE", "有未解决问题时不能标记已验收", 409)
    if data["status"] == "accepted":
        from app.services.video import dependency_is_stale, is_stale

        if await flow.scene_media_issues(db, p, sc):
            raise AppError("STALE_REVIEW_INPUT", "当前镜头素材已过期，请更新或重新绑定后再人工验收", 409)
    review = {
        "status": data["status"],
        "checks": checks,
        "notes": data.get("notes", ""),
        "issues": issues,
        "fingerprint": flow.review_fingerprint(sc),
        "checked_at": now().isoformat(),
        "scene_revision": sc.creative.get("revision"),
        "video_key": sc.video_key,
    }
    await flow.save_state(db, sc, {**sc.creative, "review": review}, "scene")
    await db.commit()
    return media_urls(sc.creative)


@router.post("/projects/{id}/preview-confirm")
async def confirm_preview(id: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    job = await require(db, ExportJob, body.data.get("export_job_id", ""))
    scenes = await children(db, Scene, id)
    fingerprint = flow.preview_fingerprint(scenes)
    if (
        job.project_id != id
        or job.status != "done"
        or job.settings.get("purpose") != "preview"
        or job.settings.get("source_mode") != "storyboard"
        or job.settings.get("preview_fingerprint") != fingerprint
    ):
        raise AppError(
            "STALE_PREVIEW", "请完整观看并确认当前静态分镜配声预演，旧预演或其他项目不能用于确认", 409
        )
    await flow.save_state(
        db,
        p,
        {
            **p.creative,
            "preview_confirmation": {
                "export_job_id": job.id,
                "fingerprint": fingerprint,
                "notes": body.data.get("notes", ""),
                "checked_at": now().isoformat(),
            },
        },
        "project",
    )
    await db.commit()
    return media_urls(p.creative)


@router.post("/projects/{id}/export-confirm")
async def confirm_export(id: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    job = await require(db, ExportJob, body.data.get("export_job_id", ""))
    scenes = await children(db, Scene, id)
    fingerprint = flow.render_fingerprint(scenes, p.ratio, p.style)
    checks = body.data.get("checks", {})
    categories = {"character", "environment", "action", "sound", "subtitles", "transition"}
    if (
        not isinstance(checks, dict)
        or set(checks) != categories
        or not all(value is True for value in checks.values())
    ):
        raise AppError(
            "REVIEW_INCOMPLETE", "请完整播放成片并逐项确认人物、环境、动作因果、声音、字幕和衔接", 409
        )
    if (
        job.project_id != id
        or job.status != "done"
        or job.settings.get("purpose") == "preview"
        or job.settings.get("source_mode") == "storyboard"
        or job.settings.get("render_fingerprint") != fingerprint
    ):
        raise AppError("STALE_EXPORT", "只能确认当前版本的动态成片，请更新过期导出或使用作品导出入口", 409)
    if not scenes or not all(sc.video_key and flow.review_current(sc) for sc in scenes):
        raise AppError("REVIEW_INCOMPLETE", "全部镜头需完成动态视频人工验收后再确认整片", 409)
    acceptance = {
        "status": "accepted",
        "fingerprint": fingerprint,
        "checks": checks,
        "notes": body.data.get("notes", ""),
        "checked_at": now().isoformat(),
        "export_job_id": job.id,
    }
    job.settings = {**job.settings, "wholeAcceptance": acceptance}
    await flow.save_state(db, p, {**p.creative, "export_confirmation": acceptance}, "project")
    await db.commit()
    return media_urls(p.creative)


@router.post("/characters/{id}/voice-reference")
async def upload_voice_reference(id: str, db: DB, expected: int = Form(...), file: UploadFile = File(...)):
    import tempfile
    from pathlib import Path

    from app.services.media import probe, run_ffmpeg

    c = await require(db, Character, id)
    await project(db, c.project_id)
    flow.check_version(c.creative, expected)
    raw = await file.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise AppError("PAYLOAD_TOO_LARGE", "声音参考上限 20 MB", 413)
    if Path(file.filename or "").suffix.lower() not in (".mp3", ".m4a", ".wav"):
        raise AppError("INVALID_MEDIA", "请上传 MP3、M4A 或 WAV 声音参考", 422)

    async def checkpoint():
        pass

    with tempfile.TemporaryDirectory(prefix="cineai-voice-reference-") as folder:
        source, output = Path(folder) / "input", Path(folder) / "reference.wav"
        source.write_bytes(raw)
        duration = await probe(source)
        if not 10 <= duration <= 300:
            raise AppError("INVALID_MEDIA", "声音参考需要 10 秒至 5 分钟的同一人独白", 422)
        await run_ffmpeg(
            ["-i", str(source), "-vn", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
            checkpoint,
        )
        asset = await save_asset(
            db,
            c.project_id,
            "voice-reference",
            output.read_bytes(),
            "audio/wav",
            "wav",
            duration_ms=round(duration * 1000),
        )
    st = {
        **c.creative,
        "voice_reference": {
            "key": asset.object_key,
            "asset_id": asset.id,
            "duration_ms": asset.duration_ms,
            "filename": Path(file.filename or "reference.wav").name,
        },
    }
    await flow.save_state(db, c, st, "character")
    await db.commit()
    return media_urls(c.creative)


@router.post("/characters/{id}/voice-source")
async def upload_original_voice(id: str, db: DB, expected: int = Form(...), file: UploadFile = File(...)):
    from app.services.audio_import import audio_asset

    c = await require(db, Character, id)
    p = await project(db, c.project_id)
    flow.check_version(c.creative, expected)
    asset = await audio_asset(db, p.id, file, "voice-source", maximum=300)
    inp = await flow.current_input(db, p, "voice_source", c.id)
    candidate = Candidate(
        project_id=p.id,
        entity_id=c.id,
        kind="voice_source",
        fingerprint=flow.digest(inp),
        data={
            "key": asset.object_key,
            "asset_id": asset.id,
            "duration_ms": asset.duration_ms,
            "voice_id": "source-" + c.id,
            "mode": "original",
            "model": "original-audio",
            "provider": "source-audio",
            "request": {},
        },
    )
    db.add(candidate)
    await db.commit()
    return {"candidateId": candidate.id}


@router.post("/scenes/{id}/line-audio")
async def upload_line_audio(
    id: str, db: DB, expected: int = Form(...), line_id: str = Form(...), file: UploadFile = File(...)
):
    from app.services.audio_import import import_line

    sc = await require(db, Scene, id)
    p = await project(db, sc.project_id)
    await db.refresh(sc)
    flow.check_version(sc.creative, expected)
    if not p.creative.get("shots_confirmed"):
        raise AppError("CONFIRMATION_REQUIRED", "先确认分镜，再导入录音", 409)
    result = await import_line(db, p, sc, line_id, file)
    await db.commit()
    return result


@router.post("/characters/{id}/confirm-image")
async def confirm_character_image(id: str, body: Edit, db: DB):
    c = await require(db, Character, id)
    p = await project(db, c.project_id)
    flow.check_version(c.creative or {}, body.expected)
    image = flow.character_reference(c.creative, None, p.style)
    checks = body.data.get("checks", {})
    if (
        not isinstance(checks, dict)
        or set(checks) - {"clear_silhouette", "no_subtitles", "low_occlusion", "identity_consistent"}
        or not all(checks.get(k) is True for k in ("clear_silhouette", "no_subtitles", "low_occlusion"))
    ):
        raise AppError("VISUAL_CHECK_REQUIRED", "请人工确认角色轮廓清楚、无字幕、少遮挡后再确认主图", 409)
    st = {
        **c.creative,
        "visual_checks": {
            "checks": checks,
            "notes": body.data.get("notes", ""),
            "image_fingerprint": image["fingerprint"],
            "candidate_id": image.get("candidate_id"),
            "source": "human",
            "checked_at": now().isoformat(),
        },
    }
    await flow.save_state(db, c, st, "character")
    await db.commit()
    return media_urls(c.creative)


@router.post("/characters/{id}/confirm")
async def confirm_character(id: str, body: Edit, db: DB):
    c = await require(db, Character, id)
    await project(db, c.project_id)
    flow.check_version(c.creative, body.expected)
    await flow.confirm_character(db, c, body.data.get("checks"), body.data.get("notes", ""))
    await db.commit()
    return media_urls(c.creative)


@router.patch("/scenes/{id}")
async def edit_scene(id: str, body: Edit, db: DB):
    sc = await require(db, Scene, id)
    await project(db, sc.project_id)
    await db.refresh(sc)
    flow.check_version(sc.creative or {}, body.expected)
    shot = await flow.validate_shot(db, sc.project_id, body.data, (sc.creative or {}).get("edit"))
    await apply_shot(db, sc, shot)
    await flow.unconfirm(db, sc.project_id, "shots")
    await db.commit()
    return media_urls(sc.creative)


apply_shot = flow.apply_shot

@router.post("/projects/{id}/confirm/{stage}")
async def confirm_stage(id: str, stage: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    st = deepcopy(p.creative)
    if stage == "plan":
        proposed = body.data.get("plan") or st.get("plan_draft") or st.get("plan")
        plan = Plan.model_validate(await workbench.publish_plan(db, p, st, proposed))
        if not st.get("cast_created"):
            for persona in plan.characters:
                c = Character(project_id=id, name=persona.name)
                db.add(c)
                await db.flush()
                await flow.save_state(
                    db, c, {"persona": persona.model_dump(), "confirmed": False}, "character"
                )
            st["cast_created"] = True
        st.update(plan_confirmed=True)
        p.name, p.style, p.ratio = plan.title, plan.style, plan.ratio
        p.outline = plan.model_dump()
    elif stage == "cast":
        chars = await children(db, Character, id)
        if st.get("plan_confirmed") and body.data.get("finalize_characters"):
            for ch in chars:
                if not (ch.creative or {}).get("confirmed"):
                    await flow.confirm_character(db, ch)
        if (
            not st.get("plan_confirmed")
            or not chars
            or any(not (c.creative or {}).get("confirmed") for c in chars)
        ):
            raise AppError("CONFIRMATION_REQUIRED", "请先确认方案并定稿全部角色", 409)
        st.update(cast_confirmed=True)
    elif stage == "shots":
        issues = await flow.check_project(db, p, media=False)
        if issues or not st.get("cast_confirmed"):
            raise AppError("PRECHECK_FAILED", "；".join(issues) or "先确认角色阶段", 409)
        st.update(shots_confirmed=True)
    else:
        raise AppError("INVALID_STAGE", "未知确认阶段", 422)
    await flow.save_state(db, p, st, "project")
    await db.commit()
    return await project_out(db, p)


async def job_payload(db, p, body):
    if (body.operation.startswith("shot_") or body.operation == "role_audio") and not p.creative.get(
        "shots_confirmed"
    ):
        raise AppError("CONFIRMATION_REQUIRED", "先确认分镜，再开始生成", 409)
    inp = await flow.current_input(
        db, p, body.operation, body.target, body.variant, body.voice_id, body.text, body.view, body.frame, body.use_reference
    )
    if body.operation == "shot_audio":
        for line in inp["lines"]:
            if line["provider"] not in ("source-audio", get_settings().tts_provider):
                raise AppError(
                    "VOICE_RESELECTION_REQUIRED",
                    "配音服务已切换，请试听并选用新角色和旁白音色，重新定稿角色并确认分镜；原配音已保留",
                    409,
                )
    if body.regenerate_line_ids and not set(body.regenerate_line_ids) <= {
        x["line"]["id"] for x in inp.get("lines", [])
    }:
        raise AppError("INVALID_LINE", "重录句子不属于当前分镜", 422)
    billable = inp.get("lines", [])
    if body.operation == "shot_audio":
        sc = await require(db, Scene, body.target)
        selected_fingerprints = {
            x["fingerprint"] for x in (sc.creative.get("audio") or {}).get("segments", [])
        }
        billable = [
            x
            for x in billable
            if x["fingerprint"] not in selected_fingerprints or x["line"]["id"] in body.regenerate_line_ids
        ]
    if body.operation == "shot_audio" and any(x.get("provider") == "source-audio" for x in billable):
        raise AppError("SOURCE_AUDIO_REQUIRED", "原声录音角色需要上传对应台词录音；不能自动合成新台词", 409)
    kind = (
        "image"
        if body.operation.endswith("image")
        else "tts"
        if body.operation in ("voice_preview", "voice_design", "voice_clone", "shot_audio", "role_audio")
        else "script"
    )
    return kind, {
        "creative": {
            "operation": body.operation,
            "target": body.target,
            "input": inp,
            "request": body.model_dump(),
        },
        "billable_calls": len(billable) if body.operation == "shot_audio" else 2 if body.operation == "character_image" and not body.view and not body.variant else 1,
        "text": "".join(x["line"]["text"] for x in billable)
        if body.operation in ("shot_audio", "role_audio")
        else body.text
        if kind == "tts"
        else "",
        "nonce": body.nonce,
    }


async def estimate_targets(db, p, requests):
    scenes = {scene.id: scene for scene in await children(db, Scene, p.id)}
    characters = {character.id: character for character in await children(db, Character, p.id)}
    locations = {location["id"]: location for location in (p.creative.get("plan") or {}).get("locations", [])}
    result = []
    for request in requests:
        scene = scenes.get(request.target)
        character = characters.get(request.target)
        kind = "image" if request.operation.endswith("image") else "tts" if request.operation.startswith("voice") or request.operation in ("shot_audio", "role_audio") else "script"
        result.append({
            "id": request.target or p.id,
            "title": scene.title if scene else character.name if character else locations[request.target]["name"] if request.target in locations else p.name,
            "operation": request.operation,
            "kind": kind,
            **({"orderIndex": scene.order_index + 1} if scene else {}),
        })
    return result


@router.post("/projects/{id}/estimate")
async def estimate(id: str, body: Generate, db: DB):
    p = await require(db, Project, id)
    if not p.creative:
        raise AppError("START_REQUIRED", "先开启创作流程", 409)
    kind, payload = await job_payload(db, p, body)
    price = {"image": "imagePerCall", "tts": "ttsPerKChar", "script": "llmPerMToken"}[kind]
    configured = get_settings().cost_unit_price_json.get(price, 0) > 0 and body.operation not in (
        "voice_design",
        "voice_clone",
    )
    return {
        "targets": await estimate_targets(db, p, [body]),
        "operation": body.operation,
        "scope": body.target or p.name,
        "calls": payload["billable_calls"],
        "estimateCents": estimate_cost(kind, payload) if configured else None,
        "label": "估算（非账单）" if configured else "无法估算：未配置完整价格",
        "note": "音色设计或复刻可能产生试听及首次使用费用；以服务商账单为准"
        if body.operation in ("voice_design", "voice_clone")
        else "相同输入重复提交复用已有任务；重新抽取候选才创建新调用",
    }


@router.post("/projects/{id}/generate", status_code=202)
async def generate(id: str, body: Generate, db: DB, bg: BackgroundTasks):
    p = await project(db, id)
    kind, payload = await job_payload(db, p, body)
    task = await create_job(db, id, kind, payload)
    await finish_submit(db, bg)
    return {"taskId": task.id}


validated_storyboard = flow.validated_storyboard

async def edit_storyboard_candidate(db, p, candidate, data, expected):
    flow.check_version(p.creative, expected)
    if candidate.project_id != p.id or candidate.kind != "storyboard":
        raise AppError("INVALID_CANDIDATE", "人工修稿只适用于当前项目的分镜候选", 422)
    if await flow.stale(db, p, candidate):
        raise AppError("STALE_CANDIDATE", "故事或角色输入已经变化，请以当前确认输入创建新分镜草稿", 409)
    board = await validated_storyboard(db, p, data)
    child = Candidate(
        project_id=p.id,
        entity_id=candidate.entity_id,
        kind="storyboard",
        fingerprint=candidate.fingerprint,
        task_id=candidate.task_id,
        data={
            **deepcopy(candidate.data),
            "value": board,
            "parent_candidate_id": candidate.id,
            "source": "manual-edit",
            "edited_at": now().isoformat(),
            "validation_issues": [],
            "draft": False,
            "logs": [*candidate.data.get("logs", []), "显式人工修正原始分镜草稿，未调用模型"],
        },
    )
    db.add(child)
    await db.flush()
    return child


@router.patch("/projects/{id}/candidates/{candidate_id}")
async def edit_candidate(id: str, candidate_id: str, body: Edit, db: DB):
    p = await project(db, id)
    candidate = await require(db, Candidate, candidate_id)
    child = await edit_storyboard_candidate(db, p, candidate, body.data, body.expected)
    await db.commit()
    return {"candidateId": child.id, "parentCandidateId": candidate.id}


@router.post("/projects/{id}/candidates/{candidate_id}/repair")
async def recover_candidate(id: str, candidate_id: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    candidate = await require(db, Candidate, candidate_id)
    if candidate.project_id != p.id or candidate.kind != "storyboard":
        raise AppError("INVALID_CANDIDATE", "只能恢复当前项目的分镜候选", 422)
    from app.services.storyboard_recovery import recover
    child, ready = await recover(db, p, candidate)
    await db.commit()
    return {"candidateId": child.id, "parentCandidateId": candidate.id, "ready": ready,
            "corrections": child.data.get("corrections", []), "issues": child.data.get("validation_issues", [])}


@router.post("/projects/{id}/select")
async def select_candidate(id: str, body: Selection, db: DB):
    p = await project(db, id)
    c = await require(db, Candidate, body.candidate_id)
    if c.project_id != id:
        raise AppError("INVALID_CANDIDATE", "候选不属于项目", 422)
    if c.data.get("package_pending") and c.task_id:
        task = await db.get(Task, c.task_id)
        if task and task.status in ("queued", "running"):
            raise AppError("CANDIDATE_GENERATING", "主形象已完成，三视图仍在生成，请稍后一起选用", 409)
    if c.kind == "video_correction":
        if body.data is not None:
            raise AppError("INVALID_SELECTION", "视频修正不能修改来源审计字段，请重新上传候选", 422)
        from app.services.video_correction import select_candidate as select_correction

        await select_correction(db, p, c, body.expected)
        await db.commit()
        return await project_out(db, p)
    if body.data is not None:
        c = await edit_storyboard_candidate(db, p, c, body.data, body.expected)
    if body.data is None and await selected(db, p, c):
        return await project_out(db, p)
    if await flow.stale(db, p, c):
        raise AppError("STALE_CANDIDATE", "候选基于旧输入；已保留历史，但不能覆盖新修改", 409)
    if c.kind == "storyboard" and (c.data.get("draft") or c.data.get("validation_issues")):
        flow.check_version(p.creative, body.expected)
        from app.services.storyboard_recovery import recover
        recovered, ready = await recover(db, p, c)
        if not ready:
            raise AppError("VALIDATION_ERROR" if c.data.get("validation_stage") == "schema" else "STORYBOARD_INCOMPLETE", "此方案还有无法自动整理的内容，请点击“AI 完善此方案”后重试。", 422)
        c = recovered
    value = c.data
    if c.kind in ("plan", "storyboard"):
        flow.check_version(p.creative, body.expected)
        st = deepcopy(p.creative)
        st["selected_" + c.kind] = c.id
        if c.kind == "plan":
            st["plan_draft"] = value["value"]
            if not st.get("plan_confirmed"):
                st["plan"] = value["value"]
        else:
            await flow.apply_storyboard_candidate(db, p, c)
        if c.kind == "plan":
            await flow.save_state(db, p, st, "project")
    elif c.kind == "role_audio":
        ch = await require(db, Character, c.entity_id)
        flow.check_version(ch.creative, body.expected)
        from app.services.voice_continuity import select_role

        await select_role(db, p, c)
    elif c.kind == "location_image":
        st = await flow.location_state(db, p, c.entity_id)
        flow.check_version(st, body.expected)
        name = value.get("request", {}).get("variant", "")
        image = {
            "key": value["key"],
            "asset_id": value.get("asset_id"),
            "candidate_id": c.id,
            "fingerprint": flow.location_fingerprint(st, p.style, name),
            "source": value.get("source", "provider"),
            "parent_revision": value.get("parent_revision"),
            "confirmed": True,
        }
        if name:
            st["states"] = {**st.get("states", {}), name: image}
        else:
            st["image"] = image
        st["confirmed"] = False
        await flow.save_location(db, p, c.entity_id, st)
    elif c.kind.startswith("shot_"):
        sc = await require(db, Scene, c.entity_id)
        flow.check_version(sc.creative, body.expected)
        st = deepcopy(sc.creative)
        if c.kind == "shot_image":
            image = {
                "key": value["key"],
                "asset_id": value.get("asset_id"),
                "fingerprint": c.fingerprint,
                "candidate_id": c.id,
                "logs": value.get("logs", []),
                "reference_count": value.get("reference_count"),
                "reference_mode": value.get("reference_mode", "manual"),
            }
            if value.get("request", {}).get("frame") == "last":
                image["first_frame_reference"] = (value.get("input") or {}).get("first_frame_reference")
                image["reference_policy"] = (value.get("input") or {}).get("reference_policy")
                st["last_frame"] = image
                st["shot"]["last_frame_asset_id"] = value.get("asset_id")
            else:
                st["image"] = image
                sc.first_frame_key, sc.video_key, sc.status = value["key"], None, "image_ready"
        else:
            st["audio"] = {
                "segments": value["segments"],
                "duration_ms": value["duration_ms"],
                "fingerprint": c.fingerprint,
                "candidate_id": c.id,
            }
            sc.audio_duration_ms = value["duration_ms"]
            sc.duration_sec = max(st["shot"]["duration"], value["duration_ms"] / 1000 + 0.3)
        await flow.save_state(db, sc, st, "scene")
    else:
        ch = await require(db, Character, c.entity_id)
        flow.check_version(ch.creative, body.expected)
        st = deepcopy(ch.creative)
        if c.kind == "character":
            await flow.change_character(db, ch, value["value"])
        else:
            if c.kind == "character_image":
                image = {
                    "key": value["key"],
                    "asset_id": value.get("asset_id"),
                    "candidate_id": c.id,
                    "fingerprint": flow.image_fingerprint(st["persona"], p.style),
                    "source": value.get("source", "provider"),
                    "parent_revision": value.get("parent_revision"),
                    "use": value.get(
                        "use",
                        value.get("request", {}).get("view")
                        or value.get("request", {}).get("variant")
                        or "main",
                    ),
                    "checks": value.get("checks", {}),
                    **({"turnaround": value["turnaround"]} if value.get("turnaround") else {}),
                    "confirmed": True,
                }
                variant = value["request"].get("variant")
                view = value["request"].get("view")
                if view and view != "state":
                    image["fingerprint"] = flow.view_fingerprint(st, view, p.style)
                    st["views"] = {**st.get("views", {}), view: image}
                elif variant:
                    image["fingerprint"] = flow.variant_fingerprint(st, variant, p.style)
                    st["references"] = {**st.get("references", {}), variant: image}
                else:
                    st["image"] = image
                    ch.image_key = value["key"]
            elif c.kind in ("voice_preview", "voice_design", "voice_clone", "voice_source"):
                st["voice"] = {k: value[k] for k in ("key", "voice_id", "mode", "provider")}
                st["voice"].update(
                    candidate_id=c.id,
                    model=value.get("model", get_settings().tts_model),
                    fingerprint=flow.digest(flow.voice_spec(st["persona"])),
                )
                if value.get("reference"):
                    st["voice"]["reference"] = value["reference"]
                if value.get("generation_model"):
                    st["voice"]["generation_model"] = value["generation_model"]
                ch.voice_id = value["voice_id"]
            else:
                raise AppError("INVALID_SELECTION", "匹配结果请逐个试听后选择声音", 422)
            st["confirmed"] = False
            await flow.save_state(db, ch, st, "character")
            await flow.invalidate_character_dependents(db, ch)
            await flow.unconfirm(db, id, "cast")
    await db.commit()
    return await project_out(db, p)


@router.get("/library")
async def library(db: DB):
    return [
        {**columns(x), "image": providers().storage.url((x.data.get("image") or {}).get("key"))}
        for x in await db.scalars(select(LibraryCharacter).order_by(LibraryCharacter.created_at.desc()))
    ]


@router.post("/characters/{id}/publish-library")
async def publish_library(id: str, db: DB):
    c = await require(db, Character, id)
    if not c.creative or not c.creative.get("confirmed"):
        raise AppError("CONFIRMATION_REQUIRED", "先定稿角色再存入可复用角色库", 409)
    data = deepcopy(c.creative)
    # Library owns copies: deleting a source project cannot invalidate reusable characters.
    for field in ("image", "voice", "voice_reference"):
        if data.get(field, {}).get("key"):
            old = data[field]["key"]
            key = f"library/{uid()}/{old.rsplit('/', 1)[-1]}"
            await providers().storage.put(
                key,
                await providers().storage.get(old),
                "image/png"
                if field == "image"
                else "audio/wav"
                if field == "voice_reference"
                else "audio/mpeg",
            )
            data[field]["key"] = key
    sheet = (data.get("image") or {}).get("turnaround")
    if sheet and sheet.get("key"):
        key = f"library/{uid()}/turnaround.png"
        await providers().storage.put(key, await providers().storage.get(sheet["key"]), "image/png")
        data["image"]["turnaround"] = {"key": key}
    locked = (data.get("voice") or {}).get("reference")
    if locked and data["voice"].get("provider") == "mimo":
        key = f"library/{uid()}/voice-reference.mp3"
        await providers().storage.put(key, await providers().storage.get(locked["key"]), "audio/mpeg")
        data["voice"]["reference"] = {**locked, "key": key}
    data["references"] = {}
    data["views"] = {}
    row = LibraryCharacter(name=c.name, data=data)
    db.add(row)
    await db.commit()
    return columns(row)


@router.post("/projects/{id}/reuse/{library_id}")
async def reuse(id: str, library_id: str, db: DB):
    p = await project(db, id)
    lib = await require(db, LibraryCharacter, library_id)
    data = deepcopy(lib.data)
    for field in ("image", "voice", "voice_reference"):
        if data.get(field, {}).get("key"):
            raw = await providers().storage.get(data[field]["key"])
            asset = await save_asset(
                db,
                id,
                "reference"
                if field == "image"
                else "voice-reference"
                if field == "voice_reference"
                else "voice-preview",
                raw,
                "image/png"
                if field == "image"
                else "audio/wav"
                if field == "voice_reference"
                else "audio/mpeg",
                "png" if field == "image" else "wav" if field == "voice_reference" else "mp3",
            )
            data[field]["key"] = asset.object_key
            if field == "voice_reference":
                data[field]["asset_id"] = asset.id
    sheet = (data.get("image") or {}).get("turnaround")
    if sheet and sheet.get("key"):
        asset = await save_asset(db, id, "character-turnaround", await providers().storage.get(sheet["key"]), "image/png", "png")
        data["image"]["turnaround"] = {"key": asset.object_key, "asset_id": asset.id}
    # The locked MiMo sample belongs to the imported role too; do not keep a
    # dependency on media in the source project (which may later be deleted).
    locked = (data.get("voice") or {}).get("reference")
    if locked and data["voice"].get("provider") == "mimo":
        raw = await providers().storage.get(locked["key"])
        asset = await save_asset(
            db,
            id,
            "voice-reference-locked",
            raw,
            "audio/mpeg",
            "mp3",
            duration_ms=locked.get("duration_ms"),
        )
        data["voice"]["reference"] = {**locked, "key": asset.object_key, "asset_id": asset.id}
    data["source_library_id"] = lib.id
    c = Character(
        project_id=id, name=lib.name, image_key=data["image"]["key"], voice_id=data["voice"]["voice_id"]
    )
    db.add(c)
    await db.flush()
    await flow.save_state(db, c, data, "character")
    await flow.unconfirm(db, p.id, "cast")
    await db.commit()
    return await project_out(db, p)


@router.post("/projects/{id}/batch/{mode}")
async def batch(id: str, mode: str, db: DB, bg: BackgroundTasks):
    p = await project(db, id)
    if mode not in ("estimate", "generate"):
        raise AppError("INVALID_MODE", "未知批量操作", 422)
    requests = []
    for sc in await children(db, Scene, id):
        from app.services.production_segments import segment_for
        group = segment_for(p, sc.id)
        leader = await require(db, Scene, group["scene_ids"][0]) if group else sc
        shot = (leader.creative or {}).get("shot") or {}
        inp = shot.get("video_input") or {}
        need_image = leader.id == sc.id and inp.get("mode", "first_frame") in ("first_frame", "first_last_frame") and not (inp.get("first_frame_asset_id") or shot.get("first_frame_asset_id"))
        need_audio = inp.get("sound_strategy", "post_audio") != "model_audio"
        if not need_image and not need_audio:
            continue
        image, lines = await flow.shot_inputs(db, sc, need_image=need_image, need_audio=need_audio)
        if need_image and not flow.image_fingerprint_matches((sc.creative.get("image") or {}).get("fingerprint"), image):
            requests.append(Generate(operation="shot_image", target=sc.id))
        if need_audio and lines and (sc.creative.get("audio") or {}).get("fingerprint") != flow.digest({"lines": lines}):
            requests.append(Generate(operation="shot_audio", target=sc.id))
    prepared = [await job_payload(db, p, req) for req in requests]
    if mode == "estimate":
        prices = get_settings().cost_unit_price_json
        configured = bool(prepared) and all(
            prices.get({"image": "imagePerCall", "tts": "ttsPerKChar"}[kind], 0) > 0 for kind, _ in prepared
        )
        return {
            "targets": await estimate_targets(db, p, requests),
            "calls": sum(v["billable_calls"] for _, v in prepared),
            "estimateCents": sum(estimate_cost(k, v) for k, v in prepared) if configured else None,
            "label": "估算（非账单）" if configured else "无法估算：未配置完整价格",
            "note": "仅生成缺失或过期的画面与配音；全部结果作为候选，确认后替换。",
        }
    tasks = [await create_job(db, id, kind, payload) for kind, payload in prepared]
    await finish_submit(db, bg)
    return {"taskIds": [t.id for t in tasks]}


@router.post("/scenes/{id}/archive")
async def archive_scene(id: str, body: Edit, db: DB):
    sc = await require(db, Scene, id)
    await project(db, sc.project_id)
    await db.refresh(sc)
    flow.check_version(sc.creative or {}, body.expected)
    await flow.save_state(db, sc, {**sc.creative, "archived": True}, "scene")
    from sqlalchemy import func

    lowest = await db.scalar(select(func.min(Scene.order_index)).where(Scene.project_id == sc.project_id))
    sc.order_index = min(-1, lowest - 1)
    await flow.unconfirm(db, sc.project_id, "shots")
    await db.commit()
    return {"archived": True, "revision": sc.creative["revision"]}


async def selected(db, p, c):
    if c.kind == "location_image":
        st = (p.creative or {}).get("locations", {}).get(c.entity_id, {})
        return (st.get("image") or {}).get("candidate_id") == c.id or any(
            x.get("candidate_id") == c.id for x in st.get("states", {}).values()
        )
    if c.kind == "role_audio":
        selected_keys = {
            x["key"]
            for sc in await children(db, Scene, p.id)
            for x in (sc.creative.get("audio") or {}).get("segments", [])
        }
        return bool(c.data.get("segments")) and all(x["key"] in selected_keys for x in c.data["segments"])
    if c.kind in ("plan", "storyboard"):
        return (p.creative or {}).get("selected_" + c.kind) == c.id or (
            c.kind == "plan" and (p.creative or {}).get("plan") == c.data.get("value")
        )
    model = Scene if c.kind.startswith("shot_") or c.kind == "video_correction" else Character
    row = await db.get(model, c.entity_id)
    if not row or not row.creative:
        return False
    refs = [v for v in row.creative.values() if isinstance(v, dict)]
    refs += list(row.creative.get("views", {}).values()) + list(row.creative.get("references", {}).values())
    return any(v.get("candidate_id") == c.id for v in refs)


@router.post("/scenes/{id}/video-correction")
async def upload_video_correction(
    id: str,
    db: DB,
    expected: int = Form(...),
    reason: str = Form(...),
    source_task_id: str = Form(...),
    file: UploadFile = File(...),
):
    from app.services.video_correction import create_candidate, MAX_BYTES

    raw = await file.read(MAX_BYTES + 1)
    candidate = await create_candidate(
        db, id, expected, reason, source_task_id, raw, file.content_type, file.filename
    )
    await db.commit()
    return {
        "candidateId": candidate.id,
        "assetId": candidate.data["asset_id"],
        "sha256": candidate.data["sha256"],
        "durationSeconds": candidate.data["duration_ms"] / 1000,
        "sourceTaskId": source_task_id,
        "modelCalled": False,
    }


@router.post("/scenes/{id}/reference")
async def reuse_shot_image(id: str, body: Edit, db: DB):
    sc = await require(db, Scene, id)
    p = await project(db, sc.project_id)
    await db.refresh(sc)
    flow.check_version(sc.creative or {}, body.expected)
    key = await bind_image(db, p.id, body.data.get("image", ""))
    if not key:
        raise AppError("IMAGE_REQUIRED", "请选择本项目图片或上传参考图", 422)
    frame = body.data.get("frame", "first")
    if frame not in ("first", "last"):
        raise AppError("INVALID_FRAME", "请选择首帧或尾帧用途", 422)
    inp = await flow.current_input(db, p, "shot_image", sc.id, frame=frame)
    asset = await db.scalar(select(Asset).where(Asset.project_id == p.id, Asset.object_key == key))
    c = Candidate(
        project_id=p.id,
        entity_id=sc.id,
        kind="shot_image",
        fingerprint=flow.digest(inp),
        data={
            "key": key,
            "asset_id": asset.id if asset else None,
            "request": {"frame": frame},
            "source": "manual-reuse",
            "logs": ["人工上传/复用已有素材，未调用生图模型；请预览确认动作和构图"],
        },
    )
    db.add(c)
    await db.commit()
    return {"candidateId": c.id}


@router.post("/projects/{id}/plan-impact")
async def plan_impact(id: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    proposed = Plan.model_validate(body.data).model_dump()
    return workbench.plan_impact(p.creative.get("confirmed_plan") or p.creative.get("plan"), proposed)


@router.get("/projects/{id}/history")
async def history(id: str, db: DB):
    p = await require(db, Project, id)
    return await workbench.history(db, p)


async def restore_context(db, id, revision_id):
    p = await project(db, id)
    r = await require(db, Revision, revision_id)
    if r.project_id != id:
        raise AppError("INVALID_REVISION", "版本不属于本项目", 422)
    if r.kind == "location":
        from types import SimpleNamespace

        Location.model_validate(r.data.get("location"))
        state = await flow.location_state(db, p, r.entity_id)
        return (
            p,
            r,
            SimpleNamespace(creative=state),
            ["恢复该环境设定与当时选用素材为新版本；需要重新确认场景，关联镜头保留原版本直到显式更新。"],
        )
    row = (
        p
        if r.kind == "project"
        else await require(db, Character if r.kind == "character" else Scene, r.entity_id)
    )
    if isinstance(row, Scene) and row.order_index < 0:
        raise AppError("ARCHIVED_SCENE", "该镜头已归档，请在当前分镜中手动引用需要的内容", 409)
    messages = []
    if r.kind == "project":
        data = r.data.get("plan_draft") or r.data.get("plan")
        if not data:
            raise AppError("EMPTY_REVISION", "该版本没有故事文稿", 422)
        Plan.model_validate(data)
        messages = ["创建新的故事草稿；确认前不影响角色、分镜与成片。"]
    elif r.kind == "character":
        Persona.model_validate(r.data["persona"])
        linked = [
            s.title
            for s in await children(db, Scene, id)
            if r.entity_id in ((s.creative or {}).get("shot") or {}).get("cast", {})
        ]
        messages = [
            "恢复人物设定与当时选用的形象、声音，需重新定稿；角色与分镜阶段需再次确认。",
            "关联镜头：" + ("、".join(linked) or "无") + "。画面与配音按实际依赖标记更新，旧资产保留。",
        ]
    else:
        await flow.validate_shot(db, id, r.data.get("shot"), r.data.get("edit"))
        messages = ["恢复该镜头的脚本与选用素材，分镜阶段需再次确认；过期的角色引用或媒体仍需更新。"]
    return p, r, row, messages


@router.get("/projects/{id}/history/{revision_id}/impact")
async def restore_impact(id: str, revision_id: str, db: DB):
    p, r, row, messages = await restore_context(db, id, revision_id)
    return {
        "expected": row.creative["version"],
        "projectExpected": p.creative["version"],
        "messages": messages,
    }


@router.post("/projects/{id}/history/{revision_id}/restore")
async def restore(id: str, revision_id: str, body: Edit, db: DB):
    p, r, row, messages = await restore_context(db, id, revision_id)
    flow.check_version(row.creative, body.expected)
    flow.check_version(p.creative, body.data.get("projectExpected"))
    if r.kind == "location":
        await flow.save_location(db, p, r.entity_id, {**deepcopy(r.data), "confirmed": False})
    elif r.kind == "project":
        st = {**p.creative, "plan_draft": deepcopy(r.data.get("plan_draft") or r.data["plan"])}
        await flow.save_state(db, p, st, "project")
    elif r.kind == "character":
        st = {**deepcopy(r.data), "confirmed": False}
        await flow.save_state(db, row, st, "character")
        row.name, row.description, row.clothing = (
            st["persona"]["name"],
            st["persona"]["identity"],
            st["persona"]["clothing"],
        )
        row.image_key = (st.get("image") or {}).get("key")
        row.voice_id = (st.get("voice") or {}).get("voice_id")
        await flow.unconfirm(db, id, "cast")
    else:
        # Preserve the current version counter while restoring immutable content.
        restored = {**deepcopy(r.data), "version": row.creative["version"]}
        row.creative = restored
        await apply_shot(db, row, await flow.validate_shot(db, id, restored["shot"], restored.get("edit")))
        row.first_frame_key = (restored.get("image") or {}).get("key")
        row.video_key = None
        row.audio_duration_ms = (restored.get("audio") or {}).get("duration_ms", 0)
        await flow.unconfirm(db, id, "shots")
    await db.commit()
    return {"messages": messages}


@router.post("/projects/{id}/sync-character/{character_id}")
async def sync_character(id: str, character_id: str, body: Edit, db: DB):
    p = await project(db, id)
    c = await require(db, Character, character_id)
    if c.project_id != id:
        raise AppError("INVALID_CHARACTER", "角色不属于本项目", 422)
    flow.check_version(c.creative, body.expected)
    flow.check_version(p.creative, body.data.get("projectExpected"))
    plan = p.creative.get("plan_draft") or p.creative.get("plan") or {}
    index, fields = body.data.get("index"), body.data.get("fields", [])
    if (
        not isinstance(index, int)
        or not 0 <= index < len(plan.get("characters", []))
        or not fields
        or not set(fields) <= set(Persona.model_fields)
    ):
        raise AppError("INVALID_FIELDS", "请选择有效的人物初稿与同步字段", 422)
    persona = {**c.creative["persona"], **{k: plan["characters"][index][k] for k in fields}}
    await flow.change_character(db, c, persona)
    await db.commit()
    return media_urls(c.creative)


@router.patch("/projects/{id}/brief")
async def edit_brief(id: str, body: Edit, db: DB):
    p = await project(db, id)
    flow.check_version(p.creative, body.expected)
    if p.creative.get("plan") or p.creative.get("plan_draft"):
        raise AppError("PLAN_EXISTS", "已有故事，请在故事文稿中修改创作设定", 409)
    idea = body.data.get("idea", "").strip()
    ratio, style = body.data.get("ratio"), body.data.get("style", "").strip()
    duration, count = body.data.get("duration"), body.data.get("scene_count")
    if (
        not idea
        or len(idea) > 10000
        or ratio not in ("16:9", "9:16", "1:1")
        or not style
        or len(style) > 2000
        or not isinstance(duration, int)
        or not 6 <= duration <= 240
        or not isinstance(count, int)
        or not 1 <= count <= 24
    ):
        raise AppError("INVALID_BRIEF", "请填写创意、风格、6–240 秒时长与 1–24 个镜头", 422)
    p.description, p.style, p.ratio = idea, style, ratio
    await flow.save_state(
        db, p, {**p.creative, "plan_settings": {"duration": duration, "scene_count": count}}, "project"
    )
    await db.commit()
    return media_urls(p.creative)

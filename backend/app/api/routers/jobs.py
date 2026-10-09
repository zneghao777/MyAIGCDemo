from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select
from app.api.routers.resources import DB
from app.core.errors import AppError
from app.core.events import redis_client
from app.core.config import get_settings
from app.models import Project, Scene, Character, Task, ExportJob, Asset, now
from app.schemas import Batch, Pause, ScriptInput, AIInput, TTSInput, ExportSettings, VideoRetake
from app.services.resources import require, children, task_out, export_out, ensure_idle
from app.services.jobs import create_job, scene_payload, dispatch_pending, previous_video_take
from app.providers import providers
from app.providers import voice_presets

router = APIRouter(prefix="/api")


async def finish_submit(db, bg):
    await db.commit()
    bg.add_task(dispatch_pending)


@router.post("/tasks", status_code=202)
async def batch(body: Batch, db: DB, bg: BackgroundTasks):
    await require(db, Project, body.project_id, True)
    project = await require(db, Project, body.project_id)
    if project.creative and body.kind != "video":
        raise AppError("USE_CREATIVE_FLOW", "请在创作流程确认分镜后生成候选，预览后选用", 409)
    if body.kind == "video" and not get_settings().feature_video_generation:
        raise AppError("FEATURE_DISABLED", "AI 视频未启用，请使用动态预演导出", 403)
    if await db.scalar(
        select(Task.id).where(
            Task.project_id == body.project_id,
            Task.kind.in_(["script", "compose"]),
            Task.status.in_(["queued", "running"]),
        )
    ):
        raise AppError("SCENE_HAS_RUNNING_TASK", "剧本或导出任务进行中", 409)
    if body.kind == "tts":
        raise AppError("LEGACY_BINDING_REQUIRED", "旧台词需先升级并明确绑定发言人，再生成语音", 409)
    queued = []
    rejected = []
    for id in dict.fromkeys(body.scene_ids):
        scene = await db.get(Scene, id)
        if not scene or scene.project_id != body.project_id:
            rejected.append({"sceneId": id, "code": "RESOURCE_NOT_FOUND"})
            continue
        if body.kind == "video" and scene.video_key:
            rejected.append({"sceneId": id, "code": "VIDEO_ALREADY_EXISTS"})
            continue
        try:
            job = await create_job(
                db, body.project_id, body.kind, await scene_payload(db, scene, body.kind), id
            )
            queued.append(task_out(job))
        except AppError as exc:
            if exc.status == 402:
                raise
            rejected.append({"sceneId": id, "code": exc.code})
    await finish_submit(db, bg)
    return {"queued": queued, "rejected": rejected}


@router.get("/projects/{id}/tasks")
async def tasks(id: str, db: DB):
    await require(db, Project, id)
    return [task_out(t) for t in await children(db, Task, id)]


@router.get("/tasks/{id}")
async def task(id: str, db: DB):
    row = await require(db, Task, id)
    output = task_out(row)
    if row.result and row.result.get("assetId"):
        asset = await db.get(Asset, row.result["assetId"])
        if asset:
            output["result"] = {**row.result, "url": providers().storage.url(asset.object_key)}
    return output


@router.post("/scenes/{id}/video-retake", status_code=202)
async def video_retake(id: str, body: VideoRetake, db: DB, bg: BackgroundTasks):
    import hashlib
    from copy import deepcopy

    scene = await require(db, Scene, id)
    await require(db, Project, scene.project_id, True)
    scene = await require(db, Scene, id, True)
    await db.refresh(scene)
    identity = "retake-" + hashlib.sha256(f"{scene.project_id}|{scene.id}|{body.nonce}".encode()).hexdigest()
    existing = await db.scalar(
        select(Task)
        .where(
            Task.project_id == scene.project_id,
            Task.scene_id == scene.id,
            Task.kind == "video",
            Task.payload["submission_id"].as_string() == identity,
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    if existing:
        # Return the latest recovery of the same paid identity after input edits.
        return {**task_out(existing), "deduplicated": True}
    from app.services.creative import check_version

    check_version(scene.creative or {"version": 0}, body.expected)
    await ensure_idle(db, scene.project_id, scene.id)
    previous = previous_video_take(scene)
    if not previous:
        raise AppError("VIDEO_RETAKE_REQUIRES_TAKE", "单镜重做需要已有视频；首次生成使用批量视频流程", 409)
    from app.services.video import retake_payload
    project = await require(db, Project, scene.project_id)
    payload = await retake_payload(db, project, scene, body)
    payload.update(
        submission_id=identity,
        retake={
            "nonce": body.nonce,
            "reason": body.reason,
            "preserve": body.preserve,
            "source_asset_id": body.source_asset_id,
            "modify": body.modify,
            "expected": body.expected,
            "previous_video_key": previous["key"],
            "previous_take": deepcopy(previous),
        },
    )
    new = await create_job(db, scene.project_id, "video", payload, scene.id)
    new.result = {"retake": payload["retake"]}
    await finish_submit(db, bg)
    return {**task_out(new), "deduplicated": False}


@router.post("/tasks/{id}/retry", status_code=202)
async def retry(id: str, db: DB, bg: BackgroundTasks):
    row = await require(db, Task, id)
    await require(db, Project, row.project_id, True)
    if row.status not in ("failed", "cancelled"):
        raise AppError("INVALID_STATE", "只能重试失败或取消的任务", 409)
    await ensure_idle(db, row.project_id, row.scene_id)
    # New task identity avoids Celery's revoked task-id cache, preserving history/costs.
    payload = dict(row.payload)
    if row.payload.get("creative"):
        from app.services.creative import current_input, digest

        req = row.payload["creative"]
        p = await require(db, Project, row.project_id)
        args = req["request"]
        current = await current_input(
            db,
            p,
            req["operation"],
            req["target"],
            args.get("variant", ""),
            args.get("voice_id", ""),
            args.get("text", ""),
            args.get("view", ""),
            args.get("frame", "first"),
        )
        if digest(current) != digest(req["input"]):
            raise AppError("STALE_TASK", "任务输入已过期，请按当前版本重新生成", 409)
    if row.scene_id:
        scene = await require(db, Scene, row.scene_id)
        payload = await scene_payload(db, scene, row.kind)
    if row.kind == "video":
        if payload.get("video_source") != row.payload.get("video_source"):
            raise AppError("STALE_TASK", "分镜已改变，请创建新的视频任务", 409)
        payload = {**row.payload, "submission_id": row.payload.get("submission_id") or row.id}
    if row.kind == "compose":
        old = await require(db, ExportJob, payload["export_id"])
        job = ExportJob(project_id=row.project_id, settings=old.settings)
        db.add(job)
        await db.flush()
        payload["export_id"] = job.id
    new = await create_job(db, row.project_id, row.kind, payload, row.scene_id)
    if row.kind == "video":
        new.provider_task_id = row.provider_task_id
        new.result = row.result
    await finish_submit(db, bg)
    return task_out(new)


@router.post("/tasks/{id}/cancel")
async def cancel(id: str, db: DB):
    row = await require(db, Task, id, True)
    if row.status not in ("queued", "running"):
        return task_out(row)
    row.status = "cancelled"
    row.finished_at = now()
    if row.scene_id:
        scene = await db.get(Scene, row.scene_id)
        if scene and row.kind in ("image", "video"):
            scene.status = "image_ready" if scene.first_frame_key else "draft"
    if row.kind == "compose":
        job = await db.get(ExportJob, row.payload["export_id"])
        if job:
            job.status = "cancelled"
    await db.commit()
    from app.core.events import publish

    await publish(row.project_id, "task", task_out(row))
    return task_out(row)


@router.post("/projects/{id}/queue/pause")
async def pause(id: str, body: Pause, db: DB):
    await require(db, Project, id)
    async with redis_client() as redis:
        if body.paused:
            await redis.set(f"cineai:paused:{id}", "1")
        else:
            await redis.delete(f"cineai:paused:{id}")
    return {"paused": body.paused}


@router.get("/projects/{id}/queue")
async def queue_state(id: str, db: DB):
    await require(db, Project, id)
    async with redis_client() as redis:
        return {"paused": bool(await redis.get(f"cineai:paused:{id}"))}


@router.post("/projects/{id}/script/generate", status_code=202)
async def generate(id: str, body: ScriptInput, db: DB, bg: BackgroundTasks, request: Request):
    project = await require(db, Project, id, True)
    if project.creative:
        raise AppError("USE_CREATIVE_FLOW", "请根据已确认方案生成分镜候选", 409)
    await ensure_idle(db, id)
    payload = {
        **body.model_dump(),
        "style": project.style,
        "ratio": project.ratio,
        "characters": [
            {"name": c.name, "description": c.description, "clothing": c.clothing}
            for c in await children(db, Character, id)
        ],
    }
    task = await create_job(db, id, "script", payload)
    await finish_submit(db, bg)
    if "text/event-stream" in request.headers.get("accept", ""):
        from .events import stream_response

        # Dispatch before streaming; BackgroundTasks only execute after response closes.
        await dispatch_pending()
        return await stream_response(id, request, task.id)
    return {"taskId": task.id}


@router.post("/ai/{operation}", status_code=202)
async def ai(operation: str, body: AIInput, db: DB, bg: BackgroundTasks):
    if operation not in ("optimize-prompt", "camera-description", "stage-layout"):
        raise AppError("RESOURCE_NOT_FOUND", "未知 AI 功能", 404)
    scene = await require(db, Scene, body.scene_id)
    if scene.project_id != body.project_id:
        raise AppError("RESOURCE_NOT_FOUND", "分镜不属于项目", 404)
    project = await require(db, Project, body.project_id, True)
    task = await create_job(
        db,
        project.id,
        "script",
        {
            "operation": operation,
            "scene_id": scene.id,
            "prompt": scene.image_prompt,
            "style": project.style,
            "directorData": body.director_data.model_dump(by_alias=True)
            if body.director_data
            else scene.director_data,
        },
    )
    await finish_submit(db, bg)
    return {"taskId": task.id}


@router.get("/tts/voices")
async def voices():
    return [
        {"label": label, "voiceId": voice, "previewUrl": None, "verified": False}
        for label, voice in voice_presets().items()
    ]


@router.post("/tts", status_code=202)
@router.post("/tts/preview", status_code=202)
async def tts(body: TTSInput, db: DB, bg: BackgroundTasks):
    task = await create_job(db, body.project_id, "tts", body.model_dump(exclude={"project_id"}))
    await finish_submit(db, bg)
    return {"taskId": task.id}


@router.post("/characters/{id}/voice-preview", status_code=202)
async def preview_character(id: str, db: DB, bg: BackgroundTasks):
    row = await require(db, Character, id)
    task = await create_job(
        db, row.project_id, "tts", {"text": "总有人，在等一封信。", "voice_id": row.voice_id}
    )
    await finish_submit(db, bg)
    return {"taskId": task.id}


@router.post("/projects/{id}/exports", status_code=202)
@router.post("/projects/{id}/preview", status_code=202)
async def export(id: str, body: ExportSettings, db: DB, bg: BackgroundTasks, request: Request):
    project = await require(db, Project, id, True)
    await ensure_idle(db, id)
    scenes = await children(db, Scene, id)
    static = body.source_mode == "storyboard"
    if not scenes or any(
        not sc.first_frame_key if static else not sc.first_frame_key and not sc.video_key for sc in scenes
    ):
        raise AppError("FIRST_FRAME_REQUIRED", "请先为全部分镜生成首帧", 409)
    if project.creative:
        from app.services.creative import check_project

        issues = await check_project(db, project, video=not static)
        if not project.creative.get("shots_confirmed"):
            issues.append("分镜尚未确认")
        if issues:
            raise AppError("PRECHECK_FAILED", "；".join(issues), 409)
    if not project.creative and any(
        (sc.dialogue and not sc.audio_key) or (sc.narration and not sc.narration_key) for sc in scenes
    ):
        raise AppError("LEGACY_BINDING_REQUIRED", "旧项目缺少配音，请先补全发言人和独立旁白配置", 409)
    settings = body.model_dump()
    settings["purpose"] = "preview" if request.url.path.endswith("/preview") else "export"
    from app.services.creative import preview_fingerprint, review_current, render_fingerprint

    settings["manualAcceptance"] = not static and bool(scenes) and all(review_current(sc) for sc in scenes)
    settings["acceptanceLabel"] = "逐镜人工已验收" if settings["manualAcceptance"] else "草稿，待艺术验收"
    settings["preview_fingerprint"] = preview_fingerprint(scenes)
    settings["render_fingerprint"] = render_fingerprint(scenes, project.ratio, project.style, static)
    if body.music:
        if body.bgm_asset_id:
            bgm = await require(db, Asset, body.bgm_asset_id)
            if bgm.project_id != id or bgm.kind != "bgm":
                raise AppError("INVALID_ASSET", "背景音乐必须属于当前项目", 422)
            settings["bgm_key"] = bgm.object_key
        elif not any(get_settings().bgm_dir.glob(body.mood + ".*")):
            raise AppError("BGM_REQUIRED", "所选背景音乐尚未配置，请上传音乐或关闭混音", 409)
    job = ExportJob(project_id=id, settings=settings)
    db.add(job)
    await db.flush()
    # Include missing voice synthesis in composition's budget reservation.
    text = "".join(
        (s.dialogue if not s.audio_key else "") + (s.narration if not s.narration_key else "") for s in scenes
    )
    payload = {"export_id": job.id, "text": text}
    if project.creative:
        from copy import deepcopy

        snapshot = {
            "project_revision": project.creative["revision"],
            "ratio": project.ratio,
            "manualAcceptance": settings["manualAcceptance"],
            "scenes": [
                {col.name: deepcopy(getattr(sc, col.name)) for col in sc.__table__.columns} for sc in scenes
            ],
        }
        for sc in snapshot["scenes"]:
            sc["sound_effect_assets"] = []
            for effect in ((sc.get("creative") or {}).get("shot") or {}).get("sound_effects", []):
                asset = await require(db, Asset, effect["asset_id"])
                sc["sound_effect_assets"].append({**effect, "key": asset.object_key})
        job.settings = {**settings, "manifest": snapshot}
        payload["snapshot"] = snapshot
        payload["text"] = ""
    task = await create_job(db, id, "compose", payload)
    project.export_settings = settings
    await finish_submit(db, bg)
    return {"exportJobId": job.id, "taskId": task.id, "status": "queued"}


@router.get("/exports/{id}")
async def get_export(id: str, db: DB):
    return await export_with_status(db, await require(db, ExportJob, id))


@router.get("/projects/{id}/exports")
async def list_exports(id: str, db: DB):
    await require(db, Project, id)
    rows = await db.scalars(
        select(ExportJob).where(ExportJob.project_id == id).order_by(ExportJob.created_at.desc()).limit(20)
    )
    return [await export_with_status(db, row) for row in rows]


async def export_with_status(db, row):
    out = export_out(row)
    manifest = row.settings.get("manifest")
    out["stale"] = False
    if manifest:
        p = await require(db, Project, row.project_id)
        scenes = await children(db, Scene, p.id)
        if row.settings.get("render_fingerprint"):
            from app.services.creative import render_fingerprint

            out["stale"] = row.settings["render_fingerprint"] != render_fingerprint(
                scenes, p.ratio, p.style, row.settings.get("source_mode") == "storyboard"
            )
            out["wholeAcceptanceCurrent"] = bool(row.settings.get("wholeAcceptance")) and not out["stale"]
            return out
        if row.settings.get("source_mode") == "storyboard":
            from app.services.creative import preview_fingerprint

            out["stale"] = row.settings.get("preview_fingerprint") != preview_fingerprint(scenes)
            return out
        current = {s.id: (s.creative or {}).get("revision") for s in scenes}
        used = {s["id"]: (s.get("creative") or {}).get("revision") for s in manifest["scenes"]}
        out["stale"] = current != used or (p.creative or {}).get("revision") != manifest["project_revision"]
    return out


@router.get("/scenes/{id}/video-quote")
async def scene_video_quote(id: str, db: DB):
    if not get_settings().feature_video_generation:
        raise AppError("FEATURE_DISABLED", "视频生成未启用", 403)
    scene = await require(db, Scene, id)
    inp = await scene_payload(db, scene, "video")
    from app.services.jobs import video_reservations, estimate_cost

    prior = await video_reservations(db, scene.project_id)
    active = list(
        await db.scalars(
            select(Task).where(
                Task.project_id == scene.project_id,
                Task.kind == "video",
                Task.status.in_(["queued", "running"]),
            )
        )
    )
    balance = await providers().video.balance()
    return {
        "sceneId": scene.id,
        "title": scene.title,
        "expected": (scene.creative or {}).get("version", 0),
        "duration": inp["duration_sec"],
        "points": inp["estimated_points"],
        "estimatedPoints": inp["estimated_points"],
        "inputMode": inp["input_mode"],
        "soundStrategy": inp["sound_strategy"],
        "model": inp["model"],
        "resolution": inp["resolution"],
        "prompt": inp["prompt"],
        "materials": [
            {k: v for k, v in m.items() if k != "key"} | {"url": providers().storage.url(m["key"])}
            for m in inp["materials"]
        ],
        "reservedPoints": sum(x.payload.get("estimated_points", 0) for x in active),
        "projectPointsUsed": sum(prior.values()),
        "pointsHardLimit": get_settings().video_points_hard_limit,
        "concurrencyLimit": get_settings().video_concurrency_limit,
        "previousVideoUrl": providers().storage.url((previous_video_take(scene) or {}).get("key")),
        "activeTasks": [task_out(x) for x in active if x.scene_id == scene.id],
        "estimateCents": estimate_cost("video", inp)
        if get_settings().cost_unit_price_json.get("videoPerSec", 0)
        else None,
        "warnings": ["本段修改会创建新的付费任务；原片和采用状态保留，新候选需回放后选用"],
        **balance,
    }


@router.get("/projects/{id}/video-quote")
async def video_quote(id: str, db: DB):
    if not get_settings().feature_video_generation:
        raise AppError("FEATURE_DISABLED", "视频生成未启用", 403)
    await require(db, Project, id)
    active = list(
        await db.scalars(
            select(Task).where(
                Task.project_id == id, Task.kind == "video", Task.status.in_(["queued", "running"])
            )
        )
    )
    active_scene_ids = {x.scene_id for x in active}
    items = []
    rejected = []
    for scene in await children(db, Scene, id):
        if scene.video_key or scene.id in active_scene_ids:
            continue
        try:
            inp = await scene_payload(db, scene, "video")
        except AppError as exc:
            rejected.append(
                {"sceneId": scene.id, "title": scene.title, "code": exc.code, "message": exc.message}
            )
            continue
        items.append(
            {
                "sceneId": scene.id,
                "title": scene.title,
                "duration": inp["duration_sec"],
                "points": inp["estimated_points"],
                "inputMode": inp["input_mode"],
                "resolution": inp["resolution"],
                "soundStrategy": inp["sound_strategy"],
                "prompt": inp["prompt"],
                "materials": [
                    {k: v for k, v in m.items() if k != "key"} | {"url": providers().storage.url(m["key"])}
                    for m in inp["materials"]
                ],
                "warnings": ["人物、场景与动作衔接须人工预览验收"],
            }
        )
    balance = await providers().video.balance()
    return {
        "activeTasks": len(active),
        "tasks": [task_out(x) for x in active],
        "rejected": rejected,
        "concurrencyLimit": get_settings().video_concurrency_limit,
        "reservedPoints": sum(x.payload.get("estimated_points", 0) for x in active),
        "pointsHardLimit": get_settings().video_points_hard_limit,
        "scenes": items,
        "estimatedPoints": sum(x["points"] for x in items),
        "resolution": get_settings().minimax_video_resolution,
        **balance,
    }


@router.post("/scenes/{id}/video-retake-quote")
async def retake_quote(id: str, body: VideoRetake, db: DB):
    from app.services.video import retake_payload
    scene = await require(db, Scene, id)
    p = await require(db, Project, scene.project_id)
    inp = await retake_payload(db, p, scene, body)
    balance = await providers().video.balance()
    return {"prompt": inp["prompt"], "points": inp["estimated_points"], "duration": inp["duration_sec"],
            "materials": [{k: v for k, v in m.items() if k != "key"} | {"url": providers().storage.url(m["key"])} for m in inp["materials"]], **balance}

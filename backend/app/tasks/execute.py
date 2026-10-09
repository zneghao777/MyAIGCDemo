import asyncio
import logging
import mimetypes
import base64
from datetime import timedelta
from sqlalchemy import select, delete
from redis import Redis
from app.worker import celery
from app.core.config import get_settings
from app.core.db import Session
from app.core.errors import Cancelled, AppError, TransientProviderError, safe_error
from app.core.events import publish, redis_client
from app.models import Task, Project, Scene, Character, ExportJob, Cleanup, now
from app.providers import providers
from app.providers.minimax import fetch_video as fetch_bytes
from app.services.resources import require, children, save_asset, scene_out, task_out, scene_values
from app.services.jobs import dispatch_pending
from app.services import script, tts, compose
from app.schemas import TextResult, DirectorData
from app.prompts import OPTIMIZE, CAMERA, LAYOUT

log = logging.getLogger("cineai.worker")


async def execute_job(task_id, celery_task=None):
    from app.core.provider_audit import current_task_id

    current_task_id.set(task_id)
    async with Session() as db:
        task = await db.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if not task or task.status in ("done", "cancelled", "failed"):
            return
        async with redis_client() as r:
            if await r.get(f"cineai:paused:{task.project_id}"):
                if celery_task:
                    raise celery_task.retry(countdown=3, max_retries=None)
                return
        task.status = "running"
        task.started_at = now()
        task.attempts += 1
        await db.commit()
        project_id = task.project_id

        async def checkpoint():
            async with Session() as check:
                row = await check.get(Task, task_id)
                if not row or row.status == "cancelled":
                    raise Cancelled()

        async def report(progress, message):
            await checkpoint()
            # Independent short transaction: publishing progress never commits partial scene/media changes.
            async with Session() as progress_db:
                row = await progress_db.get(Task, task_id)
                row.progress = progress
                row.logs = [*row.logs, {"progress": progress, "message": message}][-100:]
                if task.kind == "compose":
                    job = await progress_db.get(ExportJob, task.payload["export_id"])
                    if job:
                        job.progress = progress
                        job.status = "running"
                await progress_db.commit()
                await publish(project_id, "task", {**task_out(row), "message": message})
                if task.kind == "compose":
                    await publish(
                        project_id,
                        "export",
                        {"exportJobId": task.payload["export_id"], "stage": message, "progress": progress},
                    )
            if celery_task:
                celery_task.update_state(state="PROGRESS", meta={"progress": progress})

        try:
            await report(5, "任务开始")
            project = await require(db, Project, project_id)
            scene = await db.get(Scene, task.scene_id) if task.scene_id else None
            payload = task.payload
            result = {}
            if payload.get("creative"):
                from app.services.creative import execute_candidate

                result = await execute_candidate(db, task, checkpoint, report)
                task.provider = "creative:" + payload["creative"]["operation"]
            elif task.kind == "script":
                if payload.get("operation"):
                    operation = payload["operation"]
                    schema = DirectorData if operation == "stage-layout" else TextResult
                    prompt = {
                        "optimize-prompt": OPTIMIZE,
                        "camera-description": CAMERA,
                        "stage-layout": LAYOUT,
                    }[operation]
                    output = await providers().llm.structured(schema, prompt, payload)
                    result = output.model_dump(by_alias=True)
                    task.provider = "deepseek"
                else:
                    outline, generated = await script.generate(payload, report)
                    await checkpoint()
                    await db.execute(delete(Scene).where(Scene.project_id == project_id))
                    for i, spec in enumerate(generated):
                        values = scene_values(spec, exclude={"id"}, exclude_none=True)
                        db.add(Scene(project_id=project_id, order_index=i, **values))
                    if not await children(db, Character, project_id):
                        for character in outline.get("characters", []):
                            db.add(
                                Character(
                                    project_id=project_id,
                                    name=character["name"][:50],
                                    age=character.get("age", "")[:8],
                                    description=character.get("persona", "")[:1000],
                                    clothing=character.get("clothing", "")[:500],
                                )
                            )
                    project.outline = outline
                    project.status = "剪辑中"
                    task.provider = "deepseek"
                    result = {"sceneCount": len(generated)}
            elif task.kind == "image":
                refs = [await providers().storage.get(key) for key in payload["references"]]
                if len(refs) < 2:
                    previous = await db.scalar(
                        select(Scene)
                        .where(
                            Scene.project_id == project_id,
                            Scene.order_index < scene.order_index,
                            Scene.first_frame_key.is_not(None),
                        )
                        .order_by(Scene.order_index.desc())
                        .limit(1)
                    )
                    if previous:
                        refs.append(await providers().storage.get(previous.first_frame_key))
                await report(20, "生成首帧图")
                raw, logs = await providers().image.generate(
                    payload["prompt"], payload["ratio"], payload["quality"], refs
                )
                await checkpoint()
                asset = await save_asset(
                    db, project_id, "first-frame", raw, "image/png", "png", f"scenes/{scene.id}/frames"
                )
                scene.first_frame_key = asset.object_key
                scene.video_key = None
                scene.status = "image_ready"
                scene.last_error = None
                project.cover_key = project.cover_key or asset.object_key
                task.provider = "gpt-image"
                result = {"assetId": asset.id}
                task.logs = [*task.logs, *logs]
            elif task.kind == "tts":
                task.provider = get_settings().tts_provider + "-tts"
                if scene:
                    raise AppError("LEGACY_BINDING_REQUIRED", "旧分镜需先明确发言人，不自动选取角色音色", 409)
                else:
                    raw, duration = await tts.synthesize(payload["text"], payload["voice_id"], checkpoint)
                    await checkpoint()
                    asset = await save_asset(
                        db, project_id, "voice-preview", raw, "audio/mpeg", "mp3", duration_ms=duration
                    )
                    result = {"assetId": asset.id, "durationMs": duration}
            elif task.kind == "video":
                from app.services import video_capacity
                from app.services import video as video_service
                from app.services import video_dependency

                identity = payload.get("submission_id") or task.id
                await db.commit()  # Never hold a row lock while remote generation runs.
                payload = await video_dependency.prepare(db, task, scene, payload, checkpoint)
                await video_capacity.acquire(identity)
                if not task.provider_task_id:
                    raw_materials = []
                    for material in payload.get("materials", ([{"key": payload["first_frame_key"], "kind": "image", "role": "first_frame"}] if payload.get("first_frame_key") else [])):
                        raw = await providers().storage.get(material["key"])
                        limit = {"image": 30, "video": 50, "audio": 15}[material["kind"]]
                        if len(raw) > limit * 1024 * 1024:
                            raise AppError("PAYLOAD_TOO_LARGE", f"H3 单个素材上限 {limit} MiB", 413)
                        mime = (
                            material.get("content_type")
                            or mimetypes.guess_type(material["key"])[0]
                            or "image/png"
                        )
                        external_url = f"data:{mime};base64," + base64.b64encode(raw).decode()
                        kind = material["kind"] + "_url"
                        raw_materials.append(
                            {"type": kind, kind: {"url": external_url}, "role": material["role"]}
                        )
                    await checkpoint()
                    task.result = {**(task.result or {}), "submissionStartedAt": now().isoformat()}
                    await db.commit()
                    await video_capacity.reserve(identity, payload["estimated_points"], providers().video)
                    await checkpoint()
                    task.result = {
                        **(task.result or {}),
                        "postAttemptedAt": now().isoformat(),
                        "submissionRejected": False,
                    }
                    await db.commit()
                    task.provider_task_id = await providers().video.create(
                        payload["video_prompt"] or payload["prompt"],
                        raw_materials[0].get("image_url", {}).get("url") if raw_materials else None,
                        payload["duration_sec"],
                        payload["ratio"],
                        idempotency_key="cineai-video-" + identity,
                        resolution=payload.get("resolution"),
                        model=payload.get("model"),
                        materials=raw_materials,
                        mute_audio=payload.get("mute_audio", True),
                        use_context_ir=payload.get("use_context_ir", False),
                        balance_checked=True,
                    )
                    task.result = {
                        **(task.result or {}),
                        "providerSubmittedAt": now().isoformat(),
                        "providerTaskId": task.provider_task_id,
                    }
                    await db.commit()
                    await video_capacity.acknowledge(identity)
                task.provider = "minimax-video"
                for i in range(max(1, 600_000 // get_settings().minimax_video_poll_interval_ms)):
                    await checkpoint()
                    await video_capacity.acquire(identity)  # Renew the account-wide lease.
                    status = await providers().video.query(task.provider_task_id)
                    state = str(status.get("status", "")).lower()
                    if state in ("success", "done", "succeeded"):
                        task.result = {
                            **(task.result or {}),
                            "providerCompletedAt": now().isoformat(),
                            "providerOutput": status,
                        }
                        await db.commit()  # Persist remote completion even if local download fails.
                        await video_capacity.release(identity)
                        url = status.get("fileUrl") or status.get("video_url") or status.get("download_url")
                        if not url:
                            raise AppError("PROVIDER_OUTPUT_INVALID", "视频任务成功但缺少下载地址", 422)
                        raw = await fetch_bytes(url)
                        break
                    if state in ("failed", "fail", "cancelled"):
                        await video_capacity.release(identity)
                        raise AppError("PROVIDER_ERROR", "视频生成失败", 502)
                    await report(min(90, 10 + i // 2), "等待视频生成")
                    await asyncio.sleep(get_settings().minimax_video_poll_interval_ms / 1000)
                else:
                    raise TransientProviderError("PROVIDER_TIMEOUT", "视频生成超时；保留远端任务供恢复", 504)
                await checkpoint()
                asset = await save_asset(
                    db, project_id, "video", raw, "video/mp4", "mp4", f"scenes/{scene.id}/video"
                )
                from app.services.locking import locked_scene

                project, scene = await locked_scene(db, scene.id, check_idle=False)
                try:
                    source_current = payload.get("video_source") == await video_service.current_source(db, scene, project.ratio)
                except AppError:
                    source_current = False
                # Preserve every paid result, even if the design changed during generation.
                import tempfile
                from pathlib import Path
                from app.services.media import probe_video
                structured = bool((scene.creative or {}).get("shot"))
                measured = {}
                if structured:
                    with tempfile.TemporaryDirectory() as folder:
                        path = Path(folder) / "take.mp4"
                        path.write_bytes(raw)
                        measured = await probe_video(path)
                    asset.duration_ms = round(measured["duration"] * 1000)
                    asset.width, asset.height = measured["width"], measured["height"]
                else:
                    scene.video_key = asset.object_key
                scene.status = "done"
                trace = {
                    "key": asset.object_key,
                    "asset_id": asset.id,
                    **measured,
                    "stale_at_completion": not source_current,
                    "generation_source": payload["video_source"],
                    "source": payload["video_source"],
                    "provider_task_id": task.provider_task_id,
                    "model": payload["model"],
                    "resolution": status.get("resolution"),
                    "usage": status.get("usage", {}),
                    "materials": payload.get("materials", []),
                    "prompt": payload["prompt"],
                    "input_mode": payload.get("input_mode", "first_frame"),
                    "sound_strategy": payload.get("sound_strategy", "post_audio"),
                    "take": task.id,
                    "parameters": {
                        k: payload.get(k)
                        for k in ("duration_sec", "ratio", "resolution", "mute_audio", "use_context_ir")
                    },
                    "raw_output": status,
                    "post_processing": [],
                    "accepted": False,
                    "retake": {
                        k: v
                        for k, v in (payload.get("retake") or {}).items()
                        if k in ("nonce", "reason", "previous_video_key", "preserve", "source_asset_id", "modify")
                    },
                }
                if scene.creative:
                    from app.services.creative import save_state

                    takes = [*(scene.creative.get("video_takes") or [])]
                    previous = (payload.get("retake") or {}).get("previous_take")
                    if previous and not any(x.get("key") == previous.get("key") for x in takes):
                        takes.append(previous)

                    await save_state(
                        db,
                        scene,
                        {
                            **scene.creative,
                            **({"video": trace} if not structured else {}),
                            "video_takes": [*takes, trace],
                        },
                        "scene",
                    )
                result = {
                    **(task.result or {}),
                    "assetId": asset.id,
                    "estimatedPoints": payload.get("estimated_points"),
                    "providerTaskId": task.provider_task_id,
                    "usage": status.get("usage", {}),
                    "inputMode": payload.get("input_mode", "first_frame"),
                    "materials": payload.get("materials", []),
                    "prompt": payload["prompt"],
                }
            elif task.kind == "compose":
                job = await require(db, ExportJob, payload["export_id"])
                scenes = await children(db, Scene, project_id)
                if not scenes:
                    raise AppError("FIRST_FRAME_REQUIRED", "项目没有分镜", 409)
                if payload.get("snapshot"):
                    from types import SimpleNamespace

                    scenes = [SimpleNamespace(**x) for x in payload["snapshot"]["scenes"]]
                    render_project = SimpleNamespace(ratio=payload["snapshot"]["ratio"])
                else:
                    render_project = project
                    if any(
                        (sc.dialogue and not sc.audio_key) or (sc.narration and not sc.narration_key)
                        for sc in scenes
                    ):
                        raise AppError(
                            "LEGACY_BINDING_REQUIRED", "旧分镜缺少发言人绑定，不能自动猜测声音", 409
                        )
                raw, cover, ass, duration, logs = await compose.compose(
                    render_project, scenes, job.settings, checkpoint, report
                )
                await checkpoint()
                webm = job.settings["format"] == "WebM"
                output = await save_asset(
                    db,
                    project_id,
                    "export",
                    raw,
                    "video/webm" if webm else "video/mp4",
                    "webm" if webm else "mp4",
                    f"exports/{job.id}",
                    round(duration * 1000),
                )
                cover_asset = await save_asset(
                    db, project_id, "cover", cover, "image/png", "png", f"exports/{job.id}"
                )
                sub_asset = await save_asset(
                    db, project_id, "subtitle", ass, "text/plain", "ass", f"exports/{job.id}"
                )
                job.output_key = output.object_key
                job.cover_key = cover_asset.object_key
                job.subtitle_key = sub_asset.object_key
                job.duration_sec = duration
                job.logs = logs
                manifest = job.settings.get("manifest") or {}
                job.settings = {
                    **job.settings,
                    "renderLog": logs,
                    "manualAcceptance": manifest.get("manualAcceptance", False),
                }
                job.status = "done"
                job.progress = 100
                job.finished_at = now()
                await db.refresh(project)
                snapshot_current = True
                if payload.get("snapshot"):
                    current_scenes = await children(db, Scene, project_id)
                    snapshot_current = {x.id: (x.creative or {}).get("revision") for x in current_scenes} == {
                        x["id"]: (x.get("creative") or {}).get("revision")
                        for x in payload["snapshot"]["scenes"]
                    }
                if snapshot_current and (
                    not payload.get("snapshot")
                    or project.creative["revision"] == payload["snapshot"]["project_revision"]
                ):
                    project.cover_key = cover_asset.object_key
                    if job.settings.get("purpose") != "preview":
                        project.status = "已导出"
                task.provider = "ffmpeg"
                result = {"exportJobId": job.id}
            # Lock current task row before committing assets; cancellation wins if already committed.
            fresh = await db.scalar(
                select(Task)
                .where(Task.id == task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not fresh or fresh.status == "cancelled":
                raise Cancelled()
            fresh.status = "done"
            fresh.progress = 100
            fresh.finished_at = now()
            fresh.result = result
            fresh.cost_cents = fresh.estimated_cost_cents
            fresh.error = None
            project.updated_at = now()
            await db.commit()
            await publish(project_id, "task", task_out(fresh))
            if scene:
                await publish(project_id, "scene", scene_out(scene))
            else:
                await publish(project_id, "project", {"id": project_id})
        except (Exception, asyncio.CancelledError) as exc:
            uploaded_keys = db.info.get("uploaded_keys", [])
            await db.rollback()
            async with Session() as failures:
                row = await failures.get(Task, task_id)
                if not row or row.status == "done":
                    return
                if uploaded_keys:
                    failures.add(Cleanup(keys=uploaded_keys))
                cancelled = isinstance(exc, (Cancelled, asyncio.CancelledError)) or row.status == "cancelled"
                from app.services.video_capacity import CapacityPending

                capacity_wait = isinstance(exc, CapacityPending)
                retry = capacity_wait or (
                    not row.payload.get("creative")
                    and isinstance(exc, TransientProviderError)
                    and row.attempts < (3 if row.kind == "image" else 4)
                )
                if (
                    row.kind == "video"
                    and not row.provider_task_id
                    and isinstance(exc, AppError)
                    and (
                        exc.details.get("status") == 429
                        or 400 <= exc.details.get("status", 0) < 500
                        or exc.code in ("PROVIDER_BALANCE_LOW", "PAYLOAD_TOO_LARGE", "INVALID_VIDEO_INPUT")
                    )
                ):
                    from app.services import video_capacity

                    identity = row.payload.get("submission_id") or row.id
                    await video_capacity.reject_reservation(identity)
                    await video_capacity.release(identity)
                    row.result = {**(row.result or {}), "submissionRejected": True}
                if (
                    row.kind == "video"
                    and cancelled
                    and not row.provider_task_id
                    and not (row.result or {}).get("postAttemptedAt")
                ):
                    from app.services import video_capacity

                    identity = row.payload.get("submission_id") or row.id
                    await video_capacity.reject_reservation(identity)
                    await video_capacity.release(identity)
                if capacity_wait:
                    row.attempts = max(0, row.attempts - 1)
                row.status = "cancelled" if cancelled else "queued" if retry else "failed"
                row.error = None if cancelled or capacity_wait else safe_error(exc)
                row.finished_at = None if retry else now()
                if retry:
                    row.dispatched_at = None
                    delay = 3 if capacity_wait else min(60, 2**row.attempts)
                    if isinstance(exc, AppError):
                        try:
                            delay = max(delay, min(300, int(exc.details.get("retry_after") or 0)))
                        except (TypeError, ValueError):
                            pass
                    row.available_at = now() + timedelta(seconds=delay)
                if row.scene_id:
                    sc = await failures.get(Scene, row.scene_id)
                    if sc:
                        if row.kind in ("image", "video"):
                            sc.status = (
                                ("image_ready" if sc.first_frame_key else "draft")
                                if cancelled
                                else (f"{row.kind}_pending" if retry else "failed")
                            )
                        sc.last_error = row.error
                if row.kind == "compose":
                    job = await failures.get(ExportJob, row.payload["export_id"])
                    if job:
                        job.status = row.status
                        job.error = row.error
                await failures.commit()
                await publish(project_id, "task", task_out(row))
            log.error(
                "task_failed",
                extra={"task_id": task_id, "project_id": project_id, "error_type": type(exc).__name__},
            )


@celery.task(bind=True, name="cineai.execute", soft_time_limit=920, time_limit=950)
def execute(self, task_id):
    # Same Celery task_id does not provide deduplication. Redis lock fences redelivery explicitly.
    client = Redis.from_url(get_settings().redis_url)
    lock = client.lock(f"cineai:execution:{task_id}", timeout=1000, blocking=False)
    if not lock.acquire():
        return
    try:
        asyncio.run(execute_job(task_id, self))
    finally:
        try:
            lock.release()
        except Exception:
            pass
        client.close()


@celery.task(name="cineai.dispatch")
def dispatch():
    async def run():
        # Re-deliver jobs committed as dispatched but never started (worker startup/crash).
        # Redis execution lock and task row state still fence duplicate deliveries.
        async with Session() as pending_db:
            pending = await pending_db.scalars(
                select(Task).where(
                    Task.status == "queued", Task.dispatched_at < now() - timedelta(seconds=60)
                )
            )
            for item in pending:
                item.dispatched_at = None
            await pending_db.commit()
        # Recover executions left running after a worker crash/hard timeout.
        async with Session() as db:
            rows = await db.scalars(
                select(Task).where(
                    Task.status == "running", Task.started_at < now() - timedelta(seconds=1000)
                )
            )
            for row in rows:
                recoverable_video = row.kind == "video"
                row.status = "queued" if recoverable_video else "failed"
                row.error = (
                    "Worker 中断，恢复原 H3 任务" if recoverable_video else "Worker 中断或执行超时，可重试"
                )
                row.finished_at = None if recoverable_video else now()
                if recoverable_video:
                    row.dispatched_at = None
                    row.available_at = now()
                if row.scene_id:
                    scene = await db.get(Scene, row.scene_id)
                    if scene:
                        scene.last_error = row.error
                        if row.kind in ("image", "video"):
                            scene.status = "video_pending" if recoverable_video else "failed"
                if row.kind == "compose":
                    job = await db.get(ExportJob, row.payload["export_id"])
                    if job:
                        job.status = "failed"
                        job.error = row.error
            await db.commit()
        await dispatch_pending()

    asyncio.run(run())


@celery.task(name="cineai.cleanup")
def cleanup():
    async def run():
        async with Session() as db:
            for item in await db.scalars(select(Cleanup).limit(20)):
                for key in item.keys:
                    await providers().storage.delete(key)
                await db.delete(item)
            await db.commit()

    asyncio.run(run())


@celery.task(name="cineai.cleanup_external_media")
def cleanup_external_media():
    try:
        asyncio.run(providers().external_media.cleanup())
        log.info("external_media_cleanup_done")
    except Exception as exc:
        log.warning("external_media_cleanup_failed", extra={"error_type": type(exc).__name__})
        raise AppError("EXTERNAL_MEDIA_CLEANUP_FAILED", "七牛临时素材清理失败", 502) from None

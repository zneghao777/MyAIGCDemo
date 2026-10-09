import hashlib
import json
import math
from sqlalchemy import select, func, or_
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Task, Project, Scene, Character, Asset
from .resources import require, children


def estimate_cost(kind, payload):
    prices = get_settings().cost_unit_price_json
    if kind == "image":
        value = prices.get("imagePerCall", 0) * payload.get("billable_calls", 1)
    elif kind in ("tts", "compose"):
        value = (
            len(payload.get("dialogue", "") + payload.get("narration", "") + payload.get("text", ""))
            / 1000
            * prices.get("ttsPerKChar", 0)
        )
    elif kind == "video":
        value = payload.get("duration_sec", 5) * prices.get("videoPerSec", 0)
    elif kind == "script":
        value = (payload.get("scene_count", 12) * 800 + 2000) / 1_000_000 * prices.get("llmPerMToken", 0)
    else:
        value = 0
    return math.ceil(value)


async def video_reservations(db, project_id):
    """Cumulative paid/reserved points, one entry for each stable paid identity."""
    prior = list(
        (await db.scalars(select(Task).where(Task.project_id == project_id, Task.kind == "video"))).all()
    )
    reservations = {}
    for item in prior:
        if (
            item.status in ("queued", "running", "done")
            or item.provider_task_id
            or (
                (item.result or {}).get("postAttemptedAt")
                and not (item.result or {}).get("submissionRejected")
            )
        ):
            identity = item.payload.get("submission_id") or item.id
            reservations[identity] = item.payload.get("estimated_points", 0)
    return reservations


def previous_video_take(scene):
    """Selected input edits can clear video_key while retaining the paid take."""
    state = scene.creative or {}
    takes = [state.get("video") or {}, *reversed(state.get("video_takes") or [])]
    if scene.video_key:
        return next((x for x in takes if x.get("key") == scene.video_key), {"key": scene.video_key})
    return next((x for x in takes if x.get("key")), None)


async def create_job(db, project_id, kind, payload, scene_id=None):
    # Project row lock serializes all submitters, including budget reservations and retries.
    await require(db, Project, project_id, lock=True)
    if kind == "video" and not get_settings().feature_video_generation:
        raise AppError("FEATURE_DISABLED", "AI 视频生成未启用，可直接导出分镜动态预演", 403)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if any(word and word in text for word in get_settings().sensitive_words.split(",")):
        raise AppError("CONTENT_REJECTED", "输入包含已配置的禁止词", 422)
    dedupe = hashlib.sha256(f"{project_id}|{scene_id}|{kind}|{text}".encode()).hexdigest()
    existing = await db.scalar(
        select(Task)
        .where(Task.dedupe_key == dedupe, Task.status.in_(["done", "queued", "running"]))
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    if existing:
        # Repeated batches recover observation of the same queued/running task.
        if existing.status != "done" and scene_id and kind != "video":
            raise AppError("SCENE_HAS_RUNNING_TASK", "该分镜已有同类任务", 409)
        if existing.status == "done" and scene_id and existing.result:
            scene = await require(db, Scene, scene_id)
            if kind == "image" and existing.result.get("assetId"):
                asset = await db.get(Asset, existing.result["assetId"])
                if asset:
                    scene.first_frame_key = asset.object_key
                    scene.video_key = None
                    scene.status = "image_ready"
            elif kind == "tts":
                scene.audio_key = existing.result.get("audioKey")
                scene.narration_key = existing.result.get("narrationKey")
                scene.audio_duration_ms = existing.result.get("durationMs", 0)
        return existing
    if kind == "video" and not payload.get("submission_id"):
        failed = await db.scalar(
            select(Task.id)
            .where(Task.dedupe_key == dedupe, Task.status.in_(["failed", "cancelled"]))
            .limit(1)
        )
        if failed:
            raise AppError(
                "VIDEO_RETRY_REQUIRED",
                "该镜头已有失败或中断任务，请在队列中重试以复用原任务，避免重复扣费",
                409,
            )
    if scene_id and await db.scalar(
        select(Task.id).where(
            Task.scene_id == scene_id, Task.kind == kind, Task.status.in_(["queued", "running"])
        )
    ):
        raise AppError("SCENE_HAS_RUNNING_TASK", "该分镜已有同类任务", 409)
    costs = (
        await db.execute(
            select(
                func.coalesce(func.sum(Task.cost_cents), 0),
                func.coalesce(
                    func.sum(Task.estimated_cost_cents).filter(Task.status.in_(["queued", "running"])), 0
                ),
            ).where(Task.project_id == project_id)
        )
    ).one()
    estimate = estimate_cost(kind, payload)
    if sum(costs) + estimate > get_settings().cost_hard_limit_cents:
        raise AppError("COST_LIMIT_EXCEEDED", "超过项目成本硬上限（含排队任务预留）", 402)
    if kind == "video":
        # This remains within the short project-row transaction. Paid identities
        # are counted once even when a retry gets a new local Celery task ID.
        reservations = await video_reservations(db, project_id)
        identity = payload.get("submission_id")
        added = 0 if identity in reservations else payload.get("estimated_points", 0)
        if sum(reservations.values()) + added > get_settings().video_points_hard_limit:
            raise AppError("VIDEO_POINTS_LIMIT", "超过项目 H3 积分硬上限（包含运行任务与已支付任务）", 402)
    row = Task(
        project_id=project_id,
        scene_id=scene_id,
        kind=kind,
        dedupe_key=dedupe,
        payload=payload,
        estimated_cost_cents=estimate,
    )
    db.add(row)
    await db.flush()
    if scene_id:
        scene = await require(db, Scene, scene_id)
        if kind in ("image", "video"):
            scene.status = f"{kind}_pending"
    return row


async def scene_payload(db, scene, kind):
    project = await require(db, Project, scene.project_id)
    if kind == "video":
        from .video import payload

        return await payload(db, project, scene)
    chars = await children(db, Character, project.id)
    from app.prompts import STYLE_PRESETS, EXCLUSIONS

    s = get_settings()
    return {
        "title": scene.title,
        "dialogue": scene.dialogue,
        "narration": scene.narration,
        "prompt": STYLE_PRESETS.get(project.style, project.style)
        + "。"
        + scene.image_prompt
        + "。"
        + EXCLUSIONS,
        "video_prompt": scene.video_prompt,
        "camera_move": scene.camera_move,
        "director_data": scene.director_data,
        "duration_sec": scene.duration_sec,
        "ratio": project.ratio,
        "model": s.image_model if kind == "image" else s.tts_model,
        "quality": "low" if scene.model == "turbo" else s.image_quality,
        "seed": scene.seed,
        "first_frame_key": scene.first_frame_key if kind == "video" else None,
        "references": [c.image_key for c in chars if c.image_key][:2],
        "voice_id": s.tts_voice_id,
    }


async def dispatch_pending():
    # Durable DB outbox: commit first, dispatch later. Beat retries broker failures.
    from app.core.db import Session
    from app.worker import celery
    from app.models import now
    import asyncio

    async with Session() as db:
        rows = list(
            (
                await db.scalars(
                    select(Task)
                    .where(
                        Task.status == "queued",
                        Task.dispatched_at.is_(None),
                        or_(Task.available_at.is_(None), Task.available_at <= now()),
                    )
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
            ).all()
        )
        for row in rows:
            try:
                await asyncio.to_thread(
                    celery.send_task,
                    "cineai.execute",
                    args=[row.id],
                    task_id=row.id,
                    queue="cineai." + row.kind,
                )
            except Exception:
                import logging

                logging.getLogger("cineai.outbox").warning("broker_unavailable", extra={"task_id": row.id})
                break
            row.dispatched_at = now()
        await db.commit()

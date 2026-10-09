import asyncio
import shutil
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text, select, func
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST
from app.api.routers.resources import DB
from app.core.config import get_settings
from app.core.events import redis_client
from app.providers import providers
from app.models import Task

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(db: DB):
    checks = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
    try:
        async with redis_client() as r:
            await r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
    checks["ffmpeg"] = "ok" if shutil.which(get_settings().ffmpeg_path) else "unavailable"
    try:
        await asyncio.wait_for(providers().storage.health(), 10)
        checks["local_media"] = "ok"
    except Exception:
        checks["local_media"] = "unavailable"
    return JSONResponse(
        {"status": "ok" if all(v == "ok" for v in checks.values()) else "degraded", "checks": checks},
        status_code=200 if all(v == "ok" for v in checks.values()) else 503,
    )


@router.get("/metrics")
async def metrics(db: DB):
    registry = CollectorRegistry()
    gauge = Gauge("cineai_tasks", "Persisted task counts", ["kind", "status"], registry=registry)
    for kind, status, count in await db.execute(
        select(Task.kind, Task.status, func.count()).group_by(Task.kind, Task.status)
    ):
        gauge.labels(kind, status).set(count)
    cost = Gauge("cineai_cost_estimated_cents", "Estimated accounted cost", registry=registry)
    cost.set(await db.scalar(select(func.coalesce(func.sum(Task.cost_cents), 0))))
    durations = Gauge(
        "cineai_task_duration_seconds",
        "Persisted completed task durations",
        ["kind", "quantile"],
        registry=registry,
    )
    success = Gauge("cineai_task_success_ratio", "Completed task success ratio", ["kind"], registry=registry)
    failures = Gauge("cineai_provider_failed_tasks", "Failed provider tasks", ["provider"], registry=registry)
    from collections import defaultdict

    by_kind = defaultdict(list)
    outcomes = defaultdict(list)
    for row in await db.scalars(select(Task).where(Task.status.in_(["done", "failed"]))):
        outcomes[row.kind].append(row.status == "done")
        if row.started_at and row.finished_at:
            by_kind[row.kind].append(max(0, (row.finished_at - row.started_at).total_seconds()))
    for kind, values in by_kind.items():
        values.sort()
        durations.labels(kind, "0.95").set(values[min(len(values) - 1, int(len(values) * 0.95))])
    for kind, values in outcomes.items():
        success.labels(kind).set(sum(values) / len(values))
    for provider, count in await db.execute(
        select(Task.provider, func.count()).where(Task.status == "failed").group_by(Task.provider)
    ):
        failures.labels(provider or "unknown").set(count)
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

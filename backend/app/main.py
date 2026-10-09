import time
import re
from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from app.core.logging import configure_logging
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import AppError
from app.core.events import redis_client
from app.api.routers import resources, jobs, assets, events, health, creative, media, production

configure_logging()
structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()]
)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app):
    yield
    await engine.dispose()


app = FastAPI(title="CineAI Studio API", version="0.1.0", lifespan=lifespan)
s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in s.api_cors_origins.split(",")],
    allow_methods=["GET", "HEAD", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Accept", "Range", "If-Range", "If-None-Match", "If-Modified-Since"],
    expose_headers=["X-Next-Cursor", "Accept-Ranges", "Content-Range", "Content-Length", "ETag"],
)


@app.exception_handler(AppError)
async def app_error(request, exc):
    return JSONResponse(
        {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": {k: v for k, v in exc.details.items() if k != "stderr"},
            }
        },
        status_code=exc.status,
    )


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(request, exc):
    errors = [{"loc": list(e["loc"]), "type": e["type"], "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        {"error": {"code": "VALIDATION_ERROR", "message": "请求字段不合法", "details": {"fields": errors}}},
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(
        {"error": {"code": "RESOURCE_CONFLICT", "message": "资源冲突或重复提交", "details": {}}},
        status_code=409,
    )


@app.exception_handler(Exception)
async def unknown(request, exc):
    log.error("request_failed", error_type=type(exc).__name__, path=request.url.path)
    return JSONResponse(
        {"error": {"code": "INTERNAL_ERROR", "message": "服务暂不可用，请检查配置与依赖", "details": {}}},
        status_code=500,
    )


@app.middleware("http")
async def limit(request: Request, call_next):
    if (
        request.url.path.startswith("/api")
        and request.method != "OPTIONS"
        and not request.url.path.endswith(("/health", "/metrics", "/events"))
    ):
        ip = request.client.host if request.client else "unknown"
        project = re.search(r"/projects/([^/]+)", request.url.path)
        scope = project.group(1) if project else "global"
        minute = int(time.time() / 60)
        generation = request.method == "POST" and any(
            part in request.url.path for part in ("/tasks", "/generate", "/tts", "/ai/", "/exports")
        )
        cap = min(30, s.api_rate_limit_per_min) if generation else s.api_rate_limit_per_min
        try:
            async with redis_client() as redis:
                value = await redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],65) end; return n",
                    1,
                    f"cineai:rate:{ip}:{scope}:{generation}:{minute}",
                )
            if value > cap:
                return JSONResponse(
                    {"error": {"code": "RATE_LIMITED", "message": "请求过于频繁", "details": {}}},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        except Exception:
            return JSONResponse(
                {"error": {"code": "REDIS_UNAVAILABLE", "message": "Redis 不可用", "details": {}}},
                status_code=503,
            )
    from app.services.workbench import creation_event
    from app.models import uid

    token = creation_event.set({"id": uid(), "action": request.url.path, "method": request.method})
    try:
        return await call_next(request)
    finally:
        creation_event.reset(token)


for router in (
    resources.router,
    creative.router,
    jobs.router,
    assets.router,
    events.router,
    health.router,
    media.router,
):
    app.include_router(router)

app.include_router(production.router)

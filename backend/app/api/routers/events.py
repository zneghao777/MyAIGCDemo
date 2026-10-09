import asyncio
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.api.routers.resources import DB
from app.core.events import redis_client
from app.core.errors import AppError
from app.models import Project
from app.services.resources import require

router = APIRouter(prefix="/api")


async def stream_response(id, request, task_id=None):
    redis = redis_client()
    key = f"cineai:sse:{id}"
    # Atomic expiring leases avoid leaked connection counts after API restarts.
    token = __import__("uuid").uuid4().hex
    count = await redis.eval(
        "redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',ARGV[1]); if redis.call('ZCARD',KEYS[1])>=5 then return 0 end; redis.call('ZADD',KEYS[1],ARGV[2],ARGV[3]); redis.call('EXPIRE',KEYS[1],60); return 1",
        1,
        key,
        time.time(),
        time.time() + 45,
        token,
    )
    if not count:
        await redis.aclose()
        raise AppError("RATE_LIMITED", "当前项目 SSE 连接过多", 429)

    async def events():
        try:
            async with redis.pubsub() as pubsub:
                await pubsub.subscribe(f"cineai:project:{id}:events")
                yield "retry: 3000\nevent: connected\ndata: {}\n\n"
                last = time.monotonic()
                while not await request.is_disconnected():
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                    if message:
                        event = json.loads(message["data"])
                        yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                        if (
                            task_id
                            and event["event"] == "task"
                            and event["data"]["id"] == task_id
                            and event["data"]["status"] in ("done", "failed", "cancelled")
                        ):
                            break
                    if time.monotonic() - last >= 15:
                        await redis.zadd(key, {token: time.time() + 45})
                        await redis.expire(key, 60)
                        yield f'event: ping\ndata: {{"ts":{int(time.time() * 1000)}}}\n\n'
                        last = time.monotonic()
                    await asyncio.sleep(0.05)
        finally:
            await redis.zrem(key, token)
            await redis.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/projects/{id}/events")
async def events(id: str, request: Request, db: DB):
    await require(db, Project, id)
    await db.rollback()  # Do not hold a PostgreSQL transaction for the lifetime of SSE.
    return await stream_response(id, request)

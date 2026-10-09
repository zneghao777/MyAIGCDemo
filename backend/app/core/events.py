import json
from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis
from app.core.config import get_settings


def redis_client():
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def publish(project_id, event, data):
    async with redis_client() as r:
        await r.publish(
            f"cineai:project:{project_id}:events",
            json.dumps({"event": event, "data": jsonable_encoder(data)}, ensure_ascii=False),
        )

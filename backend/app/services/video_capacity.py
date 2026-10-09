"""Account-wide H3 admission. Redis operations are short; generation holds no lock."""

import hashlib
import json
import time

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.events import redis_client


class CapacityPending(AppError):
    def __init__(self):
        super().__init__("VIDEO_CAPACITY_PENDING", "等待 H3 并发名额", 409)


def account_key():
    s = get_settings()
    identity = s.minimax_video_base_url + "|" + s.minimax_video_api_key.get_secret_value()
    return "cineai:h3:" + hashlib.sha256(identity.encode()).hexdigest()[:24]


ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZSCORE', KEYS[1], ARGV[4]) or redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[3]) then
  redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[5]))
  return 1
end
return 0
"""


async def acquire(identity):
    s = get_settings()
    async with redis_client() as r:
        permitted = await r.eval(
            ACQUIRE,
            1,
            account_key() + ":active",
            time.time(),
            time.time() + s.video_lease_seconds,
            s.video_concurrency_limit,
            identity,
            s.video_lease_seconds * 2,
        )
    if not permitted:
        raise CapacityPending()


async def release(identity):
    async with redis_client() as r:
        await r.zrem(account_key() + ":active", identity)


async def reserve(identity, points, provider):
    """A fresh balance plus in-flight POST reservations prevents concurrent overspend.

    Acknowledgements newer than the balance-read start are also counted, because
    that read may precede the provider's debit. Completed old acknowledgements are
    reconciled against the fresh balance. No remote generation is inside this lock.
    """
    key = account_key() + ":budget"
    async with redis_client() as r:
        async with r.lock(key + ":lock", timeout=30, blocking_timeout=30):
            snapshot_start = time.time()
            balance = (await provider.balance())["available_points"]
            entries = await r.hgetall(key)
            current = json.loads(entries[identity]) if identity in entries else None
            if current:
                return balance  # Same paid identity: reuse the reservation and Idempotency-Key.
            reserved = 0
            for entry in entries.values():
                item = json.loads(entry)
                if not item.get("ack_at") or item["ack_at"] >= snapshot_start:
                    reserved += item["points"]
            if balance - reserved < points:
                raise AppError(
                    "PROVIDER_BALANCE_LOW",
                    f"H3 可用积分不足（余额 {balance:g}，并发预留 {reserved:g}，本镜 {points:g}）",
                    402,
                )
            await r.hset(key, identity, json.dumps({"points": points, "reserved_at": time.time()}))
            # Outstanding uncertain submissions are retained for explicit recovery.
            return balance


async def acknowledge(identity):
    key = account_key() + ":budget"
    async with redis_client() as r:
        value = await r.hget(key, identity)
        if value:
            item = json.loads(value)
            item["ack_at"] = time.time()
            await r.hset(key, identity, json.dumps(item))


async def reject_reservation(identity):
    """Only definite rejections (e.g. 429 / 4xx) release uncharged reservations."""
    async with redis_client() as r:
        await r.hdel(account_key() + ":budget", identity)

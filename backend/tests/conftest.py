import os

os.environ["TESTING"] = "true"
os.environ["FEATURE_VIDEO_GENERATION"] = "false"
# Legacy workflow regressions use their original provider; MiMo tests opt in explicitly.
os.environ["TTS_PROVIDER"] = "minimax"
os.environ["DATABASE_URL"] = os.environ.get(
    "CINEAI_TEST_DATABASE_URL", "postgresql+asyncpg://zenghao@127.0.0.1:5432/cineai_test"
)
os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/5"
os.environ["QINIU_ACCESS_KEY"] = "test-only"
os.environ["QINIU_SECRET_KEY"] = "test-only"
os.environ["QINIU_S3_BUCKET"] = "test-only"
import io
import subprocess
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.config import get_settings
from app.core.db import engine
from app.core.events import redis_client
from app.main import app
from app.models import Base
from app.providers import providers
from app.schemas import DirectorData, GeneratedScript, Outline, TextResult


class FakeStorage:
    def __init__(self):
        self.objects = {}

    async def put(self, key, body, content_type):
        self.objects[key] = body
        return self.url(key)

    async def get(self, key):
        return self.objects[key]

    async def delete(self, key):
        self.objects.pop(key, None)

    def url(self, key):
        return "https://media.example/" + key if key else ""

    async def health(self):
        pass


class FakeLLM:
    async def structured(self, model, instruction, brief):
        if model is Outline:
            return Outline(
                logline="快递机器人学会说谎",
                synopsis="保护收件人的故事",
                themes=["信任"],
                characters=[],
                scenes=[
                    {"title": f"镜头{i + 1}", "summary": "废土中的机器人"}
                    for i in range(brief["scene_count"])
                ],
            )
        if model is GeneratedScript:
            return GeneratedScript(
                scenes=[
                    {
                        "title": f"镜头{i + 1}",
                        "imagePrompt": "沙漠中的机器人",
                        "durationSec": 4,
                        "dialogue": "这封信，一定会送到。",
                    }
                    for i in range(brief["count"])
                ]
            )
        if model is TextResult:
            return TextResult(text="清晰的电影构图")
        return DirectorData(
            template="街道",
            objects=[
                {
                    "id": "cam",
                    "name": "相机",
                    "kind": "camera",
                    "position": [0, 2, 5],
                    "rotation": [0, 0, 0],
                    "scale": 1,
                    "color": "#ffffff",
                    "action": "",
                }
            ],
            keyframes=[],
            fov=50,
        )


class FakeImage:
    async def generate(self, *args):
        out = io.BytesIO()
        Image.new("RGB", (384, 256), "#526c82").save(out, format="PNG")
        return out.getvalue(), []


class FakeTTS:
    def __init__(self, raw):
        self.raw = raw

    async def synthesize(self, *args):
        return self.raw


@pytest_asyncio.fixture
async def env(monkeypatch, tmp_path):
    assert engine.url.database.endswith("_test")
    # Production .env.local prices must not affect default unconfigured-price cases.
    monkeypatch.setattr(get_settings(), "cost_unit_price_json", {})
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with redis_client() as redis:
        keys = [key async for key in redis.scan_iter("cineai:*")]
        if keys:
            await redis.delete(*keys)
    storage = FakeStorage()
    p = providers()
    monkeypatch.setattr(p, "storage", storage)
    monkeypatch.setattr(p, "llm", FakeLLM())
    monkeypatch.setattr(p, "image", FakeImage())
    monkeypatch.setattr(p.external_media, "publish", AsyncMock(return_value="https://external.example/signed"))
    monkeypatch.setattr(p.external_media, "cleanup", AsyncMock(return_value=0))
    mp3 = tmp_path / "voice.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.6",
            "-y",
            str(mp3),
        ],
        check=True,
    )
    monkeypatch.setattr(p, "tts", FakeTTS(mp3.read_bytes()))
    from app.api.routers import jobs

    monkeypatch.setattr(jobs, "dispatch_pending", AsyncMock())
    yield storage
    await engine.dispose()


@pytest_asyncio.fixture
async def client(env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

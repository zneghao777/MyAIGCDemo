import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.providers.minimax import MiniMaxVideo


async def test_h3_request_separate_key_idempotency_and_explicit_low_cost(monkeypatch):
    from pydantic import SecretStr

    s = get_settings()
    monkeypatch.setattr(s, "minimax_video_api_key", SecretStr("video-test"))
    calls = []

    async def request(method, url, **kw):
        calls.append((method, url, kw))
        assert kw["headers"]["Authorization"] == "Bearer video-test"
        if method == "GET":
            return httpx.Response(200, json={"available_points": 100})
        return httpx.Response(200, json={"task_id": "remote-1"})

    monkeypatch.setattr("app.providers.minimax.request", request)
    v = MiniMaxVideo()
    assert (
        await v.create(
            "动作", "data:image/png;base64,eA==", 5.2, "16:9", idempotency_key="job-1", resolution="480P"
        )
        == "remote-1"
    )
    _, url, kw = calls[-1]
    assert url.endswith("/minimax/v2/video_generation")
    assert kw["retries"] == 0
    assert kw["headers"]["Idempotency-Key"] == "job-1"
    assert kw["json"]["duration"] == 6
    assert kw["json"]["resolution"] == "480P"
    assert kw["json"]["mute_audio"] is True
    assert kw["json"]["use_context_ir"] is False
    assert kw["json"]["content"][1]["role"] == "first_frame"


async def test_low_balance_never_submits_paid_request(monkeypatch):
    async def request(method, *args, **kw):
        assert method == "GET"
        return httpx.Response(200, json={"available_points": 20})

    monkeypatch.setattr("app.providers.minimax.request", request)
    with pytest.raises(AppError) as exc:
        await MiniMaxVideo().create("动作", "image", 6, "16:9", idempotency_key="job")
    assert exc.value.code == "PROVIDER_BALANCE_LOW"


@pytest.mark.parametrize("state", ["queued", "running", "succeeded", "failed", "cancelled"])
async def test_nested_status_and_result(monkeypatch, state):
    async def request(*args, **kw):
        return httpx.Response(
            200,
            json={
                "task": {
                    "status": state,
                    "content": {"url": "https://example.com/movie.mp4"},
                    "usage": {"total_seconds": 6},
                }
            },
        )

    monkeypatch.setattr("app.providers.minimax.request", request)
    result = await MiniMaxVideo().query("remote-1")
    assert result["status"] == state
    assert result["fileUrl"].endswith("movie.mp4")
    assert result["usage"]["total_seconds"] == 6


@pytest.mark.parametrize("duration,resolution", [(3, "480P"), (31, "480P"), (6, "480p")])
def test_reject_invalid_specs_before_billing(duration, resolution):
    with pytest.raises(AppError):
        MiniMaxVideo.estimate_points(duration, resolution)


async def test_worker_downloads_video_and_reuses_remote_task_on_retry(client, env, monkeypatch):
    from app.core.db import Session
    from app.models import Task
    from app.providers import providers
    from app.tasks.execute import execute_job
    from app.core.errors import TransientProviderError
    from unittest.mock import AsyncMock

    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    monkeypatch.setattr(get_settings(), "minimax_video_poll_interval_ms", 1)
    project = (
        await client.post(
            "/api/projects",
            json={
                "name": "视频测试",
                "ratio": "16:9",
                "scenes": [{"title": "镜头", "durationSec": 6, "imagePrompt": "抬手"}],
            },
        )
    ).json()
    sid = project["scenes"][0]["id"]
    jobs = (
        await client.post("/api/tasks", json={"projectId": project["id"], "sceneIds": [sid], "kind": "image"})
    ).json()
    await execute_job(jobs["queued"][0]["id"])
    jobs = (
        await client.post("/api/tasks", json={"projectId": project["id"], "sceneIds": [sid], "kind": "video"})
    ).json()
    tid = jobs["queued"][0]["id"]

    class FakeVideo:
        balance = AsyncMock(return_value={"available_points": 1000})
        create = AsyncMock(return_value="remote-stable")
        query = AsyncMock(side_effect=TransientProviderError("TIMEOUT", "timeout"))

    provider = FakeVideo()
    monkeypatch.setattr(providers(), "video", provider)
    await execute_job(tid)
    assert provider.create.call_count == 1
    assert provider.create.call_args.args[1].startswith("data:image/")
    async with Session() as db:
        row = await db.get(Task, tid)
        assert row.provider_task_id == "remote-stable"
        assert row.status == "queued"
    provider.query = AsyncMock(return_value={"status": "succeeded", "fileUrl": "https://example.com/v.mp4"})
    monkeypatch.setattr("app.tasks.execute.fetch_bytes", AsyncMock(return_value=b"fake-video"))
    await execute_job(tid)
    assert provider.create.call_count == 1
    result = (await client.get("/api/tasks/" + tid)).json()
    assert result["status"] == "done"
    assert result["result"]["providerTaskId"] == "remote-stable"
    repeat = (
        await client.post("/api/tasks", json={"projectId": project["id"], "sceneIds": [sid], "kind": "video"})
    ).json()
    assert not repeat["queued"]
    assert repeat["rejected"][0]["code"] == "VIDEO_ALREADY_EXISTS"


async def test_comp_share_download_keeps_origin_redirect_and_mp4_guards(monkeypatch):
    from app.providers.minimax import fetch_video
    from unittest.mock import AsyncMock

    original = httpx.AsyncClient
    requests = []

    async def handler(request):
        requests.append(request)
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"\x00\x00\x00\x18ftypmp42payload")

    def client(**kw):
        assert kw["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr("app.providers.minimax.httpx.AsyncClient", client)
    fallback = AsyncMock(side_effect=AppError("INVALID_MEDIA_URL", "blocked"))
    monkeypatch.setattr("app.providers.minimax.fetch_bytes", fallback)
    assert (
        await fetch_video("https://compshare-files.cn-wlcb.ufileos.com/media/prod/task.mp4")
        == b"\x00\x00\x00\x18ftypmp42payload"
    )
    for url in (
        "https://127.0.0.1/media/prod/task.mp4",
        "https://compshare-files.cn-wlcb.ufileos.com.evil.test/media/prod/task.mp4",
        "https://u:p@compshare-files.cn-wlcb.ufileos.com/media/prod/task.mp4",
    ):
        with pytest.raises(AppError):
            await fetch_video(url)
    assert len(requests) == 1

from app.core.config import get_settings
from app.tasks.execute import execute_job
from app.providers import providers
from app.core.errors import AppError
from test_backend import create, enqueue


async def test_director_camelcase_roundtrip(client):
    p = await create(client, 1)
    id = p["scenes"][0]["id"]
    data = {
        "template": "街道",
        "fov": 50,
        "objects": [
            {
                "id": "camera",
                "name": "摄影机",
                "kind": "camera",
                "position": [0, 2, 5],
                "rotation": [0, 0, 0],
                "scale": 1,
                "color": "#ffffff",
                "action": "",
            }
        ],
        "keyframes": [{"id": "key1", "objectId": "camera", "t": 0, "position": [0, 2, 5]}],
    }
    r = await client.patch("/api/scenes/" + id, json={"directorData": data})
    assert r.status_code == 200, r.text
    assert r.json()["directorData"] == data


async def test_successful_image_is_reused(client, monkeypatch):
    p = await create(client, 1)
    first = (await enqueue(client, p))[0]
    await execute_job(first["id"])
    second = (await enqueue(client, p))[0]
    assert second["id"] == first["id"] and second["status"] == "done"


async def test_invalid_script_preserves_existing_scenes(client, monkeypatch):
    p = await create(client, 2)
    ids = [s["id"] for s in p["scenes"]]

    async def invalid(*args):
        raise AppError("PROVIDER_OUTPUT_INVALID", "模型输出不合法", 422)

    monkeypatch.setattr(providers().llm, "structured", invalid)
    r = await client.post(
        "/api/projects/" + p["id"] + "/script/generate",
        json={"idea": "故事", "sceneCount": 8, "durationSec": 32},
    )
    await execute_job(r.json()["taskId"])
    task = (await client.get("/api/tasks/" + r.json()["taskId"])).json()
    assert task["status"] == "failed"
    assert [s["id"] for s in (await client.get("/api/projects/" + p["id"])).json()["scenes"]] == ids


async def test_legacy_missing_audio_requires_explicit_binding(client):
    p = await create(client, 1)
    for task in await enqueue(client, p):
        await execute_job(task["id"])
    s = get_settings()
    prices = s.cost_unit_price_json
    limit = s.cost_hard_limit_cents
    s.cost_unit_price_json = {"ttsPerKChar": 10000}
    s.cost_hard_limit_cents = 1
    try:
        r = await client.post("/api/projects/" + p["id"] + "/exports", json={})
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "LEGACY_BINDING_REQUIRED"
    finally:
        s.cost_unit_price_json = prices
        s.cost_hard_limit_cents = limit


async def test_retry_backoff_is_durable_and_does_not_lose_delivery(client, monkeypatch):
    from app.core.errors import TransientProviderError
    from app.models import Task, now
    from app.core.db import Session
    from app.services.jobs import dispatch_pending
    from app.worker import celery
    from datetime import timedelta

    p = await create(client, 1)
    row = (await enqueue(client, p))[0]

    async def unavailable(*args):
        raise TransientProviderError("PROVIDER_ERROR", "暂时失败", 502)

    monkeypatch.setattr(providers().image, "generate", unavailable)
    await execute_job(row["id"])
    calls = []
    monkeypatch.setattr(celery, "send_task", lambda *args, **kwargs: calls.append(kwargs))
    await dispatch_pending()
    assert not calls
    async with Session() as db:
        task = await db.get(Task, row["id"])
        assert task.status == "queued" and task.available_at > now()
        task.available_at = now() - timedelta(seconds=1)
        await db.commit()
    await dispatch_pending()
    assert len(calls) == 1 and calls[0]["task_id"] == row["id"]


async def test_cached_image_rebinds_original_asset(client):
    p = await create(client, 1)
    scene = p["scenes"][0]["id"]
    first = (await enqueue(client, p))[0]
    await execute_job(first["id"])
    image_a = (await client.get("/api/projects/" + p["id"])).json()["scenes"][0]["image"]
    await client.patch("/api/scenes/" + scene, json={"imagePrompt": "夜晚"})
    second = (await enqueue(client, p))[0]
    await execute_job(second["id"])
    image_b = (await client.get("/api/projects/" + p["id"])).json()["scenes"][0]["image"]
    assert image_a != image_b
    await client.patch("/api/scenes/" + scene, json={"imagePrompt": "机器人"})
    reused = (await enqueue(client, p))[0]
    assert reused["id"] == first["id"]
    assert (await client.get("/api/projects/" + p["id"])).json()["scenes"][0]["image"] == image_a


async def test_metrics_and_unconfigured_prices(client):
    p = await create(client, 0)
    r = await client.get("/api/metrics")
    assert r.status_code == 200 and "cineai_tasks" in r.text
    r = await client.get("/api/projects/" + p["id"] + "/estimate")
    assert r.json()["pricingConfigured"] is False

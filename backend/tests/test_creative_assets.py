"""Paid providers are mocked; persistence and local preview rendering are real."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from test_creative import confirm, fetch, generate, select, setup

from app.core.config import get_settings
from app.core.db import Session
from app.models import Scene
from app.providers import providers
from app.schemas.creative import Shot, VideoInput
from app.services.creative import digest, image_fingerprint_matches, review_current, review_fingerprint
from app.tasks.execute import execute_job


@pytest.mark.parametrize(
    "patch",
    [
        {"action_steps": [{"id": "touch", "start_sec": 1, "end_sec": 7, "description": "按下按钮"}]},
        {
            "action_steps": [
                {
                    "id": "touch",
                    "start_sec": 1,
                    "end_sec": 2,
                    "description": "按下按钮",
                    "trigger_line_id": "missing",
                }
            ]
        },
        {
            "subtitle_cues": [
                {"id": "a", "start_sec": 0, "end_sec": 2, "text": "第一句"},
                {"id": "b", "start_sec": 1, "end_sec": 3, "text": "第二句"},
            ]
        },
        {"character_views": {"wrong-character": "side"}},
    ],
)
def test_structural_timing_and_identity_references(patch):
    with pytest.raises(ValidationError):
        Shot(title="动作结果", location_id="station", duration=6, **patch)


def test_video_inputs_reject_conflicting_modes():
    with pytest.raises(ValidationError):
        VideoInput(
            mode="first_last_frame", references=[{"asset_id": "ref", "kind": "image", "purpose": "环境"}]
        )


def test_review_is_bound_to_inputs_and_not_editorial_version():
    scene = SimpleNamespace(
        creative={"shot": {"end_state": "灯亮"}}, video_key="video", director_data=None, duration_sec=6
    )
    scene.creative["review"] = {"status": "accepted", "fingerprint": review_fingerprint(scene)}
    assert review_current(scene)
    scene.creative["version"] = 9
    assert review_current(scene)
    scene.creative["shot"]["end_state"] = "灯灭"
    assert not review_current(scene)


def test_empty_new_fields_preserve_historical_image_hash_without_rewriting_it():
    legacy = {
        "model": "model",
        "quality": "low",
        "ratio": "16:9",
        "style": "动画",
        "cast": {},
        "director": None,
        "shot": {"title": "送信", "action": "递信", "location_id": "station"},
    }
    fingerprint = digest(legacy)
    current = {
        **legacy,
        "frame": "first",
        "location": None,
        "shot": {
            **legacy["shot"],
            "purpose": "",
            "start_state": "",
            "end_state": "",
            "action_steps": [],
            "spatial_relations": {},
            "continuity_from": None,
            "continuity_requirements": "",
            "location_revision": None,
            "location_state": "",
            "character_views": {},
        },
    }
    assert image_fingerprint_matches(fingerprint, current)
    assert fingerprint == digest(legacy)
    current["shot"]["start_state"] = "手里没有信"
    assert not image_fingerprint_matches(fingerprint, current)


async def test_character_view_reuses_master_and_preserves_source(client, monkeypatch):
    p = await setup(client, monkeypatch)
    pid, character = p["id"], p["characters"][0]
    spy = AsyncMock(wraps=providers().image.generate)
    monkeypatch.setattr(providers().image, "generate", spy)
    task = await generate(client, pid, "character_image", target=character["id"], view="side")
    p = await select(client, pid, task)
    selected = next(c for c in p["characters"] if c["id"] == character["id"])
    view = selected["creative"]["views"]["side"]
    assert view["confirmed"] and view["asset_id"] and view["url"].startswith("https://media.example/")
    assert view["source"] == "provider" and view["parent_revision"]
    assert len(spy.call_args.args[3]) == 1
    assert "沿用已确认主造型" in spy.call_args.args[0]
    checked = await client.post(
        f"/api/creative/characters/{character['id']}/confirm-image",
        json={
            "expected": selected["creative"]["version"],
            "data": {
                "checks": {"clear_silhouette": True, "no_subtitles": True, "low_occlusion": True},
                "notes": "已人工检查主造型",
            },
        },
    )
    assert checked.status_code == 200, checked.text
    assert (
        checked.json()["visual_checks"]["image_fingerprint"] == selected["creative"]["image"]["fingerprint"]
    )


async def test_location_versions_bind_environment_and_enforce_combined_limit(client, monkeypatch):
    # Exercise the intentionally constrained deployment independently of the new default of four.
    monkeypatch.setattr(get_settings(), "image_max_references", 2)
    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    result = await client.patch(
        f"/api/creative/projects/{pid}/locations/station",
        json={
            "expected": 0,
            "data": {"id": "station", "name": "车站", "description": "无人候车大厅", "landmarks": "绿色站牌"},
        },
    )
    assert result.status_code == 200, result.text
    task = await generate(client, pid, "location_image", target="station")
    f = await fetch(client, pid)
    candidate = next(c for c in f["candidates"] if c["id"] == task["result"]["candidateId"])
    result = await client.post(
        f"/api/creative/projects/{pid}/select",
        json={
            "candidate_id": candidate["id"],
            "expected": f["project"]["creative"]["locations"]["station"]["version"],
        },
    )
    assert result.status_code == 200, result.text
    location = result.json()["creative"]["locations"]["station"]
    result = await client.post(
        f"/api/creative/projects/{pid}/locations/station/confirm",
        json={"expected": location["version"], "data": {"notes": "地标、光照检查完成"}},
    )
    assert result.status_code == 200, result.text
    location = result.json()
    f = await fetch(client, pid)
    sc = f["project"]["scenes"][0]
    shot = {**sc["creative"]["shot"], "location_revision": location["revision"]}
    monkeypatch.setattr(get_settings(), "image_max_references", 2)
    result = await client.patch(
        f"/api/creative/scenes/{sid}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert result.status_code == 200, result.text
    await confirm(client, pid, "shots")
    spy = AsyncMock(wraps=providers().image.generate)
    monkeypatch.setattr(providers().image, "generate", spy)
    result = await client.post(f"/api/creative/projects/{pid}/estimate", json={"operation": "shot_image", "target": sid})
    assert result.status_code == 409 and result.json()["error"]["code"] == "REFERENCE_LIMIT"
    assert spy.await_count == 0
    monkeypatch.setattr(get_settings(), "image_max_references", 3)
    await select(client, pid, await generate(client, pid, "shot_image", target=sid))
    assert len(spy.call_args.args[3]) == 3 and "用途是无人环境" in spy.call_args.args[0]
    assets = (await client.get(f"/api/projects/{pid}/assets")).json()
    assert any(a["id"] == location["image"]["asset_id"] for a in assets)
    history = (await client.get(f"/api/creative/projects/{pid}/history")).json()
    current = next(item for item in history if item["id"] == location["revision"])
    assert current["kind"] == "location" and current["name"] == "车站" and current["current"]
    assert current["restorable"] and current["usedBy"] == ["交接"]
    impact = (await client.get(f"/api/creative/projects/{pid}/history/{location['revision']}/impact")).json()
    restored = await client.post(
        f"/api/creative/projects/{pid}/history/{location['revision']}/restore",
        json={"expected": impact["expected"], "data": {"projectExpected": impact["projectExpected"]}},
    )
    assert restored.status_code == 200, restored.text
    state = (await fetch(client, pid))["project"]["creative"]["locations"]["station"]
    assert not state["confirmed"] and state["version"] > location["version"]
    assert state["image"]["asset_id"] == location["image"]["asset_id"]


async def test_explicit_static_preview_uses_frames_even_with_video_and_invalidates_locally(
    client, monkeypatch, env
):
    p = await setup(client, monkeypatch)
    pid, sid = p["id"], p["scenes"][0]["id"]
    for op in ("shot_image", "shot_audio"):
        await select(client, pid, await generate(client, pid, op, target=sid))
    # Only the isolated _test database is edited to install an unavailable video fixture.
    async with Session() as db:
        scene = await db.get(Scene, sid)
        scene.video_key = "must-not-read-this-video"
        await db.commit()
    for provider, method in (
        (providers().image, "generate"),
        (providers().tts, "synthesize"),
        (providers().video, "create"),
    ):
        monkeypatch.setattr(
            provider, method, AsyncMock(side_effect=AssertionError("preview must never generate"))
        )
    response = await client.post(
        f"/api/projects/{pid}/preview",
        json={"sourceMode": "storyboard", "resolution": "720p", "subtitles": True},
    )
    assert response.status_code == 202, response.text
    await execute_job(response.json()["taskId"])
    job = (await client.get("/api/exports/" + response.json()["exportJobId"])).json()
    assert job["status"] == "done", job
    assert job["label"] == "静态分镜配声预演" and not job["manualAcceptance"]
    assert any(isinstance(log, dict) and log.get("soundGapSec", 0) > 0 for log in job["logs"])
    f = await fetch(client, pid)
    denied = await client.post(
        f"/api/creative/projects/{pid}/export-confirm",
        json={
            "expected": f["project"]["creative"]["version"],
            "data": {
                "export_job_id": job["id"],
                "checks": {
                    key: True
                    for key in ("character", "environment", "action", "sound", "subtitles", "transition")
                },
            },
        },
    )
    assert denied.status_code == 409 and denied.json()["error"]["code"] == "STALE_EXPORT"
    response = await client.post(
        f"/api/creative/projects/{pid}/preview-confirm",
        json={
            "expected": f["project"]["creative"]["version"],
            "data": {"export_job_id": job["id"], "notes": "完整听看"},
        },
    )
    assert response.status_code == 200, response.text
    assert (await fetch(client, pid))["workflowReadiness"]["preview_confirmed"]
    sc = (await fetch(client, pid))["project"]["scenes"][0]
    shot = deepcopy(sc["creative"]["shot"])
    shot["end_state"] = "交接后两人微笑"
    response = await client.patch(
        f"/api/creative/scenes/{sid}", json={"expected": sc["creative"]["version"], "data": shot}
    )
    assert response.status_code == 200, response.text
    f = await fetch(client, pid)
    assert not f["workflowReadiness"]["preview_confirmed"]
    assert f["project"]["creative"]["preview_confirmation"]["stale"]
    assert (await client.get("/api/exports/" + job["id"])).json()["stale"]

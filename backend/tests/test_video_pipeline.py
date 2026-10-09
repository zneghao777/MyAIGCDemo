import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import Session
from app.core.errors import AppError
from app.models import Task, Scene, now
from app.providers import providers
from app.providers.minimax import MiniMaxVideo
from app.services import video_capacity
from app.tasks.execute import execute_job
from app.worker_config import worker_commands


def media(kind, role, n=1):
    key = kind + "_url"
    return {"type": key, key: {"url": f"https://example.com/{n}"}, "role": role}


@pytest.mark.parametrize(
    "materials",
    [
        [media("image", "first_frame")],
        [media("image", "first_frame"), media("image", "last_frame")],
        [
            media("image", "reference_image"),
            media("video", "reference_video"),
            media("audio", "reference_audio"),
        ],
    ],
)
async def test_three_h3_modes_pass_real_content(monkeypatch, materials):
    request = AsyncMock(return_value=httpx.Response(200, json={"task_id": "remote"}))
    monkeypatch.setattr("app.providers.minimax.request", request)
    await MiniMaxVideo().create(
        "动作", None, 5, "16:9", idempotency_key="same-paid-task", materials=materials, balance_checked=True
    )
    body = request.call_args.kwargs["json"]
    assert body["content"][1:] == materials
    assert body["use_context_ir"] is False


@pytest.mark.parametrize(
    "materials,code",
    [
        ([media("image", "first_frame"), media("image", "reference_image")], "H3_MODE_CONFLICT"),
        ([media("audio", "reference_audio")], "H3_AUDIO_ONLY"),
        ([media("image", "first_frame"), media("image", "first_frame", 2)], "H3_REFERENCE_LIMIT"),
        ([media("image", "reference_image", n) for n in range(10)], "H3_REFERENCE_LIMIT"),
    ],
)
def test_invalid_h3_material_combinations(materials, code):
    with pytest.raises(AppError) as exc:
        MiniMaxVideo.validate_content([{"type": "text", "text": "动作"}, *materials])
    assert exc.value.code == code


def test_reference_labels_use_separate_actual_media_counts():
    contents = [
        media("image", "reference_image"),
        media("video", "reference_video"),
        media("image", "reference_image", 2),
        media("audio", "reference_audio"),
    ]
    MiniMaxVideo.validate_content([{"type": "text", "text": "<Picture 2> <Video 1> <Audio 1>"}, *contents])
    with pytest.raises(AppError) as exc:
        MiniMaxVideo.validate_content([{"type": "text", "text": "<Audio 2>"}, *contents])
    assert exc.value.code == "H3_REFERENCE_MISSING"


def test_mac_workers_are_distinct_processes_and_names():
    commands = worker_commands(2, platform="darwin", run_id="test")
    video = [x for x in commands if "cineai.video" in x]
    assert len(video) == 2
    assert len({x[x.index("-n") + 1] for x in commands}) == len(commands)
    assert all(x[x.index("-c") + 1] == "1" and "solo" in x for x in video)
    linux = [x for x in worker_commands(3, platform="linux") if "cineai.video" in x]
    assert len(linux) == 1 and linux[0][linux[0].index("-c") + 1] == "3"


async def prepare_video_jobs(client, count, submit=True):
    project = (
        await client.post(
            "/api/projects",
            json={
                "name": "并发独立测试",
                "ratio": "16:9",
                "scenes": [{"title": str(i), "imagePrompt": "抬手", "durationSec": 5} for i in range(count)],
            },
        )
    ).json()
    ids = [x["id"] for x in project["scenes"]]
    jobs = (
        await client.post("/api/tasks", json={"projectId": project["id"], "sceneIds": ids, "kind": "image"})
    ).json()
    for task in jobs["queued"]:
        await execute_job(task["id"])
    if not submit:
        return project, []
    jobs = (
        await client.post("/api/tasks", json={"projectId": project["id"], "sceneIds": ids, "kind": "video"})
    ).json()
    return project, jobs["queued"]


async def test_account_admission_and_atomic_budget_reservations(env, monkeypatch):
    monkeypatch.setattr(get_settings(), "video_concurrency_limit", 2)
    await video_capacity.acquire("one")
    await video_capacity.acquire("two")
    with pytest.raises(video_capacity.CapacityPending):
        await video_capacity.acquire("three")
    await video_capacity.release("one")
    await video_capacity.acquire("three")
    provider = type("P", (), {"balance": AsyncMock(return_value={"available_points": 40})})()
    # Concurrent requests cannot both reserve a 25-point shot from the same 40 points.
    results = await asyncio.gather(
        video_capacity.reserve("paid-one", 25, provider),
        video_capacity.reserve("paid-two", 25, provider),
        return_exceptions=True,
    )
    assert sum(isinstance(x, AppError) for x in results) == 1
    assert any(getattr(x, "code", None) == "PROVIDER_BALANCE_LOW" for x in results)
    identity = "paid-one" if not isinstance(results[0], Exception) else "paid-two"
    await video_capacity.reserve(identity, 25, provider)  # Idempotent recovery.


async def test_parallel_remote_overlap_out_of_order_and_failed_shot_isolated(client, env, monkeypatch):
    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    monkeypatch.setattr(get_settings(), "minimax_video_poll_interval_ms", 1)
    _, jobs = await prepare_video_jobs(client, 2)
    submitted = []
    done = []
    both_created = asyncio.Event()
    second_queried = asyncio.Event()

    class FakeVideo:
        balance = AsyncMock(return_value={"available_points": 1000})

        async def create(self, *args, **kw):
            identity = str(len(submitted))
            submitted.append(identity)
            if len(submitted) == 2:
                both_created.set()
            return identity

        async def query(self, identity):
            await asyncio.wait_for(both_created.wait(), 3)
            if identity == "0":
                await asyncio.wait_for(second_queried.wait(), 3)
            else:
                second_queried.set()
            done.append(identity)
            return (
                {"status": "failed"}
                if identity == "1"
                else {"status": "succeeded", "fileUrl": "https://example.com/video.mp4"}
            )

    provider = FakeVideo()
    monkeypatch.setattr(providers(), "video", provider)
    monkeypatch.setattr("app.tasks.execute.fetch_bytes", AsyncMock(return_value=b"video"))
    await asyncio.gather(*(execute_job(x["id"]) for x in jobs))
    assert submitted == ["0", "1"] and done == ["1", "0"]
    async with Session() as db:
        rows = [await db.get(Task, x["id"]) for x in jobs]
        assert {x.status for x in rows} == {"done", "failed"}
        successful = next(x for x in rows if x.status == "done")
        assert successful.result["providerSubmittedAt"] < successful.result["providerCompletedAt"]
        scenes = list((await db.scalars(select(Scene).order_by(Scene.order_index))).all())
        assert [x.order_index for x in scenes] == [0, 1]


async def test_duplicate_batches_return_same_jobs_and_points_limit_atomic(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    project, jobs = await prepare_video_jobs(client, 2)
    body = {"projectId": project["id"], "sceneIds": [x["id"] for x in project["scenes"]], "kind": "video"}
    again = (await client.post("/api/tasks", json=body)).json()
    assert [x["id"] for x in again["queued"]] == [x["id"] for x in jobs]
    assert not again["rejected"]
    project2, _ = await prepare_video_jobs(client, 2, submit=False)
    monkeypatch.setattr(get_settings(), "video_points_hard_limit", 40)
    response = await client.post(
        "/api/tasks",
        json={
            "projectId": project2["id"],
            "sceneIds": [x["id"] for x in project2["scenes"]],
            "kind": "video",
        },
    )
    assert response.status_code == 402 and response.json()["error"]["code"] == "VIDEO_POINTS_LIMIT"
    # An over-budget batch rolls back the first reservation as well.
    all_jobs = (await client.get(f"/api/projects/{project2['id']}/tasks")).json()
    assert not [x for x in all_jobs if x["kind"] == "video"]


async def test_worker_crash_recovers_same_remote_identity(client, env, monkeypatch):
    from app.tasks.execute import dispatch

    monkeypatch.setattr(get_settings(), "feature_video_generation", True)
    _, jobs = await prepare_video_jobs(client, 1)
    tid = jobs[0]["id"]
    async with Session() as db:
        row = await db.get(Task, tid)
        row.status = "running"
        row.provider_task_id = "remote-before-crash"
        row.started_at = now() - timedelta(seconds=1100)
        await db.commit()
    monkeypatch.setattr("app.tasks.execute.dispatch_pending", AsyncMock())
    await asyncio.to_thread(dispatch.run)
    async with Session() as db:
        row = await db.get(Task, tid)
        assert row.status == "queued" and row.provider_task_id == "remote-before-crash"
        assert row.dispatched_at is None


def video_scene(creative=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        id="shot-2",
        project_id="project",
        order_index=1,
        first_frame_key="first.png",
        duration_sec=5,
        video_prompt="",
        image_prompt="抬手",
        camera_move="固定",
        video_key="video.mp4",
        creative=creative,
    )


def test_legacy_video_source_remains_compatible_until_new_inputs_change():
    from app.services.video import source, is_stale

    scene = video_scene(
        {
            "shot": {
                "id": "shot-2",
                "action": "抬手",
                "cast": {"character-1": "character-revision"},
                "location_id": "location-1",
                "location_description": "车站",
                "duration": 5,
                "lines": [
                    {"id": "line-1", "speaker_id": "character-1", "text": "到站了。", "pause_after": 0.2}
                ],
                "narration": [],
                "variants": {},
                "audio_order": ["line-1"],
                "sound_effects": [],
            }
        }
    )
    old = source(scene, "16:9")
    old.pop("shot")
    scene.creative["video"] = {"source": old}
    assert not is_stale(scene, "16:9")
    scene.creative["shot"]["start_state"] = "双手垂下"
    assert is_stale(scene, "16:9")


async def test_dependency_tail_updates_actual_source_snapshot(monkeypatch):
    from types import SimpleNamespace
    from pathlib import Path
    from app.services import video_dependency, video

    previous = SimpleNamespace(id="shot-1", title="前镜", project_id="project", order_index=0, video_key=None, creative={})
    db = SimpleNamespace(
        get=AsyncMock(return_value=previous), scalar=AsyncMock(return_value=None), commit=AsyncMock()
    )
    scene = video_scene({"shot": {"continuity_from": "shot-1"}})
    initial = await video.current_source(db, scene, "16:9")
    task = SimpleNamespace(
        project_id="project",
        provider_task_id=None,
        result=None,
        payload={"video_source": initial, "materials": [], "input_mode": "first_frame"},
    )
    with pytest.raises(video_dependency.DependencyPending):
        await video_dependency.prepare(db, task, scene, task.payload, AsyncMock())
    previous.video_key = "real-previous.mp4"
    monkeypatch.setattr(providers().storage, "get", AsyncMock(return_value=b"local-video"))
    monkeypatch.setattr(video_dependency, "probe", AsyncMock(return_value=5))

    async def extract(args, checkpoint):
        Path(args[-1]).write_bytes(b"extracted-tail")

    monkeypatch.setattr(video_dependency, "run_ffmpeg", extract)
    asset = SimpleNamespace(id="tail-asset", object_key="tail.png", size_bytes=14)
    monkeypatch.setattr(video_dependency, "save_asset", AsyncMock(return_value=asset))
    prepared = await video_dependency.prepare(db, task, scene, task.payload, AsyncMock())
    assert prepared["materials"][0]["asset_id"] == "tail-asset"
    assert prepared["video_source"] == await video.current_source(db, scene, "16:9")
    scene.creative["video"] = {"source": prepared["video_source"]}
    assert not await video.dependency_is_stale(db, scene)
    previous.creative = {"edit": {"in_sec": 0, "out_sec": 3}}
    assert await video.dependency_is_stale(db, scene)
    previous.creative = {}
    previous.video_key = "corrected-previous.mp4"
    assert await video.dependency_is_stale(db, scene)


def test_subtitle_calibration_does_not_expire_paid_video_or_change_h3_prompt():
    from copy import deepcopy
    from app.services.video import source, is_stale, organized_prompt

    scene = video_scene(
        {
            "shot": {
                "action": "抬手",
                "start_state": "双手垂下",
                "end_state": "手举起",
                "subtitle_cues": [],
                "subtitles_calibrated": False,
            },
            "audio": {
                "segments": [
                    {
                        "key": "voice.mp3",
                        "duration_ms": 1000,
                        "line": {
                            "id": "line-1",
                            "speaker_id": "character-1",
                            "text": "到站了。",
                            "pause_after": 0.2,
                        },
                    }
                ]
            },
        }
    )
    scene.creative["video"] = {"source": deepcopy(source(scene, "16:9"))}
    original_prompt = organized_prompt(scene, [], {})
    scene.creative["shot"]["subtitle_cues"] = [
        {"id": "cue-1", "line_id": "line-1", "start_sec": 0.5, "end_sec": 1.5, "text": "到站了。"}
    ]
    scene.creative["shot"]["subtitles_calibrated"] = True
    assert not is_stale(scene, "16:9")
    assert organized_prompt(scene, [], {}) == original_prompt
    assert "0–1秒" in original_prompt
    # A real voice duration change still changes the generation timing inputs.
    scene.creative["audio"]["segments"][0]["duration_ms"] = 1600
    assert is_stale(scene, "16:9")

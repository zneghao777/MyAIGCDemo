"""Explicit local video corrections preserve their paid H3 source and review history."""

import asyncio
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile

from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Asset, Candidate, Project, Scene, Task, now
from app.providers import providers
from app.services import creative as flow
from app.services.resources import require, save_asset
from app.services.locking import locked_scene
from app.services import video


MAX_BYTES = 50 * 1024 * 1024


async def inspect_mp4(path):
    proc = await asyncio.create_subprocess_exec(
        get_settings().ffprobe_path,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 15)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise AppError("INVALID_MEDIA", "视频格式校验超时", 422) from None
    try:
        metadata = json.loads(out)
        streams = metadata["streams"]
        videos = [s for s in streams if s.get("codec_type") == "video"]
        duration = float(metadata["format"]["duration"])
        width, height = int(videos[0]["width"]), int(videos[0]["height"])
        numerator, denominator = videos[0]["avg_frame_rate"].split("/")
        fps = float(numerator) / float(denominator)
        if (
            proc.returncode
            or len(videos) != 1
            or "mp4" not in metadata["format"]["format_name"]
            or not all(math.isfinite(x) and x > 0 for x in (duration, width, height, fps))
        ):
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        raise AppError("INVALID_MEDIA", "需要可解码、含单一画面轨的 MP4 视频", 422) from None
    return {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "audio_tracks": sum(s.get("codec_type") == "audio" for s in streams),
    }


async def verify_decode(path):
    proc = await asyncio.create_subprocess_exec(
        get_settings().ffmpeg_path,
        "-v",
        "error",
        "-xerror",
        "-nostdin",
        "-threads",
        "2",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-f",
        "null",
        "-",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), 30)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise AppError("INVALID_MEDIA", "视频完整解码校验超时", 422) from None
    if proc.returncode:
        raise AppError("INVALID_MEDIA", "修正视频无法完整播放，请重新导出 MP4", 422)

def base_key(scene):
    trace = (scene.creative or {}).get("video") or {}
    key = scene.video_key or trace.get("key")
    if not key or trace.get("key") != key:
        raise AppError("INVALID_VIDEO_SOURCE", "当前选中或保留的视频来源不完整", 422)
    return key


async def parent(db, project, scene, source_task_id):
    task = await require(db, Task, source_task_id)
    if (
        task.project_id != project.id
        or task.scene_id != scene.id
        or task.kind != "video"
        or task.status != "done"
        or not task.provider_task_id
        or task.provider != "minimax-video"
    ):
        raise AppError("INVALID_VIDEO_SOURCE", "修正必须引用同项目、本镜已完成的真实 H3 任务", 422)
    source_asset = await require(db, Asset, (task.result or {}).get("assetId"))
    if source_asset.project_id != project.id or source_asset.content_type != "video/mp4":
        raise AppError("INVALID_VIDEO_SOURCE", "原 H3 素材不属于当前项目或格式不匹配", 422)
    state = scene.creative or {}
    prior = [state.get("video") or {}, *(state.get("video_takes") or [])]
    trace = deepcopy(
        next((x for x in prior if x.get("take") == task.id and x.get("key") == source_asset.object_key), {})
    )
    result, payload = task.result or {}, task.payload
    trace.update(
        key=source_asset.object_key,
        asset_id=source_asset.id,
        source=deepcopy(payload["video_source"]),
        take=task.id,
        provider_task_id=task.provider_task_id,
        model=payload.get("model"),
        resolution=(result.get("providerOutput") or {}).get("resolution") or payload.get("resolution"),
        usage=deepcopy(result.get("usage", {})),
        materials=deepcopy(result.get("materials") or payload.get("materials", [])),
        prompt=result.get("prompt") or payload.get("prompt"),
        input_mode=result.get("inputMode") or payload.get("input_mode"),
        sound_strategy=payload.get("sound_strategy", "post_audio"),
        raw_output=deepcopy(result.get("providerOutput", {})),
        parameters={
            k: payload.get(k) for k in ("duration_sec", "ratio", "resolution", "mute_audio", "use_context_ir")
        },
    )
    current = await video.current_source(db, scene, project.ratio)
    return task, deepcopy(trace), current


async def create_candidate(db, scene_id, expected, reason, source_task_id, raw, content_type, filename):
    if content_type != "video/mp4" or Path(filename or "").suffix.lower() != ".mp4" or raw[4:8] != b"ftyp":
        raise AppError("INVALID_MEDIA", "请上传 MIME 为 video/mp4 的真实 MP4 文件", 422)
    if not raw or len(raw) > MAX_BYTES:
        raise AppError("PAYLOAD_TOO_LARGE", "视频修正文件上限 50 MiB", 413)
    reason = reason.strip()
    if not reason or len(reason) > 1000:
        raise AppError("CORRECTION_REASON_REQUIRED", "请填写不超过1000字的具体后期修正原因", 422)
    project, scene = await locked_scene(db, scene_id)
    flow.check_version(scene.creative or {}, expected)
    guard = base_key(scene)
    task, trace, current = await parent(db, project, scene, source_task_id)
    source_raw = await providers().storage.get(trace["key"])
    with tempfile.TemporaryDirectory(prefix="cineai-video-correction-") as folder:
        path, source = Path(folder) / "corrected.mp4", Path(folder) / "source.mp4"
        path.write_bytes(raw)
        source.write_bytes(source_raw)
        metadata, original = await inspect_mp4(path), await inspect_mp4(source)
        if abs(metadata["duration_seconds"] - scene.duration_sec) > scene.duration_sec * 0.15 + 1e-8:
            raise AppError("VIDEO_DURATION_MISMATCH", "修正视频时长与本镜相差不得超过15%", 422)
        if (metadata["width"], metadata["height"]) != (original["width"], original["height"]) or abs(
            metadata["fps"] - original["fps"]
        ) > original["fps"] * 0.05:
            raise AppError("VIDEO_GEOMETRY_MISMATCH", "后期修正需保留原视频画幅和帧率", 422)
        if metadata["audio_tracks"] > original["audio_tracks"]:
            raise AppError("VIDEO_AUDIO_MISMATCH", "局部画面修正不能添加未知音轨，请保持原声或静音", 422)
        await verify_decode(path)
    sha = hashlib.sha256(raw).hexdigest()
    source_fp = flow.digest(current)
    signature = flow.digest(
        {
            "source_task_id": source_task_id,
            "source_key": trace["key"],
            "base_video_key": guard,
            "current_source_fp": source_fp,
            "sha256": sha,
            "reason": reason,
        }
    )
    existing = await db.scalar(
        select(Candidate)
        .where(
            Candidate.project_id == project.id,
            Candidate.entity_id == scene.id,
            Candidate.kind == "video_correction",
            Candidate.fingerprint == signature,
        )
        .limit(1)
    )
    if existing:
        return existing
    asset = await save_asset(
        db,
        project.id,
        "video-correction",
        raw,
        "video/mp4",
        "mp4",
        duration_ms=round(metadata["duration_seconds"] * 1000),
    )
    asset.width, asset.height = metadata["width"], metadata["height"]
    event = {
        "operation": "local_video_correction",
        "at": now().isoformat(),
        "reason": reason,
        "source_task_id": source_task_id,
        "source_key": trace["key"],
        "source_sha256": hashlib.sha256(source_raw).hexdigest(),
        "sha256": sha,
        "filename": Path(filename).name,
        "metadata": metadata,
        "source_metadata": original,
        "base_video_key": guard,
        "original_source": deepcopy(trace["source"]),
        "adopted_historical_h3": guard != trace["key"],
        "editorial_source": deepcopy(current),
        "model_called": False,
        "charged_points": 0,
    }
    candidate = Candidate(
        project_id=project.id,
        entity_id=scene.id,
        kind="video_correction",
        fingerprint=signature,
        task_id=source_task_id,
        data={
            "key": asset.object_key,
            "asset_id": asset.id,
            "sha256": sha,
            "source": "local-post-processing",
            "source_task_id": source_task_id,
            "source_video_key": trace["key"],
            "base_video_key": guard,
            "base_trace": deepcopy((scene.creative or {}).get("video")),
            "original_source": deepcopy(trace["source"]),
            "reason": reason,
            "duration_ms": asset.duration_ms,
            "current_source_fp": source_fp,
            "parent_trace": trace,
            "parent_task_snapshot": {
                "id": task.id,
                "kind": task.kind,
                "provider": task.provider,
                "provider_task_id": task.provider_task_id,
                "payload": deepcopy(task.payload),
                "result": deepcopy(task.result),
            },
            "post_processing": [*trace.get("post_processing", []), event],
        },
    )
    db.add(candidate)
    await db.flush()
    return candidate


async def is_stale(db, project, candidate):
    scene = await db.get(Scene, candidate.entity_id)
    if not scene or scene.project_id != project.id:
        return True
    value = candidate.data
    try:
        current = await video.current_source(db, scene, project.ratio)
        if flow.digest(current) != value["current_source_fp"]:
            return True
        selected = ((scene.creative or {}).get("video") or {}).get("candidate_id") == candidate.id
        if selected:
            return scene.video_key != value["key"] or await video.dependency_is_stale(db, scene)
        if base_key(scene) != value["base_video_key"]:
            return True
        _, trace, _ = await parent(db, project, scene, value["source_task_id"])
        return trace["key"] != value["source_video_key"]
    except (AppError, KeyError):
        return True


async def select_candidate(db, project, candidate, expected):
    _, scene = await locked_scene(db, candidate.entity_id)
    if scene.project_id != project.id or candidate.project_id != project.id:
        raise AppError("INVALID_CANDIDATE", "视频修正候选不属于本项目", 422)
    flow.check_version(scene.creative or {}, expected)
    if await is_stale(db, project, candidate):
        raise AppError("STALE_CANDIDATE", "视频修正的父take或当前输入已变化，不能覆盖新版本", 409)
    value = candidate.data
    asset = await require(db, Asset, value["asset_id"])
    if (
        asset.project_id != project.id
        or asset.object_key != value["key"]
        or hashlib.sha256(await providers().storage.get(asset.object_key)).hexdigest() != value["sha256"]
    ):
        raise AppError("INVALID_VIDEO_CORRECTION", "修正素材归属或内容签名不匹配", 422)
    if ((scene.creative or {}).get("video") or {}).get("candidate_id") == candidate.id:
        return
    task, previous, current = await parent(db, project, scene, value["source_task_id"])
    if (
        hashlib.sha256(await providers().storage.get(previous["key"])).hexdigest()
        != value["post_processing"][-1]["source_sha256"]
    ):
        raise AppError("STALE_VIDEO_SOURCE", "父视频文件已改变，请重新导入修正候选", 409)
    original_asset = await require(db, Asset, task.result["assetId"])
    trace = {
        **deepcopy(previous),
        "key": asset.object_key,
        "asset_id": asset.id,
        "source": current,
        "original_source": deepcopy(value["original_source"]),
        "take": candidate.id,
        "candidate_id": candidate.id,
        "parent_task_id": task.id,
        "source_task_id": task.id,
        "parent_video_key": previous["key"],
        "superseded_base_video_key": value["base_video_key"],
        "original_h3_key": original_asset.object_key,
        "sha256": value["sha256"],
        "post_processing": deepcopy(value["post_processing"]),
        "accepted": False,
        "parent_h3_trace": deepcopy(previous.get("parent_h3_trace") or previous),
    }
    state = deepcopy(scene.creative)
    takes = state.get("video_takes") or []
    base = value.get("base_trace") or {}
    if base.get("key") and not any(t.get("key") == base["key"] for t in takes):
        takes.append(deepcopy(base))
    if not any(t.get("key") == previous["key"] for t in takes):
        takes.append(previous)
    history = state.get("review_history") or []
    if state.get("review"):
        history.append(state["review"])
    state.update(
        video=trace,
        video_takes=[*takes, trace],
        review_history=history,
        review={"status": "pending", "checks": {}, "notes": "选用本地视频修正后需重新逐镜验收", "issues": []},
    )
    scene.video_key, scene.status, scene.last_error = asset.object_key, "done", None
    await flow.save_state(db, scene, state, "scene")

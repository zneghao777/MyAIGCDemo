"""Keep imported performances distinct from synthesized voices and preserve exact line binding."""

import tempfile
from copy import deepcopy
from pathlib import Path

from app.core.errors import AppError
from app.models import Candidate

from . import creative as flow
from .media import probe, run_ffmpeg
from .resources import save_asset


async def audio_asset(db, project_id, upload, kind, maximum=120):
    raw = await upload.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise AppError("PAYLOAD_TOO_LARGE", "录音上限 20 MB", 413)

    async def checkpoint():
        pass

    with tempfile.TemporaryDirectory(prefix="cineai-audio-import-") as folder:
        source, output = Path(folder) / "source", Path(folder) / "audio.mp3"
        source.write_bytes(raw)
        duration = await probe(source)
        if not 0.1 <= duration <= maximum:
            raise AppError("INVALID_MEDIA", f"录音时长需要 0.1 至 {maximum} 秒", 422)
        await run_ffmpeg(
            [
                "-i",
                str(source),
                "-vn",
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=7,aformat=sample_fmts=s16:sample_rates=48000",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "libmp3lame",
                str(output),
            ],
            checkpoint,
        )
        return await save_asset(
            db,
            project_id,
            kind,
            output.read_bytes(),
            "audio/mpeg",
            "mp3",
            duration_ms=round(await probe(output) * 1000),
        )


async def import_line(db, project, scene, line_id, upload):
    _, inputs = await flow.shot_inputs(db, scene)
    line = next((x for x in inputs if x["line"]["id"] == line_id), None)
    if not line:
        raise AppError("INVALID_LINE", "录音必须绑定当前分镜已有的台词", 422)
    asset = await audio_asset(db, project.id, upload, "original-dialogue")
    segment = {
        **line,
        "key": asset.object_key,
        "duration_ms": asset.duration_ms,
        "provider": "source-audio",
        "model": "original-audio",
        "strategy": "source-audio-v1",
        "speed": 1,
        "pitch": 0,
        "emotion": "original",
        "source_filename": Path(upload.filename or "audio").name,
        "take_id": asset.id,
    }
    available = {
        x["fingerprint"]: deepcopy(x) for x in (scene.creative.get("audio") or {}).get("segments", [])
    }
    available[line["fingerprint"]] = segment
    segments, current, offset = [], [], 0
    for inp in inputs:
        if inp["fingerprint"] in available:
            item = available[inp["fingerprint"]]
            item["start_ms"] = offset
            offset += item["duration_ms"] + round(item["line"]["pause_after"] * 1000)
            segments.append(item)
            current.append(inp)
    fingerprint = flow.digest({"lines": current})
    audio = {"segments": segments, "duration_ms": offset, "fingerprint": fingerprint}
    # Only complete candidates may be selected as a complete shot performance.
    if len(current) == len(inputs):
        candidate = Candidate(
            project_id=project.id,
            entity_id=scene.id,
            kind="shot_audio",
            fingerprint=fingerprint,
            data={**audio, "request": {}, "source": "original-dialogue-upload"},
        )
        db.add(candidate)
        await db.flush()
        audio["candidate_id"] = candidate.id
    await flow.save_state(db, scene, {**scene.creative, "audio": audio}, "scene")
    scene.audio_duration_ms = offset
    scene.duration_sec = max(scene.creative["shot"]["duration"], offset / 1000 + 0.3)
    return scene.creative

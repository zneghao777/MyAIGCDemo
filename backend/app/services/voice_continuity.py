"""One continuous performance per character; exact alignment before scene replacement."""

from copy import deepcopy
from pathlib import Path
import tempfile
import math
import unicodedata

from sqlalchemy import select
from app.core.errors import AppError
from app.models import Candidate, Character, Scene
from app.providers import providers
from .resources import require, children, save_asset
from .media import run_ffmpeg, probe


def spoken(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def align_lines(texts, subtitles, duration_ms):
    """Never guess boundaries by text length: every spoken character must match."""
    if not isinstance(subtitles, list) or not subtitles:
        raise AppError("ALIGNMENT_REQUIRED", "缺少可用的字幕时间戳；原始配音已保留，请重试切分", 422)
    # MiniMax nests word timestamps within sentence records. Older responses
    # use sentence timestamps; both are accepted only with exact boundaries.
    normalized = []
    for item in subtitles:
        if item.get("timestamped_words"):
            normalized.extend(
                {"text": word["word"], "start": word["time_begin"], "end": word["time_end"]}
                for word in item["timestamped_words"]
            )
        else:
            normalized.append(
                {
                    "text": item.get("text", ""),
                    "start": item.get("start", item.get("time_begin")),
                    "end": item.get("end", item.get("time_end")),
                }
            )
    subtitles = normalized
    words, cursor, previous_end = [], 0, 0
    for item in subtitles:
        text = spoken(item.get("text", ""))
        if not text:
            continue
        start, end = item.get("start"), item.get("end")
        if (
            not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not math.isfinite(start)
            or not math.isfinite(end)
            or start < previous_end
            or end <= start
            or end > duration_ms + 100
        ):
            raise AppError("ALIGNMENT_INVALID", "字幕时间戳不完整或顺序异常，未替换原配音", 422)
        words.append((cursor, cursor + len(text), start, end))
        cursor += len(text)
        previous_end = end
    expected = [spoken(t) for t in texts]
    if any(not t for t in expected) or "".join(expected) != "".join(
        spoken(x.get("text", "")) for x in subtitles
    ):
        raise AppError("ALIGNMENT_MISMATCH", "字幕与台词不完全对应，已保留整段候选但未切分替换", 422)
    spans, cursor = [], 0
    for text in expected:
        left, right = cursor, cursor + len(text)
        covered = [w for w in words if w[0] >= left and w[1] <= right]
        if not covered or covered[0][0] != left or covered[-1][1] != right:
            raise AppError("ALIGNMENT_BOUNDARY", "字幕跨越台词边界，无法安全切分，未替换原配音", 422)
        spans.append((covered[0][2], covered[-1][3]))
        cursor = right
    # Keep a little breathing room without including speech from the next line.
    return [
        (
            max(0, start - min(80, (start - spans[i - 1][1]) / 2)) if i else 0,
            min(duration_ms, end + min(120, (spans[i + 1][0] - end) / 2))
            if i + 1 < len(spans)
            else duration_ms,
        )
        for i, (start, end) in enumerate(spans)
    ]


async def role_input(db, p, target):
    from . import creative as flow

    character = await require(db, Character, target)
    if character.project_id != p.id:
        raise AppError("INVALID_TARGET", "角色不属于本项目", 422)
    if not p.creative.get("shots_confirmed") or not character.creative.get("confirmed"):
        raise AppError("CONFIRMATION_REQUIRED", "先定稿角色并确认分镜，再生成整段配音", 409)
    if character.creative["persona"].get("voice_mode") != "stable":
        raise AppError("VOICE_MODE_REQUIRED", "请先在角色声音设定中选择稳定模式并定稿", 409)
    lines = []
    for sc in await children(db, Scene, p.id):
        _, scene_lines = await flow.shot_inputs(db, sc)
        for line in scene_lines:
            if line["line"]["speaker_id"] == target:
                lines.append({**line, "scene_id": sc.id})
    if any(x.get("provider") == "source-audio" for x in lines):
        raise AppError(
            "SOURCE_AUDIO_REQUIRED", "该角色使用原声录音，请上传各句录音，或先选定可合成的音色", 409
        )
    if not lines:
        raise AppError("NO_DIALOGUE", "这个角色还没有台词", 422)
    signature = lambda x: (x["voice_id"], x["model"], x["speed"], x.get("pitch", 0), x.get("emotion"))
    if len({signature(x) for x in lines}) != 1:
        raise AppError("VOICE_REVISION_MISMATCH", "分镜引用了不同声音版本，请重新定稿角色并确认分镜", 409)
    if sum(len(x["line"]["text"]) + 8 for x in lines) > 3000:
        raise AppError("ROLE_TEXT_LIMIT", "整段配音目前支持每个角色最多 3000 字，请拆为较短的剧集", 422)
    return {"lines": lines, "strategy": "role-continuous-v1"}


async def generate_role(db, task, inp, checkpoint, report):
    from .creative import digest

    fingerprint = digest(inp)
    request = task.payload["creative"]["request"]
    nonce = request.get("nonce", "")
    takes = await db.scalars(
        select(Candidate)
        .where(
            Candidate.project_id == task.project_id,
            Candidate.entity_id == task.payload["creative"]["target"],
            Candidate.fingerprint == fingerprint,
            Candidate.kind == "role_take",
        )
        .order_by(Candidate.created_at.desc())
    )
    take = next((x for x in takes if x.data.get("nonce", "") == nonce), None)
    with tempfile.TemporaryDirectory(prefix="cineai-role-") as folder:
        root = Path(folder)
        source = root / "take.mp3"
        if take:
            raw = await providers().storage.get(take.data["key"])
            subtitles = take.data["subtitles"]
        else:
            await checkpoint()
            await report(10, "同角色台词整段生成，保持同一次声音表演")
            first = inp["lines"][0]
            raw, subtitles = await providers().tts.synthesize_aligned(
                "<#0.5#>\n".join(x["line"]["text"] for x in inp["lines"]),
                first["voice_id"],
                {k: first[k] for k in ("model", "speed", "emotion", "pitch")},
            )
            source.write_bytes(raw)
            duration = round(await probe(source) * 1000)
            asset = await save_asset(
                db, task.project_id, "role-take", raw, "audio/mpeg", "mp3", duration_ms=duration
            )
            take = Candidate(
                project_id=task.project_id,
                entity_id=task.payload["creative"]["target"],
                kind="role_take",
                fingerprint=fingerprint,
                task_id=task.id,
                data={
                    "key": asset.object_key,
                    "subtitles": subtitles,
                    "duration_ms": duration,
                    "nonce": nonce,
                },
            )
            db.add(take)
            await db.commit()  # Alignment retries must not pay for the same recording again.
        source.write_bytes(raw)
        if isinstance(subtitles, dict):
            from app.providers.minimax import fetch_subtitles

            if not subtitles.get("url"):
                raise AppError("ALIGNMENT_REQUIRED", "模型未返回字幕时间戳，原始录音已保留", 422)
            subtitles = await fetch_subtitles(subtitles["url"])
            take.data = {**take.data, "subtitles": subtitles}
            await db.commit()
        spans = align_lines([x["line"]["text"] for x in inp["lines"]], subtitles, take.data["duration_ms"])
        normalized = root / "normalized.mp3"
        await run_ffmpeg(
            [
                "-i",
                str(source),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=7",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "libmp3lame",
                str(normalized),
            ],
            checkpoint,
        )
        segments = []
        for i, (line, (start, end)) in enumerate(zip(inp["lines"], spans)):
            await report(40 + int(50 * i / len(spans)), f"按字幕切分台词 {i + 1}/{len(spans)}")
            dest = root / f"{i}.mp3"
            await run_ffmpeg(
                [
                    "-i",
                    str(normalized),
                    "-ss",
                    str(start / 1000),
                    "-t",
                    str((end - start) / 1000),
                    "-c:a",
                    "libmp3lame",
                    str(dest),
                ],
                checkpoint,
            )
            duration = round(await probe(dest) * 1000)
            asset = await save_asset(
                db,
                task.project_id,
                "line-audio",
                dest.read_bytes(),
                "audio/mpeg",
                "mp3",
                duration_ms=duration,
            )
            segments.append(
                {
                    **line,
                    "key": asset.object_key,
                    "duration_ms": duration,
                    "take_id": task.id,
                    "strategy": "role-continuous-v1",
                    "source_start_ms": start,
                    "source_end_ms": end,
                }
            )
        return {
            "segments": segments,
            "key": take.data["key"],
            "duration_ms": take.data["duration_ms"],
            "voice_id": inp["lines"][0]["voice_id"],
            "mode": "continuous",
        }


async def select_role(db, p, candidate):
    from . import creative as flow

    from app.services.locking import locked_scene

    replacements = {(x["scene_id"], x["line"]["id"]): x for x in candidate.data["segments"]}
    for sc in await children(db, Scene, p.id):
        if not any(sid == sc.id for sid, _ in replacements):
            continue
        _, sc = await locked_scene(db, sc.id, check_idle=False)
        _, expected = await flow.shot_inputs(db, sc)
        state = deepcopy(sc.creative)
        previous = {x["line"]["id"]: x for x in (state.get("audio") or {}).get("segments", [])}
        segments, actual_inputs, offset = [], [], 0
        for line in expected:
            seg = replacements.get((sc.id, line["line"]["id"]), previous.get(line["line"]["id"]))
            if not seg or seg["fingerprint"] != line["fingerprint"]:
                continue
            seg = {**deepcopy(seg), "start_ms": offset}
            offset += seg["duration_ms"] + round(seg["line"]["pause_after"] * 1000)
            segments.append(seg)
            actual_inputs.append(line)
        state["audio"] = {
            "segments": segments,
            "duration_ms": offset,
            "fingerprint": flow.digest({"lines": actual_inputs}),
            "candidate_id": candidate.id,
        }
        sc.audio_duration_ms = offset
        sc.duration_sec = max(state["shot"]["duration"], offset / 1000 + 0.3)
        await flow.save_state(db, sc, state, "scene")

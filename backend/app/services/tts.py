import re
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.providers import providers

from .media import probe, run_ffmpeg


def split_text(text, limit):
    pieces = []
    current = ""
    for part in re.split(r"(?<=[。！？；.!?\n])", text):
        for start in range(0, len(part), limit):
            chunk = part[start : start + limit]
            if len(current) + len(chunk) > limit:
                if current:
                    pieces.append(current)
                current = ""
            current += chunk
    if current:
        pieces.append(current)
    return pieces


async def synthesize(text, voice, checkpoint, performance=None):
    if not text.strip():
        return None, 0
    if (
        get_settings().tts_provider == "mimo"
        and (performance or {}).get("model") == get_settings().mimo_tts_clone_model
    ):
        reference = (performance or {}).get("reference") or {}
        if not reference.get("key"):
            raise AppError(
                "VOICE_REFERENCE_REQUIRED", "该角色缺少已锁定的声音参考，请重新选用并定稿声音", 409
            )
        await checkpoint()
        raw = await providers().storage.get(reference["key"])
        # Only the in-memory provider request carries audio bytes, never task JSON.
        performance = {**performance, "reference_audio": raw}
    with tempfile.TemporaryDirectory(prefix="cineai-tts-") as folder:
        root = Path(folder)
        paths = []
        for i, part in enumerate(split_text(text, get_settings().tts_max_chars)):
            await checkpoint()
            raw = (
                await providers().tts.synthesize(part, voice, performance)
                if performance
                else await providers().tts.synthesize(part, voice)
            )
            path = root / f"{i}.mp3"
            path.write_bytes(raw)
            paths.append(path)
        output = paths[0]
        if len(paths) > 1:
            listing = root / "list.txt"
            listing.write_text("\n".join(f"file '{p.name}'" for p in paths))
            output = root / "merged.mp3"
            await run_ffmpeg(
                ["-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "libmp3lame", str(output)],
                checkpoint,
            )
        normalized = root / "normalized.mp3"
        await run_ffmpeg(
            [
                "-i",
                str(output),
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
        duration = await probe(normalized)
        return normalized.read_bytes(), round(duration * 1000)


async def normalize_sample(raw, checkpoint):
    """Compact MP3 shared by audition and future cloning, without cropping speech."""
    with tempfile.TemporaryDirectory(prefix="cineai-voice-sample-") as folder:
        source, output = Path(folder) / "input", Path(folder) / "sample.mp3"
        source.write_bytes(raw)
        await run_ffmpeg(
            [
                "-i",
                str(source),
                "-vn",
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=7",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                str(output),
            ],
            checkpoint,
        )
        audio = output.read_bytes()
        from app.providers.mimo import reference_data_url

        reference_data_url(audio)
        return audio, round(await probe(output) * 1000)

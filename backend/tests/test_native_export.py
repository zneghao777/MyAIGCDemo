"""Real FFmpeg checks for native geometry, speed and explicit duration choices."""

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.schemas import ExportSettings
from app.services import compose, media


def source_movie(path, size="864x480", seconds=2):
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        f"color=c=red:s={size}:r=24:d={seconds}", "-vf",
        "drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='gte(t,1)'",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True)
    return path.read_bytes()


def scene(key="one", duration=2.2, audio=None):
    return SimpleNamespace(id=key, video_key=key, first_frame_key=None, creative={},
                           audio_key=audio, narration_key=None, duration_sec=duration,
                           dialogue="", narration="", sound_effect_assets=[])


async def render(monkeypatch, objects, scenes, **settings):
    storage = SimpleNamespace(get=AsyncMock(side_effect=lambda key: objects[key]))
    monkeypatch.setattr(compose, "providers", lambda: SimpleNamespace(storage=storage))
    return await compose.compose(SimpleNamespace(ratio="16:9"), scenes,
                                 ExportSettings(**settings).model_dump(), AsyncMock(), AsyncMock())


def pixel(path, at, x=430, y=240):
    return subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path), "-frames:v", "1",
        "-vf", f"crop=2:2:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])[:3]


@pytest.mark.parametrize("tier", ["source", "480P", "768P", "1080P", "2K", "4K", "720p", "1080p"])
def test_resolution_schema_and_portrait_canvas(tier):
    assert ExportSettings(resolution=tier).resolution == tier
    if tier != "source":
        landscape = media.dimensions(tier, "16:9")
        portrait = media.dimensions(tier, "9:16")
        assert landscape == tuple(reversed(portrait))
        assert all(x > 0 and x % 2 == 0 for x in landscape)


def test_reject_unknown_policies():
    for settings in [{"resolution": "8K"}, {"fit_mode": "stretch"}, {"timing_mode": "retime"}]:
        with pytest.raises(ValidationError):
            ExportSettings(**settings)


@pytest.mark.parametrize("mode,expected", [("source", 2), ("planned", 2.2)])
async def test_normal_speed_native_export(monkeypatch, tmp_path, mode, expected):
    raw = source_movie(tmp_path / "source.mp4")
    movie, _, _, duration, logs = await render(monkeypatch, {"one": raw}, [scene()], timing_mode=mode, subtitles=False)
    path = tmp_path / "out.mp4"
    path.write_bytes(movie)
    meta = await media.probe_video(path)
    assert (meta["width"], meta["height"]) == (864, 480)
    assert abs(meta["duration"] - expected) < .06
    assert duration == expected
    # The colour transition is at the same presentation time in both sources.
    # Old implicit 1.1x PTS retiming would still show red at 1.045 seconds.
    for at, blue in [(.8, False), (1.045, True)]:
        rgb = pixel(path, at)
        assert (rgb[2] > rgb[0]) == blue
    assert all(log.get("playbackSpeed", 1) == 1 for log in logs if isinstance(log, dict))
    assert not any("setpts=" in str(log.get("retime", "")) for log in logs if isinstance(log, dict))


async def test_mixed_ratio_padding_preserves_complete_picture(monkeypatch, tmp_path):
    objects = {"one": source_movie(tmp_path / "wide.mp4", seconds=.25),
               "two": source_movie(tmp_path / "tall.mp4", size="480x864", seconds=.25)}
    movie, _, _, _, logs = await render(monkeypatch, objects, [scene(), scene("two")], subtitles=False)
    path = tmp_path / "mixed.mp4"
    path.write_bytes(movie)
    assert (await media.probe_video(path))["width"] == 864
    assert max(pixel(path, .35, x=4)) < 15  # black side bar, not widened portrait
    assert pixel(path, .35)[0] > 200
    assert logs[0]["fitMode"] == "pad"


@pytest.mark.parametrize("tier,expected", [("480P", (864, 480)), ("768P", (1366, 768)),
                                          ("1080P", (1920, 1080)), ("2K", (2560, 1440)),
                                          ("4K", (3840, 2160))])
async def test_actual_output_tiers(monkeypatch, tmp_path, tier, expected):
    raw = source_movie(tmp_path / "small.mp4", seconds=.125)
    movie, _, _, _, _ = await render(monkeypatch, {"one": raw}, [scene()], resolution=tier, subtitles=False)
    path = tmp_path / "out.mp4"
    path.write_bytes(movie)
    meta = await media.probe_video(path)
    assert (meta["width"], meta["height"]) == expected


async def test_voice_overrun_does_not_slow_video_or_cut_words(monkeypatch, tmp_path):
    raw = source_movie(tmp_path / "source.mp4")
    audio = tmp_path / "voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2.4", str(audio)], check=True)
    with pytest.raises(AppError) as error:
        await render(monkeypatch, {"one": raw, "voice": audio.read_bytes()}, [scene(audio="voice")], subtitles=False)
    assert error.value.code == "AUDIO_EXCEEDS_VIDEO"


async def test_non_square_pixels_keep_display_shape(monkeypatch, tmp_path):
    source_movie(tmp_path / "raw.mp4", size="720x576", seconds=.125)
    anamorphic = tmp_path / "sar.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp_path / "raw.mp4"),
                    "-vf", "setsar=16/15", "-c:v", "libx264", str(anamorphic)], check=True)
    movie, _, _, _, _ = await render(monkeypatch, {"one": anamorphic.read_bytes()}, [scene()], subtitles=False)
    path = tmp_path / "out.mp4"
    path.write_bytes(movie)
    meta = await media.probe_video(path)
    assert (meta["width"], meta["height"]) == (768, 576)
    # A black bar here would mean SAR was dropped before scaling, squeezing the picture.
    assert pixel(path, .04, x=4)[0] > 200

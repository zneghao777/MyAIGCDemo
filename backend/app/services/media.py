import asyncio
import json
import math
from fractions import Fraction
from app.core.config import get_settings
from app.core.errors import AppError


async def probe(path):
    proc = await asyncio.create_subprocess_exec(
        get_settings().ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    if proc.returncode:
        raise AppError("INVALID_MEDIA", "媒体无法解码", 422)
    duration = float(json.loads(out)["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise AppError("INVALID_MEDIA", "媒体时长不合法", 422)
    return duration


async def probe_video(path):
    proc = await asyncio.create_subprocess_exec(
        get_settings().ffprobe_path, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,sample_aspect_ratio,duration:format=duration",
        "-of", "json", str(path), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    try:
        if proc.returncode:
            raise ValueError
        meta = json.loads(out)
        stream = meta["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        sar = stream.get("sample_aspect_ratio") or "1:1"
        sar = Fraction(sar.replace(":", "/")) if sar not in ("N/A", "0:1") else Fraction(1)
        raw_duration = stream.get("duration")
        duration = float(raw_duration if raw_duration not in (None, "N/A") else meta["format"]["duration"])
        if width <= 0 or height <= 0 or sar <= 0 or not math.isfinite(duration) or duration <= 0:
            raise ValueError
    except (ValueError, KeyError, IndexError, TypeError, ZeroDivisionError):
        raise AppError("INVALID_MEDIA", "视频尺寸或时长不合法", 422)
    # Square pixels preserve display geometry even for anamorphic imported sources.
    display_width = max(2, round(width * float(sar) / 2) * 2)
    return {"width": display_width, "height": max(2, round(height / 2) * 2), "duration": duration}


async def run_ffmpeg(args, checkpoint, progress=None, duration=1):
    proc = await asyncio.create_subprocess_exec(
        get_settings().ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-threads",
        "2",
        "-filter_threads",
        "1",
        "-filter_complex_threads",
        "1",
        *args,
        "-progress",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Drain stderr concurrently to avoid pipe deadlocks; retain a bounded tail.
    tail = bytearray()

    async def drain():
        while chunk := await proc.stderr.read(4096):
            tail.extend(chunk)
            if len(tail) > 8192:
                del tail[:-8192]

    reader = asyncio.create_task(drain())

    async def watch():
        while proc.returncode is None:
            await checkpoint()
            await asyncio.sleep(0.3)

    watcher = asyncio.create_task(watch())

    async def consume():
        async for line in proc.stdout:
            if progress and line.startswith(b"out_time_us="):
                value = line.strip().split(b"=")[1]
                if value.isdigit():
                    await progress(min(0.99, int(value) / 1_000_000 / duration))
        await proc.wait()

    consumer = asyncio.create_task(consume())
    try:
        done, _ = await asyncio.wait({watcher, consumer}, timeout=880, return_when=asyncio.FIRST_COMPLETED)
        if not done:
            raise AppError("COMPOSE_TIMEOUT", "媒体处理超时", 504)
        for finished in done:
            finished.result()
        if proc.returncode:
            raise AppError(
                "FFMPEG_ERROR",
                "媒体合成失败，请检查 ffmpeg、字体与素材",
                502,
                {"stderr": tail.decode(errors="replace")[-2000:]},
            )
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 3)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        watcher.cancel()
        consumer.cancel()
        await asyncio.gather(watcher, consumer, reader, return_exceptions=True)


def dimensions(resolution, ratio):
    if resolution == "480P":
        # H3's actual native 480P raster is slightly wider than exact 16:9.
        return {"21:9": (1120, 480), "16:9": (864, 480), "4:3": (640, 480),
                "1:1": (480, 480), "3:4": (480, 640), "9:16": (480, 864)}[ratio]
    short = {"768P": 768, "720p": 720, "1080P": 1080, "1080p": 1080, "2K": 1440, "4K": 2160}[resolution]
    a, b = (int(x) for x in ratio.split(":"))
    long = max(2, round(short * max(a, b) / min(a, b) / 2) * 2)
    return (short, long) if a < b else (long, short)


def fit_filter(width, height, mode="pad"):
    normalize = "scale=w='max(2,round(iw*if(gt(sar,0),sar,1)/2)*2)':h=ih,setsar=1,"
    if mode == "crop":
        return normalize + f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    return (normalize + f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")


def motion_filter(scene, width, height, fps, duration):
    frames = max(1, round(fps * duration))
    denominator = max(frames - 1, 1)
    move = scene.camera_move
    z = "1"
    x = "iw/2-iw/zoom/2"
    y = "ih/2-ih/zoom/2"
    if move == "缓推":
        z = f"1+0.25*on/{denominator}"
    elif move == "拉远":
        z = f"1.25-0.25*on/{denominator}"
    elif move in ("缓慢横移", "摇镜", "跟随"):
        z = "1.15"
        reverse = False
        data = scene.director_data or {}
        cameras = {
            o["id"]
            for o in data.get("objects", [])
            if o.get("kind") == ("actor" if move == "跟随" else "camera")
        }
        keys = sorted(
            [k for k in data.get("keyframes", []) if k.get("objectId") in cameras], key=lambda k: k["t"]
        )
        if len(keys) > 1:
            reverse = keys[-1]["position"][0] < keys[0]["position"][0]
        x = "(iw-iw/zoom)*" + (f"(1-on/{denominator})" if reverse else f"on/{denominator}")
    return (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,crop={width * 2}:{height * 2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},setsar=1"
    )


def ass_time(seconds):
    n = round(seconds * 100)
    return f"{n // 360000}:{n // 6000 % 60:02}:{n // 100 % 60:02}.{n % 100:02}"


def subtitles(path, entries, width, height):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,PingFang SC,{max(24, width // 25)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,50,50,{height // 12},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for start, end, text in entries:
        # Remove ASS control syntax from user input.
        clean = (
            text.replace("\\", "").replace("{", "").replace("}", "").replace("\r", "").replace("\n", r"\N")
        )
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{clean}")
    path.write_text(header + "\n".join(lines), encoding="utf-8")


async def has_subtitle_filter():
    proc = await asyncio.create_subprocess_exec(
        get_settings().ffmpeg_path,
        "-hide_banner",
        "-filters",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return b" subtitles " in out


def render_caption(path, text, width, height):
    from PIL import Image, ImageDraw, ImageFont
    from pathlib import Path

    candidates = [
        get_settings().subtitle_font_path,
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    font_path = next((p for p in candidates if p and Path(p).exists()), None)
    if not font_path:
        raise AppError("FONT_REQUIRED", "缺少中文字体，请配置 SUBTITLE_FONT_PATH", 422)
    font = ImageFont.truetype(font_path, max(24, width // 25))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lines = []
    line = ""
    for ch in text:
        if ch == "\n" or draw.textlength(line + ch, font=font) > width * 0.85:
            lines.append(line)
            line = ""
        if ch != "\n":
            line += ch
    if line:
        lines.append(line)
    size = max(24, width // 25)
    y = height - height // 12 - len(lines) * int(size * 1.4)
    for line in lines:
        draw.text(
            (width / 2, y), line, font=font, fill="white", stroke_width=2, stroke_fill="black", anchor="mt"
        )
        y += int(size * 1.4)
    image.save(path)

import tempfile
from pathlib import Path

from app.core.config import ROOT, get_settings
from app.core.errors import AppError
from app.providers import providers

from .media import (
    dimensions,
    has_subtitle_filter,
    motion_filter,
    probe,
    probe_video,
    fit_filter,
    render_caption,
    run_ffmpeg,
    subtitles,
)


async def compose(project, scenes, settings, checkpoint, report):
    fps = settings["fps"]
    logs = []
    with tempfile.TemporaryDirectory(prefix="cineai-compose-") as folder:
        root = Path(folder)
        clips = []
        entries = []
        total = 0
        # Probe the delivered raster, not the requested H3 tier (upscaling can fall back).
        source_paths = {}
        source_meta = {}
        if settings.get("source_mode") != "storyboard":
            for index, scene in enumerate(scenes):
                if scene.video_key:
                    path = root / f"{index}.source.mp4"
                    path.write_bytes(await providers().storage.get(scene.video_key))
                    source_paths[scene.id] = path
                    source_meta[scene.id] = await probe_video(path)
                    await checkpoint()
        resolution = settings.get("resolution", "source")
        first = next(iter(source_meta.values()), None)
        if resolution == "source" and first:
            width, height = first["width"], first["height"]
        elif resolution == "source":
            # A static preview has no delivered video; use the configured H3 tier.
            tier = (((getattr(scenes[0], "creative", None) or {}).get("shot") or {}).get("video_input") or {}).get("resolution", "480P")
            width, height = dimensions(tier if tier in ("480P", "768P", "1080P", "2K", "4K") else "480P", project.ratio)
        else:
            width, height = dimensions(resolution, project.ratio)
            requested_short = min(width, height)
            if first and min(first["width"], first["height"]) == requested_short:
                width, height = first["width"], first["height"]
        geometry = fit_filter(width, height, settings.get("fit_mode", "pad"))
        logs.append({"outputWidth": width, "outputHeight": height, "resolution": resolution,
                     "fitMode": settings.get("fit_mode", "pad"),
                     "timingMode": settings.get("timing_mode", "source"),
                     "note": "保留原速；导出缩放不调用模型或超分服务"})

        async def render_intro():
            nonlocal total
            source = ROOT / "public/assets/intro.mp4"
            if not source.exists():
                logs.append("片头素材不存在，已跳过")
                return
            duration = await probe(source)
            target = root / "intro.mp4"
            await run_ffmpeg(
                [
                    "-i",
                    str(source),
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a",
                    "-vf",
                    f"{geometry},fps={fps}",
                    "-t",
                    str(duration),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(target),
                ],
                checkpoint,
            )
            clips.append(target)
            total = duration

        if settings.get("intro"):
            await render_intro()
        for index, scene in enumerate(scenes):
            await checkpoint()
            await report(20 + int(45 * index / max(1, len(scenes))), f"拼接分镜 {index + 1}/{len(scenes)}")
            image = root / f"{index}.png"
            video = source_paths.get(scene.id, root / f"{index}.source.mp4")
            use_video = bool(scene.video_key) and settings.get("source_mode") != "storyboard"
            shot = (getattr(scene, "creative", None) or {}).get("shot") or {}
            model_audio = use_video and ((getattr(scene, "creative", None) or {}).get("video") or {}).get("sound_strategy", (shot.get("video_input") or {}).get("sound_strategy")) == "model_audio"
            if not use_video and scene.first_frame_key:
                image.write_bytes(await providers().storage.get(scene.first_frame_key))
            elif not use_video:
                raise AppError("FIRST_FRAME_REQUIRED", f"分镜 {index + 1} 缺少首帧图", 409)
            audios = []
            lengths = []
            creative_audio = ((getattr(scene, "creative", None) or {}).get("audio") or {}).get("segments")
            keys = (
                [x["key"] for x in creative_audio]
                if creative_audio is not None
                else [scene.audio_key, scene.narration_key]
            )
            if model_audio:
                keys = []
                logs.append(
                    {
                        "sceneId": scene.id,
                        "soundStrategy": "model_audio",
                        "postAudio": "已明确停用，保留模型音轨",
                    }
                )
            for n, key in enumerate(keys):
                if key:
                    path = root / f"{index}-{n}.mp3"
                    path.write_bytes(await providers().storage.get(key))
                    audios.append(path)
                    lengths.append(await probe(path))
                    if creative_audio is not None:
                        pause = creative_audio[n]["line"]["pause_after"]
                        # Normalize every clip to the measured duration plus exact pause.
                        # PCM avoids cumulative MP3 encoder padding changing subtitle offsets.
                        padded = root / f"{index}-{n}-padded.wav"
                        span = creative_audio[n]["duration_ms"] / 1000 + pause
                        await run_ffmpeg(
                            [
                                "-i",
                                str(path),
                                "-af",
                                "apad",
                                "-t",
                                str(span),
                                "-c:a",
                                "pcm_s16le",
                                str(padded),
                            ],
                            checkpoint,
                        )
                        audios[-1] = padded
                        lengths[-1] = span
            duration = max(scene.duration_sec, sum(lengths) + 0.3 if lengths else 0)
            if use_video:
                source_duration = source_meta[scene.id]["duration"]
                edit = (getattr(scene, "creative", None) or {}).get("edit") or {}
                in_sec = edit.get("in_sec", 0)
                out_sec = edit.get("out_sec", source_duration)
                if not 0 <= in_sec < out_sec <= source_duration + .05:
                    raise AppError("INVALID_EDIT_RANGE", "采用区间超出实际视频，请重新调整", 409)
                source_duration = out_sec - in_sec
                duration = source_duration if settings.get("timing_mode", "source") == "source" else scene.duration_sec
                if sum(lengths) > duration + 0.05:
                    raise AppError("AUDIO_EXCEEDS_VIDEO", f"分镜 {index + 1} 配声含停顿 {sum(lengths):.2f} 秒，超过镜头 {duration:.2f} 秒；请调整配声或镜头时长，导出不会自动变速", 409)
            logs.append({"sceneId": scene.id, "requestedSec": scene.duration_sec, "alignedSec": duration})
            clip = root / f"clip{index}.mp4"
            args = (
                ["-ss", str(in_sec), "-t", str(source_duration), "-i", str(video)]
                if use_video
                else (
                    ["-loop", "1", "-i", str(image)]
                    if settings.get("source_mode") == "storyboard"
                    else ["-i", str(image)]
                )
            )
            for audio in audios:
                args += ["-i", str(audio)]
            if use_video:
                timing = f"tpad=stop_mode=clone:stop_duration={max(0, duration - source_duration)}"
                vf = f"{geometry},fps={fps},setpts=PTS-STARTPTS,{timing}"
            else:
                vf = (
                    f"{geometry},fps={fps}"
                    if settings.get("source_mode") == "storyboard"
                    else motion_filter(scene, width, height, fps, duration)
                )
            if model_audio:
                audio_filter = "[0:a]apad[a]"
            elif not audios:
                args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                audio_filter = "[1:a]anull[a]"
            elif len(audios) == 1:
                audio_filter = "[1:a]apad[a]"
            else:
                audio_filter = (
                    "".join(f"[{n + 1}:a]" for n in range(len(audios)))
                    + f"concat=n={len(audios)}:v=0:a=1,apad[a]"
                )
            effects = getattr(scene, "sound_effect_assets", [])
            if effects:
                audio_filter = audio_filter.removesuffix("[a]") + "[voice]"
                first_effect = 1 + (len(audios) if model_audio else max(1, len(audios)))
                labels = []
                for n, effect in enumerate(effects):
                    path = root / f"{index}-effect{n}.mp3"
                    path.write_bytes(await providers().storage.get(effect["key"]))
                    args += ["-i", str(path)]
                    delay = round(effect["start_sec"] * 1000)
                    label = f"effect{n}"
                    audio_filter += (
                        f";[{first_effect + n}:a]volume={effect['volume']},adelay={delay}|{delay}[{label}]"
                    )
                    labels.append(f"[{label}]")
                audio_filter += f";[voice]{''.join(labels)}amix=inputs={len(effects) + 1}:duration=first:normalize=0,alimiter=limit=0.95:latency=1[a]"
            if settings.get("transition") == "fade":
                vf += f",fade=t=in:d=0.2,fade=t=out:st={max(0, duration - 0.2)}:d=0.2"
            args += [
                "-filter_complex",
                audio_filter,
                "-vf",
                vf,
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-t",
                str(duration),
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(clip),
            ]
            await run_ffmpeg(args, checkpoint)
            clips.append(clip)
            offset = total
            texts = (
                [x["line"]["text"] for x in creative_audio]
                if creative_audio is not None
                else [scene.dialogue, scene.narration]
            )
            cues = shot.get("subtitle_cues", [])
            if cues:
                for cue in sorted(cues, key=lambda x: x["start_sec"]):
                    if cue["start_sec"] < duration:
                        entries.append((total + cue["start_sec"], total + min(duration, cue["end_sec"]), cue["text"]))
                logs.append(
                    {
                        "sceneId": scene.id,
                        "subtitleTiming": "人工校准"
                        if shot.get("subtitles_calibrated")
                        else "人工草稿，待校准",
                    }
                )
            elif model_audio:
                logs.append(
                    {
                        "sceneId": scene.id,
                        "subtitleTiming": "模型音轨缺少可靠分句时间，需人工校准；未伪造自动对齐",
                    }
                )
            else:
                for n, text in enumerate(texts):
                    if text:
                        span = lengths[n] if n < len(lengths) else duration
                        spoken = (
                            creative_audio[n]["duration_ms"] / 1000 if creative_audio is not None else span
                        )
                        start = (
                            creative_audio[n].get("start_ms", round((offset - total) * 1000)) / 1000 + total
                            if creative_audio is not None
                            else offset
                        )
                        entries.append((start, min(total + duration, start + spoken), text))
                        offset += span
                if texts and any(text for text in texts):
                    logs.append({"sceneId": scene.id, "subtitleTiming": "逐条音频实测时长，未做句内自动对齐"})
            voice_span = sum(lengths)
            if not model_audio and voice_span < duration:
                logs.append(
                    {
                        "sceneId": scene.id,
                        "soundGapSec": round(duration - voice_span, 3),
                        "note": "保留真实声音空档，不循环对白",
                    }
                )
            logs.append(
                {
                    "sceneId": scene.id,
                    "sourceMode": "video" if use_video else "storyboard",
                    "sourceVideoDuration": source_duration if use_video else None,
                    "outputDuration": duration,
                    "startSec": total,
                    "endSec": total + duration,
                    "playbackSpeed": 1.0,
                    "retime": "none" if use_video else None,
                    "tailPaddingSec": max(0, duration - source_duration) if use_video else 0,
                    "trimmedTailSec": max(0, source_duration - duration) if use_video else 0,
                }
            )
            total += duration
        listing = root / "list.txt"
        listing.write_text("\n".join(f"file '{p.name}'" for p in clips))
        merged = root / "merged.mp4"
        await run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(merged)], checkpoint
        )
        ass = root / "subtitles.ass"
        subtitles(ass, entries, width, height)
        await report(70, "烧录字幕与混音")
        args = ["-i", str(merged)]
        filters = []
        video_label = "0:v"
        audio_label = "0:a"
        input_index = 1
        if settings.get("subtitles"):
            if await has_subtitle_filter():
                filters.append(f"[0:v]subtitles=filename='{ass.as_posix()}'[sub]")
                video_label = "sub"
            else:
                logs.append("ffmpeg 无 libass，使用中文字体栅格字幕叠加")
                for n, (start, end, text) in enumerate(entries):
                    caption = root / f"caption{n}.png"
                    render_caption(caption, text, width, height)
                    args += ["-i", str(caption)]
                    filters.append(
                        f"[{video_label}][{input_index}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[sub{n}]"
                    )
                    video_label = f"sub{n}"
                    input_index += 1
        watermark = ROOT / "public/assets/watermark.png"
        if settings.get("watermark"):
            if watermark.exists():
                args += ["-i", str(watermark)]
                filters.append(f"[{video_label}][{input_index}:v]overlay=W-w-24:H-h-24[wm]")
                video_label = "wm"
                input_index += 1
            else:
                logs.append("水印素材不存在，已跳过")
        if settings.get("music"):
            bgm = next(
                (
                    p
                    for p in sorted(get_settings().bgm_dir.glob(settings["mood"] + ".*"))
                    if p.suffix in (".mp3", ".wav", ".m4a")
                ),
                None,
            )
            if settings.get("bgm_key"):
                bgm = root / "selected-bgm.mp3"
                bgm.write_bytes(await providers().storage.get(settings["bgm_key"]))
            if bgm:
                args += ["-stream_loop", "-1", "-i", str(bgm)]
                filters.append(
                    f"[0:a]asplit=2[voice][side];[{input_index}:a]volume=0.3[bg];[bg][side]sidechaincompress=threshold=0.05:ratio=8[duck];[voice][duck]amix=inputs=2:duration=first[aout]"
                )
                audio_label = "aout"
            else:
                logs.append("所选 BGM 素材不存在，已保留配音音轨")
        if filters:
            args += ["-filter_complex", ";".join(filters)]
        args += [
            "-map",
            video_label if ":" in video_label else f"[{video_label}]",
            "-map",
            audio_label if ":" in audio_label else f"[{audio_label}]",
            "-t",
            str(total),
        ]
        webm = settings["format"] == "WebM"
        output = root / ("output.webm" if webm else "output.mp4")
        args += [
            "-c:v",
            "libvpx-vp9" if webm else "libx264",
            "-c:a",
            "libopus" if webm else "aac",
            "-pix_fmt",
            "yuv420p",
        ]
        if not webm:
            args += ["-preset", "veryfast", "-movflags", "+faststart"]
        args += [str(output)]
        last = -1

        async def progress(value):
            nonlocal last
            percent = 70 + int(value * 23)
            if percent > last:
                last = percent
                await report(percent, "编码成片")

        await run_ffmpeg(args, checkpoint, progress, total)
        cover = root / "cover.png"
        await run_ffmpeg(["-i", str(output), "-frames:v", "1", str(cover)], checkpoint)
        return output.read_bytes(), cover.read_bytes(), ass.read_bytes(), total, logs

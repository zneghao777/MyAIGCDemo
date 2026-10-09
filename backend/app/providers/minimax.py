import json
import re
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, TransientProviderError

from .http import fetch_bytes, request

VOICES = {
    "女声 · 冷静": "female-shaonv",
    "女声 · 温柔": "female-yujie",
    "男声 · 沉稳": "male-qn-qingse",
    "男声 · 青年": "male-qn-jingying",
}


class MiniMaxTTS:
    async def synthesize(self, text, voice, performance=None):
        raw, _ = await self._synthesize(text, voice, performance)
        return raw

    async def synthesize_aligned(self, text, voice, performance=None):
        return await self._synthesize(text, voice, performance, aligned=True)

    async def _synthesize(self, text, voice, performance=None, aligned=False):
        s = get_settings()
        performance = performance or {}
        setting = {
            "voice_id": voice,
            "speed": performance.get("speed", 1),
            "vol": 1,
            "pitch": performance.get("pitch", 0),
        }
        if performance.get("emotion") not in (None, "neutral"):
            setting["emotion"] = performance["emotion"]
        response = await request(
            "POST",
            s.minimax_tts_base_url.rstrip("/") + "/v1/t2a_v2",
            retries=0,
            headers={"Authorization": "Bearer " + s.minimax_api_key.get_secret_value()},
            params={"GroupId": s.minimax_group_id} if s.minimax_group_id else {},
            json={
                "model": performance.get("model", s.minimax_tts_model),
                "text": text,
                "stream": False,
                "output_format": "hex",
                **({"subtitle_enable": True, "subtitle_type": "word"} if aligned else {}),
                "voice_setting": setting,
                "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
            },
        )
        result = response.json()
        code = result.get("base_resp", {}).get("status_code", 0)
        if code == 1008:
            raise AppError(
                "PROVIDER_BALANCE_LOW", "MiniMax 余额不足；已生成的声音保留，可充值后继续或导入原声录音", 402
            )
        if code:
            error = TransientProviderError if code in (1001, 1002) else AppError
            raise error("PROVIDER_ERROR", f"MiniMax 返回错误码 {code}", 502)
        data = result.get("data") or {}
        if not data.get("audio") and not data.get("audio_file"):
            raise AppError("PROVIDER_OUTPUT_INVALID", "语音输出为空", 422)
        raw = bytes.fromhex(data["audio"]) if data.get("audio") else await fetch_bytes(data["audio_file"])
        if not raw:
            raise AppError("PROVIDER_OUTPUT_INVALID", "语音输出为空", 422)
        subtitles = []
        if aligned:
            subtitles = {"url": data.get("subtitle_file")}
        return raw, subtitles

    async def clone(self, raw, voice_id):
        """Clone once per stable voice ID; retries reuse the account's existing voice."""
        catalog = await self.voices()
        if any(v.get("voice_id") == voice_id for v in catalog.get("voice_cloning", [])):
            return voice_id
        s = get_settings()
        headers = {"Authorization": "Bearer " + s.minimax_api_key.get_secret_value()}
        root = s.minimax_tts_base_url.rstrip("/")
        uploaded = (
            await request(
                "POST",
                root + "/v1/files/upload",
                retries=0,
                headers=headers,
                data={"purpose": "voice_clone"},
                files={"file": ("reference.wav", raw, "audio/wav")},
            )
        ).json()
        code = uploaded.get("base_resp", {}).get("status_code", 0)
        file_id = (uploaded.get("file") or {}).get("file_id")
        if code or not file_id:
            raise AppError("VOICE_CLONE_UPLOAD_FAILED", f"音色样本上传失败（MiniMax {code}）", 422)
        result = (
            await request(
                "POST",
                root + "/v1/voice_clone",
                retries=0,
                timeout=180,
                headers=headers,
                json={
                    "file_id": file_id,
                    "voice_id": voice_id,
                    "need_noise_reduction": True,
                    "need_volume_normalization": True,
                },
            )
        ).json()
        code = result.get("base_resp", {}).get("status_code", 0)
        if code or result.get("input_sensitive"):
            raise AppError(
                "VOICE_CLONE_UNAVAILABLE", f"音色复刻未成功（MiniMax {code}），请检查账号权限和样本质量", 422
            )
        return voice_id

    async def voices(self):
        s = get_settings()
        response = await request(
            "POST",
            s.minimax_tts_base_url.rstrip("/") + "/v1/get_voice",
            headers={"Authorization": "Bearer " + s.minimax_api_key.get_secret_value()},
            json={"voice_type": "all"},
            retries=0,
        )
        data = response.json()
        if data.get("base_resp", {}).get("status_code", 0):
            raise AppError("VOICE_CATALOG_UNAVAILABLE", "当前账号无法查询音色列表", 502)
        return data

    async def design(self, prompt, text, voice_id):
        s = get_settings()
        response = await request(
            "POST",
            s.minimax_tts_base_url.rstrip("/") + "/v1/voice_design",
            headers={"Authorization": "Bearer " + s.minimax_api_key.get_secret_value()},
            json={"prompt": prompt, "preview_text": text[:500], "voice_id": voice_id},
            retries=0,
        )
        data = response.json()
        code = data.get("base_resp", {}).get("status_code", 0)
        if code:
            raise AppError(
                "VOICE_DESIGN_UNAVAILABLE", f"账号音色设计失败（MiniMax {code}）；可改用匹配预设音色", 422
            )
        if not data.get("voice_id") or not data.get("trial_audio"):
            raise AppError("PROVIDER_OUTPUT_INVALID", "音色设计未返回 voice_id 和试听音频", 422)
        return data["voice_id"], bytes.fromhex(data["trial_audio"])


class DisabledVideo:
    async def create(self, **kwargs):
        raise AppError("FEATURE_DISABLED", "AI 视频生成未启用，请使用分镜动态预演导出", 403)

    async def query(self, task_id):
        return {"status": "failed", "fileUrl": None}


class MiniMaxVideo:
    """CompShare H3: separate credential, stable job identity, no blind paid retries."""

    @staticmethod
    def estimate_points(duration, resolution):
        import math

        from app.services.video_capabilities import CAPABILITIES, validate_duration
        validate_duration(math.ceil(duration))
        rates = CAPABILITIES["rates"]
        if resolution not in rates:
            raise AppError("INVALID_VIDEO_RESOLUTION", "不支持的视频分辨率", 422)
        return math.ceil(duration) * rates[resolution]

    def headers(self):
        return {
            "Authorization": "Bearer " + get_settings().minimax_video_api_key.get_secret_value(),
            "Accept": "application/json",
        }

    async def balance(self):
        s = get_settings()
        response = await request(
            "GET",
            s.minimax_video_base_url.rstrip("/") + "/minimax/v2/query/point_usage_summary",
            headers=self.headers(),
            timeout=15,
            retries=0,
        )
        data = response.json()
        if not isinstance(data.get("available_points"), (int, float)):
            raise AppError("PROVIDER_OUTPUT_INVALID", "积分接口未返回有效余额", 502)
        return data

    @staticmethod
    def validate_content(content):
        from app.services.video_capabilities import CAPABILITIES
        counts = {
            "first_frame": 0,
            "last_frame": 0,
            "reference_image": 0,
            "reference_video": 0,
            "reference_audio": 0,
        }
        texts = []
        for item in content:
            kind = item.get("type")
            if kind == "text":
                texts.append(item.get("text", ""))
                continue
            expected = {
                "image_url": ("first_frame", "last_frame", "reference_image"),
                "video_url": ("reference_video",),
                "audio_url": ("reference_audio",),
            }
            if kind not in expected:
                raise AppError("INVALID_VIDEO_INPUT", "H3 素材类型不合法", 422)
            role = item.get("role") or expected[kind][0]
            if role not in expected[kind] or not (item.get(kind) or {}).get("url"):
                raise AppError("INVALID_VIDEO_INPUT", "H3 素材缺少地址或用途不匹配", 422)
            counts[role] += 1
        prompt = "\n".join(texts)
        if len(prompt) > CAPABILITIES["max_prompt_chars"]:
            raise AppError("INVALID_VIDEO_INPUT", "H3 提示词不能超过 7000 字", 422)
        frame_count = counts["first_frame"] + counts["last_frame"]
        reference_count = sum(counts[k] for k in ("reference_image", "reference_video", "reference_audio"))
        if frame_count and reference_count:
            raise AppError("H3_MODE_CONFLICT", "首尾帧不能与参考图片、视频或音频混用", 422)
        if counts["first_frame"] > 1 or counts["last_frame"] > 1:
            raise AppError("H3_REFERENCE_LIMIT", "首帧和尾帧各最多一张", 422)
        if (
            counts["reference_image"] > CAPABILITIES["max_references"]["image"]
            or counts["reference_video"] > CAPABILITIES["max_references"]["video"]
            or counts["reference_audio"] > CAPABILITIES["max_references"]["audio"]
            or reference_count > CAPABILITIES["max_references"]["total"]
        ):
            raise AppError("H3_REFERENCE_LIMIT", "H3 参考素材超限：图片 9 / 视频 3 / 音频 3 / 合计 12", 422)
        if counts["reference_audio"] and not (counts["reference_image"] or counts["reference_video"]):
            raise AppError("H3_AUDIO_ONLY", "参考音频必须同时提供参考图片或参考视频", 422)
        if not frame_count and not reference_count and not prompt.strip():
            raise AppError("INVALID_VIDEO_INPUT", "文生视频需要非空文本", 422)
        limits = {
            "Picture": counts["reference_image"],
            "Video": counts["reference_video"],
            "Audio": counts["reference_audio"],
        }
        for category, number in re.findall(r"<(Picture|Video|Audio) (\d+)>", prompt):
            if not 1 <= int(number) <= limits[category]:
                raise AppError("H3_REFERENCE_MISSING", f"<{category} {number}> 没有实际传入的素材", 422)
        if re.search(r"@图片\d+|<Image \d+>", prompt):
            raise AppError("H3_REFERENCE_LABEL", "请使用实际素材对应的 <Picture N> 标签", 422)
        return counts

    async def create(
        self,
        prompt,
        image,
        duration,
        ratio,
        *,
        idempotency_key,
        resolution=None,
        model=None,
        materials=None,
        mute_audio=True,
        use_context_ir=False,
        balance_checked=False,
    ):
        import math

        s = get_settings()
        resolution = resolution or s.minimax_video_resolution
        points = self.estimate_points(duration, resolution)
        from app.services.video_capabilities import CAPABILITIES
        if ratio not in CAPABILITIES["ratios"]:
            raise AppError("INVALID_VIDEO_RATIO", "不支持的视频比例", 422)
        content = [{"type": "text", "text": prompt}]
        if materials is not None:
            content.extend(materials)
        elif image:
            content.append({"type": "image_url", "image_url": {"url": image}, "role": "first_frame"})
        self.validate_content(content)
        body = {
            "model": model or s.minimax_video_model,
            "content": content,
            "duration": math.ceil(duration),
            "ratio": ratio,
            "resolution": resolution,
            "use_context_ir": use_context_ir,
            "mute_audio": mute_audio,
        }
        if len(json.dumps(body, ensure_ascii=False).encode()) > CAPABILITIES["max_request_mib"] * 1024 * 1024:
            raise AppError("PAYLOAD_TOO_LARGE", "H3 请求体超过 72 MiB，请减少素材或使用临时公网地址", 413)
        if not balance_checked and (await self.balance())["available_points"] < points:
            raise AppError("PROVIDER_BALANCE_LOW", f"H3 积分不足，本镜预计需要 {points} 积分", 402)
        response = await request(
            "POST",
            s.minimax_video_base_url.rstrip("/") + s.minimax_video_create_path,
            retries=0,
            headers={**self.headers(), "Idempotency-Key": idempotency_key},
            json=body,
        )
        data = response.json()
        if not data.get("task_id"):
            raise AppError("PROVIDER_OUTPUT_INVALID", "H3 未返回任务 ID，请检查任务列表，勿重复提交", 502)
        return str(data["task_id"])

    async def query(self, task_id):
        from urllib.parse import quote

        s = get_settings()
        response = await request(
            "GET",
            s.minimax_video_base_url.rstrip("/") + s.minimax_video_query_path + "/" + quote(task_id, safe=""),
            headers=self.headers(),
        )
        task = response.json().get("task")
        if not isinstance(task, dict) or not task.get("status"):
            raise AppError("PROVIDER_OUTPUT_INVALID", "H3 任务状态格式不正确", 502)
        return {
            **task,
            "fileUrl": (task.get("content") or {}).get("url"),
        }


async def fetch_subtitles(url):
    # MiniMax's provider-owned OSS host may resolve to a local proxy's fake IP.
    # Keep generic media SSRF checks intact; this dedicated path accepts one exact
    # HTTPS origin, no user-supplied hosts, credentials, ports or redirects.
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "minimax-algeng-chat-tts.oss-cn-wulanchabu.aliyuncs.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        return json.loads(await fetch_bytes(url, max_bytes=4 * 1024 * 1024))
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 4 * 1024 * 1024:
                    raise AppError("PAYLOAD_TOO_LARGE", "字幕文件过大", 413)
    return json.loads(raw)


async def fetch_video(url):
    """Download only the verified CompShare result origin through local proxy DNS.

    Kept separate from arbitrary user media URLs; TLS verification stays enabled
    and redirects remain forbidden. CompShare signs this URL in its task result.
    """
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "compshare-files.cn-wlcb.ufileos.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/media/prod/")
        or not parsed.path.endswith(".mp4")
    ):
        return await fetch_bytes(url)
    async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 100 * 1024 * 1024:
                    raise AppError("PAYLOAD_TOO_LARGE", "第三方视频超过 100 MiB", 413)
    if len(raw) < 12 or raw[4:8] != b"ftyp":
        raise AppError("PROVIDER_OUTPUT_INVALID", "H3 下载结果不是 MP4 视频", 422)
    return bytes(raw)

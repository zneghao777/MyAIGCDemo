"""MiMo presets, one-off voice design, and reference-based synthesis."""

import base64
import binascii
import hashlib

from app.core.config import get_settings
from app.core.errors import AppError

from .http import request

VOICES = {
    "女声 · 冷静": "冰糖",
    "女声 · 温柔": "茉莉",
    "男声 · 沉稳": "白桦",
    "男声 · 青年": "苏打",
    "英文女声 · Mia": "Mia",
    "英文女声 · Chloe": "Chloe",
    "英文男声 · Milo": "Milo",
    "英文男声 · Dean": "Dean",
}
LEGACY_VOICES = {
    "female-shaonv": "冰糖",
    "female-yujie": "茉莉",
    "male-qn-qingse": "白桦",
    "male-qn-jingying": "苏打",
}
EMOTIONS = {
    "neutral": "自然",
    "calm": "平静",
    "happy": "开心",
    "sad": "悲伤",
    "angry": "愤怒",
    "fearful": "恐惧",
    "surprised": "惊讶",
    "disgusted": "厌恶",
}


def resolve_voice(voice):
    voice = LEGACY_VOICES.get(voice, voice) or get_settings().mimo_tts_voice_id
    if voice not in {*VOICES.values(), "mimo_default"}:
        raise AppError(
            "VOICE_RESELECTION_REQUIRED", "请试听并选用 MiMo 预置音色，旧自定义音色不能直接复用", 409
        )
    return voice


def unsupported(operation):
    messages = {
        "role_audio": "MiMo 未提供逐字时间戳，暂不支持整段生成后自动切分；请逐句配音后连续试听",
    }
    raise AppError("TTS_CAPABILITY_UNSUPPORTED", messages[operation], 422)


def reference_voice_id(raw):
    # Application-owned identity, not a provider-registered voice ID.
    return "mimo-ref-" + hashlib.sha256(raw).hexdigest()


def reference_data_url(raw):
    if not isinstance(raw, bytes) or not raw:
        raise AppError("VOICE_REFERENCE_REQUIRED", "缺少已选定的声音参考，请重新选用声音候选", 409)
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        mime = "audio/wav"
    elif raw[:3] == b"ID3" or (len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0):
        mime = "audio/mpeg"
    else:
        raise AppError("INVALID_VOICE_REFERENCE", "MiMo 声音参考必须为 MP3 或 WAV", 422)
    encoded = base64.b64encode(raw).decode("ascii")
    if len(encoded) > 10_000_000:
        raise AppError(
            "VOICE_REFERENCE_TOO_LARGE", "声音参考编码后超过 MiMo 的 10 MB 上限，请缩短参考录音", 413
        )
    return f"data:{mime};base64,{encoded}"


class MiMoTTS:
    async def voices(self):
        return {"system_voice": [{"voice_id": voice, "voice_name": label} for label, voice in VOICES.items()]}

    async def synthesize(self, text, voice, performance=None):
        s = get_settings()
        performance = performance or {}
        model = performance.get("model", s.mimo_tts_model)
        if model not in (s.mimo_tts_model, s.mimo_tts_clone_model):
            raise AppError(
                "VOICE_RESELECTION_REQUIRED", "配音模型已切换，请重新试听、选用角色音色并确认分镜", 409
            )
        emotion = performance.get("emotion", "neutral")
        directions = (
            f"保持选定音色与说话人身份稳定。情绪：{EMOTIONS.get(emotion, emotion)}。"
            f"语速为自然语速的 {performance.get('speed', 1)} 倍。"
            "只朗读目标台词，不改写，不增删内容。"
        )
        pitch = performance.get("pitch", 0)
        if pitch:
            directions += f"音高相对基础音色{'提高' if pitch > 0 else '降低'}约 {abs(pitch)} 个半音。"
        if model == s.mimo_tts_clone_model:
            raw = performance.get("reference_audio")
            audio_voice = reference_data_url(raw)
            if voice != reference_voice_id(raw):
                raise AppError("VOICE_REFERENCE_MISMATCH", "声音参考与锁定版本不一致，已停止生成", 409)
        else:
            audio_voice = resolve_voice(voice)
        return await self._generate(model, text, directions, {"voice": audio_voice})

    async def _generate(self, model, text, directions, audio):
        if not text.strip():
            raise AppError("VOICE_TEXT_REQUIRED", "请填写试听台词", 422)
        s = get_settings()
        response = await request(
            "POST",
            s.mimo_base_url.rstrip("/") + "/chat/completions",
            retries=0,
            timeout=180,
            headers={"Authorization": "Bearer " + s.mimo_api_key.get_secret_value()},
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": directions},
                    {"role": "assistant", "content": text},
                ],
                "audio": {"format": "wav", **audio},
                "stream": False,
            },
        )
        try:
            data = response.json()["choices"][0]["message"]["audio"]["data"]
            raw = base64.b64decode(data, validate=True)
            if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE" or len(raw) <= 44:
                raise ValueError("Invalid WAV")
        except (ValueError, TypeError, KeyError, IndexError, binascii.Error):
            raise AppError("PROVIDER_OUTPUT_INVALID", "MiMo 未返回有效的 WAV 音频", 422) from None
        return raw

    async def design(self, prompt, text, voice_id):
        if not prompt.strip():
            raise AppError("VOICE_DESCRIPTION_REQUIRED", "请先填写声音描述或音色设计提示词", 422)
        raw = await self._generate(
            get_settings().mimo_tts_design_model,
            text,
            prompt,
            {"optimize_text_preview": False},
        )
        return reference_voice_id(raw), raw

    async def clone(self, raw, voice_id):
        reference_data_url(raw)
        return reference_voice_id(raw)

    async def synthesize_aligned(self, text, voice, performance=None):
        unsupported("role_audio")

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings

from .base import ImageProvider, LLMProvider, StorageProvider, TTSProvider, VideoProvider
from .deepseek import DeepSeek
from .gpt_image import GPTImage
from .local import LocalStorage
from .mimo import MiMoTTS
from .minimax import DisabledVideo, MiniMaxTTS, MiniMaxVideo
from .qiniu import QiniuTemporaryMedia


@dataclass
class Providers:
    llm: LLMProvider
    image: ImageProvider
    tts: TTSProvider
    storage: StorageProvider
    video: VideoProvider
    external_media: QiniuTemporaryMedia


@lru_cache
def providers():
    return Providers(
        DeepSeek(),
        GPTImage(),
        MiMoTTS() if get_settings().tts_provider == "mimo" else MiniMaxTTS(),
        LocalStorage(),
        MiniMaxVideo() if get_settings().feature_video_generation else DisabledVideo(),
        QiniuTemporaryMedia(),
    )


def voice_presets():
    if get_settings().tts_provider == "mimo":
        from .mimo import VOICES
    else:
        from .minimax import VOICES
    return VOICES

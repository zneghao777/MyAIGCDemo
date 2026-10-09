from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env.example", ROOT / ".env", ROOT / ".env.local"),
        extra="ignore",
        hide_input_in_errors=True,
    )
    database_url: str
    redis_url: str = "redis://127.0.0.1:6379/4"
    testing: bool = False
    deepseek_api_key: SecretStr
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_reasoning_effort: str = ""
    deepseek_thinking: Literal["", "enabled", "disabled"] = ""
    llm_max_tokens_per_job: int = Field(default=12000, ge=2000)
    image_api_key: SecretStr
    image_base_url: str = "https://mfttai.cc"
    image_model: str = "gpt-image-2.5"
    image_size: str = "1024x1536"
    image_quality: str = "medium"
    image_max_references: int = Field(default=4, ge=1, le=16)
    image_n: int = Field(default=1, ge=1, le=1)
    image_response_format: str = "b64_json"
    image_timeout_seconds: int = 180
    tts_provider: Literal["mimo", "minimax"] = "mimo"
    mimo_api_key: SecretStr = SecretStr("")
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_tts_model: Literal["mimo-v2.5-tts"] = "mimo-v2.5-tts"
    mimo_tts_design_model: Literal["mimo-v2.5-tts-voicedesign"] = "mimo-v2.5-tts-voicedesign"
    mimo_tts_clone_model: Literal["mimo-v2.5-tts-voiceclone"] = "mimo-v2.5-tts-voiceclone"
    mimo_tts_voice_id: str = "白桦"
    minimax_api_key: SecretStr = SecretStr("")
    minimax_tts_base_url: str = "https://api.minimax.cn"
    minimax_tts_model: str = "speech-2.8-hd"
    minimax_tts_voice_id: str = "male-qn-qingse"
    minimax_group_id: str = ""
    tts_max_chars: int = Field(default=2000, ge=50, le=10000)
    feature_video_generation: bool = False
    minimax_video_api_key: SecretStr = SecretStr("")
    minimax_video_base_url: str = "https://cp.compshare.cn"
    minimax_video_model: str = "MiniMax-H3"
    minimax_video_create_path: str = "/minimax/v2/video_generation"
    minimax_video_query_path: str = "/minimax/v2/query/video_generation"
    minimax_video_resolution: Literal["480P", "768P", "1080P", "2K", "4K"] = "480P"
    minimax_video_poll_interval_ms: int = 3000
    video_concurrency_limit: int = Field(default=2, ge=1, le=16)
    video_points_hard_limit: int = Field(default=2000, ge=0)
    video_lease_seconds: int = Field(default=1200, ge=1000, le=86400)
    local_media_root: Path = ROOT / "data/media"
    media_base_url: str = "http://127.0.0.1:8000/media"
    qiniu_access_key: SecretStr = SecretStr("")
    qiniu_secret_key: SecretStr = SecretStr("")
    qiniu_s3_bucket: str = "aigc2030"
    qiniu_s3_region: str = "cn-east-1"
    qiniu_s3_endpoint: str = "https://s3.cn-east-1.qiniucs.com"
    qiniu_temp_prefix: str = "cineai-tmp/"
    qiniu_temp_retention_days: int = Field(default=3, ge=2)
    qiniu_signed_url_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    media_max_mb: int = 5
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    subtitle_font_path: str = ""
    bgm_dir: Path = ROOT / "public/assets/bgm"
    api_cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    api_rate_limit_per_min: int = 120
    cost_hard_limit_cents: int = Field(default=5000, ge=0)
    cost_unit_price_json: dict[str, float] = Field(default_factory=dict)
    sensitive_words: str = ""

    @model_validator(mode="after")
    def required_credentials(self):
        if not self.testing:
            missing = [
                key.upper()
                for key in (
                    "deepseek_api_key",
                    "image_api_key",
                    "mimo_api_key" if self.tts_provider == "mimo" else "minimax_api_key",
                    *(("minimax_video_api_key",) if self.feature_video_generation else ()),
                )
                if not (
                    getattr(self, key).get_secret_value()
                    if isinstance(getattr(self, key), SecretStr)
                    else getattr(self, key)
                )
            ]
            if missing:
                raise ValueError("缺少必填配置: " + ", ".join(missing))
        if any(v < 0 for v in self.cost_unit_price_json.values()):
            raise ValueError("单价不能为负数")
        self.local_media_root = (
            self.local_media_root if self.local_media_root.is_absolute() else ROOT / self.local_media_root
        ).resolve()
        from urllib.parse import urlsplit

        for value in (self.media_base_url, self.qiniu_s3_endpoint):
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError("素材地址和 S3 endpoint 必须是有效的 HTTP(S) 地址")
        prefix = self.qiniu_temp_prefix
        if not prefix.endswith("/") or any(p in ("", ".", "..") for p in prefix[:-1].split("/")):
            raise ValueError("七牛临时前缀必须为非空的相对目录，且以 / 结尾")
        if self.qiniu_signed_url_ttl_seconds > (self.qiniu_temp_retention_days - 1) * 86400:
            raise ValueError("签名有效期至少要比临时素材保留期短一天")
        return self

    @property
    def tts_model(self):
        return self.mimo_tts_model if self.tts_provider == "mimo" else self.minimax_tts_model

    @property
    def tts_voice_id(self):
        return self.mimo_tts_voice_id if self.tts_provider == "mimo" else self.minimax_tts_voice_id


@lru_cache
def get_settings():
    return Settings()

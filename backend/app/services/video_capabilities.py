"""CompShare H3 contract, verified against channel docs on 2026-10-05.

The model manual describes another surface (4–15 s / 64 MB). Do not conflate it
with this channel. Audio/video duration guidance remains conservative at 2–15 s.
"""
from app.core.errors import AppError

CAPABILITIES = {
    "channel": "CompShare", "model": "MiniMax-H3", "min_duration": 4, "max_duration": 30,
    "resolutions": ["480P", "768P", "1080P", "2K", "4K"],
    "rates": {"480P": 5, "768P": 10, "1080P": 19, "2K": 20, "4K": 22},
    "modes": ["first_frame", "first_last_frame", "references", "text"],
    "ratios": ["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
    "max_references": {"image": 9, "video": 3, "audio": 3, "total": 12},
    "max_file_mib": {"image": 30, "video": 50, "audio": 15},
    "max_request_mib": 72, "max_prompt_chars": 7000,
    "reference_duration_min": 2, "reference_duration_max": 15,
    "source": "https://www.compshare.cn/docs/minimax-h3/api/minimax-h3-video-api",
}


def validate_duration(duration):
    if not CAPABILITIES["min_duration"] <= duration <= CAPABILITIES["max_duration"]:
        raise AppError("INVALID_VIDEO_DURATION", "当前渠道每段支持 4–30 秒，请拆分片段或调整设计时长", 422)
    if int(duration) != duration:
        raise AppError("INVALID_VIDEO_DURATION", "生成片段须为整数秒，请调整设计时长；采用区间可精确到小数秒", 422)

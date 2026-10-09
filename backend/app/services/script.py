from app.schemas import Outline, GeneratedScript
from app.prompts import OUTLINE, SCENES
from app.providers import providers
from app.core.config import get_settings
from app.core.errors import AppError


async def generate(payload, report):
    await report(10, "正在构思故事梗概")
    brief = {**payload, "sceneCount": payload["scene_count"]}
    outline = await providers().llm.structured(Outline, OUTLINE, brief)
    if len(outline.scenes) != payload["scene_count"]:
        raise AppError("PROVIDER_OUTPUT_INVALID", "大纲镜头数与请求不一致", 422)
    await report(25, "正在设计角色关系")
    batch = (
        6 if payload["scene_count"] * 800 > get_settings().llm_max_tokens_per_job else payload["scene_count"]
    )
    scenes = []
    for start in range(0, payload["scene_count"], batch):
        count = min(batch, payload["scene_count"] - start)
        await report(
            35 + int(50 * start / payload["scene_count"]),
            f"正在拆分分镜（第 {start + 1}/{payload['scene_count']} 镜）",
        )
        result = await providers().llm.structured(
            GeneratedScript,
            SCENES,
            {
                **brief,
                "outline": outline.model_dump(),
                "selectedScenes": [s.model_dump() for s in outline.scenes[start : start + count]],
                "count": count,
            },
        )
        if len(result.scenes) != count:
            raise AppError("PROVIDER_OUTPUT_INVALID", "分镜数量与请求不一致", 422)
        scenes.extend(result.scenes)
    await report(90, "正在匹配镜头语言")
    return outline.model_dump(), scenes

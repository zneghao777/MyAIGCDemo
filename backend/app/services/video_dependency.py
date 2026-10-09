"""Only explicit previous-output dependencies delay a shot's H3 admission."""

import tempfile
from pathlib import Path

from sqlalchemy import select

from app.core.errors import AppError
from app.models import Scene, Task
from app.providers import providers
from app.services.media import probe, run_ffmpeg
from app.services.resources import save_asset
from app.services.video_capacity import CapacityPending


class DependencyPending(CapacityPending):
    def __init__(self):
        AppError.__init__(self, "VIDEO_DEPENDENCY_PENDING", "等待所引用前镜的真实生成尾帧", 409)


async def prepare(db, task, scene, payload, checkpoint):
    previous_id = ((scene.creative or {}).get("shot") or {}).get("continuity_from")
    if not previous_id or task.provider_task_id:
        return payload
    previous = await db.get(Scene, previous_id)
    if not previous or previous.project_id != task.project_id or previous.order_index >= scene.order_index:
        raise AppError("VIDEO_DEPENDENCY_INVALID", "尾帧依赖必须指向同项目的前序分镜", 422)
    if payload.get("input_mode") == "references":
        raise AppError("H3_MODE_CONFLICT", "前镜尾帧依赖属于首帧输入，不能与全能参考模式混用", 422)
    if not previous.video_key:
        latest = await db.scalar(
            select(Task)
            .where(Task.scene_id == previous.id, Task.kind == "video")
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        if latest and latest.status in ("failed", "cancelled"):
            raise AppError(
                "VIDEO_DEPENDENCY_FAILED", "所引用前镜失败，请先恢复该镜；其他独立镜头继续执行", 409
            )
        raise DependencyPending()
    previous_key = previous.video_key
    edit = (getattr(previous, "creative", None) or {}).get("edit")
    dependency = {"scene_id": previous.id, "video_key": previous_key, **({"edit": edit} if edit else {})}
    cached = (task.result or {}).get("dependency") or {}
    if cached.get("video_key") == previous_key and cached.get("edit") == edit:
        return task.payload
    await db.commit()
    with tempfile.TemporaryDirectory(prefix="cineai-tail-") as folder:
        root = Path(folder)
        video = root / "source.mp4"
        image = root / "tail.png"
        video.write_bytes(await providers().storage.get(previous_key))
        duration = await probe(video)
        if edit:
            duration = min(duration, edit["out_sec"])
        await run_ffmpeg(
            ["-ss", str(max(0, duration - 0.05)), "-i", str(video), "-frames:v", "1", str(image)], checkpoint
        )
        asset = await save_asset(
            db,
            task.project_id,
            "video-tail",
            image.read_bytes(),
            "image/png",
            "png",
            f"scenes/{previous.id}/tail",
        )
    material = {
        "asset_id": asset.id,
        "key": asset.object_key,
        "kind": "image",
        "role": "first_frame",
        "purpose": f"引用前镜“{previous.title}”实际采用区间的尾帧",
        "content_type": "image/png",
        "size_bytes": asset.size_bytes,
    }
    materials = [material, *[x for x in payload.get("materials", []) if x["role"] != "first_frame"]]
    updated = {
        **payload,
        "materials": materials,
        "dependency_source": dependency,
        "video_source": {
            **payload["video_source"],
            "dependency": dependency,
        },
    }
    task.payload = updated
    task.result = {
        **(task.result or {}),
        "dependency": {**dependency, "tail_asset_id": asset.id},
    }
    await db.commit()
    return updated

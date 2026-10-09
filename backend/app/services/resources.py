import base64

from pydantic.alias_generators import to_camel
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Asset, Character, Project, Scene, Task, now, uid
from app.providers import providers, voice_presets
from app.providers.gpt_image import inspect_image


async def require(db, model, id, lock=False):
    query = select(model).where(model.id == id)
    if lock:
        query = query.with_for_update()
    row = await db.scalar(query)
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "资源不存在", 404)
    return row


async def children(db, model, project_id):
    query = select(model).where(model.project_id == project_id)
    if model is Character:
        query = query.order_by(Character.id)
    if model is Task:
        query = query.order_by(Task.created_at, Task.id)
    if model is Scene:
        query = query.where(Scene.order_index >= 0).order_by(Scene.order_index)
    return list((await db.scalars(query)).all())


def columns(row):
    return {to_camel(c.name): getattr(row, c.name) for c in row.__table__.columns}


def media_urls(value):
    """Decorate copied JSON only; immutable fingerprints never include delivery URLs."""
    if isinstance(value, dict):
        result = {k: media_urls(v) for k, v in value.items()}
        if result.get("key"):
            result["url"] = providers().storage.url(result["key"])
        return result
    if isinstance(value, list):
        return [media_urls(v) for v in value]
    return value


def scene_out(row):
    data = columns(row)
    if data.get("creative"):
        data["creative"] = media_urls(data["creative"])
        from app.services.creative import review_current

        data["creative"]["review_current"] = review_current(row)
    for field, alias in [
        ("first_frame_key", "image"),
        ("video_key", "videoUrl"),
        ("audio_key", "audioUrl"),
        ("narration_key", "narrationUrl"),
    ]:
        data[alias] = providers().storage.url(getattr(row, field))
        data.pop(to_camel(field), None)
    return data


def character_out(row):
    data = columns(row)
    if data.get("creative"):
        data["creative"] = media_urls(data["creative"])
    data["image"] = providers().storage.url(row.image_key)
    if data.get("creative"):
        from copy import deepcopy

        data["creative"] = deepcopy(data["creative"])
        for ref in (
            data["creative"].get("voice"),
            data["creative"].get("voice_reference"),
            (data["creative"].get("voice") or {}).get("reference"),
        ):
            if ref and ref.get("key"):
                ref["url"] = providers().storage.url(ref["key"])
    data.pop("imageKey", None)
    return data


def task_out(row):
    data = columns(row)
    labels = {
        "image": ("图片", "生图"),
        "video": ("视频", "视频"),
        "tts": ("配音", "配音"),
        "compose": ("合成", "合成"),
        "script": ("剧本", "剧本"),
    }
    data["type"], data["typeLabel"] = labels[row.kind]
    if row.payload.get("creative"):
        data["operation"] = row.payload["creative"]["operation"]
        data["targetId"] = row.payload["creative"]["target"]
        data["generationRequest"] = row.payload["creative"].get("request")
    price = {
        "image": "imagePerCall",
        "tts": "ttsPerKChar",
        "script": "llmPerMToken",
        "video": "videoPerSec",
    }.get(row.kind)
    data["pricingConfigured"] = bool(price and get_settings().cost_unit_price_json.get(price, 0) > 0)
    if not data["pricingConfigured"]:
        data["estimatedCostCents"] = None
    data.pop("payload", None)
    data.pop("dedupeKey", None)
    return data


async def project_out(db, row):
    data = columns(row)
    if data.get("creative"):
        data["creative"] = media_urls({key: value for key, value in data["creative"].items() if key != "stage"})
    data["cover"] = providers().storage.url(row.cover_key)
    data.pop("coverKey", None)
    data["scenes"] = [scene_out(s) for s in await children(db, Scene, row.id)]
    data["characters"] = [character_out(c) for c in await children(db, Character, row.id)]
    if (data.get("creative") or {}).get("preview_confirmation"):
        from app.services.creative import preview_fingerprint

        data["creative"]["preview_confirmation"]["stale"] = data["creative"]["preview_confirmation"].get(
            "fingerprint"
        ) != preview_fingerprint(await children(db, Scene, row.id))
    return data


def export_out(row):
    data = columns(row)
    for field, alias in [("output_key", "url"), ("cover_key", "coverUrl"), ("subtitle_key", "subtitleUrl")]:
        data[alias] = providers().storage.url(getattr(row, field))
        data.pop(to_camel(field), None)
    scenes = (row.settings.get("manifest") or {}).get("scenes", [])
    data["label"] = (
        "静态分镜配声预演"
        if row.settings.get("source_mode") == "storyboard"
        else (
            "AI 视频成片"
            if scenes and all(s.get("video_key") for s in scenes)
            else "混合视频成片"
            if any(s.get("video_key") for s in scenes)
            else "分镜动态预演成片"
        )
    )
    data["manualAcceptance"] = bool(row.settings.get("manualAcceptance", False))
    data["wholeAcceptance"] = row.settings.get("wholeAcceptance")
    return data


async def save_asset(db, project_id, kind, raw, content_type, suffix, scope="", duration_ms=None):
    key = f"projects/{project_id}/{scope or kind}/{uid()}.{suffix}"
    await providers().storage.put(key, raw, content_type)
    db.info.setdefault("uploaded_keys", []).append(key)
    width = height = None
    if content_type.startswith("image/"):
        _, width, height = inspect_image(raw)
    asset = Asset(
        project_id=project_id,
        kind=kind,
        object_key=key,
        content_type=content_type,
        size_bytes=len(raw),
        duration_ms=duration_ms,
        width=width,
        height=height,
    )
    db.add(asset)
    await db.flush()
    return asset


async def upload_image(db, project_id, raw, kind="reference"):
    if len(raw) > get_settings().media_max_mb * 1024 * 1024:
        raise AppError("PAYLOAD_TOO_LARGE", "图片超过上传大小上限", 413)
    fmt, _, _ = inspect_image(raw)
    ext, mime = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp")}[
        fmt
    ]
    return await save_asset(db, project_id, kind, raw, mime, ext)


async def bind_image(db, project_id, image):
    if not image:
        return None
    if image.startswith("data:"):
        try:
            raw = base64.b64decode(image.split(",", 1)[1], validate=True)
        except Exception:
            raise AppError("INVALID_IMAGE", "图片编码不合法", 422) from None
        return (await upload_image(db, project_id, raw)).object_key
    # Only owned assets can be attached, never arbitrary URLs/SSRF or other projects' keys.
    assets = await children(db, Asset, project_id)
    # Accept owned keys/ids or exact local URLs, including their /media prefix.
    asset = next(
        (a for a in assets if image in (a.id, a.object_key, providers().storage.url(a.object_key))),
        None,
    )
    if not asset:
        raise AppError("INVALID_ASSET", "只能绑定当前项目已上传的图片", 422)
    return asset.object_key


async def add_character(db, project_id, payload):
    data = payload.model_dump(exclude={"image", "voice_id"}, exclude_none=True)
    row = Character(
        project_id=project_id,
        **data,
        voice_id=payload.voice_id or voice_presets().get(payload.voice, get_settings().tts_voice_id),
        image_key=await bind_image(db, project_id, payload.image),
    )
    db.add(row)
    await db.flush()
    return row


async def touch(db, project_id):
    project = await require(db, Project, project_id)
    project.updated_at = now()


async def ensure_idle(db, project_id, scene_id=None):
    query = select(Task.id).where(Task.project_id == project_id, Task.status.in_(["queued", "running"]))
    if scene_id:
        query = query.where((Task.scene_id == scene_id) | (Task.kind.in_(["script", "compose"])))
    if await db.scalar(query.limit(1)):
        raise AppError("SCENE_HAS_RUNNING_TASK", "请先等待或取消进行中的任务", 409)


async def reorder(db, project_id, ids):
    rows = await children(db, Scene, project_id)
    if len(ids) != len(set(ids)) or set(ids) != {r.id for r in rows}:
        raise AppError("VALIDATION_ERROR", "排序必须包含当前项目的全部分镜，且不能重复", 422)
    for n, row in enumerate(rows):
        row.order_index = -n - 1
    await db.flush()
    by_id = {r.id: r for r in rows}
    for n, id in enumerate(ids):
        by_id[id].order_index = n
    await touch(db, project_id)


def scene_values(schema, **kwargs):
    values = schema.model_dump(**kwargs)
    if schema.director_data is not None:
        values["director_data"] = schema.director_data.model_dump(by_alias=True, exclude_none=True)
    return values

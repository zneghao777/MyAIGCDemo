from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import session
from app.core.errors import AppError
from app.models import Project, Scene, Character, Task, Asset, Cleanup, uid
from app.schemas import ProjectInput, SceneInput, CharacterInput, Order
from app.services.resources import (
    require,
    children,
    project_out,
    scene_out,
    character_out,
    add_character,
    bind_image,
    ensure_idle,
    reorder,
    touch,
    scene_values,
)
from app.services.jobs import estimate_cost
from app.providers import voice_presets

router = APIRouter(prefix="/api")
DB = Annotated[AsyncSession, Depends(session)]


@router.get("/projects")
async def projects(
    db: DB,
    response: Response,
    q: str = "",
    status: str | None = None,
    sort: Literal["updated", "name"] = "updated",
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=100),
):
    query = select(Project)
    if q:
        query = query.where(Project.name.ilike("%" + q + "%"))
    if status:
        query = query.where(Project.status == status)
    query = (
        query.order_by(Project.name, Project.id)
        if sort == "name"
        else query.order_by(Project.updated_at.desc(), Project.id)
    )
    rows = list((await db.scalars(query)).all())
    if cursor:
        index = next((i for i, p in enumerate(rows) if p.id == cursor), None)
        if index is None:
            raise AppError("INVALID_CURSOR", "分页游标不存在", 422)
        rows = rows[index + 1 :]
    page = rows[:limit]
    response.headers["X-Next-Cursor"] = page[-1].id if len(rows) > limit else ""
    return [await project_out(db, p) for p in page]


@router.post("/projects", status_code=201)
async def create_project(body: ProjectInput, db: DB):
    values = body.model_dump(exclude={"scenes", "characters"}, exclude_none=True)
    row = Project(**values)
    db.add(row)
    await db.flush()
    for i, spec in enumerate(body.scenes):
        db.add(Scene(project_id=row.id, order_index=i, **scene_values(spec, exclude_none=True)))
    for spec in body.characters:
        await add_character(db, row.id, spec)
    await db.commit()
    return await project_out(db, row)


@router.get("/projects/{id}")
async def get_project(id: str, db: DB):
    return await project_out(db, await require(db, Project, id))


@router.patch("/projects/{id}")
async def patch_project(id: str, body: dict, db: DB):
    row = await require(db, Project, id, True)
    if row.creative and set(body) & {"style", "ratio", "description"}:
        raise AppError("USE_CREATIVE_FLOW", "请在故事方案中修改风格与画幅", 409)
    await ensure_idle(db, id)
    allowed = {"name", "description", "style", "ratio", "exportSettings", "cover"}
    if set(body) - allowed:
        raise AppError("VALIDATION_ERROR", "包含不可编辑字段", 422)
    image = body.pop("cover", None)
    merged = {key: getattr(row, key) for key in ("name", "description", "style", "ratio")}
    data = ProjectInput.model_validate({**merged, **body})
    for key in data.model_fields_set - {"characters", "scenes", "id"}:
        setattr(row, key, data.model_dump()[key])
    if image is not None:
        row.cover_key = await bind_image(db, id, image)
    await db.commit()
    return await project_out(db, row)


@router.delete("/projects/{id}", status_code=204)
async def remove_project(id: str, db: DB):
    row = await require(db, Project, id, True)
    await ensure_idle(db, id)
    keys = [a.object_key for a in await children(db, Asset, id)]
    if keys:
        db.add(Cleanup(keys=keys))
    await db.delete(row)
    await db.commit()


@router.post("/projects/{id}/copy", status_code=201)
async def copy_project(id: str, db: DB):
    row = await require(db, Project, id, True)
    if row.creative:
        raise AppError("USE_LIBRARY", "版本化项目请新建故事并从全局库复用角色，避免错误复制版本引用", 409)
    await ensure_idle(db, id)
    from app.providers import providers

    original_assets = await children(db, Asset, id)
    mapping = {}
    copy = Project(
        name=(row.name + " · 副本")[:100],
        description=row.description,
        style=row.style,
        ratio=row.ratio,
        outline=row.outline,
        export_settings=row.export_settings,
    )
    db.add(copy)
    await db.flush()
    # Copy object bytes so deleting either project cannot break the other's assets.
    for asset in original_assets:
        key = f"projects/{copy.id}/copied/{uid()}.{asset.object_key.rsplit('.', 1)[-1]}"
        await providers().storage.put(
            key, await providers().storage.get(asset.object_key), asset.content_type
        )
        mapping[asset.object_key] = key
        db.add(
            Asset(
                project_id=copy.id,
                kind=asset.kind,
                object_key=key,
                content_type=asset.content_type,
                size_bytes=asset.size_bytes,
                duration_ms=asset.duration_ms,
                width=asset.width,
                height=asset.height,
            )
        )
    copy.cover_key = mapping.get(row.cover_key)
    for model in (Scene, Character):
        for source in await children(db, model, id):
            values = {
                c.name: getattr(source, c.name)
                for c in source.__table__.columns
                if c.name not in ("id", "project_id")
            }
            for key in list(values):
                if key.endswith("_key"):
                    values[key] = mapping.get(values[key])
            if model is Scene:
                values["status"] = "image_ready" if values["first_frame_key"] else "draft"
            db.add(model(project_id=copy.id, **values))
    await db.commit()
    return await project_out(db, copy)


@router.get("/projects/{id}/estimate")
async def estimate(id: str, db: DB):
    from app.core.config import get_settings

    await require(db, Project, id)
    scenes = await children(db, Scene, id)
    counts = {
        kind: sum(
            estimate_cost(
                kind, {"dialogue": s.dialogue, "narration": s.narration, "duration_sec": s.duration_sec}
            )
            for s in scenes
        )
        for kind in ("image", "tts", "video")
    }
    spent = await db.scalar(select(func.coalesce(func.sum(Task.cost_cents), 0)).where(Task.project_id == id))
    return {
        "estimated": True,
        "pricingConfigured": any(price > 0 for price in get_settings().cost_unit_price_json.values()),
        "byKind": counts,
        "totalCents": counts["image"] + counts["tts"],
        "spentCents": spent,
        "hardLimitCents": get_settings().cost_hard_limit_cents,
    }


@router.get("/projects/{id}/characters")
async def characters(id: str, db: DB):
    await require(db, Project, id)
    return [character_out(c) for c in await children(db, Character, id)]


@router.post("/projects/{id}/characters", status_code=201)
async def create_character(id: str, body: CharacterInput, db: DB):
    await require(db, Project, id, True)
    await ensure_idle(db, id)
    row = await add_character(db, id, body)
    await touch(db, id)
    await db.commit()
    return character_out(row)


@router.patch("/characters/{id}")
async def patch_character(id: str, body: dict, db: DB):
    row = await require(db, Character, id)
    await require(db, Project, row.project_id, True)
    if row.creative:
        raise AppError("USE_CREATIVE_FLOW", "请在角色资产编辑器保存版本", 409)
    await ensure_idle(db, row.project_id)
    merged = {
        key: getattr(row, key)
        for key in ("name", "age", "description", "clothing", "voice", "voice_id", "consistency")
    }
    if "voice" in body and "voiceId" not in body:
        merged["voice_id"] = voice_presets().get(body["voice"], row.voice_id)
    from pydantic.alias_generators import to_camel

    names = {to_camel(k): k for k in CharacterInput.model_fields}
    normalized = {names.get(k, k): v for k, v in body.items()}
    if "id" in normalized:
        raise AppError("VALIDATION_ERROR", "不能修改 ID", 422)
    data = CharacterInput.model_validate({**merged, **normalized})
    if data.voice_id != row.voice_id:
        for scene in await children(db, Scene, row.project_id):
            scene.audio_key = None
            scene.narration_key = None
    for key, value in data.model_dump(exclude={"id", "image"}).items():
        setattr(row, key, value)
    if "image" in body:
        row.image_key = await bind_image(db, row.project_id, body["image"])
    await touch(db, row.project_id)
    await db.commit()
    return character_out(row)


@router.delete("/characters/{id}", status_code=204)
async def delete_character(id: str, db: DB):
    row = await require(db, Character, id)
    await require(db, Project, row.project_id, True)
    await ensure_idle(db, row.project_id)
    if row.creative:
        for scene in await children(db, Scene, row.project_id):
            shot = (scene.creative or {}).get("shot") or {}
            lines = [*shot.get("lines", []), *shot.get("narration", [])]
            if id in shot.get("cast", {}) or any(line.get("speaker_id") == id for line in lines):
                raise AppError("REFERENCED_CHARACTER", "该角色正在被分镜使用，请先移除其出场和台词绑定", 409)
        from app.services.creative import unconfirm

        await unconfirm(db, row.project_id, "cast")
    await touch(db, row.project_id)
    await db.delete(row)
    await db.commit()


@router.post("/projects/{id}/scenes", status_code=201)
async def add_scene(id: str, body: SceneInput, db: DB):
    await require(db, Project, id, True)
    await ensure_idle(db, id)
    scenes = await children(db, Scene, id)
    if len(scenes) >= 24:
        raise AppError("VALIDATION_ERROR", "最多 24 个分镜", 422)
    row = Scene(project_id=id, order_index=len(scenes), **scene_values(body, exclude_none=True))
    db.add(row)
    await touch(db, id)
    await db.commit()
    return scene_out(row)


@router.patch("/scenes/{id}")
async def patch_scene(id: str, body: dict, db: DB):
    row = await require(db, Scene, id)
    await require(db, Project, row.project_id, True)
    if row.creative:
        if set(body) <= {"directorData", "expectedVersion"}:
            from app.schemas import DirectorData
            from app.services.creative import save_state, unconfirm, check_version

            check_version(row.creative, body.get("expectedVersion"))

            row.director_data = DirectorData.model_validate(body["directorData"]).model_dump(by_alias=True)
            cast = (row.creative.get("shot") or {}).get("cast", {})
            if any(
                o.get("characterId") and o["characterId"] not in cast for o in row.director_data["objects"]
            ):
                raise AppError("INVALID_CAST", "导演台角色必须绑定当前镜头出场角色", 422)
            await save_state(db, row, row.creative, "scene")
            await unconfirm(db, row.project_id, "shots")
            await db.commit()
            return scene_out(row)
        raise AppError("USE_CREATIVE_FLOW", "请在结构化分镜编辑器修改台词和角色引用", 409)
    await ensure_idle(db, row.project_id, id)
    merged = {field: getattr(row, field) for field in SceneInput.model_fields if field != "id"}
    # Normalize incoming aliases before merging to avoid duplicate alias/name keys.
    from pydantic.alias_generators import to_camel

    names = {to_camel(k): k for k in SceneInput.model_fields}
    normalized = {names.get(k, k): v for k, v in body.items()}
    if "id" in normalized:
        raise AppError("VALIDATION_ERROR", "不能修改 ID", 422)
    data = SceneInput.model_validate({**merged, **normalized})
    if "dialogue" in normalized and normalized["dialogue"] != row.dialogue:
        row.audio_key = None
    if "narration" in normalized and normalized["narration"] != row.narration:
        row.narration_key = None
    for key, value in scene_values(data, exclude={"id"}).items():
        setattr(row, key, value)
    await touch(db, row.project_id)
    await db.commit()
    return scene_out(row)


@router.delete("/scenes/{id}", status_code=204)
async def delete_scene(id: str, db: DB):
    row = await require(db, Scene, id)
    await require(db, Project, row.project_id, True)
    await ensure_idle(db, row.project_id)
    project_id = row.project_id
    await db.delete(row)
    await db.flush()
    await reorder(db, project_id, [r.id for r in await children(db, Scene, project_id)])
    await db.commit()


@router.post("/scenes/{id}/copy", status_code=201)
async def copy_scene(id: str, db: DB):
    row = await require(db, Scene, id)
    await require(db, Project, row.project_id, True)
    await ensure_idle(db, row.project_id)
    rows = await children(db, Scene, row.project_id)
    if len(rows) >= 24:
        raise AppError("VALIDATION_ERROR", "最多 24 个分镜", 422)
    values = {
        c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in ("id", "order_index")
    }
    values["status"] = "image_ready" if row.first_frame_key else "draft"
    copy = Scene(order_index=len(rows), **values)
    db.add(copy)
    await db.flush()
    ids = [r.id for r in rows]
    ids.insert(ids.index(id) + 1, copy.id)
    await reorder(db, row.project_id, ids)
    await db.commit()
    return scene_out(copy)


@router.patch("/projects/{id}/scenes/order")
async def order_scenes(id: str, body: Order, db: DB):
    await require(db, Project, id, True)
    await ensure_idle(db, id)
    await reorder(db, id, body.ids)
    await db.commit()
    return {"ids": body.ids}

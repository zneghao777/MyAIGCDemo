from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import RedirectResponse
from app.api.routers.resources import DB
from app.schemas import UploadData
from app.models import Project, Asset
from app.core.config import get_settings
from app.services.resources import require, upload_image, bind_image, columns
from app.providers import providers
from sqlalchemy import select

router = APIRouter(prefix="/api")


def output(asset):
    return {**columns(asset), "url": providers().storage.url(asset.object_key)}


@router.get("/projects/{id}/assets")
async def list_assets(id: str, db: DB):
    await require(db, Project, id)
    rows = await db.scalars(select(Asset).where(Asset.project_id == id).order_by(Asset.created_at.desc()))
    return [output(row) for row in rows]


@router.post("/assets/upload", status_code=201)
async def upload(db: DB, projectId: str = Form(...), file: UploadFile = File(...)):
    await require(db, Project, projectId)
    raw = await file.read(get_settings().media_max_mb * 1024 * 1024 + 1)
    asset = await upload_image(db, projectId, raw)
    await db.commit()
    return output(asset)


@router.post("/assets", status_code=201)
async def upload_data(body: UploadData, db: DB):
    await require(db, Project, body.project_id)
    key = await bind_image(db, body.project_id, body.data_url)
    asset = await db.scalar(select(Asset).where(Asset.object_key == key))
    await db.commit()
    return output(asset)


@router.get("/assets/{id}")
async def asset(id: str, db: DB, redirect: bool = False):
    row = await require(db, Asset, id)
    return (
        RedirectResponse(providers().storage.url(row.object_key), status_code=302)
        if redirect
        else output(row)
    )


@router.post("/projects/{id}/bgm", status_code=201)
@router.post("/projects/{id}/sound-effects", status_code=201)
async def upload_bgm(id: str, db: DB, request: Request, file: UploadFile = File(...)):
    import tempfile
    from pathlib import Path
    from app.core.errors import AppError
    from app.services.media import probe, run_ffmpeg
    from app.services.resources import save_asset

    await require(db, Project, id)
    raw = await file.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise AppError("PAYLOAD_TOO_LARGE", "背景音乐上限 20 MB", 413)

    async def checkpoint():
        return None

    with tempfile.TemporaryDirectory(prefix="cineai-bgm-") as folder:
        path = Path(folder) / "input"
        path.write_bytes(raw)
        duration = await probe(path)
        if duration > 600:
            raise AppError("INVALID_MEDIA", "背景音乐最长 10 分钟", 422)
        output_path = Path(folder) / "bgm.mp3"
        await run_ffmpeg(["-i", str(path), "-vn", "-c:a", "libmp3lame", str(output_path)], checkpoint)
        asset = await save_asset(
            db,
            id,
            "sound-effect" if request.url.path.endswith("sound-effects") else "bgm",
            output_path.read_bytes(),
            "audio/mpeg",
            "mp3",
            duration_ms=round(duration * 1000),
        )
    await db.commit()
    return output(asset)


@router.get("/projects/{id}/bgm")
async def list_bgm(id: str, db: DB):
    await require(db, Project, id)
    rows = await db.scalars(
        select(Asset).where(Asset.project_id == id, Asset.kind == "bgm").order_by(Asset.created_at.desc())
    )
    return [output(a) for a in rows]

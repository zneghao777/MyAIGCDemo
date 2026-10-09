from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from app.core.errors import AppError
from app.providers import providers

router = APIRouter(prefix="/media")


@router.api_route("/{key:path}", methods=["GET", "HEAD"])
def media(key: str, request: Request):
    # Only validated/generated media lives here, never .env or application code.
    path = providers().storage.path(key)
    if any(part.startswith(".") for part in key.split("/")) or not path.is_file():
        raise AppError("ASSET_NOT_FOUND", "本地素材不存在", 404)
    response = FileResponse(
        path,
        stat_result=path.stat(),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
    if StaticFiles().is_not_modified(response.headers, request.headers):
        return Response(
            status_code=304,
            headers={name: response.headers[name] for name in ("etag", "last-modified", "cache-control")},
        )
    return response

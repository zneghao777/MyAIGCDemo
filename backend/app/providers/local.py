"""Persistent local media; API and workers must share the same root."""

import asyncio
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

from app.core.config import get_settings
from app.core.errors import AppError


class LocalStorage:
    def __init__(self, root: Path | None = None, base_url: str | None = None):
        s = get_settings()
        self.root = (root or s.local_media_root).resolve()
        self.base_url = (base_url or s.media_base_url).rstrip("/")

    def path(self, key: str) -> Path:
        if not key or "\\" in key or "\x00" in key or any(p in ("", ".", "..") for p in key.split("/")):
            raise AppError("INVALID_ASSET", "素材路径不合法", 422)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise AppError("INVALID_ASSET", "素材路径不合法", 422)
        return path

    async def put(self, key, body, content_type):
        path = self.path(key)

        def write():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Readers never see a partially written image/video.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as out:
                    temporary = Path(out.name)
                    out.write(body)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

        await asyncio.to_thread(write)
        return self.url(key)

    async def get(self, key):
        try:
            return await asyncio.to_thread(self.path(key).read_bytes)
        except FileNotFoundError:
            raise AppError("ASSET_NOT_FOUND", "本地素材不存在", 404) from None

    async def delete(self, key):
        await asyncio.to_thread(self.path(key).unlink, missing_ok=True)

    def url(self, key):
        if not key:
            return ""
        self.path(key)
        return self.base_url + "/" + quote(key, safe="/")

    async def health(self):
        def check():
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=self.root) as out:
                out.write(b"ok")
                out.flush()

        await asyncio.to_thread(check)

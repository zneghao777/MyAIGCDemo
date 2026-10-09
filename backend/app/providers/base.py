from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class LLMProvider(Protocol):
    async def structured(self, model: type[BaseModel], instruction: str, brief: dict) -> BaseModel: ...


class ImageProvider(Protocol):
    async def generate(
        self, prompt: str, ratio: str, quality: str, references: list[bytes]
    ) -> tuple[bytes, list]: ...


class TTSProvider(Protocol):
    async def clone(self, raw: bytes, voice_id: str) -> str: ...

    async def synthesize(self, text: str, voice: str, performance: dict | None = None) -> bytes: ...

    async def synthesize_aligned(
        self, text: str, voice: str, performance: dict | None = None
    ) -> tuple[bytes, list[dict] | dict]: ...


class StorageProvider(Protocol):
    def path(self, key: str) -> Path: ...
    async def put(self, key: str, body: bytes, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    def url(self, key: str | None) -> str: ...
    async def health(self) -> None: ...


class VideoProvider(Protocol):
    async def create(
        self,
        prompt: str,
        image: str,
        duration: float,
        ratio: str,
        *,
        idempotency_key: str,
        resolution: str | None = None,
        model: str | None = None,
    ) -> str: ...
    async def query(self, task_id: str) -> dict: ...

import asyncio
import ipaddress
import socket
import logging
from urllib.parse import urlparse
import httpx
from app.core.errors import AppError, TransientProviderError


async def request(method, url, *, retries=2, timeout=120, **kwargs):
    from app.core.provider_audit import append_call, timestamp

    body = kwargs.get("json") or kwargs.get("data") or {}
    model = body.get("model") if isinstance(body, dict) else None
    for attempt in range(retries + 1):
        started_at = timestamp()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=10), follow_redirects=False
            ) as client:
                response = await client.request(method, url, **kwargs)
            try:
                await asyncio.to_thread(append_call, url, model, started_at, response.status_code, response)
            except OSError:
                logging.getLogger("cineai.audit").warning("provider_audit_unavailable")
            if response.status_code == 429 or response.status_code >= 500:
                raise TransientProviderError(
                    "PROVIDER_RATE_LIMIT" if response.status_code == 429 else "PROVIDER_ERROR",
                    f"第三方暂不可用（HTTP {response.status_code}）", 502,
                    {"status": response.status_code, "retry_after": response.headers.get("Retry-After")},
                )
            if response.is_error:
                raise AppError(
                    "PROVIDER_ERROR",
                    f"第三方拒绝请求（HTTP {response.status_code}）",
                    502,
                    {"status": response.status_code},
                )
            return response
        except (httpx.TimeoutException, httpx.NetworkError, TransientProviderError) as exc:
            if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
                try:
                    await asyncio.to_thread(append_call, url, model, started_at, None, error_type=type(exc).__name__)
                except OSError:
                    logging.getLogger("cineai.audit").warning("provider_audit_unavailable")
            if attempt == retries:
                if isinstance(exc, TransientProviderError):
                    raise
                raise TransientProviderError("PROVIDER_TIMEOUT", "第三方请求超时或暂不可用", 504) from None
            await asyncio.sleep(2**attempt)


async def fetch_bytes(url: str, max_bytes=100 * 1024 * 1024):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AppError("INVALID_MEDIA_URL", "媒体下载地址必须为公网 HTTPS")
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443)
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise AppError("INVALID_MEDIA_URL", "媒体地址不允许访问内网")
    async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > max_bytes:
                    raise AppError("PAYLOAD_TOO_LARGE", "第三方媒体过大", 413)
            return bytes(raw)

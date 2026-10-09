"""Verify the temporary bridge without logging credentials or signed URLs."""

import argparse
import asyncio
import io
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.providers.qiniu import QiniuTemporaryMedia
from app.core.errors import AppError


async def main(configure_lifecycle):
    bridge = QiniuTemporaryMedia()
    if configure_lifecycle:
        result = await bridge.configure_lifecycle()
        rule = next(r for r in result["Rules"] if r.get("ID") == "CineAITemporaryMedia")
        assert rule["Expiration"]["Days"] == bridge.s.qiniu_temp_retention_days
        assert rule.get("Filter", {}).get("Prefix", rule.get("Prefix")) == bridge.s.qiniu_temp_prefix
        assert rule["Status"] == "Enabled"
        print(
            f"七牛生命周期已配置并回读验证：仅 {bridge.s.qiniu_temp_prefix}，保留 {rule['Expiration']['Days']} 天。"
        )
    output = io.BytesIO()
    Image.new("RGB", (16, 16), "#64523b").save(output, format="PNG")
    raw = output.getvalue() + uuid4().bytes  # Unique tiny PNG; no project assets involved.
    url = await bridge.publish(raw, "image/png")
    key = unquote(urlsplit(url).path).lstrip("/")
    assert key.startswith(bridge.s.qiniu_temp_prefix)
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.get(url)
            if response.status_code != 200 or response.content != raw:
                raise AppError("SIGNED_GET_FAILED", "七牛签名下载验证失败", 502)
        second = await bridge.publish(raw, "image/png")
        assert urlsplit(second).path == urlsplit(url).path
        print("七牛上传、签名 GET 下载及重复素材复用验证通过。")
    finally:
        await asyncio.to_thread(bridge.client.delete_object, Bucket=bridge.s.qiniu_s3_bucket, Key=key)
        print("本次验证用的临时文件已删除。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configure-lifecycle", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.configure_lifecycle))
    except Exception as exc:
        # SDK exception strings can contain request URLs; print safe codes only.
        code = getattr(exc, "code", None) or getattr(exc, "response", {}).get("Error", {}).get("Code")
        print(
            f"七牛验证失败：{type(exc).__name__} / {code or 'connection_or_configuration'}", file=sys.stderr
        )
        raise SystemExit(1) from None

import base64
import io
from PIL import Image
from app.core.config import get_settings
from app.core.errors import AppError
from .http import request, fetch_bytes


def inspect_image(raw):
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ("PNG", "JPEG", "WEBP") or im.width * im.height > 40_000_000:
                raise ValueError()
            info = (im.format, im.width, im.height)
            im.verify()
        return info
    except Exception:
        raise AppError("INVALID_IMAGE", "图片格式或内容不合法", 422) from None


class GPTImage:
    async def generate(self, prompt, ratio, quality, references):
        s = get_settings()
        params = dict(
            model=s.image_model,
            prompt=prompt,
            n=1,
            quality=quality,
            size={"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}[ratio],
        )
        if s.image_response_format:
            params["response_format"] = s.image_response_format
        headers = {"Authorization": "Bearer " + s.image_api_key.get_secret_value()}
        logs = []
        if references:
            if len(references) > s.image_max_references:
                raise AppError("REFERENCE_LIMIT", "参考图超过模型配置上限，已停止生成", 409)
            try:
                response = await request(
                    "POST",
                    s.image_base_url.rstrip("/") + "/v1/images/edits",
                    headers=headers,
                    data={k: str(v) for k, v in params.items()},
                    files=[
                        ("image[]", (f"ref{i}.png", raw, "image/png")) for i, raw in enumerate(references)
                    ],
                    timeout=s.image_timeout_seconds,
                    retries=0,
                )
            except AppError as exc:
                if exc.details.get("status") not in (404, 405, 415, 422):
                    raise
                raise AppError(
                    "REFERENCE_UNSUPPORTED",
                    "当前生图服务未接受角色参考图。为保持人物一致性，已停止生成，请检查参考图接口",
                    422,
                ) from exc
        else:
            response = await request(
                "POST",
                s.image_base_url.rstrip("/") + "/v1/images/generations",
                headers=headers,
                json=params,
                timeout=s.image_timeout_seconds,
                retries=0,
            )
        item = response.json()["data"][0]
        raw = (
            base64.b64decode(item["b64_json"], validate=True)
            if item.get("b64_json")
            else await fetch_bytes(item["url"])
        )
        inspect_image(raw)
        # Normalize format instead of naming JPEG bytes .png.
        with Image.open(io.BytesIO(raw)) as im:
            output = io.BytesIO()
            im.convert("RGB").save(output, format="PNG")
        return output.getvalue(), logs

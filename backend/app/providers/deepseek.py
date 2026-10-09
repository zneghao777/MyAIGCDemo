import json
import os
from uuid import uuid4
from pydantic import ValidationError
from app.core.config import get_settings
from app.core.errors import AppError
from .http import request
from app.core.provider_audit import current_task_id, timestamp


def preserve_output(model, response_data, content, errors):
    """Keep paid final output for manual recovery; never save reasoning or headers."""
    settings = get_settings()
    if settings.testing:
        return
    folder = settings.local_media_root / "audit" / "structured-output"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid4().hex + ".json")
    record = {
        "at": timestamp(), "taskId": current_task_id.get(),
        "responseId": response_data.get("id"), "schema": model.__name__,
        "usage": response_data.get("usage", {}), "content": content,
        "validationIssues": errors,
        "finishReason": response_data["choices"][0].get("finish_reason"),
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2, default=str)
    return path.name


class DeepSeek:
    async def structured(self, model, instruction, brief):
        s = get_settings()
        messages = [
            {
                "role": "system",
                "content": instruction
                + "\n只输出 JSON，不要 Markdown。完整 JSON Schema："
                + json.dumps(model.model_json_schema(), ensure_ascii=False),
            },
            {"role": "user", "content": json.dumps(brief, ensure_ascii=False)},
        ]
        for attempt in range(2):
            body = dict(
                model=s.deepseek_model,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=s.llm_max_tokens_per_job,
            )
            if s.deepseek_reasoning_effort:
                body["reasoning_effort"] = s.deepseek_reasoning_effort
            if s.deepseek_thinking:
                body["thinking"] = {"type": s.deepseek_thinking}
            response = await request(
                "POST",
                s.deepseek_base_url.rstrip("/") + "/chat/completions",
                retries=0,
                headers={"Authorization": "Bearer " + s.deepseek_api_key.get_secret_value()},
                json=body,
            )
            response_data = response.json()
            content = response_data["choices"][0]["message"]["content"]
            try:
                result = model.model_validate_json(content)
            except (ValidationError, ValueError) as exc:
                errors = exc.errors(include_input=False, include_context=False, include_url=False) if isinstance(exc, ValidationError) else [{"msg": str(exc)}]
                archive = preserve_output(model, response_data, content, errors)
                # Storyboards are large, user-editable drafts. Preserve the paid
                # JSON and let the application repair it without a second charge.
                if attempt or model.__name__ == "Storyboard":
                    try:
                        raw_value = json.loads(content)
                    except (ValueError, TypeError):
                        raw_value = None
                    raise AppError(
                        "PROVIDER_OUTPUT_INVALID", "模型输出未通过结构校验，已保留原始输出供修正", 422,
                        {"rawValue": raw_value, "rawText": content, "archivePath": archive, "validationIssues": errors},
                    ) from None
                messages.extend(
                    [
                        {"role": "assistant", "content": content or "{}"},
                        {
                            "role": "user",
                            "content": "请按以下具体校验错误修正字段，重新输出完整 JSON：" + json.dumps(errors, ensure_ascii=False, default=str),
                        },
                    ]
                )
            else:
                preserve_output(model, response_data, content, [])
                return result

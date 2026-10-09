"""Cost-free, audited recovery. Never guess a speaker or replace an active storyboard."""

import json
import re
from copy import deepcopy

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Candidate
from app.schemas.creative import Storyboard


def dependencies(value):
    """Confirmation counters and audit metadata are not creative dependencies."""
    ignored = {"version", "revision", "_event", "url", "notes", "checks", "checked_at", "visual_checks"}

    def clean(v):
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items() if k not in ignored}
        if isinstance(v, list):
            return [clean(x) for x in v]
        return v

    return clean(
        {
            **{k: value.get(k) for k in ("plan", "cast", "locations")},
            "style": value.get("render_style", (value.get("plan") or {}).get("style")),
            "ratio": value.get("render_ratio", (value.get("plan") or {}).get("ratio")),
        }
    )


def parse_text(text):
    """Repair formatting only; preserve every word of string values."""
    if not isinstance(text, str) or len(text) > 2_000_000:
        return None, []
    candidate = text.strip()
    changes = []
    if candidate.startswith("```json\n") and candidate.endswith("```"):
        candidate = candidate[8:-3].strip()
        changes.append("移除 JSON 外层代码围栏")
    try:
        return json.loads(candidate), changes
    except ValueError:
        pass
    out = []
    inside = escaped = textual = False
    quote_count = comma_count = 0
    text_fields = (
        r'"(?:text|action|start_state|end_state|image_prompt|composition|description|sound_notes)"\s*:\s*$'
    )
    for index, char in enumerate(candidate):
        if inside:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                following = candidate[index + 1 :].lstrip()
                if textual and following and following[0] not in ",}]":
                    out.append("\\")
                    quote_count += 1
                else:
                    inside = False
        elif char == '"':
            textual = bool(re.search(text_fields, "".join(out[-200:])))
            inside = True
        elif char == "," and candidate[index + 1 :].lstrip().startswith(("}", "]")):
            comma_count += 1
            continue
        out.append(char)
    try:
        value = json.loads("".join(out))
    except ValueError:
        return None, []
    if quote_count:
        changes.append(f"转义文本内 {quote_count} 处未转义引号，保留原台词")
    if comma_count:
        changes.append(f"移除 {comma_count} 处多余尾逗号")
    return value, changes


def normalize(value, inp):
    from .creative import image_fingerprint, location_fingerprint, variant_fingerprint

    value = deepcopy(value)
    changes = []
    if not isinstance(value, dict) or not isinstance(value.get("scenes"), list):
        return value, changes
    cast = inp.get("cast", {})
    location_ids = set(inp.get("locations", {})) | {location["id"] for location in inp.get("plan", {}).get("locations", [])}
    style = inp.get("render_style", inp.get("plan", {}).get("style", ""))
    names = {}
    for cid, state in cast.items():
        names.setdefault(state.get("persona", {}).get("name", ""), []).append(cid)

    def role(token):
        if not isinstance(token, str):
            return None
        if token in cast:
            return token
        matches = names.get(token, [])
        return matches[0] if len(matches) == 1 else None

    for index, shot in enumerate(value["scenes"]):
        if not isinstance(shot, dict):
            continue
        prefix = f"镜头 {index + 1}"
        original_cast = shot.get("cast", {})
        if not isinstance(original_cast, dict):
            continue
        bound = {}
        for token, revision in original_cast.items():
            cid = role(token)
            if cid and cast[cid].get("confirmed"):
                bound[cid] = cast[cid]["revision"]
            else:
                bound[token] = revision
        if bound != original_cast:
            changes.append(f"{prefix}：关联当前已确认角色版本")
        shot["cast"] = bound
        for field in ("variants", "character_views", "spatial_relations", "offscreen_cast"):
            data = shot.get(field)
            if isinstance(data, dict):
                mapped = {role(k) or k: v for k, v in data.items()}
                if mapped != data:
                    shot[field] = mapped
                    changes.append(f"{prefix}：关联{field}中的角色引用")
        views = shot.get("character_views", {})
        if isinstance(views, dict):
            for cid, name in list(views.items()):
                state = cast.get(cid)
                if state and (name == "main" or (name == "turnaround" and not state.get("views", {}).get(name))):
                    del views[cid]
                    changes.append(f"{prefix}：{cast[cid]['persona']['name']}使用已确认主视图")
        variants = shot.get("variants", {})
        if isinstance(variants, dict):
            for cid, name in list(variants.items()):
                state = cast.get(cid)
                if not state or not isinstance(name, str):
                    continue
                persona = state.get("persona", {})
                description = persona.get("variants", {}).get(name, "")
                base_appearance = "；".join(str(persona.get(field, "")) for field in ("clothing", "accessories", "hair", "appearance"))
                traits = [part.strip() for part in re.split(r"[，,、；;。]", description) if part.strip()] if isinstance(description, str) else []
                matches_base = bool(traits) and all(
                    len(trait) >= 2 and (trait in base_appearance or
                    (trait == "披发" and re.search(r"披散|散落", persona.get("hair", ""))))
                    for trait in traits
                )
                main = state.get("image") or {}
                alternate = state.get("references", {}).get(name) or {}
                # Reuse only an explicit alias of the already-confirmed main outfit.
                # A genuinely different costume still needs its own selected reference.
                if (
                    isinstance(description, str)
                    and len(description.strip()) >= 4
                    and matches_base
                    and main.get("key")
                    and main.get("fingerprint") == image_fingerprint(persona, style)
                    and alternate.get("fingerprint") != variant_fingerprint(state, name, style)
                ):
                    del variants[cid]
                    changes.append(
                        f"{prefix}：{persona['name']}的“{name}”已包含在确认主造型中，复用主图；未重生成"
                    )
        spatial = shot.get("spatial_relations")
        if isinstance(spatial, dict):
            for token in list(spatial):
                if token not in cast and token in location_ids and isinstance(spatial[token], str):
                    shot["composition"] = (shot.get("composition", "") + "；" + spatial.pop(token)).strip("；")
                    changes.append(f"{prefix}：将环境布局保留为构图描述")
        lines = shot.get("lines", [])
        if not isinstance(lines, list):
            continue
        narration = shot.get("narration", [])
        original_audio_order = [line.get("id") for line in [*lines, *(narration if isinstance(narration, list) else [])] if isinstance(line, dict)]
        moved_narration = False
        kept = []
        removed_ids = set()
        for line in lines:
            if not isinstance(line, dict):
                kept.append(line)
                continue
            cid = role(line.get("speaker_id"))
            if cid and cast[cid].get("confirmed"):
                if line.get("speaker_id") != cid or cid not in bound:
                    changes.append(f"{prefix}：绑定台词发言角色 {cast[cid]['persona']['name']}")
                line["speaker_id"] = cid
                if line.get("delivery") == "off_screen" or cid in shot.get("offscreen_cast", {}):
                    shot.setdefault("offscreen_cast", {})[cid] = cast[cid]["revision"]
                else:
                    bound[cid] = cast[cid]["revision"]
            elif (
                line.get("speaker_id") is None
                and isinstance(shot.get("action", ""), str)
                and isinstance(line.get("text"), str)
                and re.match(r"^(手机屏幕|屏幕|手机).*?(亮起|弹出|显示)", line["text"])
            ):
                shot["action"] = (shot.get("action", "") + "；" + line["text"]).strip("；")
                removed_ids.add(line.get("id"))
                changes.append(f"{prefix}：将无人发言的屏幕描述保留为画面动作")
                continue
            # Explicit null is the provider contract for narration; never infer an
            # unknown/missing character identity from the dialogue text.
            elif "speaker_id" in line and line["speaker_id"] is None and isinstance(shot.get("narration", []), list):
                shot.setdefault("narration", []).append(line)
                moved_narration = True
                changes.append(f"{prefix}：将旁白归入旁白栏，保留原文与声音顺序")
                continue
            kept.append(line)
        shot["lines"] = kept
        if moved_narration and not shot.get("audio_order"):
            shot["audio_order"] = original_audio_order
        if removed_ids:
            if isinstance(shot.get("audio_order", []), list):
                shot["audio_order"] = [x for x in shot.get("audio_order", []) if x not in removed_ids]
            for step in shot.get("action_steps") or []:
                if isinstance(step, dict) and step.get("trigger_line_id") in removed_ids:
                    step["trigger_line_id"] = None
                    step["trigger_sec"] = None
        location_id = shot.get("location_id")
        location = inp.get("locations", {}).get(location_id) if isinstance(location_id, str) else None
        if not location or not location.get("confirmed"):
            continue
        ref = location.get("image") or {}
        if not ref.get("key") or ref.get("fingerprint") != location_fingerprint(location, style):
            continue
        if shot.get("location_revision") != location["revision"]:
            shot["location_revision"] = location["revision"]
            changes.append(f"{prefix}：关联当前已确认环境图")
        state_name = shot.get("location_state", "")
        if not isinstance(state_name, str):
            continue
        state_ref = location.get("states", {}).get(state_name) or {}
        if state_name and not (
            state_ref.get("confirmed")
            and state_ref.get("key")
            and state_ref.get("fingerprint") == location_fingerprint(location, style, state_name)
        ):
            shot["location_state"] = ""
            shot["start_state"] = (shot.get("start_state", "") + f"；环境描述：{state_name}").strip("；")
            changes.append(f"{prefix}：使用基础环境参考，将“{state_name}”保留为剧情描述；未生成新素材")
    return value, changes


async def validate(db, p, value, inp):
    from . import creative as flow

    value, changes = normalize(value, inp)
    issues = []
    try:
        board = Storyboard.model_validate(value).model_dump()
    except ValidationError as exc:
        issues = [
            {"code": x["type"], "path": list(x["loc"]), "message": x["msg"]}
            for x in exc.errors(include_input=False, include_context=False, include_url=False)
        ]
        return value, changes, issues
    count = inp.get("plan", {}).get("scene_count")
    if inp.get("plan", {}).get("fixed_scene_count") and count is not None and len(board["scenes"]) != count:
        issues.append(
            {
                "code": "SCENE_COUNT",
                "message": f"已确认方案需要 {count} 镜，草稿有 {len(board['scenes'])} 镜；请调整故事或让 AI 纠错",
            }
        )
    for index, shot in enumerate(board["scenes"]):
        try:
            await flow.validate_shot(db, p.id, shot)
        except (AppError, ValueError) as exc:
            issues.append(
                {
                    "scene_index": index,
                    "title": shot["title"],
                    "code": getattr(exc, "code", "VALIDATION_ERROR"),
                    "message": getattr(exc, "message", str(exc)),
                }
            )
    return board, changes, issues


def archived_text(candidate):
    """Old JSON-null candidates can recover their task's archived final output."""
    folder = get_settings().local_media_root / "audit/structured-output"
    name = candidate.data.get("provider_archive", "")
    paths = (
        [folder / name]
        if name and name == name.split("/")[-1] and name.endswith(".json")
        else sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:2000]
    )
    for path in paths:
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if record.get("taskId") == candidate.task_id and record.get("schema") == "Storyboard":
            return record.get("content", "")
    return ""


async def recover(db, p, candidate):
    from . import creative as flow

    inp = await flow.current_input(db, p, "storyboard")
    value = candidate.data.get("value")
    text = candidate.data.get("raw_text") or archived_text(candidate)
    parsed_changes = []
    if value is None:
        value, parsed_changes = parse_text(text)
    board, changes, issues = await validate(db, p, value, inp)
    changes = parsed_changes + changes
    if value is None:
        issues = [
            {
                "code": "JSON_REPAIR_REQUIRED",
                "message": "原始文本已保留；本地无法可靠修复，可选择 AI 纠错并先查看费用",
            }
        ]
    fingerprint = flow.digest(dependencies(inp))
    result_hash = flow.digest(
        {"value": board, "issues": issues, "parent": candidate.id, "fingerprint": fingerprint}
    )
    from sqlalchemy import select

    children = await db.scalars(
        select(Candidate).where(Candidate.project_id == p.id, Candidate.kind == "storyboard")
    )
    for child in children:
        if child.data.get("source") == "local-recovery" and child.data.get("recovery_hash") == result_hash:
            return child, not issues
    child = Candidate(
        project_id=p.id,
        entity_id="",
        kind="storyboard",
        fingerprint=fingerprint,
        task_id=candidate.task_id,
        data={
            **deepcopy(candidate.data),
            "value": board,
            "raw_text": text,
            "original_value": deepcopy(candidate.data.get("value")),
            "original_request": candidate.data.get("request", {}),
            "request": {"operation": "storyboard", "target": ""},
            "source": "local-recovery",
            "parent_candidate_id": candidate.id,
            "recovery_hash": result_hash,
            "corrections": changes,
            "validation_stage": "semantic" if issues else None,
            "validation_issues": issues,
            "draft": bool(issues),
            "logs": [*candidate.data.get("logs", []), "本地修复并关联当前输入；未调用模型，原候选保留"],
        },
    )
    db.add(child)
    await db.flush()
    return child, not issues

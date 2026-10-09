"""Draft publication, dependency previews and readable immutable history."""

from contextvars import ContextVar

from sqlalchemy import select

from app.models import Character, ExportJob, Revision, Scene
from app.providers import providers
from app.services.resources import children

creation_event = ContextVar("creation_event", default=None)


def plan_impact(previous, proposed):
    from app.schemas.creative import Plan

    if previous:
        previous = Plan.model_validate(previous).model_dump()
    changed = [k for k in proposed if proposed.get(k) != (previous or {}).get(k)]
    style = "style" in changed
    shots = bool(
        set(changed)
        & {"synopsis", "theme", "beats", "ending", "duration", "scene_count", "ratio", "style", "locations"}
    )
    messages = []
    if style:
        messages.append("视觉风格变化：角色形象需重新选定，角色与分镜阶段需再次确认；声音保留。")
    elif "ratio" in changed:
        messages.append("画幅变化：分镜需再次确认，镜头画面需更新；角色形象与声音保留。")
    elif shots:
        messages.append("故事或场景变化：分镜需再次核对确认；已有画面、配音按各镜头实际依赖保留。")
    if "characters" in changed:
        messages.append("人物初稿变化：本片角色资产不会自动覆盖，请查看差异并显式同步。")
    if not messages:
        messages.append("仅更新故事文稿，不影响已确认角色、镜头和媒体。")
    return {"changed": changed, "cast": style, "shots": shots, "messages": messages}


async def publish_plan(db, p, st, data):
    from app.schemas.creative import Plan
    from app.services import creative as flow

    plan = Plan.model_validate(data).model_dump()
    baseline = st.get("confirmed_plan") or (st.get("plan") if st.get("plan_confirmed") else None)
    impact = plan_impact(baseline, plan)
    if baseline and impact["cast"]:
        for ch in await children(db, Character, p.id):
            await flow.save_state(db, ch, {**ch.creative, "confirmed": False}, "character")
        st["cast_confirmed"] = False
    if baseline and impact["shots"]:
        st["shots_confirmed"] = False
    st.update(plan=plan, confirmed_plan=plan, plan_draft=None, plan_confirmed=True)
    return plan


async def readiness(db, p):
    from app.services import creative as flow

    result = []
    for ch in await children(db, Character, p.id):
        st = ch.creative or {}
        image = bool(st.get("image")) and st["image"].get("fingerprint") == flow.image_fingerprint(
            st.get("persona", {}), p.style
        )
        voice = bool(st.get("voice", {}).get("key")) if st.get("voice") else False
        voice = voice and st["voice"].get("fingerprint") == flow.digest(
            flow.voice_spec(st.get("persona", {}))
        )
        if st.get("persona", {}).get("role_kind") == "background":
            voice = True
        result.append(
            {
                "id": ch.id,
                "name": ch.name,
                "image": image,
                "voice": voice,
                "confirmed": st.get("confirmed", False),
            }
        )
    return result


LABELS = {
    "title": "片名 / 镜头名",
    "synopsis": "梗概",
    "theme": "主题",
    "beats": "故事节奏",
    "ending": "结局",
    "duration": "时长",
    "scene_count": "镜头数",
    "ratio": "画幅",
    "style": "视觉风格",
    "characters": "人物初稿",
    "locations": "场景",
    "name": "姓名",
    "identity": "身份",
    "personality": "性格",
    "motivation": "动机",
    "relationships": "关系",
    "appearance": "外貌",
    "clothing": "服装",
    "image_prompt": "画面描述",
    "voice_description": "音色描述",
    "voice_prompt": "声音设计",
    "base_speed": "语速",
    "base_pitch": "音高",
    "voice_mode": "声音策略",
    "action": "动作",
    "lines": "台词",
    "narration": "旁白",
    "cast": "角色引用",
    "confirmed": "角色定稿",
    "plan_confirmed": "故事确认",
    "cast_confirmed": "角色阶段确认",
    "shots_confirmed": "分镜确认",
    "image": "形象 / 画面",
    "voice": "声音",
    "audio": "配音",
    "background": "背景",
    "arc": "人物变化",
    "speech": "说话习惯",
    "age": "年龄",
    "hair": "发型",
    "features": "特征",
    "build": "体型",
    "accessories": "配饰",
    "variants": "补充造型",
    "references": "补充参考",
    "composition": "构图",
    "shot_type": "景别",
    "camera_angle": "机位",
    "camera_move": "运镜",
    "expression": "表情",
    "location_id": "场景引用",
    "location_description": "场景描述",
    "sound_notes": "声音备注",
    "audio_order": "声音顺序",
    "sound_effects": "音效",
    "narrator": "旁白配置",
    "voice_reference": "声音参考",
    "identity_traits": "固定身份特征",
    "role_kind": "发言角色 / 背景群体",
    "views": "角色视图素材包",
    "visual_checks": "角色人工检查",
    "purpose": "本镜目的",
    "start_state": "起始状态",
    "end_state": "结束状态",
    "action_steps": "动作时间事件",
    "spatial_relations": "左右 / 视线 / 朝向",
    "continuity_from": "前镜尾帧依赖",
    "continuity_requirements": "承接条件",
    "location_revision": "场景确认版本",
    "location_state": "环境状态",
    "character_views": "本镜角色视图",
    "last_frame": "选用尾帧",
    "subtitle_cues": "逐句字幕时间",
    "subtitles_calibrated": "字幕人工校准",
    "video_input": "H3 素材与声音策略",
    "review": "逐镜艺术验收",
    "landmarks": "地标",
    "lighting": "光照",
    "palette": "色调",
    "spatial_notes": "环境空间关系",
    "states": "环境状态素材",
}


def content(data, kind):
    if kind == "project":
        return {
            **(data.get("plan_draft") or data.get("plan") or {}),
            **{k: data.get(k) for k in ("plan_confirmed", "cast_confirmed", "shots_confirmed", "narrator")},
        }
    if kind == "character":
        return {
            **data.get("persona", {}),
            **{
                k: data.get(k)
                for k in ("image", "voice", "confirmed", "references", "views", "visual_checks")
            },
        }
    if kind == "location":
        return {
            **data.get("location", {}),
            **{k: data.get(k) for k in ("image", "states", "confirmed", "checks", "notes")},
        }
    return {
        **(data.get("shot") or {}),
        **{k: data.get(k) for k in ("image", "audio", "last_frame", "review")},
    }


def readable(value):
    if value is None:
        return "未设置"
    if isinstance(value, bool):
        return "已确认" if value else "待确认"
    if isinstance(value, list):
        return "\n".join(readable(v) for v in value)
    if isinstance(value, dict):
        if "text" in value:
            return value["text"]
        if "name" in value:
            return value["name"] + "：" + (value.get("identity") or value.get("description", ""))
        if "key" in value or "fingerprint" in value:
            return "已选用素材"
        return "；".join(
            f"{LABELS.get(k, k)}：{readable(v)}"
            for k, v in value.items()
            if k not in ("candidate_id", "revision", "voice_id", "model", "provider")
        )
    return str(value)


def media(data):
    url = providers().storage.url
    return {
        "image": url((data.get("image") or {}).get("key")),
        "voice": url((data.get("voice") or {}).get("key")),
        "audio": [
            {"url": url(x.get("key")), "text": x.get("line", {}).get("text", "")}
            for x in (data.get("audio") or {}).get("segments", [])
        ],
    }


async def history(db, p):
    rows = list(
        await db.scalars(
            select(Revision).where(Revision.project_id == p.id).order_by(Revision.created_at, Revision.id)
        )
    )
    chars = {c.id: c for c in await children(db, Character, p.id)}
    scenes = {c.id: c for c in await children(db, Scene, p.id)}
    previous, items = {}, []
    revision_map = {r.id: r for r in rows}
    locations = {x["id"]: x["name"] for x in ((p.creative or {}).get("plan") or {}).get("locations", [])}

    def describe(k, value):
        if k == "cast" and isinstance(value, dict):
            return (
                "；".join(
                    f"{chars[cid].name if cid in chars else '已归档角色'} · 第 {revision_map[rid].data.get('version', '?') if rid in revision_map else '?'} 版"
                    for cid, rid in value.items()
                )
                or "无出场角色"
            )
        if k == "location_id":
            return locations.get(value, "未设置 / 已归档场景")
        return readable(value)

    for r in rows:
        before = previous.get((r.kind, r.entity_id), {})
        a, b = content(before, r.kind), content(r.data, r.kind)
        changes = [
            {
                "field": k,
                "label": LABELS.get(k, k),
                "before": describe(k, a.get(k)),
                "after": describe(k, b.get(k)),
            }
            for k in dict.fromkeys([*b, *a])
            if a.get(k) != b.get(k)
        ]
        obj = (
            p
            if r.kind == "project"
            else chars.get(r.entity_id)
            if r.kind == "character"
            else scenes.get(r.entity_id)
        )
        name = (
            "故事方案"
            if r.kind == "project"
            else r.data.get("persona", {}).get("name", "角色")
            if r.kind == "character"
            else r.data.get("location", {}).get("name", "环境场景")
            if r.kind == "location"
            else (r.data.get("shot") or {}).get("title", "镜头")
        )
        labels = [x["label"] for x in changes]
        summary = "、".join(labels[:3]) or "阶段记录"
        if any(x["field"] == "voice" for x in changes):
            summary = "更换声音"
        elif any(x["field"] == "image" for x in changes):
            summary = "更换形象 / 画面"
        action = (r.data.get("_event") or {}).get("action", "")
        if action.endswith("/restore"):
            summary = "基于历史创建新版本"
        elif "/confirm/" in action:
            summary = {"plan": "确认故事", "cast": "确认角色阶段", "shots": "确认分镜"}.get(
                action.rsplit("/", 1)[-1], summary
            )
        elif action.endswith("/plan"):
            summary = "保存故事草稿 · " + summary
        items.append(
            {
                "id": r.id,
                "kind": r.kind,
                "entityId": r.entity_id,
                "name": name,
                "summary": f"{name}：{summary}",
                "createdAt": r.created_at,
                "event": r.data.get("_event"),
                "changes": changes,
                "beforeMedia": media(before),
                "afterMedia": media(r.data),
                "current": (p.creative or {}).get("locations", {}).get(r.entity_id, {}).get("revision")
                == r.id
                if r.kind == "location"
                else bool(obj and (obj.creative or {}).get("revision") == r.id),
                "usedBy": [
                    sc.title
                    for sc in scenes.values()
                    if r.id in (((sc.creative or {}).get("shot") or {}).get("cast", {})).values()
                    or ((sc.creative or {}).get("shot") or {}).get("location_revision") == r.id
                ],
                "restorable": bool(
                    r.data.get("location") and (p.creative or {}).get("locations", {}).get(r.entity_id)
                )
                if r.kind == "location"
                else bool(
                    obj
                    and (
                        r.data.get("plan_draft") or r.data.get("plan")
                        if r.kind == "project"
                        else r.data.get("persona")
                        if r.kind == "character"
                        else r.data.get("shot")
                    )
                ),
                "data": r.data,
            }
        )
        previous[(r.kind, r.entity_id)] = r.data
    for ex in await db.scalars(select(ExportJob).where(ExportJob.project_id == p.id)):
        items.append(
            {
                "id": ex.id,
                "kind": "export",
                "entityId": ex.id,
                "name": "成片导出",
                "summary": "成片导出："
                + {"done": "已完成", "failed": "失败", "queued": "等待中", "running": "合成中"}.get(
                    ex.status, ex.status
                ),
                "createdAt": ex.created_at,
                "changes": [],
                "restorable": False,
                "current": False,
                "url": providers().storage.url(ex.output_key),
                "data": ex.settings,
            }
        )
    return sorted(items, key=lambda x: x["createdAt"], reverse=True)

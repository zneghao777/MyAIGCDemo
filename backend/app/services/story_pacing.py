"""Explainable creative advice, separate from structural generation errors."""
import re


def estimated_line_seconds(line):
    text = line.get("text", "")
    units = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text))
    return round(units / (3.5 * line.get("speed", 1)) + line.get("pause_after", 0.15), 2)


def assess(plan, scenes):
    warnings = []
    coverage = set()
    total = 0
    actual = 0
    for scene in scenes:
        state = scene.creative or {}
        shot = state.get("shot") or {}
        total += shot.get("duration", scene.duration_sec)
        coverage.update(shot.get("beat_indices", []))
        lines = shot.get("lines", []) + shot.get("narration", [])
        measured = (state.get("audio") or {}).get("duration_ms", 0) / 1000
        estimate = sum(estimated_line_seconds(x) for x in lines if not x.get("continues_from"))
        if max(measured, estimate) > shot.get("duration", scene.duration_sec) - 0.3:
            warnings.append(f"{scene.title}：台词{'实测' if measured else '预计'}约 {max(measured, estimate):g} 秒，请缩短台词、延长片段或安排跨镜延续")
        if len(shot.get("action_steps", [])) > shot.get("duration", 5) / 2:
            warnings.append(f"{scene.title}：动作较密集，建议拆镜或减少动作")
        edit = state.get("edit") or {}
        actual += max(0, edit.get("out_sec", 0) - edit.get("in_sec", 0)) if edit else (state.get("video") or {}).get("duration", 0)
    for i, beat in enumerate(plan.get("beats", [])):
        if i not in coverage:
            warnings.append(f"剧情节点 {i + 1} 尚未关联镜头：{beat}")
    target = plan.get("duration", total)
    if abs(total - target) > max(2, target * .1):
        warnings.append(f"设计共 {total:g} 秒，目标 {target:g} 秒；请补足情节或调整目标，导出不会自动变速凑时长")
    return {"planned_seconds": total, "measured_seconds": actual, "target_seconds": target,
            "covered_beats": sorted(coverage), "warnings": warnings,
            "note": "节点关联仅表示创作安排；剧情是否成立、台词与口型是否准确仍需回放检查。"}

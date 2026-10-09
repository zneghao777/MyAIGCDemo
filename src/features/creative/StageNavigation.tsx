import { createPortal } from "react-dom";
import { BookOpen, UsersRound, ImageIcon, Clapperboard, Play, Check } from "lucide-react";
import { uiCopy } from "./copy";
import type { Flow } from "./types";
const keys = ["plan", "cast", "locations", "shots", "export"] as const;
/* 阶段 key 与 workflowReadiness 的键名不同，这里显式映射，
   避免再用文案比对（"已确认" / "已就绪"）来判断阶段是否完成。 */
const readinessKey = {
  plan: "plan",
  characters: "cast",
  locations: "locations",
  storyboard: "shots",
  generation: "export",
} as const;
export function confirmedStageCount(readiness: Flow["workflowReadiness"]) {
  return keys.filter(key => readiness[key]).length;
}
export function StageNavigation({ flow, current, onSelect }: { flow: Pick<Flow, "workflowReadiness" | "stageStates">; current?: string; onSelect: (stage: string) => void }) {
  const stages = [
    ["plan", uiCopy["01 故事方案"], flow.stageStates.plan],
    ["characters", uiCopy["02 角色形象与声音"], flow.stageStates.characters],
    ["locations", uiCopy["03 环境素材"], flow.workflowReadiness.locations ? uiCopy["已确认"] : uiCopy["待确认"]],
    ["storyboard", uiCopy["04 分镜创作"], flow.stageStates.storyboard],
    ["generation", uiCopy["05 预览与导出"], !flow.workflowReadiness.structure_ready ? uiCopy["结构待就绪"] : flow.workflowReadiness.video_accepted ? uiCopy["已就绪"] : flow.workflowReadiness.media_complete ? "待回放检查" : "视频待制作"],
  ];
  const icons = [BookOpen, UsersRound, ImageIcon, Clapperboard, Play];
  const navigation = <nav className="creative-steps" aria-label={uiCopy["创作阶段"]}>{stages.map(([key, label, status], index) => {
    const Icon = icons[index];
    const done = flow.workflowReadiness[readinessKey[key as keyof typeof readinessKey]];
    const state = done ? "done" : current === key ? "current" : "todo";
    return <button
      key={key}
      aria-label={`${label.replace("故事方案", "故事").replace("角色形象与声音", "角色与声音").replace("环境素材", "场景").replace("分镜创作", "分镜").replace("预览与导出", "成片")} ${status}`}
      data-state={state}
      aria-current={current === key ? "step" : undefined}
      className={current === key ? "active" : ""}
      onClick={() => onSelect(key)}
    title={status}
    ><Icon size={18}/><span>{label.replace("故事方案", "故事").replace("角色形象与声音", "角色与声音").replace("环境素材", "场景").replace("分镜创作", "分镜").replace("预览与导出", "成片")}<small>{status}</small></span>{done && <Check size={14}/>}</button>;
  })}</nav>;
  const host = typeof document !== "undefined" ? document.getElementById("project-stage-navigation") : null;
  return host ? createPortal(navigation, host) : navigation;
}

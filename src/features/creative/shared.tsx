"use client";
import { uiCopy } from "@/features/creative/copy";

import { copy, operationLabels as operationNames } from "./copy";
import { ErrorNotice } from "./ErrorNotice";
import { GenerationStatus } from "./GenerationStatus";
import { createPortal } from "react-dom";
import { History, ListVideo } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { Project } from "@/lib/types";
import type { Candidate, Persona } from "@/lib/creative-types";
export type GenerationRequest = {
  operation: string;
  target?: string;
  voice_id?: string;
  variant?: string;
  view?: string;
  use_reference?: boolean;
  auto_apply?: boolean;
  state?: string;
  frame?: "first" | "last";
  nonce?: string;
  text?: string;
  regenerate_line_ids?: string[];
};
export type CreativeTask = {
  id: string;
  operation?: string | null;
  targetId?: string;
  sceneId?: string;
  typeLabel?: string;
  createdAt?: number | string;
  generationRequest?: GenerationRequest;
  status: string;
  progress: number;
  error?: string;
  logs?: unknown[];
  result?: { operation?: string; draft?: boolean; applied?: boolean; message?: string };
};
export type Readiness = {
  id: string;
  name: string;
  image: boolean;
  voice: boolean;
  confirmed: boolean;
};
export type Capabilities = {
  maxImageReferences: number;
  voiceDesign: boolean;
  referenceVoiceLock: boolean;
  voiceClone: boolean;
  roleAudio: boolean;
  ttsModel: string;
  defaultVoice: string;
};
export { operationLabels as operationNames } from "./copy";
export const fieldNames: Record<string, string> = {
  name: uiCopy["姓名"],
  identity: uiCopy["身份"],
  identity_traits: uiCopy["固定身份特征"],
  age: uiCopy["年龄感"],
  personality: uiCopy["性格"],
  background: uiCopy["背景"],
  motivation: uiCopy["动机"],
  relationships: uiCopy["关系"],
  arc: uiCopy["人物变化"],
  speech: uiCopy["说话习惯"],
  appearance: uiCopy["外貌"],
  build: uiCopy["体型"],
  hair: uiCopy["发型"],
  features: uiCopy["显著特征"],
  clothing: uiCopy["服装"],
  accessories: uiCopy["配饰"],
  image_prompt: uiCopy["形象描述"],
  voice_description: uiCopy["声音描述"],
  voice_prompt: uiCopy["声音设计描述"],
};
export const blankPersona = (): Persona =>
  ({
    ...Object.fromEntries(Object.keys(fieldNames).map((k) => [k, ""])),
    name: uiCopy["新角色"],
    base_speed: 1,
    voice_mode: "stable",
    base_pitch: 0,
    variants: {},
  }) as Persona;
export function Field({
  label,
  value,
  onChange,
  large = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  large?: boolean;
}) {
  return (
    <label className="creative-field">
      <span>{label}</span>
      {large ? (
        <textarea
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input value={value} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  );
}
export function ActionBar({
  children,
  status,
}: {
  children: ReactNode;
  status: ReactNode;
}) {
  return (
    <footer className="cw-actionbar">
      <div role="status">{status}</div>
      <div className="creative-actions">{children}</div>
    </footer>
  );
}
export function useCreativeDraft<T>(key: string, initial: T) {
  const [draft, setDraft] = useState<T>(() => {
    try {
      const saved = sessionStorage.getItem(key);
      return saved ? JSON.parse(saved) : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(draft));
    } catch {
      /* in-memory editing remains available */
    }
  }, [key, draft]);
  return [draft, setDraft] as const;
}
export function TaskFeedback({
  tasks,
  project,
  candidates = [],
  target,
  operations,
  onCancel,
  onRetry,
  maxItems = 1,
}: {
  tasks: CreativeTask[];
  project?: Project;
  candidates?: Candidate[];
  target?: string;
  operations?: string[];
  maxItems?: number;
  onCancel?: (id: string) => void;
  onRetry?: (r: GenerationRequest) => void;
}) {
  const relevant = tasks
    .filter(
      (t) =>
        (!target || (t.targetId || t.sceneId) === target) &&
        (!operations ||
          operations.includes(t.operation || t.result?.operation || "")),
    )
    .slice(-maxItems)
    .reverse();
  if (maxItems > 1) {
    const rank = (status: string) => ["failed", "cancelled"].includes(status) ? 0 : ["running", "queued"].includes(status) ? 1 : 2;
    relevant.sort((a, b) => rank(a.status) - rank(b.status));
  }
  const titles = relevant.map(t => taskTitle(t, project));
  return (
    <div className="cw-tasks" aria-label={uiCopy["相关生成任务"]} aria-live="polite">
      {relevant.map((t, index) => {
        const pending = ["running", "queued"].includes(t.status);
        const result = candidates.find((c) => c.taskId === t.id);
        const needsRepair = result ? !!result.data.validation_issues?.length : !!t.result?.draft;
        return (
          <section key={t.id} className={`cw-task ${t.status}`}>
            <div className="cw-task-heading">
              {project?.scenes.find(scene => scene.id === (t.targetId || t.sceneId))?.image && <img className="cw-task-thumb" src={project.scenes.find(scene => scene.id === (t.targetId || t.sceneId))!.image} alt="" width={40} height={40} />}
              <GenerationStatus label={`${titles[index]}${titles.filter(title => title === titles[index]).length > 1 ? ` · ${copy.repeat} ${titles.slice(0, index + 1).filter(title => title === titles[index]).length} ${copy.attempt}` : ""}`} status={t.status} progress={t.progress} createdAt={t.createdAt} />
            </div>
            <p>
              {
                (result?.stale
                  ? uiCopy["输入已更新，旧候选可查看，不能覆盖当前内容。"]
                  : t.status === "done"
                    ? (t.operation || t.result?.operation) === "storyboard" ? result?.selected ? "分镜已应用，可直接编辑镜头。" : needsRepair ? "分镜未完整生成，请重新生成。" : "已保留为历史方案，可预览后使用。" : needsRepair ? uiCopy["原输出已保留，可本地自动修复；无法确定的内容可选择角色或让 AI 纠错，先查看费用。"] : result?.selected ? "当前已选用此结果。" : "生成结果已保存，请在候选中预览并选用。"
                    : uiCopy["可切换页面，任务会继续执行。"])}
            </p>
            <ErrorNotice error={t.error ? new Error(t.error) : null} />
            {pending && onCancel && (
              <button className="btn" onClick={() => onCancel(t.id)}>
                {uiCopy["取消任务"]}</button>
            )}
            {["failed", "cancelled"].includes(t.status) &&
              onRetry &&
              t.generationRequest && (
                <button
                  className="btn"
                  onClick={() =>
                    onRetry({
                      ...t.generationRequest!,
                      nonce: crypto.randomUUID(),
                    })
                  }
                >
                  {uiCopy["重新估算并生成"]}</button>
              )}
          </section>
        );
      })}
    </div>
  );
}

export function relativeTime(createdAt?: number | string, now = Date.now()) {
  const time = typeof createdAt === "string" ? Date.parse(createdAt) : createdAt;
  const minutes = Math.max(0, Math.floor((now - (time || now)) / 60000));
  return minutes < 1 ? copy.justNow : minutes < 60 ? copy.minutesAgo(minutes) : minutes < 1440 ? copy.hoursAgo(Math.floor(minutes / 60)) : copy.daysAgo(Math.floor(minutes / 1440));
}
export function taskTitle(task: CreativeTask, project?: Project) {
  const op = task.operation || task.result?.operation || "";
  const label = operationNames[op] ?? task.typeLabel ?? copy.unknownTask;
  const scene = project?.scenes.find(scene => scene.id === (task.targetId || task.sceneId));
  const character = project?.characters?.find(c => c.id === (task.targetId || task.sceneId));
  const location = project?.creative?.plan?.locations?.find(l => l.id === (task.targetId || task.sceneId));
  const scope = character ? `角色 · ${character.name}` : location ? `场景 · ${location.name}` : scene ? `${copy.shot} ${String(project!.scenes.indexOf(scene) + 1).padStart(2, "0")} · ${scene.title}` : `${copy.projectLevel} · ${label}`;
  return `${label} · ${scope}`;
}

export function WorkspaceTools({ active, onSelect }: { active: "history" | "tasks" | null; onSelect: (value: "history" | "tasks") => void }) {
  const nav = <nav className="workspace-tools" aria-label="工作台工具"><button aria-label="生成任务" title="生成任务" className={active === "tasks" ? "active" : ""} aria-pressed={active === "tasks"} onClick={() => onSelect("tasks")}><ListVideo size={18}/><span>生成任务</span></button><button aria-label="版本记录" title="版本记录" className={active === "history" ? "active" : ""} aria-pressed={active === "history"} onClick={() => onSelect("history")}><History size={18}/><span>版本记录</span></button></nav>;
  const host = typeof document !== "undefined" ? document.getElementById("project-workspace-tools") : null;
  return host ? createPortal(nav, host) : nav;
}

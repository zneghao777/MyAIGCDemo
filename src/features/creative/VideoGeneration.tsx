"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useState } from "react";
import { Film } from "lucide-react";
import { GenerationStatus } from "./GenerationStatus";
import { TechnicalDetails } from "./TechnicalDetails";
import { assetKindLabels } from "./copy";
import { api, ApiError } from "@/lib/api";
import { refreshRemote } from "@/lib/remote-store";
import { useStore } from "@/lib/store";
import type { Task } from "@/lib/types";
import { Modal } from "@/components/ui";

type Material = { kind: string; asset_id: string; purpose?: string; role?: string; url?: string };
type Quote = {
  scenes: { sceneId: string; title: string; duration: number; points: number; resolution?: string; materials?: Material[]; prompt?: string; inputMode?: string; soundStrategy?: string; warnings?: string[] }[];
  estimatedPoints: number; available_points: number; reservedPoints?: number;
  rejected?: { sceneId: string; title: string; code: string; message: string }[];
  resolution: string; activeTasks: number; concurrencyLimit?: number;
};
type VideoTask = { id: string; sceneId?: string; kind?: string; type?: string; status: string; progress: number; error?: string; providerTaskId?: string; createdAt?: string | number; result?: { remote_task_id?: string; provider_task_id?: string; [key: string]: unknown } };
const active = (task: VideoTask) => ["queued", "running"].includes(task.status);

export function VideoGeneration({ projectId, scenes, disabled, reload }: { projectId: string; scenes: { id: string; title: string }[]; disabled: boolean; reload: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [quote, setQuote] = useState<Quote | null>(null);
  const allTasks = useStore(s => s.tasks);
  const tasks = allTasks.filter((task) => task.projectId === projectId && scenes.some(scene => scene.id === task.sceneId) && (task.kind === "video" || task.type === uiCopy["视频"])).sort((a, b) => a.createdAt - b.createdAt || a.id.localeCompare(b.id));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>("");
  async function inspect() {
    setOpen(true); setError(""); setQuote(null); setBusy(true);
    try { const result = await api<Quote>(`/projects/${projectId}/video-quote`); setQuote({ ...result, scenes: result.scenes.filter(scene => scenes.some(item => item.id === scene.sceneId)), rejected: result.rejected?.filter(scene => scenes.some(item => item.id === scene.sceneId)), estimatedPoints: result.scenes.filter(scene => scenes.some(item => item.id === scene.sceneId)).reduce((sum, scene) => sum + scene.points, 0) }); }
    catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  async function recover(task: VideoTask) {
    if (!task.providerTaskId || busy) return;
    setBusy(true); setError("");
    try { await api(`/tasks/${task.id}/retry`, "POST"); setMessage(uiCopy["已恢复原远端任务，继续观察；未新建付费镜头。"]); await refreshRemote().catch(() => {}); }
    catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  async function generate() {
    if (!quote || busy) return;
    setBusy(true); setError("");
    try {
      // All independent shots enter the durable backend queue before observation begins.
      const result = await api<{ queued: Task[]; rejected: { sceneId?: string; code: string; message?: string }[] }>("/tasks", "POST", {
        projectId, sceneIds: quote.scenes.map((scene) => scene.sceneId), kind: "video",
      });
      useStore.setState(state => { const merged = new Map(state.tasks.map(task => [task.id, task])); result.queued.forEach(task => merged.set(task.id, { ...task, createdAt: typeof task.createdAt === "string" ? Date.parse(task.createdAt) : task.createdAt })); return { tasks: Array.from(merged.values()) }; });
      setMessage(formatCopy("已提交 {0} 个任务，按镜头顺序继续生成；可以关闭此窗口或刷新继续观察。", result.queued.length));
      const errors = result.rejected.filter((r) => !["VIDEO_ALREADY_EXISTS", "TASK_ALREADY_EXISTS", "VIDEO_ACTIVE_TASK"].includes(r.code));
      if (errors.length) setError(new ApiError(uiCopy["视频提交未完成"], 409, errors[0].code));
      await refreshRemote().catch(() => {}); await reload().catch(() => {});
      setQuote(null);
    } catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  const running = tasks.filter(active);
  const latest = new Map<string, VideoTask>();
  for (const task of tasks) if (task.sceneId) latest.set(task.sceneId, task);
  const displayed = scenes.flatMap(scene => latest.has(scene.id) ? [latest.get(scene.id)!] : []);
  const completed = displayed.filter((t) => t.status === "done").length;
  return <>
    <button className="btn ai" disabled={busy || disabled} onClick={() => void inspect()}>
      <Film size={15} />{busy ? uiCopy["查询 / 提交中…"] : running.length ? formatCopy("视频任务 {0} 个进行中", running.length) : uiCopy["生成视频"]}
    </button>
    {open && <Modal title={uiCopy["生成分镜视频"]} onClose={() => setOpen(false)}>
      <div className="cs-dialog-body">
        <p>按已保存制作方式生成片段。组合镜头共用一次生成；完成后请回放并明确选用视频版本。</p>
        {quote && <>
          <p><strong>{quote.scenes.length} {" 个片段 · 预计 "}{quote.estimatedPoints} {uiCopy["积分"]}</strong></p>
          <p>{uiCopy["可用"]}{quote.available_points} {uiCopy["积分 · 已预留"]}{quote.reservedPoints || 0} {uiCopy["积分 · 同时最多生成"]}{quote.concurrencyLimit || 2} {uiCopy["个镜头。"]}</p>
          {quote.scenes.map((scene, index) => <details key={scene.sceneId} open>
            <summary>{index + 1}. {scene.title} · {scene.resolution || quote.resolution} · {scene.duration}{uiCopy["s · "]}{scene.points} {uiCopy["积分 ·"]}{scene.inputMode === "first_last_frame" ? uiCopy["首尾画面"] : scene.inputMode === "references" ? uiCopy["参考素材"] : scene.inputMode === "text" ? "纯文字预演" : uiCopy["首帧"]}</summary>
            <p>{uiCopy["声音策略："]}{scene.soundStrategy === "model_audio" ? uiCopy["模型声音，按配置替换后期声音"] : uiCopy["后期配声，按台词时序安排动作"]}</p>
            {scene.materials?.length ? <ul>{scene.materials.map((m, i) => <li key={`${m.asset_id}-${i}`}>{m.purpose || assetKindLabels[m.kind] || "素材"}{m.url && <a href={m.url} target="_blank" rel="noreferrer">{uiCopy["查看实际素材"]}</a>}</li>)}</ul> : <p>{"本次只使用文字设计，不上传参考素材。"}</p>}
            <details><summary>本次生成内容与台词</summary><div className="generation-summary">{scene.prompt?.replace(/<d>\[Chinese\] /g,"“").replace(/<\/d>/g,"”").replace(/<(Picture|Video|Audio) (\d+)>/g, (_, kind: string, n: string) => `${kind === "Picture" ? "图片" : kind === "Video" ? "视频" : "声音"}参考 ${n}`)}</div></details>
            {scene.warnings?.map((warning) => <p className="creative-warning" key={warning}>{warning}</p>)}
          </details>)}
          {quote.rejected?.map(item => <p key={item.sceneId} className="creative-warning">{item.title}：{item.message} {uiCopy["· 其他可用镜头仍可提交。"]}</p>)}
          <button className="btn primary" disabled={busy || !quote.scenes.length || quote.available_points < quote.estimatedPoints} onClick={() => void generate()}>
            {quote.scenes.length ? formatCopy("提交全部可生成镜头 · 预计 {0} 积分", quote.estimatedPoints) : uiCopy["当前无需新建视频任务"]}
          </button>
        </>}
        {displayed.length > 0 && <section aria-label={uiCopy["视频镜头聚合进度"]} aria-live="polite">
          <p>{completed} / {displayed.length} {uiCopy["镜头完成 ·"]}{running.length} {uiCopy["个排队 / 运行"]}</p>
          {displayed.map((task) => <div key={task.id} className="cw-task">
            <GenerationStatus label={scenes.find((s) => s.id === task.sceneId)?.title || "镜头视频"} status={task.status} progress={task.progress} createdAt={task.createdAt} />
            <ErrorNotice error={task.error ? new Error(task.error) : null} />
            {task.status === "failed" && task.providerTaskId && <button className="btn" disabled={busy} onClick={() => void recover(task)}>{uiCopy["恢复已有远端任务 · 不重新生成"]}</button>}
            <small>{uiCopy["已在云端排队"]}</small><TechnicalDetails data={task} />
          </div>)}
        </section>}
        {!quote && <button className="btn" disabled={busy} onClick={() => void inspect()}>{uiCopy["重新检查素材、余额与成本"]}</button>}
        {message && <p role="status">{message}</p>}
        <ErrorNotice error={error} />
      </div>
    </Modal>}
  </>;
}

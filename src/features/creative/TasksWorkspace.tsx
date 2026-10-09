"use client";
import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { Film, RefreshCw, ChevronDown, ChevronRight, ListVideo, Play, Pause, Check, ArrowUpRight } from "lucide-react";
import { createReadObserver } from "@/lib/read-observer";
import { api } from "@/lib/api";
import { refreshRemote, subscribeRemoteChanges } from "@/lib/remote-store";
import { useStore } from "@/lib/store";
import type { Project, Task } from "@/lib/types";
import type { Flow, Request } from "./types";
import { Modal, Empty } from "@/components/ui";
import { taskTitle, relativeTime } from "./shared";
import { taskStatusLabel } from "./copy";
import { CostQuote, type Estimate } from "./CostQuote";
import { ErrorNotice } from "./ErrorNotice";
import { TechnicalDetails } from "./TechnicalDetails";

export function TasksWorkspace({ project }: { project: Project }) {
  const allTasks = useStore(s => s.tasks);
  const paused = useStore(s => s.paused);
  const tasks = allTasks.filter(t => t.projectId === project.id).slice().sort((a, b) => b.createdAt - a.createdAt);
  const [flow, setFlow] = useState<Flow | null>(null);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [quote, setQuote] = useState<(Estimate & { task: Task; request: Request }) | null>(null);
  const path = `/creative/projects/${project.id}`;
  useEffect(() => {
    setFlow(null); setSelected(""); setQuote(null); setError(null);
    const observer = createReadObserver(async signal => {
      const value = await api<Flow>(path, "GET", undefined, signal);
      if (!signal.aborted) { setFlow(value); setError(null); }
    }, setError);
    const unsubscribe = subscribeRemoteChanges(project.id, observer.request);
    return () => { observer.stop(); unsubscribe(); };
  }, [path, project.id]);
  const visible = tasks.filter(t => filter === "all" || t.status === filter);
  async function retry(task: Task) {
    if (!task.generationRequest) return;
    setBusy(true); setError(null); setConsent(false);
    const request = { ...task.generationRequest, nonce: crypto.randomUUID() };
    try { const estimate = await api<Estimate>(`${path}/estimate`, "POST", request); setQuote({ ...estimate, request, task }); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function submit() {
    if (!quote || busy) return;
    setBusy(true); setError(null);
    try { await api(`${path}/generate`, "POST", quote.request); setQuote(null); await refreshRemote(project.id); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  function destination(task: Task) {
    if (task.kind === "compose") return "/export";
    if (task.sceneId && project.scenes.some(s => s.id === task.sceneId)) return `/studio?scene=${task.sceneId}`;
    const op = task.operation || "";
    return `/studio?stage=${op.startsWith("location") ? "locations" : /voice|character/.test(op) ? "characters" : op === "plan" ? "plan" : "storyboard"}`;
  }
  const labels = { queued: "排队中", running: "生成中", done: "已完成", failed: "失败", cancelled: "已取消" };
  const toggleDetails = (id: string) => setSelected(current => current === id ? "" : id);
  return <section className="task-workspace queue-page">
    <div className="page-heading">
      <div><span className="eyebrow">RENDER QUEUE</span><h1>灵感，正在成为画面。</h1><p>{project.name} · 所有任务进度，一目了然</p></div>
      <div className="button-row">
        <button className="btn secondary" disabled={!tasks.some(t => t.status === "failed")} onClick={() => setFilter("failed")}><RefreshCw size={15}/>查看失败任务</button>
        <button className="btn primary" onClick={() => useStore.getState().togglePause()}>{paused ? <Play size={15}/> : <Pause size={15}/>} {paused ? "继续队列" : "暂停队列"}</button>
      </div>
    </div>
    <ErrorNotice error={error}/>
    <nav className="queue-stats" aria-label="任务筛选">
      {(["queued", "running", "done", "failed"] as const).map(status => <button key={status} className={`queue-stat ${status} ${filter === status ? "active" : ""}`} aria-pressed={filter === status} onClick={() => setFilter(filter === status ? "all" : status)}>
        <span><i/>{labels[status]}</span><strong className="mono">{tasks.filter(t => t.status === status).length}<small>个任务</small></strong>
      </button>)}
    </nav>
    <div className="queue-table-wrap">
      <div className="panel-heading"><ListVideo size={18}/><h2>任务列表</h2><span className="muted">{filter === "all" ? "全部任务" : labels[filter as keyof typeof labels]}</span><button className="text-action" onClick={() => setFilter("all")}>显示全部</button></div>
      <div className="queue-state-note"><span className={`status-dot ${paused ? "paused" : ""}`}/>{paused ? "队列已暂停，点击「继续队列」开始处理" : "服务端队列运行中 · 按任务类型独立处理"}</div>
      <table className="queue-table"><thead><tr><th>分镜 / 内容</th><th>任务类型</th><th>状态</th><th>进度</th><th>操作</th></tr></thead><tbody>
        {visible.map(task => {
          const target = task.targetId || task.sceneId;
          const scene = project.scenes.find(s => s.id === target);
          const character = project.characters.find(c => c.id === target);
          const location = project.creative?.plan?.locations?.find(l => l.id === target);
          const image = scene?.image || character?.image || (location && project.creative?.locations?.[location.id]?.image?.url) || project.cover;
          const name = scene ? `镜头 ${String(project.scenes.indexOf(scene) + 1).padStart(2, "0")}` : character ? `角色 · ${character.name}` : location ? `场景 · ${location.name}` : "项目任务";
          const result = flow?.candidates.find(c => c.taskId === task.id);
          const expanded = selected === task.id;
          return <Fragment key={task.id}>
            <tr>
              <td><button className="queue-shot" aria-expanded={expanded} onClick={() => toggleDetails(task.id)}>{expanded ? <ChevronDown size={15}/> : <ChevronRight size={15}/>} {image ? <img src={image} alt="任务相关素材"/> : <Film size={25}/>}<span><strong>{name}</strong><small>{scene?.title || taskTitle(task, project)}</small></span></button></td>
              <td><span className={`type-tag ${task.kind === "video" ? "purple" : ""}`}>{task.kind === "video" ? <Play size={12}/> : <Film size={12}/>} {task.type}</span></td>
              <td><span className={`badge task-${task.status}`}><i/>{labels[task.status]}</span></td>
              <td><div className={`task-progress ${task.status}`}><div className="progress-track"><span style={{transform:`scaleX(${task.progress / 100})`}}/></div><span className="mono">{task.progress}%</span></div></td>
              <td><div className="button-row">
                {["failed", "cancelled"].includes(task.status) ? task.generationRequest ? <button className="text-action gold" disabled={busy} onClick={() => void retry(task)}><RefreshCw size={13}/>重试</button> : <Link className="text-action gold" href={destination(task)}>确认重试范围</Link>
                : ["running", "queued"].includes(task.status) ? <button className="text-action" disabled={busy} onClick={async () => {setBusy(true); try {await api(`/tasks/${task.id}/cancel`, "POST"); await refreshRemote(project.id);} catch(e) {setError(e);} finally {setBusy(false);}}}>取消</button>
                : <Link className="text-action" href={destination(task)}>查看<ArrowUpRight size={12}/></Link>}
                <button className="icon-btn" aria-label={`${taskTitle(task, project)} · 详情`} aria-expanded={expanded} onClick={() => toggleDetails(task.id)}>{expanded ? <ChevronDown size={15}/> : <ChevronRight size={15}/>}</button>
              </div></td>
            </tr>
            {expanded && <tr className="task-detail"><td colSpan={5}>
              <span className="eyebrow">TASK DETAILS</span>
              <p>{taskTitle(task, project)} · {relativeTime(task.createdAt)} · {task.status === "done" && !result ? "任务完成" : taskStatusLabel(task.status, result)}</p>
              {task.status === "failed" && <p>这次生成未完成，当前已选素材保留。重试仍需确认范围与费用。</p>}
              <ErrorNotice error={task.error ? new Error(task.error) : null}/>
              <p>{result ? result.selected ? "该候选已选用，人工检查与播放验收分别记录。" : "生成结果先保存为候选，明确选用后生效。" : "完成任务不代表人工艺术验收通过。"}</p>
              <Link className="text-action" href={destination(task)}>查看相关工作区<ArrowUpRight size={12}/></Link><TechnicalDetails data={task}/>
            </td></tr>}
          </Fragment>;
        })}
      </tbody></table>
      {!visible.length && <Empty title="当前没有任务" description="生成前会展示范围与费用，结果回到相应工作区。"/>}
    </div>
    <div className="queue-footer"><span><Check size={15}/>任务状态同步到工作台，候选明确选用后生效</span><Link href="/export">前往导出预览<ArrowUpRight size={15}/></Link></div>
    {quote && <Modal title="重试范围与费用" onClose={() => setQuote(null)}><section className="creative-quote"><ErrorNotice error={error}/><CostQuote quote={quote} consent={consent} onConsent={setConsent} busy={busy} onBack={() => setQuote(null)} onConfirm={() => void submit()}/></section></Modal>}
  </section>;
}

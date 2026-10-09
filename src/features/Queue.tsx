"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { TasksWorkspace } from "./creative/TasksWorkspace";
import { TechnicalDetails } from "./creative/TechnicalDetails";
import { ErrorNotice } from "./creative/ErrorNotice";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, remoteMode } from "@/lib/api";
import {
  ArrowLeft,
  Play,
  Pause,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  Check,
  Film,
  ListVideo,
  ArrowUpRight,
  Sparkles,
} from "lucide-react";
import { useProject, useStore } from "@/lib/store";
import { Empty } from "@/components/ui";
const labels = {
  queued: uiCopy["排队中"],
  running: uiCopy["生成中"],
  done: uiCopy["已完成"],
  failed: uiCopy["失败"],
  cancelled: uiCopy["已取消"],
};
export function Queue() {
  const project = useProject();
  if (remoteMode && project?.creative) return <main className="standard-page"><TasksWorkspace key={project.id} project={project}/></main>;
  return <LegacyQueue/>;
}
function LegacyQueue() {
  const p = useProject();
  const tasks = useStore((s) => s.tasks).filter((t) => t.projectId === p?.id);
  const paused = useStore((s) => s.paused);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const [estimate, setEstimate] = useState<{
    pricingConfigured: boolean;
    totalCents: number;
    spentCents: number;
  } | null>(null);
  const finished = tasks.filter((t) => t.status === "done").length;
  useEffect(() => {
    if (!remoteMode || !p?.id) return;
    const controller = new AbortController();
    void api<{
      pricingConfigured: boolean;
      totalCents: number;
      spentCents: number;
    }>(`/projects/${p.id}/estimate`, "GET", undefined, controller.signal)
      .then(setEstimate)
      .catch(() => {});
    return () => controller.abort();
  }, [p?.id, finished]);
  return (
    <div className="standard-page queue-page">
      <div className="page-breadcrumb">
        <Link href="/studio">
          <ArrowLeft size={15} />
          {uiCopy["返回分镜"]}</Link>
        <span>/</span>
        <span>{uiCopy["渲染队列"]}</span>
      </div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">{uiCopy["RENDER QUEUE"]}</span>
          <h1>{uiCopy["灵感，正在成为画面。"]}</h1>
          <p>{p?.name || uiCopy["项目"]} {uiCopy["· 所有任务进度，一目了然"]}</p>
        </div>
        <div className="button-row">
          {remoteMode && p && !p.creative ? (
            <button
              className="btn secondary"
              onClick={() =>
                useStore.getState().enqueue(
                  p.scenes.map((s) => s.id),
                  uiCopy["配音"],
                )
              }
            >
              {uiCopy["批量配音"]}</button>
          ) : null}
          <button
            className="btn secondary"
            disabled={!tasks.some((t) => t.status === "failed")}
            onClick={() =>
              tasks
                .filter((t) => t.status === "failed")
                .forEach((t) => useStore.getState().retry(t.id))
            }
          >
            <RotateCcw size={15} />
            {uiCopy["重试失败项"]}</button>
          <button
            className="btn primary"
            onClick={() => useStore.getState().togglePause()}
          >
            {paused ? <Play size={15} /> : <Pause size={15} />}{" "}
            {paused ? uiCopy["继续队列"] : uiCopy["暂停队列"]}
          </button>
        </div>
      </div>
      {remoteMode && estimate ? (
        <p className="muted">
          {estimate.pricingConfigured
            ? formatCopy("生成预估 ¥{0} · 已记账估算 ¥{1}", (estimate.totalCents / 100).toFixed(2), (estimate.spentCents / 100).toFixed(2))
            : uiCopy["尚未配置服务商单价，当前无法提供有效费用估算；0 不代表免费。"]}
        </p>
      ) : null}
      <div className="queue-stats">
        {(["queued", "running", "done", "failed"] as const).map((s) => (
          <button
            key={s}
            className={`queue-stat ${s} ${filter === s ? "active" : ""}`}
            onClick={() => setFilter(filter === s ? "all" : s)}
          >
            <span>
              <i />
              {labels[s]}
            </span>
            <strong className="mono">
              {tasks.filter((t) => t.status === s).length}
              <small>{uiCopy["个任务"]}</small>
            </strong>
          </button>
        ))}
      </div>
      <div className="queue-table-wrap">
        <div className="panel-heading">
          <ListVideo size={18} />
          <h2>{uiCopy["任务列表"]}</h2>
          <span className="muted">
            {filter === "all"
              ? uiCopy["全部任务"]
              : labels[filter as keyof typeof labels]}
          </span>
          <button className="text-action" onClick={() => setFilter("all")}>
            {uiCopy["显示全部"]}</button>
        </div>
        <div className="queue-state-note">
          <span className={`status-dot ${paused ? "paused" : ""}`} />
          {paused
            ? uiCopy["队列已暂停，点击「继续队列」开始处理"]
            : remoteMode
              ? uiCopy["服务端队列运行中 · 按任务类型独立处理"]
              : uiCopy["演示队列运行中 · 最多同时处理 2 个任务"]}
          {!remoteMode && <span>{uiCopy["Mock 生成 · 不消耗真实额度"]}</span>}
        </div>
        <table className="queue-table">
          <thead>
            <tr>
              <th>{uiCopy["分镜"]}</th>
              <th>{uiCopy["任务类型"]}</th>
              <th>{uiCopy["状态"]}</th>
              <th>{uiCopy["进度"]}</th>
              <th>{uiCopy["操作"]}</th>
            </tr>
          </thead>
          <tbody>
            {tasks
              .filter((t) => filter === "all" || t.status === filter)
              .slice()
              .reverse()
              .map((t) => {
                const s = p?.scenes.find((s) => s.id === t.sceneId);
                const index =
                  p?.scenes.findIndex((s) => s.id === t.sceneId) || 0;
                return (
                  <QueueRow
                    key={t.id}
                    task={t}
                    image={s?.image || p?.cover || ""}
                    name={s?.title || uiCopy["已移除的分镜"]}
                    index={index}
                    expanded={expanded === t.id}
                    onExpand={() =>
                      setExpanded(expanded === t.id ? null : t.id)
                    }
                  />
                );
              })}
          </tbody>
        </table>
        {!tasks.filter((t) => filter === "all" || t.status === filter)
          .length ? (
          <Empty
            title={uiCopy["当前没有任务"]}
            description={uiCopy["回到分镜工作台，生成你的第一张画面。"]}
            action={
              <Link href="/studio" className="btn primary">
                <Sparkles size={15} />
                {uiCopy["前往分镜"]}</Link>
            }
          />
        ) : null}
      </div>
      <div className="queue-footer">
        <span>
          <Check size={15} />
          {uiCopy["已完成的任务会自动更新到分镜工作台"]}</span>
        <Link href="/export">
          {uiCopy["前往导出预览"]}<ArrowUpRight size={15} />
        </Link>
      </div>
    </div>
  );
}
function QueueRow({
  task: t,
  image,
  name,
  index,
  expanded,
  onExpand,
}: {
  task: ReturnType<typeof useStore.getState>["tasks"][number];
  image: string;
  name: string;
  index: number;
  expanded: boolean;
  onExpand: () => void;
}) {
  return (
    <>
      <tr>
        <td>
          <button className="queue-shot" onClick={onExpand}>
            {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            <img src={image} alt={uiCopy["分镜缩略图"]} />
            <span>
              <strong>{uiCopy["镜头"]}{String(index + 1).padStart(2, "0")}</strong>
              <small>{name}</small>
            </span>
          </button>
        </td>
        <td>
          <span className={`type-tag ${t.type === uiCopy["视频"] ? "purple" : ""}`}>
            {t.type === uiCopy["视频"] ? <Play size={12} /> : <Film size={12} />}{" "}
            {t.type}
          </span>
        </td>
        <td>
          <span className={`badge task-${t.status}`}>
            <i />
            {labels[t.status]}
          </span>
        </td>
        <td>
          <div className={`task-progress ${t.status}`}>
            <div className="progress-track">
              <span style={{ transform: `scaleX(${t.progress / 100})` }} />
            </div>
            <span className="mono">{t.progress}%</span>
          </div>
        </td>
        <td>
          <div className="button-row">
            {["running", "queued"].includes(t.status) ? (
              <button
                className="text-action"
                onClick={() => useStore.getState().cancel(t.id)}
              >
                {uiCopy["取消"]}</button>
            ) : t.status === "failed" || t.status === "cancelled" ? (
              <button
                className="text-action gold"
                onClick={() => useStore.getState().retry(t.id)}
              >
                <RotateCcw size={13} />
                {uiCopy["重试"]}</button>
            ) : (
              <Link
                href="/studio"
                className="text-action"
                onClick={() => useStore.getState().selectScene(t.sceneId)}
              >
                {uiCopy["查看"]}<ArrowUpRight size={12} />
              </Link>
            )}
            <button
              className="icon-btn"
              aria-label={formatCopy("任务 {0} 详情", index + 1)}
              onClick={onExpand}
            >
              <ChevronDown size={15} />
            </button>
          </div>
        </td>
      </tr>
      {expanded ? (
        <tr className="task-detail">
          <td colSpan={5}>
            <span className="eyebrow">{uiCopy["TASK DETAILS"]}</span>
            <TechnicalDetails data={t} />
            <p className={t.error ? "error-text" : "muted"}>
              {
                formatCopy("任务{0}。{1}", labels[t.status], t.status === "done" ? uiCopy["分镜状态已写回项目。"] : remoteMode ? uiCopy["任务状态保存在服务端。"] : uiCopy["队列状态会自动保存在当前浏览器。"])}
            </p>
            <ErrorNotice error={t.error ? new Error(t.error) : null} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

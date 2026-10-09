"use client";
// Adapted from Beautiful UI Loading State (MIT); see beautiful-ui.LICENSE.txt.
import { useEffect, useState } from "react";
import { Check, Clock3, Sparkles } from "lucide-react";

export function GenerationStatus({ label, status, progress = 0, createdAt }: {
  label: string; status: string; progress?: number; createdAt?: number | string;
}) {
  const start = typeof createdAt === "string" ? Date.parse(createdAt) : createdAt;
  const [now, setNow] = useState(() => Date.now());
  const active = status === "running" || status === "queued";
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  const seconds = Number.isFinite(start) ? Math.max(0, Math.floor((now - start!) / 1000)) : 0;
  const elapsed = seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`;
  const value = Math.max(0, Math.min(100, Number.isFinite(progress) ? progress : 0));
  const phase = status === "queued" ? "等待开始" : status === "running" ? "AI 正在创作" : status === "done" ? "生成完成" : status === "cancelled" ? "已取消" : "生成未完成";
  return <div className={`generation-status ${active ? "is-active" : ""}`}>
    <div className="generation-status__header">
      <span className="generation-status__icon" aria-hidden="true">{active ? <span className="generation-pixels">{Array.from({ length: 9 }, (_, i) => <i key={i} style={{ animationDelay: `${(i % 3 + Math.abs(Math.floor(i / 3) - 1)) * 90}ms` }} />)}</span> : status === "done" ? <Check size={19} /> : <Sparkles size={19} />}</span>
      <div><strong>{label}</strong><span className="generation-status__phase">{phase}</span></div>
      {active && start ? <span className="generation-status__elapsed"><Clock3 size={13} />{elapsed}</span> : null}
    </div>
    {active && <div className="generation-status__track" role="progressbar" aria-label={`${label}进度`} aria-valuemin={0} aria-valuemax={100} {...(status === "running" && value > 0 ? { "aria-valuenow": value } : {})} aria-valuetext={status === "queued" ? "等待开始" : value > 0 ? `${value}%` : "正在生成"}><span style={{ width: value > 0 ? `${value}%` : "18%" }} className={value === 0 ? "is-indeterminate" : ""} /></div>}
    {active && <div className="generation-status__footer"><span>可以继续浏览，完成后在这里选择结果</span><b>{value > 0 ? `${Math.round(value)}%` : "进行中"}</b></div>}
  </div>;
}

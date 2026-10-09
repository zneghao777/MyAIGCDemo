"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useState } from "react";
import { apiBase } from "@/lib/api";
import type { Project, Scene } from "@/lib/types";
import type { Candidate } from "@/lib/creative-types";
import { TechnicalDetails } from "./TechnicalDetails";
import { CandidateList } from "./CandidateList";

export function correctionSources(video?: Record<string, unknown>, takes: Record<string, unknown>[] = []) {
  const ids = new Set<string>();
  for (const trace of [video, ...takes]) {
    if (!trace) continue;
    const originals = [trace.parent_task_id, trace.source_task_id];
    // A locally imported take is a candidate ID; only its recorded H3 parent is valid.
    if (!trace.candidate_id && (trace.provider_task_id || /minimax.*h3/i.test(String(trace.model || "")))) originals.push(trace.take);
    originals.forEach(id => { if (typeof id === "string" && /^[a-f0-9]{32}$/i.test(id)) ids.add(id); });
  }
  return Array.from(ids);
}

export function VideoCorrection({ project, scene, candidates, busy, reload, onSelect }: {
  project: Project; scene: Scene; candidates: Candidate[]; busy: boolean;
  reload: () => Promise<void>; onSelect: (candidate: Candidate) => void;
}) {
  const [file, setFile] = useState<File | null>(null), [reason, setReason] = useState("");
  const [uploading, setUploading] = useState(false), [error, setError] = useState<unknown>(""), [message, setMessage] = useState("");
  const video = scene.creative?.video;
  const sources = correctionSources(video, scene.creative?.video_takes || []);
  const currentSources = correctionSources(video);
  const [selectedSource, setSelectedSource] = useState(() => sources[0] || "");
  const sourceTaskId = sources.includes(selectedSource) ? selectedSource : sources[0] || "";
  const expected = scene.creative?.version || 0;
  async function upload() {
    if (!file || !reason.trim() || !sourceTaskId || uploading || busy) return;
    setUploading(true); setError(""); setMessage("");
    try {
      if (file.size > 50 * 1024 * 1024) throw new Error(uiCopy["修正版 MP4 不能超过 50 MB"]);
      if (!file.name.toLowerCase().endsWith(".mp4") && file.type !== "video/mp4") throw new Error(uiCopy["请选择 MP4 视频文件"]);
      const form = new FormData();
      form.append("expected", String(expected)); form.append("reason", reason.trim());
      form.append("source_task_id", sourceTaskId); form.append("file", file);
      const response = await fetch(`${apiBase}/api/creative/scenes/${scene.id}/video-correction`, { method: "POST", body: form });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.error?.message || formatCopy("修正版导入失败 ({0})", response.status));
      if (!result?.candidateId) throw new Error(uiCopy["导入结果缺少候选编号，请刷新检查已有候选后再操作"]);
      setFile(null); setMessage(uiCopy["修正版已保存为候选。请在下方播放检查后，选用此候选。当前视频尚未替换。"]);
      await reload().catch(() => setMessage(uiCopy["候选 已保存，候选列表正在恢复同步；请等待或刷新后选择，不要重复上传。"]));
    } catch (e) { setError(e); }
    finally { setUploading(false); }
  }
  return <section className="creative-editor"><h4>{uiCopy["上传本地视频修正版"]}</h4>
    <p className="helper">{uiCopy["选择本镜当前或历史原片，完成本地后期修正后导入。先保存候选、播放预览，再选择当前版本；不调用生成模型、不扣积分。"]}</p>
    <p className="helper">{uiCopy["来源：本项目已生成的原片"]}</p><TechnicalDetails data={{ sourceTaskId, expected }} />
    <fieldset disabled={busy || uploading || !sourceTaskId}>
      <label className="creative-field">{uiCopy["修正版来源"]}<select value={sourceTaskId} onChange={e => setSelectedSource(e.target.value)}>{sources.map((id, index) => <option key={id} value={id}>{currentSources.includes(id) ? uiCopy["当前来源"] : uiCopy["历史原片"]} · {index + 1}</option>)}</select></label>
      <label className="creative-field">{uiCopy["本地 MP4 文件 · 最大 50 MB"]}<input type="file" accept=".mp4,video/mp4" onChange={e => { setFile(e.target.files?.[0] || null); setError(""); }} /></label>
      <label className="creative-field">{uiCopy["具体修正内容与原因"]}<textarea rows={3} value={reason} onChange={e => setReason(e.target.value)} placeholder={uiCopy["例如：采用历史原片保留灯光与动作，并校准本地配声。明确本地处理，不声明重新生成。"]} /></label>
      {file && <p className="helper">{file.name} · {(file.size / 1024 / 1024).toFixed(2)} {uiCopy[" MB"]}</p>}
      <button className="btn" disabled={!file || !reason.trim()} onClick={() => void upload()}>{uploading ? uiCopy["正在保存候选…"] : uiCopy["保存本地修正版候选"]}</button>
    </fieldset>
    {message && <p role="status">{message}</p>}<ErrorNotice error={error} />
    {candidates.length > 0 && <CandidateList items={candidates} project={project} busy={busy || uploading} onSelect={onSelect} />}
  </section>;
}

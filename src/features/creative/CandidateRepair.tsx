"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { TechnicalDetails } from "./TechnicalDetails";
import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useState } from "react";
import type { Candidate } from "@/lib/creative-types";
import type { Project } from "@/lib/types";
import { useCreativeDraft } from "./shared";
export type RepairResult = { candidateId: string; parentCandidateId: string };
export function CandidateRepair({ candidate, project, busy, repair, recover, aiRepair }: {
  candidate: Candidate; project: Project; busy: boolean;
  repair: (candidate: Candidate, value: unknown) => Promise<RepairResult>;
  recover?: (candidate: Candidate) => Promise<RepairResult & { ready: boolean }>;
  aiRepair?: (candidate: Candidate) => void;
}) {
  const [text, setText] = useCreativeDraft(`cineai-candidate-repair-${candidate.id}`, candidate.data.value == null ? candidate.data.raw_text || "" : JSON.stringify(candidate.data.value, null, 2));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>("");
  const [savedCandidate, setSavedCandidate] = useState("");
  const [ready, setReady] = useState(false);
  async function autoRecover() {
    if (!recover) return;
    setPending(true); setError("");
    try { const result = await recover(candidate); setSavedCandidate(result.candidateId); setReady(result.ready); }
    catch (e) { setError(e); }
    finally { setPending(false); }
  }
  async function save() {
    setError(""); setSavedCandidate("");
    let value: unknown;
    try {
      value = JSON.parse(text);
      if (!value || typeof value !== "object" || !Array.isArray((value as { scenes?: unknown }).scenes)) throw new Error(uiCopy["分镜草稿需要包含 scenes 数组。"]);
    } catch (e) { setError(e); return; }
    setPending(true);
    try { const result = await repair(candidate, value); setSavedCandidate(result.candidateId); setReady(true); }
    catch (e) { setError(e); }
    finally { setPending(false); }
  }
  let editable: { scenes: { title?: string; cast?: Record<string, string>; lines?: { id: string; text: string; speaker_id?: string | null }[] }[] } | null = null;
  try { const parsed = JSON.parse(text); if (Array.isArray(parsed?.scenes) && parsed.scenes.every((shot: unknown) => { if (!shot || typeof shot !== "object") return false; const lines = (shot as {lines?: unknown}).lines; return lines == null || (Array.isArray(lines) && lines.every(line => line && typeof line === "object" && typeof line.text === "string")); })) editable = parsed; } catch { /* Raw malformed output stays in the advanced viewer. */ }
  function chooseSpeaker(sceneIndex: number, lineIndex: number, speaker: string) {
    if (!editable) return;
    const value = JSON.parse(text) as NonNullable<typeof editable>;
    const shot = value.scenes[sceneIndex], line = shot.lines![lineIndex];
    line.speaker_id = speaker || null;
    const state = project.characters.find(c => c.id === speaker)?.creative;
    if (state) shot.cast = { ...shot.cast, [speaker]: state.revision };
    setText(JSON.stringify(value, null, 2)); setSavedCandidate("");
  }
  const needsRecovery = candidate.stale || !!candidate.data.validation_issues?.length;
  return <section className="creative-editor">
    {needsRecovery && <>
      <p className="helper">{uiCopy["系统可修复文本格式、绑定已确认角色和环境，并保留所有原始输出。历史候选恢复后会关联当前输入，供你预览后选用。"]}</p>
      <div className="creative-actions"><button className="btn primary" disabled={busy || pending || !recover} onClick={() => void autoRecover()}>{pending ? uiCopy["恢复并检查中…"] : uiCopy["本地自动修复 · 不扣费"]}</button>
        <button className="btn" disabled={busy || pending || !aiRepair} onClick={() => aiRepair?.(candidate)}>{uiCopy["AI 纠错此草稿 · 先估算"]}</button></div>
    </>}
    {!candidate.stale && needsRecovery && editable?.scenes.map((shot, sceneIndex) => (shot.lines || []).map((line, lineIndex) => <label className="creative-field" key={`${sceneIndex}-${lineIndex}`}>{shot.title || formatCopy("镜头 {0}", sceneIndex + 1)} · {line.text}<select aria-label={formatCopy("镜头 {0} 台词 {1} 发言人", sceneIndex + 1, lineIndex + 1)} disabled={busy || pending} value={line.speaker_id || ""} onChange={e => chooseSpeaker(sceneIndex, lineIndex, e.target.value)}><option value="">{uiCopy["选择发言角色"]}</option>{project.characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>))}
    {!candidate.stale && needsRecovery && editable && <button className="btn" disabled={busy || pending} onClick={() => void save()}>{uiCopy["保存角色选择并检查"]}</button>}
    <TechnicalDetails data={candidate} extra={<>
    <p className="helper">{uiCopy["一般无需编辑 JSON。保留原模型输出、当前草稿和修改记录；保存会另建候选，选用前不替换项目分镜。"]}</p>
    <label className="creative-field">{uiCopy["分镜候选 JSON 草稿"]}<textarea aria-label={uiCopy["人工修正分镜候选 JSON"]} rows={16} value={text} disabled={busy || pending || candidate.stale || candidate.selected} onChange={e => { setText(e.target.value); setSavedCandidate(""); }} style={{ fontFamily: "monospace", fontSize: 12, maxHeight: 420, overflow: "auto", width: "100%" }} /></label>
    <button className="btn primary" disabled={busy || pending || candidate.stale || candidate.selected || !text.trim()} onClick={() => void save()}>{pending ? uiCopy["校验并保存中…"] : uiCopy["校验并另存人工修正候选"]}</button>
    {candidate.data.original_value != null && <pre style={{maxHeight:240,overflow:"auto",whiteSpace:"pre-wrap"}}>{JSON.stringify(candidate.data.original_value,null,2)}</pre>}
    {candidate.data.raw_text && <details><summary>{uiCopy["模型原始文本"]}</summary><pre style={{maxHeight:240,overflow:"auto",whiteSpace:"pre-wrap"}}>{candidate.data.raw_text}</pre></details>}
    </>} />
    {savedCandidate && <p role="status">{uiCopy["恢复候选已保存"]}{ready ? uiCopy["，检查通过，可在新候选上点击选用"] : uiCopy["，请查看新候选的剩余问题"]}{uiCopy["。原草稿保留。"]}</p>}
    <ErrorNotice error={error} />
  </section>;
}

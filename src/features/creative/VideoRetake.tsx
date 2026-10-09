"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useState } from "react";
import { Modal } from "@/components/ui";
import { TechnicalDetails } from "./TechnicalDetails";
import { assetKindLabels } from "./copy";
import { api, isRateLimited } from "@/lib/api";
import { refreshRemote } from "@/lib/remote-store";
import { useStore } from "@/lib/store";
import type { Scene, Task } from "@/lib/types";

type RetakeQuote = {
  sceneId: string; title: string; expected: number; duration: number; points: number;
  available_points: number; reservedPoints: number; projectPointsUsed: number; pointsHardLimit: number;
  prompt: string; inputMode: string; soundStrategy: string; activeTasks: Task[]; previousVideoUrl?: string;
  materials: { kind: string; asset_id: string; purpose?: string; role?: string; url?: string }[];
  warnings?: string[];
};
type Attempt = { modify?: boolean; source_asset_id?: string; preserve?: string; expected: number; nonce: string; reason: string; sent?: boolean; taskId?: string };
export function VideoRetake({ scene, initialReason = "", disabled }: { scene: Scene; initialReason?: string; disabled: boolean }) {
  const [open, setOpen] = useState(false), [quote, setQuote] = useState<RetakeQuote | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(null), [reason, setReason] = useState(initialReason);
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(""), [message, setMessage] = useState("");
  const tasks = useStore(s => s.tasks);
  const [modify, setModify] = useState(true), [preserve, setPreserve] = useState("保留人物身份、服装、场景、镜头节奏与未要求修改的台词");
  const [sourceAsset, setSourceAsset] = useState(String(scene.creative?.video?.asset_id || scene.creative?.video_takes?.at(-1)?.asset_id || ""));
  const [approved, setApproved] = useState(false);
  const hasPriorVideo = !!(scene.videoUrl || scene.creative?.video?.key || scene.creative?.video_takes?.some(take => take.key));
  const storageKey = `cineai-video-retake:${scene.id}`;
  const saveAttempt = (value: Attempt) => { setAttempt(value); localStorage.setItem(storageKey, JSON.stringify(value)); };
  async function inspect() {
    setOpen(true); setBusy(true); setError(""); setQuote(null); setMessage("");
    try {
      const current = await api<RetakeQuote>(`/scenes/${scene.id}/video-quote`);
      let saved: Attempt | null = null;
      try { saved = JSON.parse(localStorage.getItem(storageKey) || "null") as Attempt | null; } catch { /* Invalid local receipt is ignored. */ }
      const previousTask = saved?.taskId ? tasks.find(task => task.id === saved!.taskId) : undefined;
      const reuse = saved?.expected === current.expected && (!saved.taskId || !previousTask || previousTask.status === "running" || previousTask.status === "queued");
      const next = reuse ? saved! : { expected: current.expected, nonce: crypto.randomUUID(), reason: initialReason };
      saveAttempt(next); setReason(next.reason); setQuote(current);
    } catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!quote || !attempt || !reason.trim() || busy) return;
    const receipt = { ...attempt, reason: attempt.sent ? attempt.reason : reason.trim(), modify, source_asset_id: sourceAsset || undefined, preserve, sent: true };
    setBusy(true); setError("");
    try {
      // Persist before POST so network failure or refresh resends the same paid request.
      saveAttempt(receipt);
      const task = await api<Task & { deduplicated: boolean }>(`/scenes/${scene.id}/video-retake`, "POST", {
        expected: receipt.expected, nonce: receipt.nonce, reason: receipt.reason, modify: receipt.modify, source_asset_id: receipt.source_asset_id, preserve: receipt.preserve,
      });
      saveAttempt({ ...receipt, taskId: task.id });
      useStore.setState(state => ({ tasks: [...state.tasks.filter(row => row.id !== task.id), { ...task, createdAt: typeof task.createdAt === "string" ? Date.parse(task.createdAt) : task.createdAt }] }));
      setMessage(`${task.deduplicated ? "已恢复同一申请" : "已提交片段修改"}。原片和采用状态保留，新候选需回放后选用。`);
      await refreshRemote().catch(e => { if (!isRateLimited(e)) setMessage(uiCopy["本镜任务已提交；任务状态会自动恢复观察。"]); });
    } catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  return <>
    <button className="btn cw-ai-button" disabled={disabled || busy || !hasPriorVideo} onClick={() => void inspect()}>{"修改当前或历史视频"}</button>
    {open && <Modal title={`修改片段 · ${scene.title}`} onClose={() => setOpen(false)}><div className="cs-dialog-body">
      <p>{"先保存分镜设计，再修改本段视频；组合镜头会一起生成新候选。"}</p>
      {quote && <>
        <p><strong>{quote.duration}{uiCopy["s · 预计"]}{quote.points} {uiCopy["积分 ·"]}{({first_last_frame:"首尾画面", references:"多素材参考", text:"文字预演", first_frame:"首帧"} as Record<string,string>)[quote.inputMode]}</strong></p>
        <p>{uiCopy["可用"]}{quote.available_points} {uiCopy["· 预留"]}{quote.reservedPoints} {uiCopy["· 项目已用"]}{quote.projectPointsUsed} {uiCopy["/ 上限"]}{quote.pointsHardLimit} {uiCopy["积分。"]}</p>
        <p>{uiCopy["声音策略："]}{quote.soundStrategy === "model_audio" ? uiCopy["模型声音"] : uiCopy["后期配声"]}</p>
        <ul>{quote.materials.map((material, i) => <li key={`${material.asset_id}-${i}`}>{material.purpose || assetKindLabels[material.kind] || "参考素材"}{material.url && <a href={material.url} target="_blank" rel="noreferrer">{uiCopy["查看实际素材"]}</a>}</li>)}</ul>
        <label className="creative-field">修改方式<select value={modify ? "modify" : "retake"} disabled={!!attempt?.sent} onChange={e=>{setModify(e.target.value === "modify");setApproved(false);}}><option value="modify">基于原视频调用模型修改</option><option value="retake">按当前设计重新生成</option></select></label>
        {modify && <><label className="creative-field">原片版本<select value={sourceAsset} disabled={!!attempt?.sent} onChange={e=>{setSourceAsset(e.target.value);setApproved(false);}}>{scene.creative?.video_takes?.map((take,i)=><option key={String(take.asset_id)} value={String(take.asset_id)}>视频版本 {i+1}{take.key === scene.creative?.video?.key ? " · 当前选用" : ""}</option>)}</select></label><label className="creative-field">需要保留什么<textarea rows={2} value={preserve} disabled={!!attempt?.sent} onChange={e=>{setPreserve(e.target.value);setApproved(false);}}/></label><p className="helper">模型可能改变未指定细节。原片保留，修改结果需对比回放后选用。</p></>}
        {quote.warnings?.map(warning => <p className="creative-warning" key={warning}>{warning}</p>)}
        <label className="creative-field">{"希望怎样调整视频"}<textarea rows={3} value={reason} disabled={!!attempt?.sent} onChange={e => {setReason(e.target.value);setApproved(false);}} /></label>
        
        <button className="btn" disabled={busy || !reason.trim() || !attempt} onClick={async()=>{setBusy(true);setError("");try{const value=await api<{prompt:string;points:number;materials:RetakeQuote["materials"]}>(`/scenes/${scene.id}/video-retake-quote`,"POST",{expected:quote.expected,nonce:attempt!.nonce,reason,modify,source_asset_id:sourceAsset || undefined,preserve});setQuote({...quote,...value});setApproved(true);}catch(e){setError(e);}finally{setBusy(false);}}}>查看本次修改内容与费用</button>
        {approved && <details open><summary>本次修改要求</summary><div className="generation-summary">{quote.prompt.replace(/<d>\[Chinese\] /g,"“").replace(/<\/d>/g,"”").replace(/<(Picture|Video|Audio) (\d+)>/g,(_,kind:string,n:string)=>`${kind==="Picture" ? "图片" : kind==="Video" ? "视频" : "声音"}参考 ${n}`)}</div></details>}
        <button className="btn primary" disabled={!approved || busy || !!attempt?.taskId || !reason.trim() || quote.activeTasks.length > 0 || quote.available_points < quote.points || (quote.pointsHardLimit > 0 && quote.projectPointsUsed + quote.points > quote.pointsHardLimit)} onClick={() => void submit()}>{attempt?.taskId ? uiCopy["本镜重做已提交"] : attempt?.sent ? formatCopy("重试同一申请 · 预计 {0} 积分", quote.points) : formatCopy("确认仅重做本镜 · 预计 {0} 积分", quote.points)}</button>
        {quote.activeTasks.length > 0 && <p className="creative-warning">{uiCopy["本镜已有活动任务，请等待或恢复原任务。"]}</p>}
      </>}
      {message && <p role="status">{message}</p>}<ErrorNotice error={error} />
    </div></Modal>}
  </>;
}

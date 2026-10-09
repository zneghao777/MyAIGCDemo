"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Scene } from "@/lib/types";
import type { ShotReview } from "@/lib/creative-types";
import { Field } from "./shared";
import { VideoRetake } from "./VideoRetake";
const checks = { character: uiCopy["人物造型与装备"], environment: uiCopy["场景地标与空间关系"], action: uiCopy["动作因果与结束结果"], sound: uiCopy["角色声音与音画同步"], subtitles: uiCopy["字幕时间与可读性"], transition: uiCopy["邻镜位置、视线与动作衔接"] };
export function ShotReviewEditor({ scene, run, busy, allowRetake = true }: { allowRetake?: boolean; scene: Scene; run: (action: () => Promise<unknown>) => Promise<void>; busy: boolean }) {
  const previous = scene.creative?.review;
  const [draft, setDraft] = useState<ShotReview>(previous || { status: "pending", checks: {}, notes: "", issues: [] });
  const allChecked = Object.keys(checks).every(key => draft.checks[key]);
  const record = (status: ShotReview["status"]) => void run(() => api(`/creative/scenes/${scene.id}/review`, "POST", { expected: scene.creative?.version || 0, data: { ...draft, issues: (draft.issues || []).filter(issue => issue.note.trim()), status } }));
  return <section className="creative-editor"><h4>{uiCopy["本镜人工艺术验收 ·"]}{previous?.status === "accepted" && !previous.stale && scene.creative?.review_current !== false ? uiCopy["当前版本已验收"] : previous?.status === "issues" ? uiCopy["记录了待修正问题"] : uiCopy["待验收"]}</h4>
    {scene.videoUrl && <video controls playsInline preload="metadata" src={scene.videoUrl} aria-label={formatCopy("{0}人工验收视频", scene.title)} style={{ width: "100%" }} />}
    {!scene.videoUrl && <p className="helper">{uiCopy["当前尚无动态视频；可以记录问题，生成视频后再逐镜验收。"]}</p>}
    <fieldset disabled={busy}>{Object.entries(checks).map(([key, label]) => <label key={key} style={{ display: "block" }}><input type="checkbox" checked={draft.checks[key] || false} onChange={e => setDraft({ ...draft, checks: { ...draft.checks, [key]: e.target.checked } })} /> {label}{uiCopy["已播放检查"]}</label>)}
      <Field label={uiCopy["检查结论 / 局部修正说明"]} value={draft.notes} large onChange={notes => setDraft({ ...draft, notes })} />
      {(draft.issues || []).map((issue, index) => <div className="creative-line" key={index}><label className="creative-field">{uiCopy["问题类别"]}<select value={issue.category} onChange={e => setDraft({ ...draft, issues: draft.issues!.map((x, i) => i === index ? { ...x, category: e.target.value } : x) })}>{Object.entries(checks).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><Field label={uiCopy["问题与修改目标"]} value={issue.note} onChange={note => setDraft({ ...draft, issues: draft.issues!.map((x, i) => i === index ? { ...x, note } : x) })} /><button className="btn" onClick={() => setDraft({ ...draft, issues: draft.issues!.filter((_, i) => i !== index) })}>{uiCopy["移除问题"]}</button></div>)}
      <button className="btn" onClick={() => setDraft({ ...draft, issues: [...draft.issues || [], { category: "action", note: "" }] })}>{uiCopy["记录本镜问题"]}</button>
      <div className="creative-actions"><button className="btn" onClick={() => record("issues")}>{uiCopy["保存问题 · 保留现有成果"]}</button><button className="btn primary" disabled={!scene.videoUrl || !allChecked || !!draft.issues?.some(issue => issue.note.trim())} onClick={() => record("accepted")}>{uiCopy["确认当前视频版本通过人工验收"]}</button></div>
      {allowRetake && <VideoRetake scene={scene} disabled={busy} initialReason={[draft.notes, ...(draft.issues || []).map(issue => issue.note)].filter(Boolean).join("；")} />}
      <p className="helper">{uiCopy["确认绑定本镜的素材、视频、声音与分镜版本。相关输入改变后需重新确认；修正不会自动付费生成或清空全片。"]}</p>
    </fieldset>
  </section>;
}

"use client";
import { useState } from "react";
import type { Candidate, Shot, Line } from "@/lib/creative-types";
import type { Project } from "@/lib/types";
import { ErrorNotice } from "./ErrorNotice";

export function StoryboardRepairForm({ candidate, project, busy, save }: {
  candidate: Candidate; project: Project; busy: boolean;
  save: (candidate: Candidate, value: unknown) => Promise<unknown>;
}) {
  const [shots, setShots] = useState<Shot[]>(() => structuredClone(((candidate.data.value as { scenes?: Shot[] }).scenes || []).map(shot => ({...shot, cast: shot.cast || {}, offscreen_cast: shot.offscreen_cast || {}, lines: Array.isArray(shot.lines) ? shot.lines : [], narration: Array.isArray(shot.narration) ? shot.narration : []}))));
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState(false);
  function change(index: number, update: (shot: Shot) => void) {
    setShots(old => { const next = structuredClone(old); update(next[index]); return next; }); setSaved(false);
  }
  function lineChange(si: number, li: number, patch: Partial<Line>) {
    change(si, shot => { shot.lines[li] = { ...shot.lines[li], ...patch }; });
  }
  async function submit() {
    setError(undefined);
    const scenes = shots.map(shot => {
      const all = [...shot.lines, ...shot.narration];
      const ids = new Set(all.map(line => line.id));
      return { ...shot, audio_order: [...(shot.audio_order || []).filter(id => ids.has(id)), ...all.filter(line => !(shot.audio_order || []).includes(line.id)).map(line => line.id)] };
    });
    try { await save(candidate, { scenes }); setSaved(true); } catch (e) { setError(e); }
  }
  return <details className="storyboard-option__preview"><summary>整理镜头内容</summary>
    <p className="helper">补充缺失的台词、发言人和剧情节点。保存为新方案，原方案继续保留。</p>
    {shots.map((shot, si) => <fieldset key={si} className="creative-editor"><legend>镜头 {si + 1} · {shot.title}</legend>
      <label className="creative-field">预计时长<input aria-label={`镜头 ${si + 1} 预计时长`} type="number" min={3} max={120} value={shot.duration} onChange={e => change(si, s => { s.duration = Number(e.target.value); })} /></label>
      <div>覆盖剧情节点{project.creative?.plan?.beats.map((beat, bi) => <label key={bi} className="creative-check"><input type="checkbox" checked={shot.beat_indices?.includes(bi) || false} onChange={e => change(si, s => { s.beat_indices = e.target.checked ? [...(s.beat_indices || []).filter(i => i >= 0 && i < (project.creative?.plan?.beats.length || 0)), bi] : (s.beat_indices || []).filter(i => i !== bi); })} />{bi + 1} · {beat}</label>)}</div>
      {shot.lines.map((line, li) => <div key={line.id} className="creative-editor">
        <label className="creative-field">台词 {li + 1}<textarea aria-label={`镜头 ${si + 1} 台词 ${li + 1}`} value={line.text} onChange={e => lineChange(si, li, { text: e.target.value })} /></label>
        <label className="creative-field">发言人<select aria-label={`镜头 ${si + 1} 台词 ${li + 1} 发言人`} value={line.speaker_id || ""} onChange={e => change(si, s => { s.lines[li].speaker_id = e.target.value; const c = project.characters.find(c => c.id === e.target.value); if (c) { if (s.lines[li].delivery === "off_screen") s.offscreen_cast = { ...s.offscreen_cast, [c.id]: c.creative?.revision || "" }; else s.cast[c.id] = c.creative?.revision || ""; } })}><option value="">选择发言人</option>{project.characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="creative-check"><input type="checkbox" checked={line.delivery === "off_screen"} onChange={e => change(si, s => { s.lines[li].delivery = e.target.checked ? "off_screen" : "on_screen"; const cid = s.lines[li].speaker_id; const c = project.characters.find(c => c.id === cid); if (c) { if (e.target.checked) { s.offscreen_cast = { ...s.offscreen_cast, [c.id]: c.creative?.revision || "" }; } else s.cast[c.id] = c.creative?.revision || ""; } })} />画外发言</label>
      </div>)}
      <button className="btn" onClick={() => change(si, s => { const used = new Set([...s.lines, ...s.narration].map(l => l.id)); const missing = s.audio_order?.find(id => !used.has(id)); s.lines.push({ id: missing || crypto.randomUUID(), text: "", speaker_id: Object.keys(s.offscreen_cast || {})[0] || Object.keys(s.cast)[0] || null, delivery: Object.keys(s.offscreen_cast || {}).length ? "off_screen" : "on_screen", emotion: "neutral", speed: 1, pause_after: .15 }); })}>为镜头 {si + 1} 添加台词</button>
    </fieldset>)}
    <button className="btn primary" disabled={busy || saved} onClick={() => void submit()}>保存为新方案</button>{saved && <p role="status">已保存，可在新方案上点击“使用此方案”。</p>}<ErrorNotice error={error} />
  </details>;
}

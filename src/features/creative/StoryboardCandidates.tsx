"use client";

import { Check, ChevronDown, Clapperboard } from "lucide-react";
import type { Candidate } from "@/lib/creative-types";
import type { Project } from "@/lib/types";
import { StoryboardRepairForm } from "./StoryboardRepairForm";

const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = (value: unknown) => typeof value === "string" ? value : "";

export function StoryboardCandidates({ items, project, busy, onSelect, onAiRepair, onRepair }: {
  items: Candidate[];
  project: Project;
  busy: boolean;
  onSelect: (candidate: Candidate) => void;
  onAiRepair?: (candidate: Candidate) => void;
  onRepair?: (candidate: Candidate, value: unknown) => Promise<unknown>;
}) {
  const sorted = [...items].sort((a, b) => Number(!!b.selected) - Number(!!a.selected));
  return <div className="storyboard-options">
    {sorted.map(candidate => {
      const value = record(candidate.data.value);
      const shots = Array.isArray(value.scenes) ? value.scenes.map(record) : [];
      const incomplete = !!candidate.data.draft || !!candidate.data.validation_issues?.length || !shots.length;
      const duration = shots.reduce((total, shot) => total + (typeof shot.duration === "number" ? shot.duration : 0), 0);
      return <article key={candidate.id} data-candidate-id={candidate.id} className={`storyboard-option${candidate.selected ? " is-selected" : ""}`}>
        <header className="storyboard-option__header">
          <span className="storyboard-option__icon"><Clapperboard size={20} /></span>
          <div><h3>{candidate.selected ? "当前方案" : `历史方案 ${items.length - items.indexOf(candidate)}`}</h3><p>{shots.length} 个镜头{duration > 0 ? ` · 约 ${Math.round(duration)} 秒` : ""}</p></div>
          {candidate.selected ? <span className="storyboard-option__selected"><Check size={14} />正在使用</span> : <button className="btn" disabled={busy || candidate.stale || !shots.length} onClick={() => onSelect(candidate)}>使用此方案</button>}
        </header>
        {(incomplete || candidate.stale) && <p className="storyboard-option__notice">{incomplete ? "方案中有内容需要整理。点击“使用此方案”会先自动整理，无需重新生成。" : "故事或角色已更新，请生成新方案。"}</p>}
        {!candidate.selected && incomplete && onAiRepair && <div className="storyboard-option__notice"><button className="btn" disabled={busy} onClick={() => onAiRepair(candidate)}>AI 完善此方案</button></div>}
        {!candidate.selected && !candidate.stale && incomplete && shots.length > 0 && onRepair && <StoryboardRepairForm candidate={candidate} project={project} busy={busy} save={onRepair} />}
        {shots.length > 0 && <details className="storyboard-option__preview" open={candidate.selected || undefined}>
          <summary><span>预览镜头内容</span><ChevronDown size={16} /></summary>
          <ol>{shots.map((shot, index) => <li key={index}>
            <span className="storyboard-option__number">{String(index + 1).padStart(2, "0")}</span>
            <div><div className="storyboard-option__shot-heading"><h4>{text(shot.title) || `镜头 ${index + 1}`}</h4><small>{[text(shot.shot_type), text(shot.camera_move), typeof shot.duration === "number" ? `${shot.duration} 秒` : ""].filter(Boolean).join(" · ")}</small></div>
              <p>{text(shot.action) || text(shot.image_prompt) || "画面内容待完善"}</p>
              {Array.isArray(shot.lines) && shot.lines.map((rawLine, lineIndex) => { const line = record(rawLine); return text(line.text) && <blockquote key={lineIndex}><b>{project.characters.find(character => character.id === line.speaker_id)?.name || (line.speaker_id === null ? "旁白" : "角色")}</b>{text(line.text)}</blockquote>; })}
              {Array.isArray(shot.narration) && shot.narration.map((rawLine, lineIndex) => text(record(rawLine).text) && <blockquote key={`n-${lineIndex}`}><b>旁白</b>{text(record(rawLine).text)}</blockquote>)}
            </div>
          </li>)}</ol>
        </details>}
      </article>;
    })}
  </div>;
}

"use client";
import { effectiveVideoInput } from "@/lib/production";
import { EmptyStoryboardAction } from "./creative/EmptyStoryboardAction";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { TechnicalDetails } from "./creative/TechnicalDetails";
import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  Film,
  Play,
  Sparkles,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Users,
  Volume2,
  ImageIcon,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Flow } from "./creative/types";
import { ErrorNotice } from "./creative/ErrorNotice";
import { VideoGeneration } from "./creative/VideoGeneration";
import { Modal } from "@/components/ui";
import { useStore } from "@/lib/store";
import { timecode, type Project, type Scene } from "@/lib/types";

export type ShotStatus = {
  id: string;
  image_stale: boolean;
  audio_stale: boolean;
  video_stale?: boolean;
  error?: string;
};
export function CreativeStudio({
  project,
  pacing,
  statuses,
  busy,
  onGenerate,
  onConfirm,
  onPhase,
  renderInspector,
  candidates,
  check,
  videoEnabled,
  reload,
}: {
  project: Project;
  pacing?: Flow["pacing"];
  statuses: ShotStatus[];
  busy: boolean;
  onGenerate: (fresh?: boolean) => void;
  onConfirm: () => void;
  onPhase: (phase: string) => void;
  renderInspector: (scene: Scene) => ReactNode;
  candidates: ReactNode;
  check: ReactNode;
  videoEnabled: boolean;
  reload: () => Promise<void>;
}) {
  const selectedId = useStore((s) => s.sceneId);
  const select = (id: string) => useStore.setState({ sceneId: id });
  const [view, setView] = useState("board");
  const [editError, setEditError] = useState<unknown>(null);
  const [adding, setAdding] = useState(false);
  const [left, setLeft] = useState(false);
  const [right, setRight] = useState(true);
  useEffect(() => {
    const compact = window.matchMedia("(max-width: 1280px)");
    const narrow = window.matchMedia("(max-width: 1100px)");
    const adapt = () => {
      setLeft(false);
      setRight(!narrow.matches);
    };
    adapt();
    compact.addEventListener("change", adapt);
    narrow.addEventListener("change", adapt);
    return () => {
      compact.removeEventListener("change", adapt);
      narrow.removeEventListener("change", adapt);
    };
  }, []);
  const [sideTab, setSideTab] = useState<string>(uiCopy["大纲"]);
  const [panel, setPanel] = useState<"candidates" | "check" | "outline" | null>(null);
  const p = project,
    st = p.creative!;
  const selected = p.scenes.find((s) => s.id === selectedId) || p.scenes[0];
  const duration = p.scenes.reduce((n, s) => n + s.durationSec, 0);
  return (
    <div className="cs-workspace">
      <div
        className={`cs-layout ${left ? "" : "cs-collapsed"} ${right ? "" : "cs-right-collapsed"}`}
      >
        {left && <aside className="cs-outline">
          <div className="cs-panel-head">
            {left && (
              <div className="cs-tabs">
                {[uiCopy["大纲"], uiCopy["角色"]].map((t) => (
                  <button
                    key={t}
                    className={sideTab === t ? "active" : ""}
                    onClick={() => setSideTab(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
            <button
              className="icon-btn"
              aria-label={left ? uiCopy["收起大纲"] : uiCopy["展开大纲"]}
              onClick={() => setLeft(!left)}
            >
              {left ? (
                <PanelLeftClose size={17} />
              ) : (
                <PanelLeftOpen size={17} />
              )}
            </button>
          </div>
          {left && (
            <div className="cs-outline-body">
              {sideTab === uiCopy["大纲"] ? (
                <>
                  <small className="cs-kicker">{uiCopy["STORY OVERVIEW"]}</small>
                  <h3>{st.plan?.title || p.name}</h3>
                  <p>
                    {st.plan?.synopsis ||
                      p.description ||
                      uiCopy["从一句创意开始，让故事在这里展开。"]}
                  </p>
                  <div className="cs-tags">
                    <span>{p.style}</span>
                    <span>{p.ratio}</span>
                    <span>{p.scenes.length} {uiCopy["个镜头"]}</span>
                  </div>
                  <button
                    className="btn cs-full"
                    onClick={() => onPhase("plan")}
                  >
                    {uiCopy["查看与编辑故事方案"]}</button>
                  <div className="cs-divider" />
                  <small className="cs-kicker">{uiCopy["SCENE LIST"]}</small>
                  {p.scenes.map((s, i) => (
                    <button
                      key={s.id}
                      className={`cs-scene-link ${selected?.id === s.id ? "active" : ""}`}
                      onClick={() => select(s.id)}
                    >
                      <b>{String(i + 1).padStart(2, "0")}</b>
                      <span>
                        {s.title}
                        <small>
                          {s.shotType} · {s.durationSec.toFixed(1)}{uiCopy["s"]}</small>
                      </span>
                    </button>
                  ))}
                </>
              ) : (
                <>
                  <small className="cs-kicker">{uiCopy["PROJECT CAST"]}</small>
                  <p>{uiCopy["本项目使用的角色与声音"]}</p>
                  {p.characters.map((c) => (
                    <button
                      className="cs-person"
                      key={c.id}
                      onClick={() => onPhase("characters")}
                    >
                      {c.image ? (
                        <img src={c.image} alt={c.name} />
                      ) : (
                        <Users size={24} />
                      )}
                      <span>
                        <b>{c.name}</b>
                        <small>
                          {c.creative?.confirmed ? uiCopy["已定稿"] : uiCopy["待确认"]} ·{" "}
                          {c.creative?.voice ? uiCopy["声音已选"] : uiCopy["声音待选"]}
                        </small>
                      </span>
                    </button>
                  ))}
                  <button
                    className="btn cs-full"
                    onClick={() => onPhase("characters")}
                  >
                    {uiCopy["管理角色形象与声音"]}</button>
                </>
              )}
            </div>
          )}
        </aside>}
        <section className="cs-board" aria-label={uiCopy["分镜画板"]}>
          <div className="cs-panel-head">
            <h2>
              分镜创作<small>{p.scenes.length} {uiCopy[" SHOTS"]}</small>
            </h2>
            <div className="creative-actions">
              <button className="btn" aria-expanded={left} onClick={() => setLeft(!left)}>大纲</button>
              {videoEnabled && st.shots_confirmed && <VideoGeneration projectId={p.id} scenes={p.scenes} disabled={busy} reload={reload} />}
              <button
                className="btn ai"
                disabled={busy || !st.plan_confirmed}
                onClick={() => {
                  setPanel("candidates");
                }}
              >
                <Sparkles size={15} /> {"分镜方案"}</button>
              <button className="btn" onClick={() => setPanel("check")}>
                <Volume2 size={16} />
                {uiCopy["角色连听"]}</button>
              <button
                className="icon-btn"
                aria-label={uiCopy["合成前检查"]}
                onClick={() => setPanel("check")}
              >
                <Film size={19} />
              </button>
            </div>
          </div>
          <div className="cs-board-scroll">
            <div className="creative-actions" aria-label="分镜视图">{[["table","分镜表"],["board","故事板"],["timeline","时间轴"]].map(([value,label])=><button className={`btn ${view===value ? "active" : ""}`} aria-pressed={view===value} key={value} onClick={()=>setView(value)}>{label}</button>)}<button className="btn" disabled={busy || adding} onClick={async()=>{setAdding(true);setEditError(null);try{const result=await api<{scene_id:string}>(`/creative/projects/${p.id}/add-shot`,"POST",{expected:st.version,data:{}});await reload();select(result.scene_id);}catch(e){setEditError(e);}finally{setAdding(false);}}}>添加镜头</button></div>
            <ErrorNotice error={editError}/>
            {pacing && <details className="story-pacing"><summary>故事与节奏 · 设计 {pacing.planned_seconds} 秒 / 目标 {pacing.target_seconds} 秒{pacing.measured_seconds > 0 ? ` / 采用 ${pacing.measured_seconds.toFixed(2)} 秒` : ""} · {pacing.warnings.length ? `${pacing.warnings.length} 项建议` : "节点已安排，待回放"}</summary><ul>{pacing.warnings.map(message=><li key={message}>{message}</li>)}</ul><p>{pacing.note}</p></details>}
            {view === "table" && <div className="story-table-wrap"><table className="story-table"><thead><tr><th>镜头</th><th>剧情与动作</th><th>对白与声音</th><th>预计时长</th></tr></thead><tbody>{p.scenes.map((row,i)=><tr key={row.id} aria-selected={selected?.id===row.id}><td><button className="btn" onClick={()=>select(row.id)}>{i+1}. {row.title}</button></td><td>{row.creative?.shot?.purpose}<p>{row.creative?.shot?.action}</p></td><td>{[...row.creative?.shot?.lines || [],...row.creative?.shot?.narration || []].map(line=><p key={line.id}>{p.characters.find(c=>c.id===line.speaker_id)?.name || "旁白"}：{line.continues_from ? "（延续前镜，不重复）" : line.delivery === "off_screen" ? "（画外）" : ""}{line.text}</p>)}</td><td>{row.durationSec} 秒</td></tr>)}</tbody></table></div>}
            {view === "timeline" && <div className="story-timeline">{p.scenes.map((row,i)=><button className="story-timeline-shot" style={{flex:row.durationSec}} key={row.id} aria-pressed={selected?.id===row.id} onClick={()=>select(row.id)}><b>{p.scenes.slice(0,i).reduce((n,s)=>n+s.durationSec,0)} 秒 · {row.title}</b><span>{row.creative?.shot?.purpose || row.creative?.shot?.action}</span><small>{row.durationSec} 秒 · {row.creative?.edit ? `采用 ${row.creative.edit.in_sec.toFixed(2)}–${row.creative.edit.out_sec.toFixed(2)} 秒` : "尚未选用视频"}</small></button>)}</div>}
            <div hidden={view !== "board"}>
            <div className="cs-board-note">
              <span>
                <i />{" "}
                {st.shots_confirmed
                  ? "分镜已确认，选择参考与制作方式后生成片段"
                  : uiCopy["检查镜头与台词，确认后开始生成"]}
              </span>
              <span>{"选中镜头，在右侧制作"}</span>
            </div>
            {p.scenes.length ? (
              <div className="cs-shot-grid">
                {p.scenes.map((s, i) => {
                  const status = statuses.find((x) => x.id === s.id),
                    shot = s.creative?.shot;
                  return (
                    <button
                      key={s.id}
                      className={`cs-shot-card ${selected?.id === s.id ? "selected" : ""}`}
                      onClick={() => select(s.id)}
                      aria-label={formatCopy("选择分镜 {0}：{1}", i + 1, s.title)}
                      aria-pressed={selected?.id === s.id}
                    >
                      <div className={`cs-shot-visual${s.image ? "" : " cs-text-visual"}`}>
                        {s.image ? (
                          <img src={s.image} alt={s.title} />
                        ) : (
                          <div className="cs-image-empty">
                            <b>{shot?.purpose || s.title}</b><p>{shot?.action}</p><small>{[...shot?.lines || [], ...shot?.narration || []].map(line=>(line.continues_from ? "延续前镜：" : line.delivery === "off_screen" ? "画外：" : "")+line.text).join(" / ") || "无对白"}</small>
                          </div>
                        )}
                        <b className="cs-shot-number">
                          {String(i + 1).padStart(2, "0")}
                        </b>
                        <span className="cs-shot-duration">
                          {s.durationSec.toFixed(1)}{uiCopy["s"]}</span>
                      </div>
                      <div className="cs-card-body">
                        <div className="cs-tags">
                          <span>{shot?.shot_type || s.shotType}</span>
                          <span>{shot?.camera_move || s.cameraMove}</span>
                        </div>
                        <h3>{s.title}</h3>
                        <p>
                          {shot?.action || shot?.image_prompt || s.imagePrompt}
                        </p>
                        <div className="cs-cast-chips">
                          {p.characters
                            .filter((c) => shot?.cast[c.id])
                            .map((c) => (
                              <span key={c.id}>
                                {c.image && <img src={c.image} alt="" />}
                                {c.name}
                              </span>
                            ))}
                        </div>
                        <div className="cs-card-status">
                          {s.videoUrl && <span><Film size={13} />{status?.video_stale ? "视频需更新" : "视频待回放"}</span>}
                          {s.status === "video_pending" && <span>{uiCopy["视频生成中"]}</span>}
                          <span
                            className={status?.image_stale ? "pending" : ""}
                          >
                            <ImageIcon size={13} />
                            {effectiveVideoInput(p, s)?.mode === "references" ? "使用联合参考" : effectiveVideoInput(p, s)?.mode === "text" ? "文字预演" : !s.image ? "画面待生成" : status?.image_stale ? uiCopy["画面待更新"] : uiCopy["画面就绪"]}
                          </span>
                          <span
                            className={status?.audio_stale ? "pending" : ""}
                          >
                            <Volume2 size={13} />
                            {effectiveVideoInput(p, s)?.sound_strategy === "model_audio" ? "视频模型原声" : !(shot?.lines.length || shot?.narration.length) ? "无需配音" : !s.audioUrl ? "配音待生成" : status?.audio_stale ? uiCopy["配音待更新"] : uiCopy["声音就绪"]}
                          </span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="cs-empty">
                <Film size={42} />
                <h2>{uiCopy["让故事成为镜头"]}</h2>
                <p>{uiCopy["先确认故事与角色，再让 AI 生成引用角色资产的分镜。"]}</p>
                <EmptyStoryboardAction planConfirmed={st.plan_confirmed} castConfirmed={st.cast_confirmed} onPhase={onPhase} onGenerate={onGenerate} />
              </div>
            )}
          </div>
          </div>
          {!st.shots_confirmed && p.scenes.length > 0 && (
            <div className="cs-confirm">
              <span>{uiCopy["确认镜头、出场角色与台词后继续"]}</span>
              <button
                className="btn primary"
                disabled={busy}
                onClick={onConfirm}
              >
                {uiCopy["确认分镜"]}</button>
            </div>
          )}
        </section>
        <aside className="cs-inspector" aria-label={uiCopy["分镜详情"]}>
          <div className="cs-panel-head">
            {right && (
              <h2>
                {"本镜制作"}{" "}
                <small>
                  {selected
                    ? String(p.scenes.indexOf(selected) + 1).padStart(2, "0")
                    : "—"}
                </small>
              </h2>
            )}
            <button
              className="icon-btn"
              aria-label={right ? uiCopy["收起分镜详情"] : uiCopy["展开分镜详情"]}
              onClick={() => setRight(!right)}
            >
              {right ? (
                <PanelRightClose size={17} />
              ) : (
                <PanelRightOpen size={17} />
              )}
            </button>
          </div>
          <div className="cs-inspector-body" hidden={!right}>
            {selected ? (
              renderInspector(selected)
            ) : (
              <p>{uiCopy["选择一个镜头，编辑画面和台词。"]}</p>
            )}
          </div>
        </aside>
      </div>
      <footer className="studio-timeline cs-timeline">
        <Link href="/export" className="cs-preview-link">
          <span className="cs-play">
            <Play size={20} />
          </span>
          <span>
            <b>{timecode(duration)}</b>
            <small>{uiCopy["全片预览 / 导出"]}</small>
          </span>
        </Link>
        <div className="cs-clips">
          {p.scenes.map((s, i) => (
            <button
              key={s.id}
              className={`cs-clip ${selected?.id === s.id ? "selected" : ""}`}
              onClick={() => select(s.id)}
              aria-label={formatCopy("时间线镜头 {0}", i + 1)}
              aria-pressed={selected?.id === s.id}
            >
              {s.image && <img src={s.image} alt="" />}
              <b>{String(i + 1).padStart(2, "0")}</b>
              <span>{s.durationSec.toFixed(1)}{uiCopy["s"]}</span>
            </button>
          ))}
        </div>
        <span className="cs-preview-label">{p.scenes.some((s) => s.videoUrl) ? uiCopy["AI 视频分镜"] : uiCopy["分镜动态预演"]}</span>
      </footer>
      {panel && (
        <Modal
          wide
          title={
            panel === "candidates"
              ? "分镜方案"
              : uiCopy["角色声音与合成检查"]
          }
          onClose={() => setPanel(null)}
        >
          <div className="cs-dialog-body">
            {panel === "candidates" ? (
              <>
                <p>{"AI 生成完成后自动应用。也可以预览历史方案，选择喜欢的一版。"}</p>
                <button
                  className="btn ai"
                  disabled={busy || !st.plan_confirmed}
                  onClick={() => onGenerate(true)}
                >
                  {"AI 生成新方案"}</button>
                {candidates}
              </>
            ) : (
              check
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

export function CandidateDraft({ value }: { value: unknown }) {
  const record = (input: unknown): Record<string, unknown> => input && typeof input === "object" && !Array.isArray(input) ? input as Record<string, unknown> : {};
  const text = (input: unknown, fallback: string = uiCopy["待补齐"]) => {
    if (input === undefined || input === null) return fallback;
    if (typeof input === "string") return input || fallback;
    return fallback;
  };
  const original = <TechnicalDetails data={value} />;
  const data = record(value);
  if (Array.isArray(data.scenes)) return <div className="cs-draft">{data.scenes.map((raw, index) => {
    const shot = record(raw);
    return <section key={index}><h4>{String(index + 1).padStart(2, "0")} · {text(shot.title, uiCopy["标题待补齐"])}</h4><p>{text(shot.action, uiCopy["动作待补齐"])}</p>{Array.isArray(shot.lines) ? shot.lines.map((rawLine, lineIndex) => <p key={lineIndex}>“{text(record(rawLine).text, uiCopy["台词文本待补齐"])}”</p>) : shot.lines !== undefined ? <p className="creative-warning">{"台词暂未生成完整。"}</p> : null}</section>;
  })}{original}</div>;
  const names: Record<string, string> = { title: uiCopy["故事标题"], synopsis: uiCopy["故事梗概"], theme: uiCopy["主题"], ending: uiCopy["结局"], beats: uiCopy["故事节奏"], name: uiCopy["角色名称"], identity: uiCopy["身份"], appearance: uiCopy["外貌"], voice_description: uiCopy["音色描述"], reason: uiCopy["推荐理由"] };
  return <div className="cs-draft">{Object.entries(names).filter(([key]) => data[key] !== undefined).map(([key, label]) => <section key={key}><h4>{label}</h4><p>{Array.isArray(data[key]) ? (data[key] as unknown[]).map(item => text(item)).join(" · ") : text(data[key])}</p></section>)}
    {Array.isArray(data.characters) && <section><h4>{uiCopy["主要角色"]}</h4>{data.characters.map((raw, index) => { const character = record(raw); return <p key={index}>{text(character.name, uiCopy["角色名称待补齐"])} · {text(character.identity, uiCopy["身份待补齐"])}</p>; })}</section>}
    {Array.isArray(data.locations) && <section><h4>{uiCopy["主要场景"]}</h4>{data.locations.map((raw, index) => { const location = record(raw); return <p key={index}>{text(location.name, uiCopy["地点名称待补齐"])} · {text(location.description, uiCopy["描述待补齐"])}</p>; })}</section>}
    {original}
  </div>;
}

"use client";

import { useState, type ReactNode } from "react";
import { ArrowRight, Check, ChevronDown, Film, ImageIcon, Pencil, Sparkles, Volume2 } from "lucide-react";
import { Modal } from "@/components/ui";
import type { Project, Scene } from "@/lib/types";
import type { Candidate } from "@/lib/creative-types";
import type { Flow, Request } from "./types";
import { TaskFeedback, type CreativeTask } from "./shared";
import { VideoGeneration } from "./VideoGeneration";
import { ProductionControls, VideoTakes } from "./ProductionControls";
import { VideoRetake } from "./VideoRetake";
import { effectiveVideoInput } from "@/lib/production";

type MediaTab = "image" | "audio" | "video";
export function productionState(project: Project, scene: Scene, status?: Flow["scenes"][number]) {
  const shot = scene.creative?.shot;
  const confirmed = !!project.creative?.shots_confirmed;
  const hasLines = !!(shot?.lines.length || shot?.narration.length);
  const imageReady = !!scene.image && status?.image_stale === false;
  const audioReady = !hasLines || (!!status?.segments?.length && !status.audio_stale);
  const input = effectiveVideoInput(project, scene);
  const mode = input?.mode || "first_frame";
  const videoBlock = status?.video_ready !== undefined ? (status.video_ready ? "" : status.video_block || "请检查制作输入") : !confirmed ? "先确认分镜，再开始制作。" : (mode !== "references" && mode !== "text" && !imageReady ? "先生成并选用本镜画面，作为视频的起始参考。" : mode === "first_last_frame" && !(input?.last_frame_asset_id || shot?.last_frame_asset_id) ? "当前使用首尾帧模式，还需要选定结束画面。" : mode === "references" && !input?.references?.some(ref => ref.kind === "image" || ref.kind === "video") ? "当前使用多素材模式，请在镜头设置中选择图片或视频参考。" : "");
  return { confirmed, hasLines, imageReady, audioReady, videoBlock, mode };
}

export function ShotProductionPanel({ project, scene, status, busy, candidates, tasks, videoEnabled, structureReady, generate, onConfirm, onPhase, onAssets, reload, editor, audioTools, correction, assets, error }: {
  project: Project; scene: Scene; status?: Flow["scenes"][number]; busy: boolean;
  candidates: Candidate[]; tasks: CreativeTask[]; videoEnabled: boolean; structureReady: boolean;
  generate: (request: Request) => void; onConfirm: () => void; onPhase: (phase: string) => void;
  onAssets: (kind: "shot_image" | "shot_audio") => void; reload: () => Promise<void>;
  editor: ReactNode; audioTools: ReactNode; correction: ReactNode; assets: ReactNode; error: ReactNode;
}) {
  const [tab, setTab] = useState<MediaTab>("video");
  const [dialog, setDialog] = useState<"editor" | "audio" | "correction" | null>(null);
  const shot = scene.creative?.shot;
  const state = productionState(project, scene, status);
  const isMember = project.creative?.production_segments?.some(group => group.scene_ids.includes(scene.id) && group.scene_ids[0] !== scene.id);
  const nativeSound = effectiveVideoInput(project, scene)?.sound_strategy === "model_audio";
  const references = project.characters.filter(character => shot?.cast[character.id]);
  const originalLineIds = new Set((shot?.lines || []).filter(line => references.find(character => character.id === line.speaker_id)?.creative?.voice?.mode === "original").map(line => line.id));
  const missingOriginal = [...originalLineIds].some(id => !status?.segments?.some(segment => segment.line.id === id && segment.strategy === "source-audio-v1"));
  const syntheticLineIds = [...(shot?.lines || []), ...(shot?.narration || [])].filter(line => !originalLineIds.has(line.id)).map(line => line.id);
  const location = project.creative?.plan?.locations.find(item => item.id === shot?.location_id);
  const mediaCandidates = candidates.filter(candidate => candidate.entityId === scene.id && candidate.kind === (tab === "audio" ? "shot_audio" : "shot_image"));
  const available = mediaCandidates.filter(candidate => !candidate.selected && !candidate.stale).length;
  const running = tasks.some(task => (task.targetId || task.sceneId) === scene.id && ["queued", "running"].includes(task.status) && task.operation === (tab === "audio" ? "shot_audio" : "shot_image"));
  const canGenerate = state.confirmed && !status?.error && !busy && !running;
  const imageLabel = !state.mode.startsWith("first") ? "可选" : !scene.image ? "待生成" : state.imageReady ? "已选用" : "待更新";
  const audioLabel = nativeSound ? "视频原声" : !state.hasLines ? "无台词" : !status?.segments?.length ? "待生成" : state.audioReady ? "已选用" : "待更新";
  const tabs = [{ id: "image" as const, title: "画面", status: imageLabel, ready: state.imageReady, icon: ImageIcon }, { id: "audio" as const, title: "声音", status: audioLabel, ready: state.audioReady, icon: Volume2 }, { id: "video" as const, title: "视频", status: scene.videoUrl ? (status?.video_stale ? "旧版可播放" : "可播放") : state.videoBlock ? "待准备" : "可生成", ready: !!scene.videoUrl, icon: Film }];
  const generateImage = (last = false) => generate({ operation: "shot_image", target: scene.id, ...(last ? { frame: "last" as const } : {}), nonce: crypto.randomUUID() });
  return <article className="shot-production">
    <header className="shot-production__heading"><div><h3>{scene.title}</h3><p>{scene.shotType} · {scene.cameraMove} · 计划 {shot?.duration ?? scene.durationSec} 秒</p></div><button className="icon-btn" aria-label="编辑镜头与台词" title="编辑镜头与台词" onClick={() => setDialog("editor")}><Pencil size={16} /></button></header>
    {!state.confirmed && <section className="shot-production__unlock" aria-label="开始制作">
      <b>下一步：确认分镜</b><p>已应用方案。确认镜头与台词后，即可生成画面和配音。</p>
      {structureReady ? <button className="btn primary" disabled={busy} onClick={onConfirm}>确认分镜，开始制作 <ArrowRight size={14} /></button> : <><p>角色或场景仍有待完成的内容，请先补齐。</p><div className="creative-actions"><button className="btn" onClick={() => onPhase("characters")}>查看角色</button><button className="btn" onClick={() => onPhase("locations")}>查看场景</button></div></>}
    </section>}
    {error}
    <ProductionControls key={`production-${scene.id}-${scene.creative?.version}`} project={project} scene={scene} reload={reload} />
    <div className="shot-production__steps" role="tablist" aria-label="本镜制作步骤">{tabs.map(({ id, title, status: label, ready, icon: Icon }, index) => <button key={id} id={`production-tab-${scene.id}-${id}`} role="tab" tabIndex={tab === id ? 0 : -1} onKeyDown={event => {
      const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); setTab(tabs[next].id); document.getElementById(`production-tab-${scene.id}-${tabs[next].id}`)?.focus(); }
    }} aria-selected={tab === id} aria-controls={`production-panel-${scene.id}`} className={tab === id ? "active" : ""} onClick={() => setTab(id)}><span><Icon size={15} />{title}</span><small>{ready ? <Check size={11} /> : null}{label}</small></button>)}</div>
    <section className="shot-production__content" role="tabpanel" id={`production-panel-${scene.id}`} aria-labelledby={`production-tab-${scene.id}-${tab}`}>
      {tab === "image" && <>
        <div className="shot-production__preview">{scene.image ? <img src={scene.image} alt={`${scene.title}已选画面`} /> : <div><ImageIcon size={30} /><b>从本镜的第一张画面开始</b><span>角色形象 + 场景环境 + 镜头设定</span></div>}</div>
        <p className="shot-production__description">参考已确认的角色形象与场景，按本镜构图、机位和起始动作生成画面。</p>
        <div className="shot-production__actions"><button className="btn cw-ai-button" disabled={!canGenerate} onClick={() => generateImage()}><Sparkles size={14} />{running ? "画面生成中" : scene.image ? "重新生成画面" : "生成分镜画面"}</button><button className="btn" disabled={!mediaCandidates.length || busy} onClick={() => onAssets("shot_image")}>{available ? `选用画面 · ${available}` : `画面候选 · ${mediaCandidates.length}`}</button></div>
        {available > 0 && <p className="shot-production__hint">有新画面待选用，选用后才能用于视频。</p>}
        <details className="shot-production__detail"><summary>结束画面 <span>可选</span><ChevronDown size={13} /></summary><p>基于已选首帧生成动作结束时的画面。仅首尾帧模式需要，普通视频不必生成。</p><button className="btn" disabled={!canGenerate || !state.imageReady || !shot?.end_state} onClick={() => generateImage(true)}>生成结束画面</button>{(!state.imageReady || !shot?.end_state) && <small>{!state.imageReady ? "先选用一张分镜画面。" : "请在镜头设置中填写结束状态。"}</small>}</details>
      </>}
      {tab === "audio" && <>
        <div className="shot-production__audio-header"><Volume2 size={22} /><div><b>{shot?.lines.length || 0} 句对白 · {shot?.narration.length || 0} 句旁白</b><span>{state.hasLines ? "使用已选音色，保持人物声音一致" : "本镜没有台词，无需生成配音"}</span></div></div>
        <p className="shot-production__description">对白参考角色已选音色，旁白使用独立音色；按每句情绪、语速与停顿生成。画面和配音可以分别制作。</p>
        {nativeSound && <p className="shot-production__hint">当前视频采用模型原声，独立配音不会自动混入该视频。可在镜头设置中切换声音方式。</p>}
        <div className="shot-production__voice-list">{references.filter(character => shot?.lines.some(line => line.speaker_id === character.id)).map(character => <div key={character.id}><span>{character.name}</span><small>{character.creative?.voice?.mode === "original" ? "使用导入录音" : "使用角色已选音色"}</small></div>)}{!!shot?.narration.length && <div><span>旁白</span><small>使用独立旁白音色</small></div>}</div>
        {scene.audioUrl && <audio aria-label="本镜已选配音" controls preload="none" src={scene.audioUrl} />}
        <div className="shot-production__actions"><button className="btn cw-ai-button" disabled={!canGenerate || !state.hasLines || missingOriginal || (originalLineIds.size > 0 && !syntheticLineIds.length)} onClick={() => generate({ operation: "shot_audio", target: scene.id, ...(state.audioReady ? { regenerate_line_ids: syntheticLineIds } : {}), nonce: crypto.randomUUID() })}><Sparkles size={14} />{running ? "配音生成中" : state.audioReady && state.hasLines ? "重新生成配音" : "生成配音"}</button><button className="btn" disabled={!mediaCandidates.length || busy} onClick={() => onAssets("shot_audio")}>{available ? `试听并选用 · ${available}` : `配音候选 · ${mediaCandidates.length}`}</button></div>
        {originalLineIds.size > 0 && <p className="shot-production__hint">本镜含原声录音角色，请在下方导入对应台词录音。</p>}
        <button className="shot-production__text-button" onClick={() => setDialog("audio")}>逐句试听、重录与导入 <ArrowRight size={13} /></button>
      </>}
      {tab === "video" && <>
        {scene.videoUrl ? <video controls playsInline preload="metadata" src={`${scene.videoUrl}#t=${scene.creative?.edit?.in_sec || 0},${scene.creative?.edit?.out_sec || scene.creative?.video?.duration || ''}`} poster={scene.image} aria-label="本镜视频预览" /> : <div className="shot-production__video-input"><Film size={25} /><b>按本段设计生成视频</b><span>{state.mode === "first_last_frame" ? "首帧 + 尾帧 + 动作" : state.mode === "references" ? "已选参考素材 + 动作" : state.mode === "text" ? "文字设计 + 动作 + 声音要求" : "已选首帧 + 动作 + 运镜"}</span></div>}
        <p className="shot-production__description">{nativeSound ? "由视频模型同步生成声音。角色音色一致性以实际试听为准。" : "默认生成无声视频，成片时合入已选配音。建议先选好配音，让视频参考实际台词时序。"}</p>
        <div className="shot-production__checklist">{(state.mode === "first_frame" || state.mode === "first_last_frame") && <span data-ready={state.imageReady}><Check size={13} />本镜画面{state.imageReady ? "已选用" : "待选用"}</span>}<span data-ready={state.audioReady}><Check size={13} />{!state.hasLines ? "本镜无需配音" : state.audioReady ? "本镜配音已选用" : nativeSound ? "使用视频模型原声" : "建议先选用配音"}</span></div>
        {state.videoBlock && <div className="shot-production__hint"><p>{state.videoBlock}</p>{state.confirmed && !state.imageReady && state.mode.startsWith("first") && <button className="shot-production__text-button" onClick={() => setTab("image")}>前往准备画面 <ArrowRight size={13} /></button>}{state.confirmed && state.imageReady && <button className="shot-production__text-button" onClick={() => setDialog("editor")}>调整镜头设置 <ArrowRight size={13} /></button>}</div>}
        {!state.videoBlock && !state.audioReady && !nativeSound && <button className="shot-production__text-button" onClick={() => setTab("audio")}>先制作配音 <ArrowRight size={13} /></button>}
        {!isMember && (videoEnabled ? scene.videoUrl ? <VideoRetake scene={scene} disabled={busy || !!state.videoBlock} /> : <VideoGeneration projectId={project.id} scenes={[scene]} disabled={busy || !!state.videoBlock} reload={reload} /> : <p className="shot-production__hint">当前未启用视频生成服务。</p>)}
        <button className="shot-production__text-button" onClick={() => setDialog("correction")}>导入视频修正版 <ArrowRight size={13} /></button>
      </>}
      {!state.confirmed && <p className="shot-production__hint">请先在上方确认分镜，生成按钮随后可用。</p>}
      {tab !== "video" && status?.error && <p className="shot-production__hint" role="alert">{status.error}</p>}
      {tab === "video" && <VideoTakes key={`takes-${scene.id}-${scene.creative?.version}`} project={project} scene={scene} reload={reload} />}
      {tab !== "video" && <TaskFeedback project={project} tasks={tasks} candidates={candidates} target={scene.id} operations={[tab === "image" ? "shot_image" : "shot_audio"]} maxItems={1} />}
    </section>
    <details className="shot-production__sources"><summary>项目参考库（未必用于本次） <ChevronDown size={14} /></summary><div className="shot-production__reference-list">{references.map(character => <button key={character.id} onClick={() => onPhase("characters")}>{character.image && <img src={character.image} alt="" />}<span>{character.name}<small>角色形象与音色</small></span></button>)}<button onClick={() => onPhase("locations")}><ImageIcon size={22} /><span>{location?.name || "场景环境"}<small>已确认环境参考</small></span></button></div><p>{project.style} · {project.ratio}</p><p>{shot?.action}</p><button className="shot-production__text-button" onClick={() => setDialog("editor")}>编辑构图、动作与台词 <ArrowRight size={13} /></button></details>
    {assets}
    {dialog && <Modal wide title={dialog === "editor" ? `${scene.title} · 镜头设置` : dialog === "audio" ? `${scene.title} · 台词与配音` : `${scene.title} · 视频修正版`} onClose={() => setDialog(null)}><div className="cs-dialog-body shot-production__dialog">{error}{dialog === "editor" ? <><p className="helper">保存修改后需重新确认分镜；受影响的画面或配音会提示更新。</p>{editor}</> : dialog === "audio" ? audioTools : correction}</div></Modal>}
  </article>;
}

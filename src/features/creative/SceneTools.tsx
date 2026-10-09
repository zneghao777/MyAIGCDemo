"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { NativeAudition } from "./NativeAudition";
import { effectiveVideoInput } from "@/lib/production";
import { TechnicalDetails } from "./TechnicalDetails";
import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useEffect, useRef, useState } from "react";
import type { Project } from "@/lib/types";
import type {
  Plan,
  Shot,
  Line,
  Candidate,
  SceneState,
  LocationState,
  VideoInput,
} from "@/lib/creative-types";
import type { Flow, Request } from "./types";
import { api, apiBase } from "@/lib/api";
import { Field, useCreativeDraft } from "./shared";
const emotionNames: Record<string, string> = {
  neutral: uiCopy["自然"],
  happy: uiCopy["开心"],
  sad: uiCopy["悲伤"],
  angry: uiCopy["生气"],
  fearful: uiCopy["害怕"],
  disgusted: uiCopy["厌恶"],
  surprised: uiCopy["惊讶"],
  calm: uiCopy["平静"],
};
export function Narrator({
  voice,
  save,
}: {
  voice: string;
  save: (v: string) => void;
}) {
  const [v, setV] = useState(voice);
  return (
    <div className="creative-actions">
      <Field
        label={uiCopy["独立旁白音色 ID（不会借用角色音色）"]}
        value={v}
        onChange={setV}
      />
      <button className="btn" onClick={() => save(v)}>
        {uiCopy["保存旁白配置"]}</button>
    </div>
  );
}
export function ShotEditor({
  projectId,
  sceneId,
  scenes,
  locations,
  candidates,
  state,
  characters,
  plan,
  title,
  draftKey,
  save,
}: {
  projectId: string;
  sceneId: string;
  scenes: Project["scenes"];
  locations: Record<string, LocationState>;
  candidates: Candidate[];
  draftKey: string;
  state?: SceneState;
  characters: Project["characters"];
  plan: Plan | null;
  title: string;
  save: (s: Shot) => void;
}) {
  const [draft, setDraft] = useCreativeDraft<Shot>(
    draftKey,
    state?.shot || {
      title,
      cast: {},
      variants: {},
      location_id: plan?.locations[0]?.id || "",
      location_description: plan?.locations[0]?.description || "",
      action: "",
      expression: "",
      composition: "",
      shot_type: uiCopy["中景"],
      camera_angle: uiCopy["平视"],
      camera_move: uiCopy["固定"],
      duration: 5,
      image_prompt: "",
      sound_notes: "",
      lines: [],
      narration: [],
    },
  );
  const [editorTab, setEditorTab] = useState<string>(uiCopy["画面"]);
  const [validationError, setValidationError] = useState("");
  const videoInput: VideoInput = draft.video_input || { mode: "first_frame", references: [], sound_strategy: "post_audio", use_context_ir: false };
  const updateVideo = (patch: Partial<VideoInput>) => {
    const soundChanged = patch.sound_strategy !== undefined && patch.sound_strategy !== videoInput.sound_strategy;
    setDraft({ ...draft, video_input: { ...videoInput, ...patch }, ...(soundChanged ? { subtitles_calibrated: false } : {}) });
    if (soundChanged) setValidationError(uiCopy["视频声音策略已修改，请重新试听并校准字幕时间。"]);
  };
  const [projectAssets, setProjectAssets] = useState<{ id: string; kind: string; contentType: string; url: string }[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    void api<{ id: string; kind: string; contentType: string; url: string }[]>(`/projects/${projectId}/assets`, "GET", undefined, controller.signal).then(setProjectAssets).catch(() => {});
    return () => controller.abort();
  }, [projectId, candidates.length]);
  const ownerName = (id: string) => characters.find(character => character.id === id)?.name || scenes.find(scene => scene.id === id)?.title || plan?.locations.find(location => location.id === id)?.name || uiCopy["项目素材"];
  const assetOptions = (kind?: string) => {
    const options = new Map(projectAssets.filter(asset => !kind || asset.contentType?.startsWith(`${kind}/`)).map(asset => [asset.id, { id: asset.id, assetId: asset.id, label: formatCopy("素材 {0}", projectAssets.indexOf(asset) + 1), url: asset.url }]));
    for (const candidate of candidates) {
      if (!candidate.url || !candidate.data.asset_id || candidate.stale) continue;
      const type = candidate.kind.includes("image") ? "image" : candidate.kind.includes("video") ? "video" : "audio";
      if (!kind || type === kind) options.set(candidate.data.asset_id, { id: candidate.id, assetId: candidate.data.asset_id, label: `${ownerName(candidate.entityId)} · ${candidate.data.request?.frame === "last" ? uiCopy["结束状态尾帧"] : candidate.data.request?.view || candidate.data.request?.variant || uiCopy["主素材"]}`, url: candidate.url });
    }
    return Array.from(options.values());
  };
  const currentLocation = locations[draft.location_id];
  const allLines = [...draft.lines, ...draft.narration];
  const validIds = new Set(allLines.map((x) => x.id));
  const audioOrder = [
    ...(draft.audio_order || []).filter((id) => validIds.has(id)),
    ...allLines
      .map((x) => x.id)
      .filter((id) => !draft.audio_order?.includes(id)),
  ];
  const moveAudio = (index: number, delta: number) => {
    const order = [...audioOrder];
    [order[index], order[index + delta]] = [order[index + delta], order[index]];
    setDraft({ ...draft, audio_order: order, subtitles_calibrated: false });
    if (draft.subtitles_calibrated) setValidationError(uiCopy["声音播放顺序已修改，字幕时间需要重新试听校准。"]);
  };
  const updateLine = (
    kind: "lines" | "narration",
    i: number,
    data: Partial<Line>,
  ) =>
    {
      setDraft({
        ...draft,
        subtitles_calibrated: false,
        [kind]: draft[kind].map((x, j) => (i === j ? { ...x, ...data } : x)),
      });
      if (draft.subtitles_calibrated) setValidationError(uiCopy["台词或声音时序已修改，字幕时间需要重新试听校准。"]);
    };
  const removeLine = (kind: "lines" | "narration", index: number) => {
    const deleted = draft[kind][index];
    setDraft({
      ...draft,
      [kind]: draft[kind].filter((_, i) => i !== index),
      subtitle_cues: (draft.subtitle_cues || []).filter(cue => cue.line_id !== deleted.id),
      action_steps: (draft.action_steps || []).map(step => step.trigger_line_id === deleted.id ? { ...step, trigger_line_id: undefined } : step),
      subtitles_calibrated: false,
    });
    setValidationError(uiCopy["已移除对应字幕并解除动作的台词触发绑定，动作描述保留；请重新检查声音与动作时序。"]);
  };
  return (
    <details className="creative-editor" open>
      <summary>
        {uiCopy["编辑结构化分镜 ·"]}{Object.keys(draft.cast).length} {uiCopy["名角色 /"]}{" "}
        {draft.lines.length} {uiCopy["句台词"]}</summary>
      {state?.needs_binding && (
        <p className="creative-warning">
          {uiCopy["旧台词保留："]}{state.legacy_dialogue} {uiCopy["/ 旁白："]}{state.legacy_narration}
          {uiCopy["。请明确选择发言人，不自动猜测。"]}</p>
      )}
      {JSON.stringify(draft) !== JSON.stringify(state?.shot) && (
        <p className="creative-warning" role="status">
          {uiCopy["有未保存修改 · 暂存在本标签页"]}</p>
      )}
      <div className="cs-tabs cs-editor-tabs">
        {[uiCopy["画面"], uiCopy["起止画面"], uiCopy["台词与声音"]].map((t) => (
          <button
            key={t}
            className={editorTab === t ? "active" : ""}
            onClick={() => setEditorTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <button
        className="btn primary shot-save"
        onClick={() => {
          if (draft.lines.some(line => !line.speaker_id || !(line.speaker_id in draft.cast) && !(line.speaker_id in (draft.offscreen_cast || {})))) { setValidationError(uiCopy["每句台词必须绑定当前出场角色，请重新选择发言人或移除该句。"]); return; }
          const subtitleDuration = state?.edit ? state.edit.out_sec - state.edit.in_sec : draft.duration;
          const timed = [...(draft.action_steps || []).map(event=>({...event, limit:draft.duration})), ...(draft.subtitle_cues || []).map(event=>({...event, limit:subtitleDuration}))];
          if (!Number.isFinite(draft.duration) || draft.duration <= 0 || timed.some(event => !Number.isFinite(event.start_sec) || !Number.isFinite(event.end_sec) || event.start_sec < 0 || event.end_sec <= event.start_sec || event.end_sec > event.limit)) { setValidationError(uiCopy["动作和字幕时间必须在镜头时长内，且结束晚于开始。"]); return; }
          if ((draft.action_steps || []).some(step => step.trigger_sec != null && (!Number.isFinite(step.trigger_sec) || step.trigger_sec < step.start_sec || step.trigger_sec > step.end_sec))) { setValidationError(uiCopy["动作触发点必须位于对应动作时间区间内。"]); return; }
          setValidationError(""); save({ ...draft, audio_order: audioOrder });
        }}
      >
        {"保存分镜设定"}</button>
      <div hidden={editorTab !== uiCopy["画面"]}>
        <fieldset><legend>覆盖的剧情节点</legend>{plan?.beats.map((beat,i)=><label className="beat-choice" key={i}><input type="checkbox" checked={draft.beat_indices?.includes(i) || false} onChange={e=>setDraft({...draft,beat_indices:e.target.checked ? [...draft.beat_indices || [],i] : draft.beat_indices?.filter(x=>x!==i)})}/> {beat}</label>)}</fieldset>
        <div className="creative-grid">
          {(
            [
              ["title", uiCopy["镜头标题"]],
              ["action", uiCopy["人物动作"]],
              ["expression", uiCopy["表情"]],
              ["composition", uiCopy["构图"]],
              ["camera_angle", uiCopy["机位"]],
              ["image_prompt", uiCopy["画面提示词"]],
              ["sound_notes", uiCopy["声音创作备注（实际音效请在声音页上传）"]],
            ] as const
          ).map(([k, l]) => (
            <Field
              key={k}
              label={l}
              value={draft[k]}
              onChange={(v) => setDraft({ ...draft, [k]: v })}
            />
          ))}
          <Field
            label={uiCopy["预计时长（秒）"]}
            value={String(draft.duration)}
            onChange={(v) => setDraft({ ...draft, duration: Number(v) })}
          />
          <label className="creative-field">
            {uiCopy["场景"]}<select
              value={draft.location_id}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  location_id: e.target.value,
                  location_description:
                    plan?.locations.find((x) => x.id === e.target.value)
                      ?.description || "",
                  location_revision: locations[e.target.value]?.revision,
                  location_state: "",
                })
              }
            >
              {plan?.locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <label className="creative-field">{"本镜场景"}<select value={draft.location_revision || ""} onChange={e => setDraft({ ...draft, location_revision: e.target.value })}><option value="">{uiCopy["旧镜头 / 尚未绑定"]}</option>{draft.location_revision && draft.location_revision !== currentLocation?.revision && <option value={draft.location_revision}>已选历史场景</option>}{currentLocation && <option value={currentLocation.revision}>{currentLocation.location.name} {currentLocation.confirmed ? uiCopy[" · 已确认"] : uiCopy[" · 待确认"]}</option>}</select></label>
          <label className="creative-field">{uiCopy["环境状态"]}<select value={draft.location_state || ""} onChange={e => setDraft({ ...draft, location_state: e.target.value })}><option value="">{uiCopy["基础环境"]}</option>{Object.keys(currentLocation?.location.states || {}).map(key => <option key={key} disabled={!currentLocation?.states?.[key]}>{key}{currentLocation?.states?.[key] ? "" : uiCopy[" · 环境图待选择"]}</option>)}</select></label>
          <label className="creative-field">
            {uiCopy["景别"]}<select
              value={draft.shot_type}
              onChange={(e) =>
                setDraft({ ...draft, shot_type: e.target.value })
              }
            >
              {[uiCopy["远景"], uiCopy["全景"], uiCopy["中景"], uiCopy["近景"], uiCopy["特写"]].map((x) => (
                <option key={x} value={x}>
                  {emotionNames[x] || x}
                </option>
              ))}
            </select>
          </label>
          <label className="creative-field">
            {uiCopy["运镜"]}<select
              value={draft.camera_move}
              onChange={(e) =>
                setDraft({ ...draft, camera_move: e.target.value })
              }
            >
              {[uiCopy["固定"], uiCopy["缓推"], uiCopy["拉远"], uiCopy["摇镜"], uiCopy["缓慢横移"], uiCopy["跟随"]].map((x) => (
                <option key={x} value={x}>
                  {emotionNames[x] || x}
                </option>
              ))}
            </select>
          </label>
        </div>
        <h4>{"出场角色"}</h4>
        {characters.map((c) => (
          <div key={c.id}>
            <label>
              <input
                type="checkbox"
                checked={!!draft.cast[c.id]}
                disabled={!c.creative?.confirmed}
                onChange={(e) => {
                  const cast = { ...draft.cast };
                  const variants = { ...draft.variants };
                  const character_views = { ...draft.character_views };
                  const spatial_relations = { ...draft.spatial_relations };
                  if (e.target.checked) cast[c.id] = c.creative!.revision;
                  else {
                    delete cast[c.id];
                    delete variants[c.id];
                    delete character_views[c.id];
                    delete spatial_relations[c.id];
                  }
                  setDraft({ ...draft, cast, variants, character_views, spatial_relations });
                  setValidationError(!e.target.checked && draft.lines.some(line => line.speaker_id === c.id) ? uiCopy["此角色仍有台词。请在台词与声音页重新选择发言人或移除此句，再保存。"] : "");
                }}
              />{" "}
              {c.name}{" "}
              {c.creative?.confirmed ? "" : uiCopy["（尚未定稿）"]}
            </label>
            {draft.cast[c.id] && (
              <select
                aria-label={formatCopy("{0}造型", c.name)}
                value={draft.variants[c.id] || ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    variants: { ...draft.variants, [c.id]: e.target.value },
                  })
                }
              >
                <option value="">{uiCopy["基础造型"]}</option>
                {Object.keys(c.creative?.persona.variants || {}).map((x) => (
                  <option key={x} value={x}>
                    {emotionNames[x] || x}
                  </option>
                ))}
              </select>
            )}
            {draft.cast[c.id] && <><label className="creative-field">{c.name} {uiCopy["· 本镜参考视图"]}<select value={draft.character_views?.[c.id] || ""} onChange={e => setDraft({ ...draft, character_views: { ...draft.character_views, [c.id]: e.target.value } })}><option value="">{uiCopy["主造型"]}</option>{Object.keys(c.creative?.views || {}).map(view => <option key={view}>{view}</option>)}</select></label><Field label={formatCopy("{0} · 左右位置 / 朝向 / 视线", c.name)} value={draft.spatial_relations?.[c.id] || ""} onChange={value => setDraft({ ...draft, spatial_relations: { ...draft.spatial_relations, [c.id]: value } })} /></>}
          </div>
        ))}
      </div>
      <div hidden={editorTab !== uiCopy["起止画面"]}>
        <h4>{uiCopy["可见动作与结果"]}</h4>
        <div className="creative-grid">{([['purpose', uiCopy["本镜目的"]], ['start_state', uiCopy["起始状态（人物、装备、环境、事件）"]], ['end_state', uiCopy["结束状态与可见结果"]], ['continuity_requirements', uiCopy["承接条件与邻镜注意事项"]]] as const).map(([key, label]) => <Field key={key} label={label} value={draft[key] || ""} large onChange={value => setDraft({ ...draft, [key]: value })} />)}</div>
        <label className="creative-field">{uiCopy["真实前镜尾帧依赖"]}<select value={draft.continuity_from || ""} onChange={e => setDraft({ ...draft, continuity_from: e.target.value || null })}><option value="">{uiCopy["无远端依赖 · 可独立并发"]}</option>{scenes.filter((_, index) => index < scenes.findIndex(scene => scene.id === sceneId)).map(scene => <option key={scene.id} value={scene.id}>{scene.title} {uiCopy["· 使用其生成尾帧"]}</option>)}</select></label>
        <p className="helper">{uiCopy["普通故事衔接写在承接条件；只有实际引用前镜生成尾帧时才建立任务依赖。"]}</p>
        {(draft.action_steps || []).map((step, index) => <div className="creative-line" key={step.id}><b>{uiCopy["动作"]}{index + 1}</b><Field label={uiCopy["起始秒"]} value={String(step.start_sec)} onChange={value => setDraft({ ...draft, action_steps: draft.action_steps!.map((x, i) => i === index ? { ...x, start_sec: Number(value) } : x) })} /><Field label={uiCopy["结束秒"]} value={String(step.end_sec)} onChange={value => setDraft({ ...draft, action_steps: draft.action_steps!.map((x, i) => i === index ? { ...x, end_sec: Number(value) } : x) })} /><Field label={uiCopy["可观察动作及结果"]} value={step.description} onChange={value => setDraft({ ...draft, action_steps: draft.action_steps!.map((x, i) => i === index ? { ...x, description: value } : x) })} /><label className="creative-field">{uiCopy["关联台词触发点"]}<select value={step.trigger_line_id || ""} onChange={e => setDraft({ ...draft, action_steps: draft.action_steps!.map((x, i) => i === index ? { ...x, trigger_line_id: e.target.value || undefined } : x) })}><option value="">{uiCopy["无台词触发"]}</option>{allLines.map(line => <option key={line.id} value={line.id}>{line.text}</option>)}</select></label><Field label={uiCopy["动作触发秒（可留空）"]} value={step.trigger_sec == null ? "" : String(step.trigger_sec)} onChange={value => setDraft({ ...draft, action_steps: draft.action_steps!.map((x, i) => i === index ? { ...x, trigger_sec: value === "" ? undefined : Number(value) } : x) })} /><button className="btn" onClick={() => setDraft({ ...draft, action_steps: draft.action_steps!.filter((_, i) => i !== index) })}>{uiCopy["移除此动作"]}</button></div>)}
        <button className="btn" onClick={() => setDraft({ ...draft, action_steps: [...draft.action_steps || [], { id: crypto.randomUUID(), start_sec: 0, end_sec: draft.duration, description: "" }] })}>{uiCopy["添加动作时间事件"]}</button>
        <h4>{uiCopy["首帧与尾帧"]}</h4>
        <p className="helper">{uiCopy["展示图用于分镜阅读；首帧应处于动作开始前，尾帧对应结束结果。首尾帧模式与多素材参考互斥。"]}</p>
        <label className="creative-field">{uiCopy["视频输入模式"]}<select value={videoInput.mode} onChange={e => setDraft({ ...draft, first_frame_asset_id: undefined, last_frame_asset_id: undefined, video_input: { ...videoInput, mode: e.target.value as VideoInput["mode"], references: [], first_frame_asset_id: undefined, last_frame_asset_id: undefined } })}><option value="first_frame">{uiCopy["首帧 · 兼容已有镜头"]}</option><option value="first_last_frame">{uiCopy["首尾帧"]}</option><option value="references">{uiCopy["多素材参考"]}</option><option value="text">纯文字预演</option></select></label>
        {videoInput.mode.startsWith("first") && <label className="creative-field">{uiCopy["首帧素材"]}<select value={draft.first_frame_asset_id || videoInput.first_frame_asset_id || ""} onChange={e => setDraft({ ...draft, first_frame_asset_id: e.target.value || undefined, video_input: { ...videoInput, first_frame_asset_id: e.target.value || undefined } })}><option value="">{uiCopy["使用当前选中分镜图"]}</option>{assetOptions("image").map(c => <option key={c.id} value={c.assetId}>{c.label}</option>)}</select></label>}
        {videoInput.mode === "first_last_frame" && <label className="creative-field">{uiCopy["尾帧素材"]}<select value={draft.last_frame_asset_id || videoInput.last_frame_asset_id || ""} onChange={e => setDraft({ ...draft, last_frame_asset_id: e.target.value || undefined, video_input: { ...videoInput, last_frame_asset_id: e.target.value || undefined } })}><option value="">{uiCopy["请选择结束状态图"]}</option>{assetOptions("image").map(c => <option key={c.id} value={c.assetId}>{c.label}</option>)}</select></label>}
        {videoInput.mode === "references" && <section><p>{uiCopy["每项素材按类型编号，请说明画面或声音的用途。生成前会检查素材是否可用。"]}</p>{videoInput.references.map((ref, index) => <div className="creative-line" key={index}><label className="creative-field">{uiCopy["素材类型"]}<select value={ref.kind} onChange={e => updateVideo({ references: videoInput.references.map((x, i) => i === index ? { ...x, kind: e.target.value as typeof ref.kind, asset_id: "" } : x) })}><option value="image">{uiCopy["画面素材"]}</option><option value="video">{uiCopy["视频素材"]}</option><option value="audio">{uiCopy["声音素材"]}</option></select></label><label className="creative-field">{uiCopy["实际素材"]}<select value={ref.asset_id} onChange={e => updateVideo({ references: videoInput.references.map((x, i) => i === index ? { ...x, asset_id: e.target.value } : x) })}><option value="">{uiCopy["选择本项目素材"]}</option>{assetOptions(ref.kind).map(c => <option key={c.id} value={c.assetId}>{c.label}</option>)}</select></label><Field label={uiCopy["用途（身份 / 环境 / 动作 / 声音）"]} value={ref.purpose} onChange={value => updateVideo({ references: videoInput.references.map((x, i) => i === index ? { ...x, purpose: value } : x) })} /><button className="btn" onClick={() => updateVideo({ references: videoInput.references.filter((_, i) => i !== index) })}>{uiCopy["移除此参考"]}</button></div>)}<button className="btn" onClick={() => updateVideo({ references: [...videoInput.references, { kind: "image", asset_id: "", purpose: "" }] })}>{uiCopy["添加必要参考素材"]}</button></section>}
        <label className="creative-field">{uiCopy["声音策略"]}<select value={videoInput.sound_strategy} onChange={e => updateVideo({ sound_strategy: e.target.value as VideoInput["sound_strategy"] })}><option value="post_audio">{uiCopy["后期配声 · 保留本片对白与原音"]}</option><option value="model_audio">{uiCopy["模型声音 · 后期避免重复混入对白"]}</option></select></label>
        <label><input type="checkbox" checked={videoInput.use_context_ir || false} onChange={e => updateVideo({ use_context_ir: e.target.checked })} /> {"整理参考关系与对白要求"}</label>
        <Field label={uiCopy["补充视频要求（素材用途 → 人物与环境约束 → 动作时间 → 镜头 → 结束 → 声音）"]} value={videoInput.prompt || ""} large onChange={value => updateVideo({ prompt: value })} />
        <p className="helper">{"保存设定后，可重新生成这一镜的视频。"}</p>
      </div>
      <div hidden={editorTab !== uiCopy["台词与声音"]}>
        <fieldset><legend>画外发言角色（只发声，不要求入画）</legend>{characters.filter(c=>!draft.cast[c.id]).map(c=><label className="beat-choice" key={c.id}><input type="checkbox" checked={c.id in (draft.offscreen_cast || {})} onChange={e=>{const cast={...draft.offscreen_cast};if(e.target.checked)cast[c.id]=c.creative?.revision || "";else delete cast[c.id];setDraft({...draft,offscreen_cast:cast});}}/> {c.name}</label>)}</fieldset>
        <section className="cs-audio-order">
          <h4>{uiCopy["声音播放顺序"]}</h4>
          <p className="helper">
            {uiCopy["对白与旁白可穿插。字幕与预览使用同一顺序，停顿跟随每句话。"]}</p>
          {audioOrder.map((id, i) => {
            const line = allLines.find((x) => x.id === id)!;
            return (
              <div className="cs-audio-order-row" key={id}>
                <span>
                  <b>
                    {i + 1} ·{" "}
                    {characters.find((c) => c.id === line.speaker_id)?.name ||
                      uiCopy["旁白"]}
                  </b>
                  <small>{line.text}</small>
                </span>
                <button
                  className="btn"
                  aria-label={formatCopy("上移声音 {0}", i + 1)}
                  disabled={i === 0}
                  onClick={() => moveAudio(i, -1)}
                >
                  ↑
                </button>
                <button
                  className="btn"
                  aria-label={formatCopy("下移声音 {0}", i + 1)}
                  disabled={i === audioOrder.length - 1}
                  onClick={() => moveAudio(i, 1)}
                >
                  ↓
                </button>
              </div>
            );
          })}
        </section>
        {(["lines", "narration"] as const).map((kind) => (
          <section key={kind}>
            <h4>
              {kind === "lines" ? uiCopy["角色台词"] : uiCopy["独立旁白（在上方调整播放顺序）"]}
            </h4>
            {draft[kind].map((line, i) => (
              <div className="creative-line" key={line.id}>
                {kind === "lines" && (
                  <select
                    aria-label={uiCopy["发言角色"]}
                    value={line.speaker_id || ""}
                    onChange={(e) =>
                      updateLine(kind, i, { speaker_id: e.target.value })
                    }
                  >
                    <option value="">{uiCopy["请选择发言人"]}</option>
                    {characters
                      .filter((c) => (c.id in draft.cast || c.id in (draft.offscreen_cast || {})) && c.creative?.persona.role_kind !== "background")
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                  </select>
                )}
                <label className="creative-field">说话方式<select value={line.delivery || "on_screen"} onChange={e=>updateLine(kind,i,{delivery:e.target.value as Line["delivery"]})}><option value="on_screen">画内说话</option><option value="off_screen">画外音</option></select></label>
                <label className="creative-field">跨镜声音<select value={line.continues_from || ""} onChange={e=>updateLine(kind,i,{continues_from:e.target.value || null})}><option value="">从本镜开始说</option>{scenes.slice(0,scenes.findIndex(s=>s.id===sceneId)).flatMap(s=>[...s.creative?.shot?.lines || [], ...s.creative?.shot?.narration || []]).filter(previous=>previous.speaker_id===line.speaker_id).map(previous=><option value={previous.id} key={previous.id}>延续前句：{previous.text}</option>)}</select></label>
                <Field
                  label={formatCopy("{0}. 文本", i + 1)}
                  value={line.text}
                  onChange={(text) => updateLine(kind, i, { text })}
                />
                {characters.find((c) => c.id === line.speaker_id)?.creative
                  ?.persona.voice_mode === "stable" ? (
                  <p className="helper">
                    {uiCopy["此角色使用稳定音色：固定基础语速与平静语气。如需逐句表演，请在角色声音设定中切换模式。"]}</p>
                ) : (
                  <>
                    <label className="creative-field">
                      {uiCopy["情绪"]}<select
                        value={line.emotion}
                        onChange={(e) =>
                          updateLine(kind, i, { emotion: e.target.value })
                        }
                      >
                        {[
                          "neutral",
                          "happy",
                          "sad",
                          "angry",
                          "fearful",
                          "disgusted",
                          "surprised",
                          "calm",
                        ].map((x) => (
                          <option key={x} value={x}>
                            {emotionNames[x] || x}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Field
                      label={uiCopy["语速倍率"]}
                      value={String(line.speed)}
                      onChange={(v) =>
                        updateLine(kind, i, { speed: Number(v) })
                      }
                    />
                  </>
                )}
                <Field
                  label={uiCopy["句后停顿秒数"]}
                  value={String(line.pause_after)}
                  onChange={(v) =>
                    updateLine(kind, i, { pause_after: Number(v) })
                  }
                />
                <button
                  className="btn"
                  onClick={() => removeLine(kind, i)}
                >
                  {uiCopy["移除此句"]}</button>
              </div>
            ))}
            <button
              className="btn"
              onClick={() =>
                setDraft({
                  ...draft,
                  subtitles_calibrated: false,
                  [kind]: [
                    ...draft[kind],
                    {
                      id: crypto.randomUUID(),
                      speaker_id:
                        kind === "lines"
                          ? Object.keys(draft.cast)[0] || null
                          : null,
                      text: uiCopy["新台词"],
                      emotion: "neutral",
                      speed: 1,
                      pause_after: 0.15,
                    },
                  ],
                })
              }
            >
              {uiCopy["添加"]}{kind === "lines" ? uiCopy["台词"] : uiCopy["旁白"]}
            </button>
          </section>
        ))}
        <section><h4>{uiCopy["逐句字幕时间轴"]}</h4><p className="helper">{"字幕按本镜实际采用区间计时；与生成原片时间不同。调整后应用并保存。"}</p>{(draft.subtitle_cues || []).map((cue, index) => <div className="creative-line" key={cue.id}><label className="creative-field">{uiCopy["对应台词"]}<select value={cue.line_id || ""} onChange={e => setDraft({ ...draft, subtitles_calibrated: false, subtitle_cues: draft.subtitle_cues!.map((x, i) => i === index ? { ...x, line_id: e.target.value || undefined } : x) })}><option value="">{uiCopy["独立字幕"]}</option>{allLines.map(line => <option key={line.id} value={line.id}>{line.text}</option>)}</select></label><Field label={uiCopy["字幕文本"]} value={cue.text} onChange={value => setDraft({ ...draft, subtitles_calibrated: false, subtitle_cues: draft.subtitle_cues!.map((x, i) => i === index ? { ...x, text: value } : x) })} /><Field label={uiCopy["开始秒"]} value={String(cue.start_sec)} onChange={value => setDraft({ ...draft, subtitles_calibrated: false, subtitle_cues: draft.subtitle_cues!.map((x, i) => i === index ? { ...x, start_sec: Number(value) } : x) })} /><Field label={uiCopy["结束秒"]} value={String(cue.end_sec)} onChange={value => setDraft({ ...draft, subtitles_calibrated: false, subtitle_cues: draft.subtitle_cues!.map((x, i) => i === index ? { ...x, end_sec: Number(value) } : x) })} /><button className="btn" onClick={() => setDraft({ ...draft, subtitles_calibrated: false, subtitle_cues: draft.subtitle_cues!.filter((_, i) => i !== index) })}>{uiCopy["移除此字幕"]}</button></div>)}<button className="btn" onClick={() => setDraft({ ...draft, subtitles_calibrated: false, subtitle_cues: [...draft.subtitle_cues || [], { id: crypto.randomUUID(), start_sec: 0, end_sec: draft.duration, text: "" }] })}>{uiCopy["添加字幕区间"]}</button><button className="btn" disabled={!draft.subtitle_cues?.length} onClick={() => setDraft({ ...draft, subtitles_calibrated: true })}>应用字幕时间</button></section>
        <SoundEffects
          projectId={projectId}
          value={draft.sound_effects || []}
          onChange={(sound_effects) => setDraft({ ...draft, sound_effects })}
        />
      </div>
      {validationError && <p role="alert" className="creative-warning">{validationError}</p>}

    </details>
  );
}

function SoundEffects({
  projectId,
  value,
  onChange,
}: {
  projectId: string;
  value: NonNullable<Shot["sound_effects"]>;
  onChange: (v: NonNullable<Shot["sound_effects"]>) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>("");
  return (
    <section>
      <h4>{uiCopy["镜头音效"]}</h4>
      <p className="helper">
        {uiCopy["上传脚步、雨声等音效，设置从镜头第几秒开始；音效与对白同时混音，超出镜头的部分自动裁切。"]}</p>
      {value.map((effect, i) => (
        <div className="creative-line" key={`${effect.asset_id}-${i}`}>
          <b>{uiCopy["音效"]}{i + 1}</b>
          <audio
            controls
            preload="none"
            src={`${apiBase}/api/assets/${effect.asset_id}?redirect=true`}
          />
          <label>
            {uiCopy["开始秒数"]}<input
              aria-label={formatCopy("音效 {0} 开始秒数", i + 1)}
              type="number"
              min={0}
              max={120}
              step={0.1}
              value={effect.start_sec}
              onChange={(e) =>
                onChange(
                  value.map((x, j) =>
                    j === i ? { ...x, start_sec: Number(e.target.value) } : x,
                  ),
                )
              }
            />
          </label>
          <label>
            {uiCopy["音量"]}<input
              aria-label={formatCopy("音效 {0} 音量", i + 1)}
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={effect.volume}
              onChange={(e) =>
                onChange(
                  value.map((x, j) =>
                    j === i ? { ...x, volume: Number(e.target.value) } : x,
                  ),
                )
              }
            />
          </label>
          <button
            className="btn"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            {uiCopy["从此镜移除音效"]}</button>
        </div>
      ))}
      <label className="btn">
        {uploading ? uiCopy["正在处理音效…"] : uiCopy["上传音效"]}
        <input
          type="file"
          accept="audio/*"
          hidden
          disabled={uploading || value.length >= 8}
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setUploading(true);
            setError("");
            try {
              if (file.size > 20 * 1024 * 1024)
                throw new Error(uiCopy["音效不能超过 20 MB"]);
              const form = new FormData();
              form.append("file", file);
              const res = await fetch(
                `${apiBase}/api/projects/${projectId}/sound-effects`,
                { method: "POST", body: form },
              );
              const data = await res.json();
              if (!res.ok)
                throw new Error(data.error?.message || uiCopy["音效上传失败"]);
              onChange([
                ...value,
                { asset_id: data.id, start_sec: 0, volume: 0.35 },
              ]);
            } catch (e) {
              setError(e);
            } finally {
              setUploading(false);
            }
          }}
        />
      </label>
      <ErrorNotice error={error} />
    </section>
  );
}

export function VoiceAudition({
  flow,
  busy,
  generate,
  renderCandidates,
}: {
  flow: Flow;
  busy: boolean;
  generate: (request: Request) => void;
  renderCandidates: (candidates: Candidate[]) => React.ReactNode;
}) {
  const [speaker, setSpeaker] = useState(
    flow.project.characters[0]?.id || "narrator",
  );
  const [index, setIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [error, setError] = useState<unknown>("");
  const player = useRef<HTMLAudioElement>(null);
  const character = flow.project.characters.find((c) => c.id === speaker);
  const clips = flow.scenes.flatMap((sc) =>
    (effectiveVideoInput(flow.project, flow.project.scenes.find(scene => scene.id === sc.id)!)?.sound_strategy === "model_audio" ? [] : (sc.segments || []))
      .filter((seg) => (seg.line.speaker_id || "narrator") === speaker)
      .map((seg) => ({
        ...seg,
        scene: flow.project.scenes.find((s) => s.id === sc.id)?.title,
        stale: sc.audio_stale,
      })),
  );
  const playlistKey = clips.map((x) => x.url).join("|");
  useEffect(() => {
    setPlaying(false);
    setIndex(0);
    setError("");
  }, [speaker, playlistKey]);
  useEffect(() => {
    if (playing)
      void player.current?.play().catch(() => {
        setPlaying(false);
        setError(uiCopy["播放失败，请点击播放重试。"]);
      });
    else player.current?.pause();
  }, [playing, index]);
  const clip = clips[index];
  const hasNative = flow.project.scenes.some(scene => scene.videoUrl && scene.creative?.video?.sound_strategy === "model_audio" && [...scene.creative?.shot?.lines || [], ...scene.creative?.shot?.narration || []].some(line => (line.speaker_id || "narrator") === speaker));
  const originalOnly =
    clips.length > 0 && clips.every((x) => x.strategy === "source-audio-v1");
  return (
    <section className="cs-voice-review">
      <div className="cs-voice-review-head">
        <div>
          <small>{uiCopy["声音一致性检查"]}</small>
          <h3>{uiCopy["把同一个人的台词，连起来听"]}</h3>
          <p className="helper">
            播放当前实际采用的声音，逐段对照人物音色与表演。原声视频包含片段内环境声。</p>
        </div>
        <select
          aria-label={uiCopy["试听角色"]}
          value={speaker}
          onChange={(e) => setSpeaker(e.target.value)}
        >
          {flow.project.characters.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
          <option value="narrator">{uiCopy["旁白"]}</option>
        </select>
      </div>
      {clips.length > 0 && <p>
        {originalOnly
          ? uiCopy["原声录音"]
          : character?.creative?.persona.voice_mode === "stable"
            ? uiCopy["稳定音色"]
            : uiCopy["逐句表演模式"]}{" "}
        · {clips.length} {uiCopy["句"]}</p>}
      <NativeAudition project={flow.project} speaker={speaker}/>
      <TechnicalDetails data={{ voice: character?.creative?.voice, clips }} />
      {clip ? (
        <>
          <audio
            ref={player}
            controls
            preload="none"
            src={clip.url}
            onPlay={() => setPlaying(true)}
            onPause={(e) => {
              if (!e.currentTarget.ended) setPlaying(false);
            }}
            onEnded={() => {
              if (index + 1 < clips.length) setIndex((i) => i + 1);
              else setPlaying(false);
            }}
            onError={() => {
              setPlaying(false);
              setError(uiCopy["音频暂时无法播放，请刷新后重试。"]);
            }}
          />
          <button
            className="btn"
            onClick={() => {
              if (player.current) player.current.currentTime = 0;
              setIndex(0);
              setPlaying(true);
            }}
          >
            {uiCopy["从头连续试听"]}</button>
        </>
      ) : !hasNative ? (
        <p className="helper">
          {uiCopy["还没有已选配音。请先生成分镜配音，试听候选后选用。"]}</p>
      ) : null}
      <ErrorNotice error={error} />
      <div className="cs-voice-lines">
        {clips.map((x, i) => (
          <button
            key={x.url}
            className={`cs-voice-line ${i === index ? "active" : ""}`}
            onClick={() => {
              setIndex(i);
              setPlaying(true);
            }}
          >
            <small>
              {i + 1} · {x.scene}
              {x.stale ? uiCopy[" · 需更新"] : ""} ·{" "}
              {x.strategy === "source-audio-v1"
                ? uiCopy["原声录音"]
                : x.strategy === "role-continuous-v1"
                  ? uiCopy["整段配音"]
                  : uiCopy["单句配音"]}
            </small>
            <span>{x.line.text}</span>
            <small>
              {x.strategy === "source-audio-v1" ? (
                uiCopy["原始表演 · 未变速"]
              ) : (
                <>
                  {uiCopy["语速"]}{x.speed?.toFixed(2) || "—"} ·{" "}
                  {emotionNames[x.emotion || x.line.emotion] ||
                    x.emotion ||
                    x.line.emotion}
                </>
              )}
            </small>
          </button>
        ))}
      </div>
      {character && !hasNative && (
        <>
          <button
            className="btn ai"
            disabled={
              busy ||
              !flow.capabilities.roleAudio ||
              !flow.project.creative?.shots_confirmed ||
              character.creative?.persona.voice_mode !== "stable" ||
              character.creative?.voice?.mode === "original"
            }
            onClick={() =>
              generate({
                operation: "role_audio",
                target: speaker,
                nonce: crypto.randomUUID(),
              })
            }
          >
            {uiCopy["整段生成"]}{character.name} {uiCopy["的全部台词"]}</button>
          <p className="helper">
            {flow.capabilities.roleAudio
              ? uiCopy["一次生成同角色台词，按时间戳切回各分镜；需先启用稳定音色并定稿。"]
              : uiCopy["当前模型未提供逐字时间戳，暂不支持整段生成后自动切分。请逐句生成，选用后在这里连续试听。"]}
          </p>
          {renderCandidates(
            flow.candidates.filter(
              (c) => c.kind === "role_audio" && c.entityId === speaker,
            ),
          )}
        </>
      )}
    </section>
  );
}

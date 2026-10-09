"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { useState, type ReactNode } from "react";
import { api, apiBase } from "@/lib/api";
import type { Candidate, Location, LocationState } from "@/lib/creative-types";
import { Modal } from "@/components/ui";
import { ActionBar, Field, TaskFeedback, type CreativeTask, useCreativeDraft } from "./shared";
import type { Request } from "./types";

export function LocationsWorkspace({ tasks, projectId, locations, states, busy, candidates, generate, renderCandidates, run, onNext, onStory, confirmedCount, totalCount }: {
  onNext: () => void; onStory: () => void; confirmedCount: number; totalCount: number;
  tasks: CreativeTask[]; projectId: string; locations: Location[]; states: Record<string, LocationState>; busy: boolean;
  candidates: Candidate[]; generate: (request: Request) => void; renderCandidates: (items: Candidate[]) => ReactNode;
  run: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [selected, setSelected] = useState(locations[0]?.id || "");
  return <section className="cw-cast cw-locations"><div className="cw-section-heading"><div><span className="cs-kicker">{uiCopy["ENVIRONMENT"]}</span><h2>场景素材</h2><p>{uiCopy["环境图不承载角色身份。固定地标、光照、色调与空间关系，按需要保存事件前后的状态。"]}</p></div></div>
    <nav className="location-selector" aria-label="地点选择">{locations.map(location => <button key={location.id} className={selected === location.id ? "active" : ""} onClick={() => setSelected(location.id)}>{states[location.id]?.image?.url && <img src={states[location.id].image!.url} alt=""/>}{location.name}</button>)}<button onClick={onStory}>在故事中编辑地点</button></nav>
    {locations.filter(location => location.id === (selected || locations[0]?.id)).map((location) => <LocationEditor key={`${location.id}-${states[location.id]?.version || 0}`} projectId={projectId} location={location} state={states[location.id]} tasks={tasks} busy={busy} candidates={candidates.filter(c => c.entityId === location.id && c.kind === "location_image")} generate={generate} renderCandidates={renderCandidates} run={run} />)}
    <ActionBar status={!locations.length ? uiCopy["请先确认故事中的地点"] : confirmedCount === totalCount ? uiCopy["全部地点环境已确认"] : formatCopy("还有 {0} 个地点未确认环境版本", totalCount - confirmedCount)}>
      {locations.length ? <button className="btn primary" disabled={busy || !locations.every(location => states[location.id]?.confirmed)} onClick={onNext}>{uiCopy["确认环境，进入分镜 →"]}</button> : <button className="btn" onClick={onStory}>{uiCopy["返回故事方案"]}</button>}
    </ActionBar>
  </section>;
}
function LocationEditor({ tasks, projectId, location, state, busy, candidates, generate, renderCandidates, run }: {
  tasks: CreativeTask[]; projectId: string; location: Location; state?: LocationState; busy: boolean; candidates: Candidate[];
  generate: (request: Request) => void; renderCandidates: (items: Candidate[]) => ReactNode; run: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [draft, setDraft] = useCreativeDraft(`cineai-location-${projectId}-${location.id}-${state?.version || 0}`, state?.location || location);
  const [source, setSource] = useState<string>(uiCopy["用户上传的无人环境图"]);
  const [environmentState, setEnvironmentState] = useState("");
  const [newStateName, setNewStateName] = useState("");
  const [pending, setPending] = useState<{ kind: "generate"; useReference?: boolean } | { kind: "upload"; file: File } | null>(null);
  const current = candidates.find(c => c.id === state?.image?.candidate_id);
  const dirty = JSON.stringify(draft) !== JSON.stringify(state?.location || location);
  const path = `/creative/projects/${projectId}/locations/${location.id}`;
  function proceed(action: NonNullable<typeof pending>, save = false) {
    void run(async () => {
      let version = state?.version || 0;
      if (save) {
        const saved = await api<LocationState>(path, "PATCH", { expected: version, data: draft });
        version = saved.version;
      }
      setPending(null);
      if (action.kind === "generate") {
        generate({ operation: "location_image", target: location.id, nonce: crypto.randomUUID(), use_reference: action.useReference, ...(environmentState ? { variant: environmentState } : {}) });
      } else {
        if (action.file.size > 5 * 1024 * 1024) throw new Error(uiCopy["环境图不能超过 5 MB"]);
        const image = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error(uiCopy["图片读取失败"])); reader.readAsDataURL(action.file); });
        await api(`${path}/reference`, "POST", { expected: version, data: { image, source, state: environmentState } });
      }
    });
  }
  function requestAction(action: NonNullable<typeof pending>) {
    if (dirty) setPending(action); else proceed(action);
  }
  const image = current?.url || state?.image?.url;
  const stateRefs = Object.entries(state?.states || {});
  return <article className="creative-shot location-editor">
    <header className="cw-panel__head">
      <h3>{draft.name} · {state?.confirmed ? uiCopy["环境版本已确认"] : uiCopy["待确认环境"]}</h3>
    </header>
    <TaskFeedback tasks={tasks} candidates={candidates} target={location.id} operations={["location_image"]} />
    <fieldset disabled={busy} className="location-layout">
      {/* 产物：已选环境图与事件状态图 */}
      <section className="cw-panel cw-panel--output location-media">
        <div className="cw-panel__head">
          <h3>{uiCopy["当前环境图"]}</h3>
          <small>{stateRefs.length ? formatCopy("{0} 个事件状态图", stateRefs.length) : uiCopy["仅基础环境"]}</small>
        </div>
        {image
          ? <img className="cw-location-image" src={image} alt={formatCopy("{0}已选环境", draft.name)} />
          : <p className="helper">{uiCopy["还没有选定环境图，可在下方生成或上传"]}</p>}
        {stateRefs.length ? <div className="cw-state-images">{stateRefs.map(([key, ref]) => (
          <figure key={key}>
            <img src={ref.url || `${apiBase}/api/assets/${ref.asset_id}?redirect=true`} alt={`${draft.name} ${key}`} />
            <figcaption>{key} {uiCopy["· 已选状态图"]}</figcaption>
          </figure>
        ))}</div> : null}
      </section>

      {/* 设定：环境本体，保存后才会影响生成 */}
      <section className="cw-panel cw-panel--setup">
        <div className="cw-panel__head">
          <h3>{uiCopy["环境设定"]}</h3>
          <small>{uiCopy["固定地标、光照、色调与空间关系"]}</small>
        </div>
        <div className="creative-grid">{([['landmarks', uiCopy["固定地标"]], ['lighting', uiCopy["光照"]], ['palette', uiCopy["色调"]]] as const).map(([key, label]) => <Field key={key} label={label} value={draft[key] || ""} large onChange={value => setDraft({ ...draft, [key]: value })} />)}</div>
        <details><summary>地点描述、空间关系与事件状态</summary>
          {([['name', uiCopy["地点名称"]], ['description', uiCopy["无人环境描述"]], ['spatial_notes', uiCopy["人物空间关系与左右方向"]]] as const).map(([key, label]) => <Field key={key} label={label} value={draft[key] || ""} large={key !== "name"} onChange={value => setDraft({ ...draft, [key]: value })} />)}
          {Object.entries(draft.states || {}).map(([key, value]) => <Field key={key} label={key} value={value} onChange={description => setDraft({ ...draft, states: { ...draft.states, [key]: description } })} />)}
          <Field label={uiCopy["新状态名称（按需，例如雨停后）"]} value={newStateName} onChange={setNewStateName} />
          <button className="btn" disabled={!newStateName.trim()} onClick={() => { setDraft({ ...draft, states: { ...draft.states, [newStateName]: uiCopy["请填写可见环境变化"] } }); setNewStateName(""); }}>{uiCopy["添加环境状态"]}</button>
        </details>
        {dirty && <p className="creative-warning">{uiCopy["环境设定有未保存的修改"]}</p>}
        <div className="cw-panel__footer">
          <button className="btn primary" disabled={!dirty} onClick={() => void run(() => api(path, "PATCH", { expected: state?.version || 0, data: draft }))}>{uiCopy["保存场景设定"]}</button>
        </div>
      </section>

      {/* 产物：候选生成与上传 */}
      <section className="cw-panel cw-panel--output location-candidates">
        <div className="cw-panel__head">
          <h3>{uiCopy["候选图与上传"]}</h3>
          <small>{candidates.length ? formatCopy("{0} 个候选图", candidates.length) : uiCopy["暂无候选图"]}</small>
        </div>
        <div className="creative-actions">
          <label className="creative-field">{uiCopy["本次素材状态"]}<select value={environmentState} onChange={e => setEnvironmentState(e.target.value)}><option value="">{uiCopy["基础环境"]}</option>{Object.keys(draft.states || {}).map(key => <option key={key}>{key}</option>)}</select></label>
          <button className="btn cw-ai-button" onClick={() => requestAction({ kind: "generate" })}>{image ? "重新生成场景图" : "AI生成场景图"}</button>
        </div>
        <button className="btn" disabled={!state?.image} onClick={() => requestAction({ kind: "generate", useReference: true })}>根据参考图生成场景</button>
        <p className="helper">上传参考图并选用后，可保持地标与空间关系生成新的场景图。</p>
        <Field label={uiCopy["素材来源"]} value={source} onChange={setSource} />
        <label className="creative-field cw-reference-upload"><span>上传场景参考图</span><small>PNG / JPG / WebP，最多 5 MB</small><input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => {
          const file = e.target.files?.[0]; e.target.value = ""; if (file) requestAction({ kind: "upload", file });
        }} /></label>
        {renderCandidates(candidates)}
      </section>

      <div className="location-confirm">
        <p>{state?.confirmed ? "当前场景已选定，可继续制作分镜" : "选用满意的场景图后，保存为本片场景"}</p>
        <button className="btn primary" disabled={dirty || !state?.image || state?.confirmed} onClick={() => void run(() => api(`${path}/confirm`, "POST", { expected: state?.version || 0, data: {} }))}>选定当前场景</button>
      </div>
    </fieldset>
    {pending && <Modal title={uiCopy["环境设定尚未保存。是否保存后继续？"]} onClose={() => setPending(null)}><div className="creative-actions"><button className="btn" onClick={() => setPending(null)}>{uiCopy["取消"]}</button><button className="btn primary" disabled={busy} onClick={() => proceed(pending, true)}>{uiCopy["保存并继续"]}</button></div></Modal>}
  </article>;
}

"use client";
import { StageNavigation } from "./creative/StageNavigation";
import { ShotProductionPanel } from "./creative/ShotProductionPanel";
import { NarrowScreenNotice } from "./creative/NarrowScreenNotice";
import { copy } from "./creative/copy";
import { ReadinessRows } from "./creative/ReadinessRows";
import { CostQuote, type Estimate } from "./creative/CostQuote";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Trash2, UserRound, ArrowUpRight, Volume2 } from "lucide-react";
import { Modal } from "@/components/ui";
import { ReviewPlayer } from "./creative/ReviewPlayer";
import { CreativeStudio } from "./CreativeStudio";
import { LocationsWorkspace } from "./creative/LocationsWorkspace";
import { StoryWorkspace } from "./creative/StoryWorkspace";
import { CharacterAsset } from "./creative/CharacterWorkspace";
import { Narrator, ShotEditor, VoiceAudition } from "./creative/SceneTools";
import { effectiveVideoInput } from "@/lib/production";
import { VideoGeneration } from "./creative/VideoGeneration";
import { VideoCorrection } from "./creative/VideoCorrection";
import { CandidateList } from "./creative/CandidateList";
import { TasksWorkspace } from "./creative/TasksWorkspace";
import { HistoryWorkspace } from "./creative/HistoryWorkspace";
import {
  ActionBar,
  WorkspaceTools,
  TaskFeedback,
  blankPersona,
  operationNames,
} from "./creative/shared";
import { useRouter } from "next/navigation";
import { api, apiBase, isRateLimited } from "@/lib/api";
import { refreshRemote, subscribeRemoteChanges } from "@/lib/remote-store";
import { createReadObserver } from "@/lib/read-observer";
import { useProject, useStore } from "@/lib/store";
import type { Project } from "@/lib/types";
import type { Persona, Candidate } from "@/lib/creative-types";

import type { Flow, Request } from "./creative/types";
export function CreativeNew() {
  const initial = useStore((s) => s.idea),
    [idea, setIdea] = useState(initial),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>("");
  const router = useRouter();
  async function create() {
    setBusy(true);
    try {
      const p = await api<Project>("/projects", "POST", {
        name: idea.slice(0, 30),
        description: idea,
      });
      await api(`/creative/projects/${p.id}/start`, "POST");
      useStore.setState({ activeId: p.id });
      await refreshRemote();
      router.push(`/studio?project=${p.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="creative-page new-project-page">
      <section className="new-project-form">
        <h1>新建项目</h1><p>先写下你的故事想法。</p>
        <label className="creative-field"><span>故事创意</span><textarea aria-label={uiCopy["一句创意"]} rows={8} maxLength={4000} value={idea} onChange={e => setIdea(e.target.value)} placeholder="故事发生在哪里，主角想做什么，又会遇到什么变化？" /></label>
        <small className="muted">{idea.length} / 4000</small>
        <details><summary>可选设置</summary><p>创建后可在故事工作区设置画幅、目标时长、镜头数和视觉风格。保存后再生成候选。</p></details>
        <ol className="new-project-stages">{["故事", "角色与声音", "场景", "分镜", "成片"].map((name, i) => <li key={name}><b>{String(i + 1).padStart(2, "0")}</b>{name}</li>)}</ol>
        <button className="btn primary" disabled={busy || !idea.trim()} onClick={() => void create()}>{busy ? "正在创建…" : "创建项目"}</button>
        <p className="helper">创建草稿不调用模型，生成前确认范围与费用。</p><ErrorNotice error={error}/>
      </section>
      <aside className="new-project-next"><h2>接下来</h2><ol><li><b>创建草稿</b><p>保存你的想法，随时继续编辑。</p></li><li><b>生成故事候选</b><p>每次生成一个方案。可再次构思，比较后明确选用。</p></li><li><b>确认后继续</b><p>故事 → 角色与声音 → 场景 → 分镜 → 成片。</p></li></ol></aside>
    </main>
  );
}
export function CreativeEntry({
  charactersOnly = false,
}: {
  charactersOnly?: boolean;
}) {
  const p = useProject();
  return p ? (
    <CreativeWorkbench
      key={p.id}
      projectId={p.id}
      charactersOnly={charactersOnly}
    />
  ) : (
    <CreativeNew />
  );
}
export function CreativeWorkbench({
  projectId,
  charactersOnly = false,
}: {
  projectId: string;
  charactersOnly?: boolean;
}) {
  const workspaceRef = useRef<HTMLElement>(null);
  const [flow, setFlow] = useState<Flow | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>("");
  const sharedTasks = useStore(s => s.tasks);
  const tasks = sharedTasks.filter(task => task.projectId === projectId);
  const loadInFlight = useRef<Promise<void> | null>(null);
  const [tab, setTab] = useState(() => { if (charactersOnly) return "characters"; if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("scene")) return "storyboard"; return typeof window !== "undefined" && ["plan", "characters", "locations", "storyboard", "generation"].includes(new URLSearchParams(window.location.search).get("stage") || "") ? new URLSearchParams(window.location.search).get("stage")! : "plan"; }),
    [quote, setQuote] = useState<{
      request: Request;
      calls: number;
      estimateCents: number | null;
      label: string;
      note: string;
      targets: Estimate["targets"];
    } | null>(null);
  const [costConsent, setCostConsent] = useState(false);
  const [editingCharacter, setEditingCharacter] = useState<string | null>(null);
  const [deletingCharacter, setDeletingCharacter] = useState<Project["characters"][number] | null>(null);
  const [characterSection, setCharacterSection] = useState("image");
  const [characterDirty, setCharacterDirty] = useState<Record<string, boolean>>(
    {},
  );
  const onCharacterDirty = useCallback(
    (id: string, dirty: boolean) =>
      setCharacterDirty((old) =>
        old[id] === dirty ? old : { ...old, [id]: dirty },
      ),
    [],
  );
  const [aux, setAux] = useState<"history" | "tasks" | null>(null);
  const [assetPanel, setAssetPanel] = useState<string | null>(null);
  const [assetKind, setAssetKind] = useState<"shot_image" | "shot_audio">("shot_image");
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [library, setLibrary] = useState<
    { id: string; name: string; image: string }[]
  >([]);
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("stage", tab);
    if (tab !== "storyboard") url.searchParams.delete("scene");
    window.history.replaceState(window.history.state, "", url);
  }, [tab]);
  useEffect(() => {
    workspaceRef.current?.scrollTo({ top: 0 });
  }, [tab, aux, editingCharacter]);
  const load = useCallback(async (signal?: AbortSignal) => {
    if (loadInFlight.current) return loadInFlight.current;
    const work = api<Flow>(`/creative/projects/${projectId}`, "GET", undefined, signal).then(f => { if (!signal?.aborted) setFlow(f); });
    loadInFlight.current = work;
    try { await work; } finally { if (loadInFlight.current === work) loadInFlight.current = null; }
  }, [projectId]);
  useEffect(() => {
    const observer = createReadObserver(load, e => {
      if (!isRateLimited(e)) setError(e);
    }, { intervalMs: 30000 });
    const unsubscribe = subscribeRemoteChanges(projectId, observer.request);
    return () => { unsubscribe(); observer.stop(); };
  }, [load]);
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
      await refreshRemote();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const path = `/creative/projects/${projectId}`;
  async function prepare(
    request: Request,
    persona?: Persona,
    expected?: number,
  ) {
    if (request.operation === "storyboard") request = { ...request, auto_apply: true };
    await run(async () => {
      if (persona && request.target) {
        await api(`/creative/characters/${request.target}`, "PATCH", {
          expected,
          data: persona,
        });
      }
      const q = await api<Omit<NonNullable<typeof quote>, "request">>(
        request.operation === "batch"
          ? `${path}/batch/estimate`
          : `${path}/estimate`,
        "POST",
        request.operation === "batch" ? undefined : request,
      );
      setCostConsent(false);
      setQuote({ ...q, request });
    });
  }
  if (!flow)
    return (
      <main className="creative-page">
        {error ? <ErrorNotice error={error} /> : uiCopy["正在恢复创作阶段与候选资产…"]}
      </main>
    );
  const p = flow.project,
    st = p.creative;
  if (!st)
    return (
      <main className="creative-page">
        <span className="cw-project-title">{p.name}</span>
        <p>
          {uiCopy["旧项目的画面、声音、任务和成片保留。启用新流程后，请补全故事方案并明确绑定每句台词的发言人；不会自动调用付费服务。"]}</p>
        <button
          className="btn primary"
          onClick={() => void run(() => api(`${path}/start`, "POST"))}
        >
          {uiCopy["补全新创作流程"]}</button>
      </main>
    );
  function select(c: Candidate) {
    let expected = st!.version;
    if (c.kind === "location_image") expected = st!.locations?.[c.entityId]?.version || 0;
    else if (c.kind.startsWith("shot_") || c.kind === "video_correction")
      expected =
        p.scenes.find((s) => s.id === c.entityId)?.creative?.version || 0;
    else if (!["plan", "storyboard"].includes(c.kind))
      expected =
        p.characters.find((x) => x.id === c.entityId)?.creative?.version || 0;
    void run(() =>
      api(`${path}/select`, "POST", { candidate_id: c.id, expected }),
    );
  }
  const generate = (request: Request) => void prepare(request);
  const confirm = (stage: string) =>
    void run(async () => {
      await api(`${path}/confirm/${stage}`, "POST", {
        expected: st.version,
        data: stage === "cast" ? { finalize_characters: true } : {},
      });
      setTab(
        stage === "plan"
          ? "characters"
          : stage === "cast"
            ? "locations"
            : "storyboard",
      );
    });
  const candidates = (kind: string, target?: string) =>
    flow.candidates.filter(
      (c) => c.kind === kind && (!target || c.entityId === target),
    );
  async function repairCandidate(candidate: Candidate, value: unknown) {
    setBusy(true); setError("");
    try {
      const result = await api<{ candidateId: string; parentCandidateId: string }>(`${path}/candidates/${candidate.id}`, "PATCH", { expected: st!.version, data: value });
      await load(); await refreshRemote();
      return result;
    } catch (e) {
      setError(e);
      throw e;
    } finally { setBusy(false); }
  }
  async function recoverCandidate(candidate: Candidate) {
    setBusy(true); setError("");
    try {
      const result = await api<{ candidateId: string; parentCandidateId: string; ready: boolean }>(`${path}/candidates/${candidate.id}/repair`, "POST", { expected: st!.version, data: {} });
      await load(); await refreshRemote();
      return result;
    } catch (e) {
      setError(e);
      throw e;
    } finally { setBusy(false); }
  }
  const candidateCards = (items: Candidate[]) => (
    <><ErrorNotice error={error} /><CandidateList items={items} project={p} busy={busy} onSelect={select} onRepair={repairCandidate} onRecover={recoverCandidate} onAiRepair={candidate => generate({ operation: "storyboard", target: candidate.id, nonce: crypto.randomUUID() })} /></>
  );
  return (
    <main
      ref={workspaceRef}
      className={`creative-page creative-workbench ${tab === "storyboard" && !aux ? "cs-mode" : ""}`}
    >
      <WorkspaceTools active={aux} onSelect={value => setAux(aux === value ? null : value)} />
      <NarrowScreenNotice />
      <StageNavigation flow={flow} current={aux ? undefined : tab} onSelect={key => { setTab(key); setAux(null); }} />
      <ErrorNotice error={error} />
      {busy && <p role="status">{uiCopy["正在保存或检查调用范围…"]}</p>}
      <div hidden={tab !== "plan" || !!aux}>
        <StoryWorkspace
          project={p}
          candidates={candidates("plan")}
          busy={busy}
          generate={() =>
            generate({ operation: "plan", nonce: crypto.randomUUID() })
          }
          select={select}
          reload={load}
          onNext={() => setTab("characters")}
          tasks={
            <TaskFeedback
              project={p}
            tasks={tasks}
              candidates={flow.candidates}
              operations={["plan"]}
            />
          }
        />
      </div>
      {tab === "locations" && !aux && <LocationsWorkspace tasks={tasks} projectId={p.id} locations={st.plan?.locations || []} states={st.locations || {}} busy={busy} candidates={flow.candidates} generate={generate} renderCandidates={candidateCards} run={run} onNext={() => setTab("storyboard")} onStory={() => setTab("plan")} confirmedCount={(st.plan?.locations || []).filter(location => st.locations?.[location.id]?.confirmed).length} totalCount={st.plan?.locations.length || 0} />}
      {tab === "characters" && !aux && (
        <section className={`cw-cast ${editingCharacter ? "cw-cast--focused" : ""}`}>
          <div className="creative-actions">
            <h2>角色与声音</h2>
            <button
              className="btn"
              onClick={() =>
                void run(async () => {
                  const updated = await api<Project>(
                    `${path}/characters`,
                    "POST",
                    blankPersona(),
                  );
                  const created = updated.characters.find(
                    (c) => !p.characters.some((old) => old.id === c.id),
                  );
                  if (created) setEditingCharacter(created.id);
                })
              }
            >
              {uiCopy["独立新建角色"]}</button>
            <button
              className="btn"
              onClick={() =>
                void run(async () => {
                  setLibrary(await api("/creative/library"));
                  setLibraryOpen(true);
                })
              }
            >
              {uiCopy["从跨项目角色库复用"]}</button>
          </div>
          <p>
            {p.characters.length} {uiCopy["位角色 ·"]}{" "}
            {(flow.readiness || []).filter((c) => !c.image).length} {uiCopy["位待选形象 ·"]}{" "}
            {(flow.readiness || []).filter((c) => !c.voice).length}{" "}
            {uiCopy["位待选声音。完成后统一确认用于分镜。"]}</p>
          {!editingCharacter && (
            <div className="cs-character-grid cw-cast-grid">
              {p.characters.map((c) => {
                const ready = flow.readiness?.find((r) => r.id === c.id);
                return (
                  <article className="cast-card" key={c.id}>
                    <button className="cast-card__portrait" aria-label={`编辑${c.name}的形象`} onClick={() => { setCharacterSection("image"); setEditingCharacter(c.id); }}>
                      {c.image ? <img src={c.image} alt={c.name} /> : <div className="cast-card__placeholder"><UserRound size={44} strokeWidth={1} /><span>等待角色形象</span></div>}
                      <span className={`cast-card__badge ${c.creative?.confirmed ? "is-ready" : ""}`}>{c.creative?.confirmed ? "已定稿" : "待完善"}</span>
                      <span className="cast-card__image-action">编辑形象 <ArrowUpRight size={14} /></span>
                    </button>
                    <div className="cast-card__body">
                      <h3>{c.name}</h3>
                      <p className="cast-card__identity">{c.creative?.persona.identity || c.description || "添加人物设定，让角色鲜活起来"}</p>
                      <div className="cast-card__status"><span className={ready?.image ? "is-ready" : ""}><i />{ready?.image ? "形象就绪" : "待选形象"}</span><span className={ready?.voice || c.creative?.persona.role_kind === "background" ? "is-ready" : ""}><i />{c.creative?.persona.role_kind === "background" ? "无需配音" : ready?.voice ? "声音就绪" : "待选声音"}</span></div>
                      <div className="cast-card__voice"><div><Volume2 size={14}/><span>{c.creative?.persona.voice_description || "尚未设置角色声音"}</span></div>{c.creative?.voice?.url && <audio aria-label={`${c.name}的声音试听`} controls preload="none" src={c.creative.voice.url} />}</div>
                    </div>
                    <footer className="cast-card__footer">
                      <button className="cast-card__edit" onClick={() => { setCharacterSection("persona"); setEditingCharacter(c.id); }}>编辑角色 <ArrowUpRight size={14}/></button>
                      <button className="cast-card__voice-edit" onClick={() => { setCharacterSection("voice"); setEditingCharacter(c.id); }}>编辑声音</button>
                      <button className="cast-card__delete" aria-label={`删除角色${c.name}`} title="删除角色" disabled={busy} onClick={() => { setError(""); setDeletingCharacter(c); }}><Trash2 size={16}/></button>
                    </footer>
                  </article>
                );
              })}
            </div>
          )}
          {editingCharacter && p.characters.length > 1 && (
            <nav className="cw-cast-switch" aria-label={uiCopy["切换本片角色"]}>
              {p.characters.map((c) => (
                <button
                  key={c.id}
                  className={editingCharacter === c.id ? "active" : ""}
                  onClick={() => setEditingCharacter(c.id)}
                >
                  {c.image && <img src={c.image} alt="" />}
                  <span>
                    {c.name}
                    <small>
                      {characterDirty[c.id]
                        ? uiCopy["有本地编辑"]
                        : c.creative?.confirmed
                          ? uiCopy["已定稿"]
                          : uiCopy["待确认"]}
                    </small>
                  </span>
                </button>
              ))}
            </nav>
          )}
          {p.characters
            .filter((c) => c.id === editingCharacter)
            .map((c) => (
              <div className="cw-focused-character" key={c.id}>
                <ErrorNotice error={error} />
                <CharacterAsset
                  project={p}
                  initialTab={characterSection}
                  ready={flow.readiness?.find((r) => r.id === c.id)}
                  onBack={() => setEditingCharacter(null)}
                  onDirty={onCharacterDirty}
                  tasks={tasks}
                  capabilities={flow.capabilities}
                  key={`${c.id}-${c.creative?.version}`}
                  id={c.id}
                  state={c.creative}
                  image={c.image}
                  busy={busy}
                  candidates={flow.candidates.filter(
                    (x) => x.entityId === c.id,
                  )}
                  renderCandidates={candidateCards}
                  generate={(request, persona) =>
                    void prepare(
                      request,
                      JSON.stringify(persona) ===
                        JSON.stringify(c.creative?.persona)
                        ? undefined
                        : persona,
                      c.creative?.version || 0,
                    )
                  }
                  save={(data) =>
                    void run(() =>
                      api(`/creative/characters/${c.id}`, "PATCH", {
                        expected: c.creative?.version || 0,
                        data,
                      }),
                    )
                  }
                  uploadVoice={(file, original = false) =>
                    void run(async () => {
                      const body = new FormData();
                      body.append("file", file);
                      body.append("expected", String(c.creative?.version || 0));
                      const response = await fetch(
                        `${apiBase}/api/creative/characters/${c.id}/${original ? "voice-source" : "voice-reference"}`,
                        { method: "POST", body },
                      );
                      const result = await response.json();
                      if (!response.ok)
                        throw new Error(
                          result.error?.message || uiCopy["声音参考上传失败"],
                        );
                    })
                  }
                  action={(op, data = {}) =>
                    void run(() =>
                      api(`/creative/characters/${c.id}/${op}`, "POST", {
                        expected: c.creative?.version || 0,
                        data,
                      }),
                    )
                  }
                />
              </div>
            ))}
          {!editingCharacter && (
            <ActionBar
              status={
                <>
                  <b>
                    {st.cast_confirmed
                      ? uiCopy["角色阶段已确认"]
                      : formatCopy("{0} / {1} 位角色形象与声音就绪", (flow.readiness || []).filter((r) => r.image && r.voice).length, p.characters.length)}
                  </b>
                  <small>
                    {!st.plan_confirmed ? (
                      <button onClick={() => setTab("plan")}>
                        {uiCopy["请先确认故事"]}</button>
                    ) : (
                      p.characters
                        .filter(
                          (c) =>
                            characterDirty[c.id] ||
                            !flow.readiness?.find(
                              (r) => r.id === c.id && r.image && r.voice,
                            ),
                        )
                        .map((c) => (
                          <button
                            key={c.id}
                            onClick={() => setEditingCharacter(c.id)}
                          >
                            {c.name}：
                            {characterDirty[c.id] ? uiCopy["保存编辑"] : uiCopy["处理缺失项"]}
                          </button>
                        ))
                    )}
                  </small>
                </>
              }
            >
              <button
                className="btn primary"
                disabled={
                  busy ||
                  !st.plan_confirmed ||
                  !p.characters.length ||
                  Object.values(characterDirty).some(Boolean) ||
                  (flow.readiness || []).some((r) => !r.image || !r.voice)
                }
                onClick={() => confirm("cast")}
              >
                {uiCopy["确认角色，进入环境 →"]}</button>
            </ActionBar>
          )}
        </section>
      )}
      {tab === "storyboard" && !aux && (
        <CreativeStudio
          project={p}
          statuses={flow.scenes}
          pacing={flow.pacing}
          videoEnabled={flow.capabilities.videoGeneration}
          reload={load}
          busy={busy}
          onGenerate={(fresh) =>
            generate({
              operation: "storyboard",
              ...(fresh ? { nonce: crypto.randomUUID() } : {}),
            })
          }
          onConfirm={() => confirm("shots")}
          onPhase={setTab}
          candidates={candidateCards(candidates("storyboard"))}
          check={
            <>
              <VoiceAudition
                key={p.id}
                flow={flow}
                busy={busy}
                generate={generate}
                renderCandidates={candidateCards}
              />
              <div className="creative-check">
                <h3>{uiCopy["合成前检查"]}</h3>
                {flow.issues.length ? (
                  <ul>
                    {flow.issues.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                ) : (
                  <p>
                    {uiCopy["结构与资产检查通过。外观与表演请在预览中确认。"]}</p>
                )}
                <p>
                  {uiCopy["本镜最多使用"]}{flow.capabilities.maxImageReferences}{" "}
                  {uiCopy["张参考图。"]}</p>
                <Link className="btn" href="/export">
                  {uiCopy["前往 MP4 导出"]}</Link>
              </div>
              <Narrator
                key={st.narrator.voice_id}
                voice={st.narrator.voice_id}
                save={(voice_id) =>
                  void run(() =>
                    api(`${path}/narrator`, "PATCH", {
                      expected: st.version,
                      data: { voice_id, speed: 1 },
                    }),
                  )
                }
              />
            </>
          }
          renderInspector={(sc) => {
            const status = flow.scenes.find((x) => x.id === sc.id);
            return <ShotProductionPanel key={sc.id} project={p} scene={sc} status={status} busy={busy}
              candidates={flow.candidates} tasks={tasks} videoEnabled={flow.capabilities.videoGeneration}
              structureReady={flow.workflowReadiness.structure_ready} generate={generate}
              onConfirm={() => confirm("shots")} onPhase={setTab} reload={load}
              onAssets={kind => { setAssetKind(kind); setAssetPanel(sc.id); }}
              error={<ErrorNotice error={error} />}
              editor={<ShotEditor
                  projectId={p.id}
                  sceneId={sc.id}
                  scenes={p.scenes}
                  locations={st.locations || {}}
                  candidates={flow.candidates}
                  draftKey={`cineai-shot-${sc.id}-${sc.creative?.version || 0}`}
                  key={`${sc.id}-${sc.creative?.version}`}
                  state={sc.creative}
                  characters={p.characters}
                  plan={st.plan}
                  title={sc.title}
                  save={(data) =>
                    void run(() =>
                      api(`/creative/scenes/${sc.id}`, "PATCH", {
                        expected: sc.creative?.version || 0,
                        data,
                      }),
                    )
                  }
                />}
              correction={<VideoCorrection key={`correction-${sc.id}-${sc.creative?.version}`} project={p} scene={sc} candidates={candidates("video_correction", sc.id)} busy={busy} reload={load} onSelect={select} />}
              assets={<>{assetPanel === sc.id && (
                  <Modal
                    wide
                    title={`${sc.title} · ${assetKind === "shot_image" ? "画面候选" : "配音候选"}`}
                    onClose={() => setAssetPanel(null)}
                  >
                    <div className="cs-dialog-body">
                      {assetKind === "shot_image" && <label className="creative-field">
                        {uiCopy["复用本项目已有画面（先保存为候选）"]}<select
                          value=""
                          onChange={(e) => {
                            if (e.target.value)
                              void run(() =>
                                api(
                                  `/creative/scenes/${sc.id}/reference`,
                                  "POST",
                                  {
                                    expected: sc.creative?.version || 0,
                                    data: { image: e.target.value },
                                  },
                                ),
                              );
                          }}
                        >
                          <option value="">{uiCopy["选择已保存图片，不调用模型"]}</option>
                          {p.scenes
                            .filter((x) => x.image && x.id !== sc.id)
                            .map((x) => (
                              <option key={x.id} value={x.image}>
                                {x.title}
                              </option>
                            ))}
                        </select>
                      </label>}
                      {candidateCards(candidates(assetKind, sc.id))}
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          void run(() =>
                            api(`/creative/scenes/${sc.id}/archive`, "POST", {
                              expected: sc.creative?.version || 0,
                              data: {},
                            }),
                          )
                        }
                      >
                        {uiCopy["归档此镜（保留历史）"]}</button>
                    </div>
                  </Modal>
                )}</>}
              audioTools={<><p className="helper">按句试听已选声音，可只重录或导入需要调整的一句。</p>{sc.creative?.shot &&
                  [
                    ...sc.creative.shot.lines,
                    ...sc.creative.shot.narration,
                  ].map((line) => (
                    <label className="btn" key={`upload-${line.id}`}>
                      {uiCopy["导入这句录音："]}{line.text.slice(0, 20)}
                      <input
                        type="file"
                        accept="audio/*"
                        hidden
                        disabled={busy || !st.shots_confirmed}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          e.target.value = "";
                          if (!file) return;
                          void run(async () => {
                            const body = new FormData();
                            body.append("file", file);
                            body.append("line_id", line.id);
                            body.append(
                              "expected",
                              String(sc.creative?.version || 0),
                            );
                            const response = await fetch(
                              `${apiBase}/api/creative/scenes/${sc.id}/line-audio`,
                              { method: "POST", body },
                            );
                            const result = await response.json();
                            if (!response.ok)
                              throw new Error(
                                result.error?.message || uiCopy["台词录音导入失败"],
                              );
                          });
                        }}
                      />
                    </label>
                  ))}
                {status?.segments?.map((x, i) => (
                  <div className="creative-audio" key={i}>
                    <span>
                      {x.line.speaker_id
                        ? p.characters.find((c) => c.id === x.line.speaker_id)
                            ?.name
                        : uiCopy["独立旁白"]}{" "}
                      ·{" "}
                      {x.strategy === "source-audio-v1"
                        ? uiCopy["原声录音"]
                        : uiCopy["合成配音"]}{" "}
                      · {(x.start_ms / 1000).toFixed(2)}{uiCopy["s · "]}{x.line.text}
                    </span>
                    <audio controls src={x.url} />
                    <button
                      className="btn"
                      disabled={
                        busy || !st.shots_confirmed || status.audio_stale
                      }
                      onClick={() =>
                        generate({
                          operation: "shot_audio",
                          target: sc.id,
                          regenerate_line_ids: [x.line.id],
                          nonce: crypto.randomUUID(),
                        })
                      }
                    >
                      {uiCopy["重录这一句 · 保留其他声音"]}</button>
                  </div>
                ))}</>}
            />;
          }}
        />
      )}
      {tab === "generation" && !aux && (
        <section className="cw-delivery">
          <div className="cw-section-heading">
            <div>
              <span className="cs-kicker">{uiCopy["05 预览与导出"]}</span>
              <h2>成片检查</h2>
            </div>
            {p.scenes.some(scene => { const input = effectiveVideoInput(p, scene); return (!input?.mode || input.mode.startsWith("first")) || input.sound_strategy !== "model_audio"; }) && <button
              className="btn"
              disabled={busy || !st.shots_confirmed}
              onClick={() => generate({ operation: "batch" })}
            >
              {uiCopy["生成缺失画面与配音 · 先估算"]}</button>}
          </div>
          <TaskFeedback
            project={p}
            tasks={tasks}
            candidates={flow.candidates}
            operations={["shot_image", "shot_audio", "role_audio"]}
          />
          <div className="cw-delivery-layout">
            <div className="cw-delivery-media">
              <ReviewPlayer project={p} />
              <div className="cw-delivery-shots">
              {p.scenes.map((sc, i) => (
                <button
                  key={sc.id}
                  onClick={() => {
                    useStore.setState({ sceneId: sc.id });
                    setTab("storyboard");
                  }}
                >
                  {sc.image && <img src={sc.image} alt={sc.title} />}
                  <span>
                    {String(i + 1).padStart(2, "0")} · {sc.title}
                  </span>
                </button>
              ))}
            </div>
            </div>
            <div>
              <h3>{uiCopy["就绪检查"]}</h3>
              {flow.issues.length ? (
                <ul>
                  {flow.issues.map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>
              ) : (
                <p>{uiCopy["结构与资产检查通过，可进入带声预览和导出。"]}</p>
              )}
              <p>{"结构就绪后，可以预览画面与声音，生成视频并导出作品。"}</p>
              <ReadinessRows locationDone={(st.plan?.locations || []).filter(location => st.locations?.[location.id]?.confirmed).length} locationTotal={st.plan?.locations.length || 0} previewConfirmed={flow.workflowReadiness.preview_confirmed} accepted={p.scenes.filter(scene => !!scene.videoUrl).length} total={p.scenes.length} />
          <VoiceAudition
            key={p.id}
            flow={flow}
            busy={busy}
            generate={generate}
            renderCandidates={candidateCards}
          />
            </div>
          </div>
          <ActionBar
            status={
              <>
                <b>
                  {flow.issues.length
                    ? formatCopy("{0} 项待处理", flow.issues.length)
                    : flow.workflowReadiness.media_complete ? "视频已采用，待全片回放检查" : uiCopy["结构就绪，可预演与草稿导出"]}
                </b>
                <small>{uiCopy["进入导出页可预览配音、字幕并检查成片"]}</small>
              </>
            }
          >
            <button className="btn" onClick={() => setTab("storyboard")}>
              {uiCopy["返回分镜处理"]}</button>
            <Link className="btn primary" href="/export">
              {uiCopy["打开预览与导出 →"]}</Link>
          </ActionBar>
        </section>
      )}
      {aux === "history" && (
        <HistoryWorkspace projectId={p.id} version={st.version} reload={load} />
      )}
      {aux === "tasks" && <TasksWorkspace project={p} />}
      {deletingCharacter && <Modal title={`删除角色「${deletingCharacter.name}」`} onClose={() => { if (!busy) setDeletingCharacter(null); }}>
        <div className="cs-dialog-body">
          {p.scenes.some(scene => scene.creative?.shot?.cast[deletingCharacter.id] || [...scene.creative?.shot?.lines || [], ...scene.creative?.shot?.narration || []].some(line => line.speaker_id === deletingCharacter.id)) ? <><p>该角色正在被分镜使用，请先在分镜中移除其出场和台词绑定，再删除角色。</p><button className="btn primary" onClick={() => { setDeletingCharacter(null); setTab("storyboard"); }}>前往分镜处理</button></> : <><p>删除后，该角色将从本片角色列表中移除。此操作无法撤销。</p><ErrorNotice error={error}/><div className="creative-actions"><button className="btn" disabled={busy} onClick={() => setDeletingCharacter(null)}>取消</button><button className="btn cast-delete-confirm" disabled={busy} onClick={() => void run(async () => { await api(`/characters/${deletingCharacter.id}`, "DELETE"); setDeletingCharacter(null); })}>{busy ? "正在删除…" : "删除角色"}</button></div></>}
        </div>
      </Modal>}
      {libraryOpen && (
        <Modal
          wide
          title={uiCopy["跨项目角色库 · 固定版本复用"]}
          onClose={() => setLibraryOpen(false)}
        >
          <div className="cw-sync">
            <p>
              {uiCopy["这是跨项目保存的角色版本。复用会在本片创建独立角色，原库中的人物与媒体不被修改。"]}</p>
            {library.length ? (
              <div className="cs-character-grid">
                {library.map((x) => (
                  <article className="cs-character-card" key={x.id}>
                    {x.image && <img src={x.image} alt={x.name} />}
                    <div>
                      <h3>{x.name}</h3>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await api(`${path}/reuse/${x.id}`, "POST");
                            setLibraryOpen(false);
                          })
                        }
                      >
                        {uiCopy["复用到本片"]}</button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p>
                {"角色库暂时为空。角色定稿后，可在角色编辑页保存到角色库。"}</p>
            )}
          </div>
        </Modal>
      )}
      {quote && (
        <Modal title={uiCopy["生成范围与费用"]} onClose={() => setQuote(null)}>
          <section className="creative-quote">
            <ErrorNotice error={error} />
            <h2>{operationNames[quote.request.operation]}</h2>
            <CostQuote quote={quote} consent={costConsent} onConsent={setCostConsent} busy={busy} onBack={() => setQuote(null)} onConfirm={() => void run(async () => {
              await api(quote.request.operation === "batch" ? `${path}/batch/generate` : `${path}/generate`, "POST", quote.request.operation === "batch" ? undefined : quote.request);
              setQuote(null);
            })} />
          </section>
        </Modal>
      )}
    </main>
  );
}

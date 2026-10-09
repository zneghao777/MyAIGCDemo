"use client";
import { Sparkles } from "lucide-react";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import type { Candidate, Plan, Persona } from "@/lib/creative-types";
import { Modal } from "@/components/ui";
import { CandidateDraft } from "../CreativeStudio";
import { ActionBar, Field, fieldNames, useCreativeDraft } from "./shared";

type Cache = { data: Plan; baseline: string };
export function StoryWorkspace({
  project,
  candidates,
  busy,
  generate,
  select,
  reload,
  onNext,
  onStatus,
  tasks,
}: {
  project: Project;
  candidates: Candidate[];
  busy: boolean;
  generate: () => void;
  select: (c: Candidate) => void;
  reload: () => Promise<void>;
  onNext: () => void;
  onStatus?: (s: string) => void;
  tasks: ReactNode;
}) {
  const st = project.creative!,
    server = st.plan_draft || st.plan,
    encoded = JSON.stringify(server),
    key = `cineai-story-v2-${project.id}`;
  const [draft, setDraft] = useState<Plan | null>(server),
    [baseline, setBaseline] = useState(encoded),
    [ready, setReady] = useState(false),
    [pending, setPending] = useState(false),
    [error, setError] = useState<unknown>(""),
    [compare, setCompare] = useState(false),
    [impact, setImpact] = useState<string[]>([]),
    [sync, setSync] = useState(false),
    [storageError, setStorageError] = useState(false);
  const dirty = JSON.stringify(draft) !== baseline,
    conflict = ready && encoded !== baseline && dirty;
  const version = useRef(st.version);
  version.current = st.version;
  useEffect(() => {
    try {
      const cached = localStorage.getItem(key);
      if (cached) {
        const x = JSON.parse(cached) as Cache;
        setDraft(x.data);
        setBaseline(x.baseline);
      }
    } catch {
      setStorageError(true);
    }
    setReady(true);
  }, [key]);
  useEffect(() => {
    if (ready && !dirty && encoded !== baseline) {
      setDraft(server);
      setBaseline(encoded);
    }
  }, [ready, dirty, encoded, baseline, server]);
  useEffect(() => {
    if (!ready) return;
    try {
      if (dirty && draft)
        localStorage.setItem(key, JSON.stringify({ data: draft, baseline }));
      else localStorage.removeItem(key);
    } catch {
      setStorageError(true);
    }
  }, [key, draft, dirty, baseline, ready]);
  const status = pending
    ? uiCopy["正在保存…"]
    : conflict
      ? uiCopy["服务端已更新 · 请处理草稿冲突"]
      : dirty
        ? storageError
          ? uiCopy["未保存 · 浏览器暂存不可用"]
          : uiCopy["本地暂存 · 尚未保存到服务端"]
        : st.plan_draft
          ? uiCopy["服务端草稿已保存 · 待确认"]
          : st.plan_confirmed
            ? uiCopy["服务端已保存 · 故事已确认"]
            : uiCopy["服务端已保存 · 待确认"];
  useEffect(() => onStatus?.(status), [status, onStatus]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    if (!draft) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api<{ messages: string[] }>(
        `/creative/projects/${project.id}/plan-impact`,
        "POST",
        { expected: version.current, data: draft },
        controller.signal,
      )
        .then((x) => setImpact(x.messages))
        .catch(() =>
          setImpact([
            uiCopy["保存草稿不影响后续内容；确认前请检查字段有效性或刷新影响说明。"],
          ]),
        );
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [draft, project.id, st.version]);
  async function persist(confirm: boolean) {
    if (!draft || conflict) return;
    setPending(true);
    setError("");
    try {
      await api(
        `/creative/projects/${project.id}/${confirm ? "confirm/plan" : "plan"}`,
        confirm ? "POST" : "PATCH",
        { expected: st.version, data: confirm ? { plan: draft } : draft },
      );
      try {
        localStorage.removeItem(key);
      } catch {
        setStorageError(true);
      }
      setBaseline(JSON.stringify(draft));
      await reload();
      if (confirm) onNext();
    } catch (e) {
      setError(e);
    } finally {
      setPending(false);
    }
  }
  const change = <K extends keyof Plan>(k: K, v: Plan[K]) =>
    setDraft((d) => (d ? { ...d, [k]: v } : d));
  const preview =
    candidates.find((c) => !c.stale && !c.selected) || candidates[0];
  const [tab, setTab] = useState<"script" | "cast">("script");
  // editing: null=只读；-1=梗概；>=0=第 n 段
  const [editing, setEditing] = useState<number | null>(null);
  const [styleOpen, setStyleOpen] = useState(false);
  // 统计条：字数按非空白字符计，镜头预估直接取设定值
  const stats = draft
    ? {
        chars: [draft.title, draft.synopsis, ...draft.beats]
          .join("")
          .replace(/\s/g, "").length,
        scenes: draft.beats.length,
        shots: draft.scene_count || 3,
      }
    : { chars: 0, scenes: 0, shots: 0 };
  return (
    <section className="cw-story" aria-label={uiCopy["故事工作区"]}>
      <ErrorNotice error={error} />
      {conflict && (
        <div className="creative-warning" role="alert">
          {uiCopy["服务端故事已改变，本地编辑已保留。请先复制需要保留的文字，再载入服务端稿。"]}<button
            className="btn"
            onClick={() => {
              setDraft(server);
              setBaseline(encoded);
            }}
          >
            {uiCopy["载入服务端稿，放弃本地修改"]}</button>
        </div>
      )}
      {draft && (
        <div className="cw-stage-strip">
          <div className="cw-stage-strip__left">
            <div className="cw-stage-strip__chip">
              <span>{uiCopy["当前阶段"]}</span>
              <span className="cw-stage-strip__num">01</span>
              <span>/</span>
              <span>05</span>
              <span className="cw-stage-strip__name">
                {uiCopy["故事方案"]}
              </span>
              {st.plan_confirmed && (
                <span className="cw-stage-strip__done">
                  {uiCopy["已确认"]}
                </span>
              )}
            </div>
          </div>
          <div className="cw-stage-strip__right">
            {candidates.length > 0 && (
              <button className="btn" onClick={() => setCompare(true)}>
                {uiCopy["其他方案"]} · {candidates.length}
              </button>
            )}
            <button
              className="btn cw-ai-button"
              disabled={busy || pending || dirty}
              onClick={generate}
            >
              <Sparkles size={16} /> AI生成方案
            </button>
          </div>
        </div>
      )}
      <div className="cw-section-heading">
        <div>
          <span className="cs-kicker">
            01 / STORY · {uiCopy["故事文稿方案"]}
          </span>
          <h2>
            {draft
              ? draft.title || uiCopy["未命名文稿"]
              : uiCopy["从一个念头，开始讲故事"]}
          </h2>
        </div>
      </div>
      {tasks}
      {draft ? (
        <div className="cw-story-layout">
          <article className="cw-manuscript">
            <div className="cw-logline">
              <div className="cw-logline__body">
                <span className="cw-logline__icon" aria-hidden>
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M7.5 8.25h9m-9 3H12M2.25 12.76c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.17 48.17 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.39 48.39 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
                  </svg>
                </span>
                <div className="cw-logline__main">
                  <span className="cw-inspector__label">
                    {uiCopy["一句话故事梗概"]}
                  </span>
                  {editing === -1 ? (
                    <>
                      <textarea
                        className="cw-scene__input"
                        value={draft.synopsis}
                        onChange={(e) => change("synopsis", e.target.value)}
                      />
                      <div className="cw-scene__done">
                        <button
                          className="btn"
                          onClick={() => setEditing(null)}
                        >
                          {uiCopy["完成"]}
                        </button>
                      </div>
                    </>
                  ) : (
                    <p className="cw-logline__text">{draft.synopsis}</p>
                  )}
                </div>
              </div>
              {editing !== -1 && (
                <button className="btn" onClick={() => setEditing(-1)}>
                  {uiCopy["编辑"]}
                </button>
              )}
            </div>

            <section className="cw-screenplay">
              <div className="cw-screenplay__bar">
                <div className="cw-tabs" role="tablist">
                  <button
                    role="tab"
                    aria-selected={tab === "script"}
                    onClick={() => setTab("script")}
                  >
                    {uiCopy["故事正文"]}
                  </button>
                  <button
                    role="tab"
                    aria-selected={tab === "cast"}
                    onClick={() => setTab("cast")}
                  >
                    {uiCopy["人物初稿"]} ({draft.characters.length})
                  </button>
                </div>
                <div className="cw-screenplay__stats">
                  <span>
                    {uiCopy["字数"]}:{" "}
                    <b>{stats.chars.toLocaleString()}</b>
                  </span>
                  <span>
                    {uiCopy["镜头预估"]}:{" "}
                    <b className="is-gold">
                      {stats.shots} {uiCopy["镜"]}
                    </b>
                  </span>
                </div>
              </div>
              <div className="cw-screenplay__body">
                {tab === "script" ? (
                  <>
                    <div className="cw-screenplay__section">
                      <div className="cw-section-label">
                        {uiCopy["故事正文 · 叙事版本"]}
                        <span className="cw-section-label__aside">
                          {formatCopy("{0} 场", stats.scenes)}
                        </span>
                      </div>
                      {draft.beats.map((beat, i) => (
                        <div
                          key={i}
                          className="cw-scene"
                          data-editing={editing === i}
                        >
                          <div className="cw-scene__read">
                            <span className="cw-scene__no">
                              {String(i + 1).padStart(2, "0")}
                            </span>
                            <p className="cw-scene__text">{beat}</p>
                            <button
                              className="cw-scene__edit"
                              onClick={() => setEditing(i)}
                            >
                              {uiCopy["编辑"]}
                            </button>
                          </div>
                          <div className="cw-scene__field">
                            <Field
                              label={formatCopy("段落 {0}", i + 1)}
                              value={beat}
                              large
                              onChange={(v) =>
                                change(
                                  "beats",
                                  draft.beats.map((b, j) =>
                                    i === j ? v : b,
                                  ),
                                )
                              }
                            />
                            <div className="cw-scene__done">
                              <button
                                className="btn"
                                onClick={() => setEditing(null)}
                              >
                                {uiCopy["完成"]}
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="cw-screenplay__section">
                      <details>
                        <summary>{uiCopy["主题与结局"]}</summary>
                        <Field
                          label={uiCopy["主题"]}
                          value={draft.theme}
                          onChange={(v) => change("theme", v)}
                          large
                        />
                        <Field
                          label={uiCopy["结局"]}
                          value={draft.ending}
                          onChange={(v) => change("ending", v)}
                          large
                        />
                      </details>
                      <details>
                        <summary>
                          {uiCopy["场景设定"]} ({draft.locations.length})
                        </summary>
                        {draft.locations.map((l) => (
                          <Field
                            key={l.id}
                            label={l.name}
                            value={l.description}
                            large
                            onChange={(v) =>
                              change(
                                "locations",
                                draft.locations.map((x) =>
                                  x.id === l.id
                                    ? { ...x, description: v }
                                    : x,
                                ),
                              )
                            }
                          />
                        ))}
                      </details>
                      <details>
                        <summary>{uiCopy["原始创意"]}</summary>
                        <p className="cw-empty">{project.description}</p>
                      </details>
                    </div>
                  </>
                ) : (
                  <div className="cw-screenplay__section">
                    <div className="cw-section-label">
                      {uiCopy["人物初稿"]}
                      <span className="cw-section-label__aside">
                        {draft.characters.length}
                      </span>
                    </div>
                    <p className="helper">
                      {uiCopy["故事中的构想，与已定稿的本片角色分别保存。"]}
                    </p>
                    {draft.characters.length === 0 ? (
                      <p className="cw-empty">
                        {uiCopy["这份方案还没有人物初稿。"]}
                      </p>
                    ) : (
                      draft.characters.map((c, i) => (
                        <details key={i}>
                          <summary>
                            {c.name} ·{" "}
                            {c.identity || uiCopy["待补充身份"]}
                          </summary>
                          {Object.entries(fieldNames).map(([k, label]) => (
                            <Field
                              key={k}
                              label={label}
                              value={String(c[k as keyof Persona] || "")}
                              large={k !== "name" && k !== "age"}
                              onChange={(v) =>
                                change(
                                  "characters",
                                  draft.characters.map((x, j) =>
                                    i === j ? { ...x, [k]: v } : x,
                                  ),
                                )
                              }
                            />
                          ))}
                        </details>
                      ))
                    )}
                    {project.characters.length > 0 && (
                      <>
                        <button
                          className="btn"
                          style={{ marginTop: 12 }}
                          disabled={dirty || pending}
                          onClick={() => setSync(true)}
                        >
                          {uiCopy["查看差异 / 同步到本片角色"]}
                        </button>
                        <p className="helper">
                          {uiCopy["同步前先保存草稿。同步只更新勾选字段，不替换已选媒体。"]}
                        </p>
                      </>
                    )}
                  </div>
                )}
              </div>
            </section>
          </article>
          <StoryInspector
            draft={draft}
            change={change}
            styleOpen={styleOpen}
            setStyleOpen={setStyleOpen}
          />
        </div>
      ) : preview ? (
        <div className="cw-candidate-story">
          <CandidateDraft value={preview.data.value} />
          <button
            className="btn primary"
            disabled={busy || preview.stale}
            onClick={() => select(preview)}
          >
            {uiCopy["采用并编辑"]}</button>
          {preview.stale && <p>{"这份方案输入已过期，请重新生成。"}</p>}
        </div>
      ) : (
        <InitialBrief
          project={project}
          reload={reload}
          generate={generate}
          busy={busy}
        />
      )}
      {draft && (
        <div className="cw-impact">
          <strong>{uiCopy["保存草稿不影响后续创作。确认当前稿后："]}</strong>
          {impact.map((x) => (
            <p key={x}>{x}</p>
          ))}
        </div>
      )}
      <ActionBar
        status={
          <>
            <b>{status}</b>
            <small>
              {draft
                ? dirty || st.plan_draft
                  ? impact.join(" ")
                  : uiCopy["编辑内容将随本次确认一起保存"]
                : uiCopy["先生成并采用一份故事方案"]}
            </small>
          </>
        }
      >
        <button
          className="btn"
          disabled={!draft || !dirty || pending || busy || conflict}
          onClick={() => void persist(false)}
        >
          {uiCopy["保存草稿"]}</button>
        <button
          className="btn primary"
          disabled={!draft || pending || busy || conflict}
          onClick={() => void persist(true)}
        >
          {uiCopy["确认故事，进入角色 →"]}</button>
      </ActionBar>
      {compare && (
        <Modal wide title={uiCopy["比较故事方案"]} onClose={() => setCompare(false)}>
          <div className="cw-story-comparison">
            {candidates.map((c, i) => (
              <article key={c.id}>
                <span className="cs-kicker">
                  {uiCopy["方案"]}{i + 1} ·{" "}
                  {c.selected ? uiCopy["已采用"] : c.stale ? uiCopy["输入已过期"] : uiCopy["可采用"]}
                </span>
                <CandidateDraft value={c.data.value} />
                <button
                  className="btn"
                  disabled={busy || dirty || c.stale || c.selected}
                  onClick={() => {
                    select(c);
                    setCompare(false);
                  }}
                >
                  {uiCopy["采用并编辑"]}</button>
                {dirty && <p>{uiCopy["先保存当前草稿，再切换方案。"]}</p>}
              </article>
            ))}
          </div>
        </Modal>
      )}
      {sync && (
        <CharacterSync
          project={project}
          reload={reload}
          close={() => setSync(false)}
        />
      )}
    </section>
  );
}
/* 右栏创作设定检视器。
   与原 aside 的写入契约完全一致 —— 全部经 change() 落到 draft，
   不引入新的状态源，因此保存/冲突/暂存逻辑无需改动。 */
const RATIOS = [
  { value: "16:9", hint: uiCopy["电影横屏"], w: 28, h: 16 },
  { value: "9:16", hint: uiCopy["短视频竖屏"], w: 15, h: 26 },
  { value: "2.39:1", hint: uiCopy["宽银幕"], w: 30, h: 13 },
] as const;
const DURATIONS = [
  { v: 15, label: "预告" },
  { v: 24, label: "标准" },
  { v: 30, label: "完整" },
] as const;
const SHOT_OPTIONS = [3, 5, 8] as const;

function StoryInspector({
  draft,
  change,
  styleOpen,
  setStyleOpen,
}: {
  draft: Plan;
  change: <K extends keyof Plan>(k: K, v: Plan[K]) => void;
  styleOpen: boolean;
  setStyleOpen: (v: boolean) => void;
}) {
  // 当前时长落在哪一档语义刻度上
  // 只有落在刻度附近（±3s）才视为该语义档，避免 6 秒被标成「15s 预告」
  const scale = DURATIONS.find(
    (x) => Math.abs(x.v - draft.duration) <= 3,
  );
  const [head, sub] = draft.style.split(/[，。,]/);
  return (
    <aside className="cw-story-settings">
      <h3 className="cw-inspector__title">
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
        </svg>
        {uiCopy["创作设定"]}
      </h3>

      <div className="cw-inspector__group">
        <div className="cw-inspector__head">
          <span className="cw-inspector__label">{uiCopy["画幅"]}</span>
        </div>
        <div className="cw-ratio-grid">
          {RATIOS.map((r) => (
            <button
              key={r.value}
              className="cw-ratio"
              aria-pressed={draft.ratio === r.value}
              onClick={() => change("ratio", r.value)}
            >
              <span
                className="cw-ratio__box"
                style={{ width: r.w, height: r.h }}
                aria-hidden
              />
              <span className="cw-ratio__name">{r.value}</span>
              <span className="cw-ratio__hint">{r.hint}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="cw-inspector__group">
        <div className="cw-inspector__head">
          <label htmlFor="cw-duration">{uiCopy["目标时长"]}</label>
          <span className="cw-inspector__value">
            {draft.duration} {uiCopy["秒"]}
          </span>
        </div>
        <div className="cw-duration">
          <input
            id="cw-duration"
            type="range"
            min={6}
            max={240}
            value={draft.duration}
            onChange={(e) => change("duration", Number(e.target.value))}
          />
          <div className="cw-duration__scale">
            {DURATIONS.map((d) => (
              <span
                key={d.v}
                className={d === scale ? "is-active" : undefined}
              >
                {d.v}s ({d.label})
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="cw-inspector__group">
        <label><input type="checkbox" checked={draft.fixed_scene_count || false} onChange={e => change("fixed_scene_count", e.target.checked)} /> 固定镜头数量（否则仅作建议）</label>
        <div className="cw-inspector__head">
          <span className="cw-inspector__label">{uiCopy["镜头数"]}</span>
          <span className="cw-inspector__hint">
            {formatCopy("推荐 {0} 镜", draft.scene_count || 3)}
          </span>
        </div>
        <div className="cw-seg">
          {SHOT_OPTIONS.map((n) => (
            <button
              key={n}
              aria-pressed={(draft.scene_count || 3) === n}
              onClick={() => change("scene_count", n)}
            >
              {formatCopy("{0} 镜头", n)}
            </button>
          ))}
        </div>
      </div>

      <div className="cw-inspector__group">
        <div className="cw-inspector__head">
          <span className="cw-inspector__label">
            {uiCopy["视觉风格"]}
          </span>
        </div>
        {styleOpen ? (
          <div className="cw-style-editor">
            <StyleChoices value={draft.style} onChange={style => change("style", style)} />
            <textarea
              aria-label="自定义视觉风格"
              value={draft.style}
              onChange={(e) => change("style", e.target.value)}
            />
            <div className="cw-style-editor__done">
              <button className="btn" onClick={() => setStyleOpen(false)}>
                {uiCopy["完成"]}
              </button>
            </div>
          </div>
        ) : (
          <div className="cw-style-card">
            <div className="cw-style-card__text">
              <b>{head || uiCopy["风格未设置"]}</b>
              <span>{sub?.trim() || formatCopy("推荐 {0} 镜", draft.scene_count || 3)}</span>
            </div>
            <button onClick={() => setStyleOpen(true)}>
              {uiCopy["调整"]}
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

function CharacterSync({
  project,
  reload,
  close,
}: {
  project: Project;
  reload: () => Promise<void>;
  close: () => void;
}) {
  const personas =
    (project.creative?.plan_draft || project.creative?.plan)?.characters || [];
  const [index, setIndex] = useState(0),
    [id, setId] = useState(project.characters[0]?.id || ""),
    [fields, setFields] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>("");
  const target = project.characters.find((c) => c.id === id),
    source = personas[index];
  const differences =
    source && target
      ? Object.keys(fieldNames).filter(
          (k) =>
            source[k as keyof Persona] !==
            target.creative?.persona[k as keyof Persona],
        )
      : [];
  return (
    <Modal wide title={uiCopy["人物初稿 → 本片角色 · 显式同步"]} onClose={close}>
      <div className="cw-sync">
        <div className="creative-grid">
          <label className="creative-field">
            {uiCopy["故事人物"]}<select
              value={index}
              onChange={(e) => {
                setIndex(Number(e.target.value));
                setFields([]);
              }}
            >
              {personas.map((c, i) => (
                <option key={i} value={i}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="creative-field">
            {uiCopy["目标角色"]}<select
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                setFields([]);
              }}
            >
              {project.characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p>
          {uiCopy["仅同步勾选字段。角色需重新定稿，关联分镜需再次确认；形象和声音按各自依赖检查，现有媒体保留。"]}</p>
        {differences.map((k) => (
          <label key={k} className="cw-diff-check">
            <input
              type="checkbox"
              checked={fields.includes(k)}
              onChange={(e) =>
                setFields(
                  e.target.checked
                    ? [...fields, k]
                    : fields.filter((x) => x !== k),
                )
              }
            />
            <b>{fieldNames[k]}</b>
            <del>
              {String(
                target?.creative?.persona[k as keyof Persona] || uiCopy["未设置"],
              )}
            </del>
            <ins>{String(source[k as keyof Persona] || uiCopy["未设置"])}</ins>
          </label>
        ))}
        {!differences.length && <p>{uiCopy["所列人物字段一致，无需同步。"]}</p>}
        <ErrorNotice error={error} />
        <button
          className="btn primary"
          disabled={busy || !fields.length}
          onClick={async () => {
            setBusy(true);
            try {
              await api(
                `/creative/projects/${project.id}/sync-character/${id}`,
                "POST",
                {
                  expected: target?.creative?.version,
                  data: {
                    projectExpected: project.creative?.version,
                    index,
                    fields,
                  },
                },
              );
              await reload();
              close();
            } catch (e) {
              setError(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          {uiCopy["同步"]}{fields.length} {uiCopy["个字段"]}</button>
      </div>
    </Modal>
  );
}

function InitialBrief({
  project,
  reload,
  generate,
  busy,
}: {
  project: Project;
  reload: () => Promise<void>;
  generate: () => void;
  busy: boolean;
}) {
  const [draft, setDraft] = useCreativeDraft(`cineai-brief-${project.id}`, {
    idea: project.description,
    ratio: project.ratio,
    style: project.style,
    duration: 30,
    scene_count: 3,
  });
  const [pending, setPending] = useState(false),
    [error, setError] = useState<unknown>("");
  return (
    <div className="cw-story-empty">
      <Field
        label={uiCopy["故事创意"]}
        large
        value={draft.idea}
        onChange={(idea) => setDraft({ ...draft, idea })}
      />
      <div className="creative-grid">
        <label className="creative-field">
          <span>{uiCopy["画幅"]}</span>
          <select
            value={draft.ratio}
            onChange={(e) => setDraft({ ...draft, ratio: e.target.value })}
          >
            {["16:9", "9:16", "1:1"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <div className="creative-field"><span>视觉风格</span><StyleChoices value={draft.style} onChange={style => setDraft({ ...draft, style })} /><input aria-label="自定义视觉风格" value={draft.style} onChange={e => setDraft({ ...draft, style: e.target.value })} /></div>
        <label className="creative-field">
          <span>{uiCopy["目标时长 / 秒"]}</span>
          <input
            type="number"
            min={6}
            max={240}
            value={draft.duration}
            onChange={(e) =>
              setDraft({ ...draft, duration: Number(e.target.value) })
            }
          />
        </label>
        <label className="creative-field">
          <span>{uiCopy["镜头数"]}</span>
          <input
            type="number"
            min={1}
            max={24}
            value={draft.scene_count}
            onChange={(e) =>
              setDraft({ ...draft, scene_count: Number(e.target.value) })
            }
          />
        </label>
      </div>
      <ErrorNotice error={error} />
      <button
        className="btn primary"
        disabled={busy || pending || !draft.idea.trim()}
        onClick={async () => {
          setPending(true);
          try {
            await api(`/creative/projects/${project.id}/brief`, "PATCH", {
              expected: project.creative?.version,
              data: draft,
            });
            await reload();
            generate();
          } catch (e) {
            setError(e);
          } finally {
            setPending(false);
          }
        }}
      >
        {uiCopy["生成故事方案"]}</button>
      <p className="helper">{uiCopy["先保存创意与设定，再确认生成范围与费用。"]}</p>
    </div>
  );
}

const STYLE_CHOICES = [
  { name: "电影写实", description: "自然光影 · 细腻质感", style: "电影写实，自然光影，细腻真实的服装与场景质感", tone: "cinematic" },
  { name: "国风三维", description: "精致人物 · 东方意境", style: "国风三维动画，精致人物建模，东方美学与柔和电影光影", tone: "fantasy" },
  { name: "日系动画", description: "清透色彩 · 手绘笔触", style: "日系二维动画，清透色彩，细腻手绘笔触与柔和光影", tone: "anime" },
  { name: "水彩绘本", description: "柔和晕染 · 温暖叙事", style: "水彩绘本，柔和色彩晕染，纸张纹理与温暖手绘叙事", tone: "watercolor" },
];
function StyleChoices({ value, onChange }: { value: string; onChange: (style: string) => void }) {
  return <div className="cw-style-choices" aria-label="视觉风格候选">{STYLE_CHOICES.map(choice => <button key={choice.name} type="button" className={`cw-style-choice ${choice.tone}`} aria-pressed={value.startsWith(choice.name)} onClick={() => onChange(choice.style)}><span className="cw-style-choice__swatch" aria-hidden="true" /><span><b>{choice.name}</b><small>{choice.description}</small></span></button>)}</div>;
}

"use client";
import { CurrentVoice } from "./CurrentVoice";
import { viewLabels } from "./copy";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { TechnicalDetails } from "./TechnicalDetails";
import { useEffect, useState, type ReactNode } from "react";
import { api, apiBase } from "@/lib/api";
import type { Candidate, CharacterState, Persona, AssetView } from "@/lib/creative-types";
import {
  ActionBar,
  Field,
  fieldNames,
  blankPersona,
  useCreativeDraft,
  type Capabilities,
  type GenerationRequest,
  type Readiness,
  type CreativeTask,
  TaskFeedback,
} from "./shared";
import type { Project } from "@/lib/types";
export function CharacterAsset({
  project,
  capabilities,
  initialTab = "image",
  id,
  state,
  image,
  busy,
  candidates,
  renderCandidates,
  generate,
  save,
  action,
  uploadVoice,
  ready,
  onBack,
  onDirty,
  tasks,
}: {
  project?: Project;
  initialTab?: string;
  capabilities: Capabilities;
  id: string;
  state?: CharacterState;
  image: string;
  busy: boolean;
  candidates: Candidate[];
  renderCandidates: (c: Candidate[]) => ReactNode;
  generate: (r: GenerationRequest, p: Persona) => void;
  save: (p: Persona) => void;
  action: (op: string, data?: object) => void;
  uploadVoice: (f: File, original?: boolean) => void;
  ready?: Readiness;
  onBack: () => void;
  onDirty: (id: string, dirty: boolean) => void;
  tasks: CreativeTask[];
}) {
  const [draft, setDraft] = useCreativeDraft(
    `cineai-character-${id}-${state?.version || 0}`,
    state?.persona || blankPersona(),
  );
  const [tab, setTab] = useState(initialTab);
  const [method, setMethod] = useState("preset"),
    [voices, setVoices] = useState<{ label: string; voiceId: string }[]>([]),
    [voice, setVoice] = useState(capabilities.defaultVoice),
    [sample, setSample] = useCreativeDraft<string>(
      `cineai-audition-${id}`,
      uiCopy["你好，我们终于见面了。这件事，我已经等了很久。别担心，我们一起把它做好。走吧，我们回家。"],
    ),
    [variant, setVariant] = useState<string>(uiCopy["状态变体"]),
    [view, setView] = useState<AssetView>("main"),
    [source, setSource] = useState<string>(uiCopy["用户上传"]),
    [referenceUse, setReferenceUse] = useState<string>(uiCopy["固定身份与服装参考"]),
    [error, setError] = useState("");
  const dirty = JSON.stringify(draft) !== JSON.stringify(state?.persona);
  useEffect(() => onDirty(id, dirty), [id, dirty, onDirty]);
  useEffect(() => {
    api<{ label: string; voiceId: string }[]>("/tts/voices")
      .then(setVoices)
      .catch(() => setError(uiCopy["预设音色暂时无法加载，请检查连接。"]));
  }, []);
  const gen = (operation: string, extra: Partial<GenerationRequest> = {}) => {
    if (
      operation === "character_image" &&
      !draft.image_prompt.trim() &&
      !draft.appearance.trim()
    ) {
      setError(uiCopy["请先填写形象描述。"]);
      return;
    }
    setError("");
    generate(
      { operation, target: id, ...extra },
      extra.variant
        ? {
            ...draft,
            variants: {
              ...draft.variants,
              [extra.variant]: draft.variants[extra.variant] || extra.variant,
            },
          }
        : draft,
    );
  };
  const images = candidates.filter((c) => c.kind === "character_image"),
    sounds = candidates.filter((c) =>
      ["voice_preview", "voice_design", "voice_clone", "voice_source"].includes(
        c.kind,
      ),
    );
  const sameText = sounds.filter(
    (c) => !c.stale && c.data.request?.text === sample,
  );
  const current = sounds.find((c) => c.id === state?.voice?.candidate_id);
  const currentUrl = state?.voice?.url || current?.url;
  const sheet = state?.views?.turnaround && state.views.turnaround.parent_revision === state?.image?.candidate_id ? state?.views?.turnaround : state?.image?.turnaround;
  const basic = [
    "name",
    "identity",
    "personality",
    "motivation",
    "relationships",
  ];
  const fields = (keys: string[]) =>
    keys.map((k) => (
      <Field
        key={k}
        label={fieldNames[k]}
        value={String(draft[k as keyof Persona] || "")}
        large={!["name", "age"].includes(k)}
        onChange={(v) => setDraft({ ...draft, [k]: v })}
      />
    ));
  return (
    <article className="cw-character-editor">
      <fieldset disabled={busy}>
        <header className="cw-selected-character">
          {image && <img src={image} alt={formatCopy("{0}当前选用形象", draft.name)} />}
          <div>
            <span className="cs-kicker">
              {uiCopy["本片角色 /"]}{state?.confirmed ? uiCopy["已定稿"] : uiCopy["待确认"]}
            </span>
            <h2>{draft.name}</h2>
            <p>{state?.persona.voice_description || uiCopy["尚未描述声音"]}</p>
            <div className="cw-status-chips">
              <span>{ready?.image ? uiCopy["形象就绪"] : uiCopy["形象待选择 / 更新"]}</span>
              <span>{draft.role_kind === "background" ? uiCopy["背景群体 · 无需绑定声音"] : ready?.voice ? uiCopy["声音就绪"] : uiCopy["声音待选择 / 更新"]}</span>
            </div>
          </div>
          {currentUrl && (
            <div className="cw-current-audio">
              <small>
                {uiCopy["当前声音 ·"]}{" "}
                {current?.data.request?.text === sample
                  ? uiCopy["相同试听文本"]
                  : uiCopy["已有样本"]}
              </small>
              <CurrentVoice url={currentUrl} durationMs={state?.voice?.reference?.duration_ms} />
            </div>
          )}
        </header>
        <nav className="cw-tabs" aria-label={uiCopy["角色编辑分区"]}>
          {[
            ["persona", uiCopy["人物设定"]],
            ["image", uiCopy["形象"]],
            ["voice", uiCopy["声音"]],
          ].map(([k, label]) => (
            <button
              key={k}
              aria-pressed={tab === k}
              className={tab === k ? "active" : ""}
              onClick={() => setTab(k)}
            >
              {label}
            </button>
          ))}
        </nav>
        {error && (
          <p role="alert" className="creative-warning">
            {error}
          </p>
        )}
        <TaskFeedback
          project={project}
          tasks={tasks}
          candidates={candidates}
          target={id}
          operations={
            tab === "image"
              ? ["character_image"]
              : tab === "persona"
                ? ["character"]
                : [
                    "voice_match",
                    "voice_preview",
                    "voice_design",
                    "voice_clone",
                    "voice_source",
                  ]
          }
        />
        {dirty && (
          <p className="creative-warning">
            {uiCopy["人物编辑已暂存在本标签页。先保存设定，再选用候选或确认角色。保存会取消角色与分镜阶段确认，媒体按各自依赖检查。"]}</p>
        )}
        {tab === "persona" && (
          <div className="cw-persona">
            <h3>{uiCopy["人物与故事的关系"]}</h3>
            <label className="creative-field">{uiCopy["角色用途"]}<select value={draft.role_kind || "speaking"} onChange={e => setDraft({ ...draft, role_kind: e.target.value as "speaking" | "background" })}><option value="speaking">{uiCopy["发言角色 · 固定身份与声音"]}</option><option value="background">{uiCopy["背景群体 · 不绑定台词"]}</option></select></label>
            <Field label={uiCopy["固定身份特征（脸、发型、衣着、装备）"]} value={draft.identity_traits || ""} large onChange={identity_traits => setDraft({ ...draft, identity_traits })} />
            {fields(basic)}
            <details>
              <summary>{uiCopy["更多人物与外貌设定"]}</summary>
              <div className="creative-grid">
                {fields(
                  Object.keys(fieldNames).filter(
                    (k) =>
                      !basic.includes(k) &&
                      !k.startsWith("voice") &&
                      k !== "image_prompt" && k !== "identity_traits",
                  ),
                )}
              </div>
            </details>
            <button
              className="btn"
              disabled={busy}
              onClick={() => gen("character")}
            >
              {uiCopy["AI 补全人物设定 · 先估算"]}</button>
            <fieldset disabled={dirty || busy}>
              {renderCandidates(
                candidates.filter((c) => c.kind === "character" && !c.stale),
              )}
            </fieldset>
          </div>
        )}
        {tab === "image" && (
          <div className="cw-image-work">
            <div className="cw-image-comparison">
              <figure>
                {image ? (
                  <img src={image} alt={uiCopy["当前选用形象大图"]} />
                ) : (
                  <div className="cs-character-placeholder">{uiCopy["还没有角色形象"]}</div>
                )}
                <figcaption>
                  {uiCopy["当前选用 ·"]}{ready?.image ? uiCopy["可用于分镜"] : uiCopy["待选择 / 更新"]}
                </figcaption>
              </figure>
              <div>
                <h3>{uiCopy["新形象候选"]}</h3>
                <p>{uiCopy["对照脸部、发型与服装，选用后才替换当前形象。"]}</p>
                <fieldset disabled={dirty || busy}>
                  {renderCandidates(
                    images.filter((c) => !c.stale && !c.selected),
                  )}
                </fieldset>
                {!images.some((c) => !c.stale && !c.selected) && (
                  <p>{uiCopy["生成或上传后，新候选会出现在这里。"]}</p>
                )}
              </div>
            </div>
            {sheet?.url && <figure className="cw-turnaround"><div><h3>角色三视图</h3><span>正面 / 侧面 / 背面</span></div><a href={sheet.url} target="_blank" rel="noreferrer" aria-label="查看角色三视图原图"><img src={sheet.url} alt={`${draft.name}的正面、侧面、背面三视图`} /></a><figcaption>与当前主形象一起生成，统一人物、服装与比例</figcaption></figure>}
            <div className="cw-image-controls">
              <section>
                <Field
                  label={uiCopy["形象描述"]}
                  value={draft.image_prompt}
                  large
                  onChange={(v) => setDraft({ ...draft, image_prompt: v })}
                />
                <button
                  className="btn cw-ai-button"
                  disabled={busy}
                  onClick={() =>
                    gen("character_image", { nonce: crypto.randomUUID() })
                  }
                >
                  {image ? "重新生成形象" : "AI生成形象"}</button>
                <button className="btn" disabled={busy || !state?.image?.key} onClick={() => gen("character_image", { use_reference: true, nonce: crypto.randomUUID() })}>根据参考图生成形象</button>
                <button className="btn" disabled={busy || !ready?.image} onClick={() => gen("character_image", { view: "turnaround", nonce: crypto.randomUUID() })}>{sheet?.url ? "重新生成三视图" : "补充三视图"}</button>
                <p className="helper">一次生成主形象与正面、侧面、背面三视图。上传参考图并选用后，可据此生成新形象。</p>
              </section>
              <section>
                <h3>上传形象参考图</h3>
                <label className="creative-field cw-reference-upload">
                  <span>选择参考图</span><small>PNG / JPG / WebP，最多 5 MB</small>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    disabled={busy || dirty}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      e.target.value = "";
                      if (!f) return;
                      if (f.size > 5 * 1024 * 1024) {
                        setError(uiCopy["图片不能超过 5 MB"]);
                        return;
                      }
                      const reader = new FileReader();
                      reader.onload = () =>
                        action("reference", { image: reader.result, ...(view !== "main" ? { view } : {}), ...(view === "state" ? { variant } : {}), source, use: referenceUse });
                      reader.onerror = () => setError(uiCopy["文件读取失败"]);
                      reader.readAsDataURL(f);
                    }}
                  />
                </label>
                <details><summary>上传用途与来源</summary>
                <p>{uiCopy["身份特征保持固定；动作、情绪和特效写在分镜或状态变体里。上传后保存为候选，再明确选用。"]}</p>
                <label className="creative-field">{uiCopy["素材用途 / 视图"]}<select value={view} onChange={e => setView(e.target.value as AssetView)}>{Object.entries({ main: uiCopy["主造型"], full_body: uiCopy["全身"], front: uiCopy["正面"], side: uiCopy["侧面"], back: uiCopy["背面"], turnaround: "三视图", half_body: uiCopy["半身"], face: uiCopy["面部特写"], state: uiCopy["状态变体"] }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
                {view === "state" && <Field label={uiCopy["状态名称"]} value={variant} onChange={setVariant} />}
                <Field label={uiCopy["来源说明"]} value={source} onChange={setSource} />
                <Field label={uiCopy["参考用途"]} value={referenceUse} onChange={setReferenceUse} />
                </details>

              </section>
            </div>
            <details>
              <summary>{uiCopy["补充视角与造型"]}</summary>
              <p>{uiCopy["补充视图沿用当前已选主造型作为父版本；只生成当前镜头需要的视图。"]}</p>
              <label className="creative-field">{uiCopy["派生视图"]}<select value={view === "main" ? "front" : view} onChange={e => setView(e.target.value as AssetView)}>{Object.entries({ full_body: uiCopy["全身"], front: uiCopy["正面"], side: uiCopy["侧面"], back: uiCopy["背面"], turnaround: "三视图", half_body: uiCopy["半身"], face: uiCopy["面部特写"], state: uiCopy["状态变体"] }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
              {view === "state" && <Field label={uiCopy["可变动作 / 情绪 / 特效"]} value={variant} onChange={setVariant} />}
              <button
                className="btn"
                disabled={busy || !ready?.image || (view === "state" && !variant.trim())}
                onClick={() => gen("character_image", { view: view === "main" ? "front" : view, ...(view === "state" ? { variant } : {}) })}
              >
                {uiCopy["基于当前主图生成 · 先估算"]}</button>
            </details>
            {Object.entries(state?.views || {}).length > 0 && <section><h3>{uiCopy["已选角色素材包"]}</h3><div className="cs-reference-strip">{Object.entries(state?.views || {}).map(([key, ref]) => <figure key={key}><img src={ref.url || `${apiBase}/api/assets/${ref.asset_id || ref.key}?redirect=true`} alt={`${draft.name} · ${viewLabels[key] || viewLabels.main}`} /><figcaption>{viewLabels[key] || viewLabels.main} · {ref.confirmed ? uiCopy["已确认"] : "已选用"}<small>{uiCopy["生成素材"]}</small></figcaption></figure>)}</div></section>}
            <details>
              <summary>
                {uiCopy["已选与历史候选 ·"]}{" "}
                {images.filter((c) => c.stale || c.selected).length}
              </summary>
              <fieldset disabled={dirty || busy}>
                {renderCandidates(images.filter((c) => c.stale || c.selected))}
              </fieldset>
            </details>
          </div>
        )}
        {tab === "voice" && (
          <div className="cw-voice-work">
            <h3>{uiCopy["为角色选择声音"]}</h3>
            <div className="cw-voice-methods">
              {[
                ["preset", uiCopy["预设音色"], true],
                ["design", uiCopy["AI 设计"], capabilities.voiceDesign],
                ["clone", uiCopy["参考录音复刻"], capabilities.voiceClone],
                ["original", uiCopy["直接使用录音"], true],
              ].map(([k, label, available]) => (
                <button
                  key={String(k)}
                  aria-pressed={method === k}
                  className={method === k ? "active" : ""}
                  onClick={() => setMethod(String(k))}
                >
                  {label}
                  <small>{available ? uiCopy["可使用"] : uiCopy["当前服务不支持"]}</small>
                </button>
              ))}
            </div>
            <Field
              label={uiCopy["统一试听文本"]}
              value={sample}
              large
              onChange={setSample}
            />
            <p className="helper">
              {uiCopy["用同一段文字比较音色。已有样本文本不一致时，会单独列在历史样本中；试听生成也需费用确认。"]}</p>
            {method === "preset" && (
              <section>
                <label className="creative-field">
                  <span>{uiCopy["预设声音"]}</span>
                  <select
                    value={voice}
                    onChange={(e) => setVoice(e.target.value)}
                  >
                    {voices.map((v) => (
                      <option key={v.voiceId} value={v.voiceId}>
                        {v.label}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="creative-actions">
                  <button
                    className="btn primary"
                    disabled={busy || !voice || !sample.trim()}
                    onClick={() =>
                      gen("voice_preview", { voice_id: voice, text: sample })
                    }
                  >
                    {uiCopy["生成声音试听 · 先估算"]}</button>
                  <button
                    className="btn"
                    disabled={busy}
                    onClick={() => gen("voice_match")}
                  >
                    {uiCopy["按人物描述推荐"]}</button>
                </div>
                {candidates
                  .filter((c) => c.kind === "voice_match" && !c.stale)
                  .flatMap(
                    (c) =>
                      (c.data.value as { voice_ids?: string[] })?.voice_ids ||
                      [],
                  )
                  .map((v) => (
                    <button key={v} className="btn" onClick={() => setVoice(v)}>
                      {voices.find((x) => x.voiceId === v)?.label || uiCopy["推荐声音"]}
                    </button>
                  ))}
              </section>
            )}
            {method === "design" && (
              <section>
                <Field
                  label={uiCopy["希望的音色与表演"]}
                  value={draft.voice_prompt}
                  large
                  onChange={(v) => setDraft({ ...draft, voice_prompt: v })}
                />
                <p>
                  {capabilities.voiceDesign
                    ? uiCopy["按描述生成试听。选用后锁定声音样本，后续台词复用该声音。账号权限与实际生成结果以服务端返回为准。"]
                    : uiCopy["当前语音服务不支持声音设计，请选择预设声音或直接录音。"]}
                </p>
                <button
                  className="btn primary"
                  disabled={busy || !capabilities.voiceDesign || !sample.trim()}
                  onClick={() => gen("voice_design", { text: sample })}
                >
                  {uiCopy["设计声音并试听 · 先估算"]}</button>
              </section>
            )}
            {method === "clone" && (
              <section>
                <p>
                  {capabilities.voiceClone
                    ? uiCopy["上传同一人 10 秒至 5 分钟独白，尽量去除配乐。复刻相似度需试听确认。"]
                    : uiCopy["当前服务不支持复刻，可改用预设音色或直接录音。"]}
                </p>
                <label className="creative-field">
                  <span>{uiCopy["参考录音 · MP3 / M4A / WAV，最多 20 MB"]}</span>
                  <input
                    type="file"
                    accept=".mp3,.m4a,.wav"
                    disabled={busy || dirty || !capabilities.voiceClone}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      e.target.value = "";
                      if (!f) return;
                      if (f.size > 20 * 1024 * 1024) {
                        setError(uiCopy["声音参考不能超过 20 MB"]);
                        return;
                      }
                      uploadVoice(f);
                    }}
                  />
                </label>
                {state?.voice_reference && (
                  <>
                    <p>{state.voice_reference.filename}</p>
                    <audio controls src={state.voice_reference.url} />
                  </>
                )}
                <button
                  className="btn primary"
                  disabled={
                    busy ||
                    !capabilities.voiceClone ||
                    !state?.voice_reference ||
                    !sample.trim()
                  }
                  onClick={() => gen("voice_clone", { text: sample })}
                >
                  {uiCopy["复刻并试听 · 先估算"]}</button>
              </section>
            )}
            {method === "original" && (
              <section>
                <p>
                  {uiCopy["保留录音原有的音色与表演。后续每句台词需要在分镜里导入对应录音，不能自动合成新台词。"]}</p>
                <label className="creative-field">
                  <span>{uiCopy["上传原声样本"]}</span>
                  <input
                    type="file"
                    accept="audio/*"
                    disabled={busy || dirty}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      e.target.value = "";
                      if (f) uploadVoice(f, true);
                    }}
                  />
                </label>
                <fieldset disabled={dirty || busy}>
                  {renderCandidates(
                    sounds.filter((c) => c.kind === "voice_source" && !c.stale),
                  )}
                </fieldset>
              </section>
            )}
            <div className="cw-divider" />
            <h3>{uiCopy["同文试听比较"]}</h3>
            {state?.voice && state.voice.mode !== "original" && (
              <button
                className="btn"
                disabled={busy || !sample.trim()}
                onClick={() =>
                  gen("voice_preview", {
                    voice_id: state.voice!.voice_id,
                    text: sample,
                  })
                }
              >
                {uiCopy["用当前声音生成相同文本 · 先估算"]}</button>
            )}
            <fieldset disabled={dirty || busy}>
              {renderCandidates(sameText)}
            </fieldset>
            {!sameText.length && (
              <p>{uiCopy["暂无使用这段文字的试听。生成后可在这里比较。"]}</p>
            )}
            <details>
              <summary>{uiCopy["历史声音样本 / 不同试听文本"]}</summary>
              <fieldset disabled={dirty || busy}>
                {renderCandidates(sounds.filter((c) => !sameText.includes(c)))}
              </fieldset>
            </details>
            <details>
              <summary>{uiCopy["声音描述与表演设定"]}</summary>
              {fields(["voice_description"])}
              <label className="creative-field">
                <span>{uiCopy["声音策略"]}</span>
                <select
                  value={draft.voice_mode || "stable"}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      voice_mode: e.target.value as "stable" | "expressive",
                    })
                  }
                >
                  <option value="stable">{uiCopy["稳定优先"]}</option>
                  <option value="expressive">{uiCopy["表演优先"]}</option>
                </select>
              </label>
              <Field
                label={uiCopy["基础语速（0.5–2）"]}
                value={String(draft.base_speed)}
                onChange={(v) => setDraft({ ...draft, base_speed: Number(v) })}
              />
              <Field
                label={uiCopy["基础音高（-12–12）"]}
                value={String(draft.base_pitch || 0)}
                onChange={(v) => setDraft({ ...draft, base_pitch: Number(v) })}
              />
              <p>{uiCopy["修改后须重新生成并选用试听。"]}</p>
            </details>
          </div>
        )}
        <TechnicalDetails title={uiCopy["角色版本信息"]} data={{ id, state, capabilities }} extra={<>
          <button
            className="btn"
            disabled={busy || dirty || !state?.confirmed}
            onClick={() => action("publish-library")}
          >
            {uiCopy["保存固定版本到跨项目角色库"]}</button>
        </>} />
        <ActionBar
          status={
            <>
              <b>
                {dirty
                  ? uiCopy["人物设定尚未保存"]
                  : state?.confirmed
                    ? uiCopy["角色已定稿"]
                    : uiCopy["选好形象与声音后，在总览统一确认"]}
              </b>
              <small>
                <button onClick={() => setTab("image")}>
                  {ready?.image ? uiCopy["✓ 形象就绪"] : uiCopy["补全形象"]}
                </button>{" "}
                ·{" "}
                <button onClick={() => setTab("voice")}>
                  {draft.role_kind === "background" ? uiCopy["背景群体无需配声"] : ready?.voice ? uiCopy["✓ 声音就绪"] : uiCopy["补全声音"]}
                </button>
              </small>
            </>
          }
        >
          <button className="btn" onClick={onBack}>
            {uiCopy["返回角色总览"]}</button>
          {dirty ? (
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => save(draft)}
            >
              {uiCopy["保存人物设定"]}</button>
          ) : (
            <button className="btn primary" onClick={onBack}>
              {uiCopy["完成编辑，返回总览 →"]}</button>
          )}
        </ActionBar>
      </fieldset>
    </article>
  );
}

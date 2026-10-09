"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { errorText } from "@/features/creative/copy";
import { remoteMode, aiTask } from "@/lib/api";
import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  Plus,
  Sparkles,
  Film,
  Video,
  Copy,
  Trash2,
  GripVertical,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  PanelLeftClose,
  PanelRightClose,
  PanelLeftOpen,
  PanelRightOpen,
  LayoutGrid,
  Rows3,
  MapPin,
  Volume2,
  RotateCcw,
  Check,
  Save,
  Download,
  Camera,
  ArrowUpRight,
  Maximize2,
  X,
} from "lucide-react";
import { useProject, useStore } from "@/lib/store";
import { type Scene, timecode } from "@/lib/types";
import { Badge, Empty, Modal, Preview, speak } from "@/components/ui";
import { CreativeWorkbench } from "./Creative";
import { CharacterEditor } from "./Characters";
import type { Character } from "@/lib/types";
let activeVoice: HTMLAudioElement | null = null;
function playSceneVoice(scene: Scene) {
  const urls = remoteMode
    ? [scene.audioUrl, scene.narrationUrl].filter((url): url is string => !!url)
    : [];
  if (!urls.length) {
    speak(scene.dialogue || scene.narration || "");
    return;
  }
  activeVoice?.pause();
  const play = (index: number) => {
    if (index >= urls.length) return;
    activeVoice = new Audio(urls[index]);
    activeVoice.onended = () => play(index + 1);
    void activeVoice.play().catch((e) => useStore.getState().notify(errorText(e)));
  };
  play(0);
}
export function Studio() {
  const p = useProject();
  return remoteMode && p?.creative ? (
    <CreativeWorkbench key={p.id} projectId={p.id} />
  ) : (
    <LegacyStudio />
  );
}
function LegacyStudio() {
  const p = useProject();
  const sceneId = useStore((s) => s.sceneId);
  const sc = p?.scenes.find((s) => s.id === sceneId) || p?.scenes[0];
  const [left, setLeft] = useState(true);
  const [right, setRight] = useState(true);
  const [tab, setTab] = useState<string>(uiCopy["大纲"]);
  const [layout, setLayout] = useState(false);
  const [preview, setPreview] = useState<Scene[] | null>(null);
  const [playing, setPlaying] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [editing, setEditing] = useState<Character | null>(null);
  const [remove, setRemove] = useState<Scene | null>(null);
  const [regenerate, setRegenerate] = useState(false);
  const tasks = useStore((s) => s.tasks);
  if (!p)
    return (
      <Empty
        title={uiCopy["准备开启你的故事"]}
        description={uiCopy["创建一个项目，即可进入分镜工作台。"]}
        action={
          <Link className="btn primary" href="/new">
            {uiCopy["新建项目"]}</Link>
        }
      />
    );
  const patch = (data: Partial<Scene>) =>
    sc && useStore.getState().patchScene(sc.id, data);
  const play = (list: Scene[]) => {
    setPreview(list);
    setSeconds(0);
    setPlaying(true);
  };
  return (
    <div className="studio-page">
      {remoteMode && (
        <button
          className="btn"
          onClick={async () => {
            const { api } = await import("@/lib/api");
            const { refreshRemote } = await import("@/lib/remote-store");
            await api(`/creative/projects/${p.id}/start`, "POST");
            await refreshRemote();
          }}
        >
          {uiCopy["升级创作流程 · 保留旧资产并补全角色绑定"]}</button>
      )}
      <header className="workspace-header">
        <div className="workspace-title">
          <Link href="/" className="icon-btn" aria-label={uiCopy["返回项目列表"]}>
            <ArrowLeft size={18} />
          </Link>
          <div>
            <h1>
              {p.name}
              <span className="badge subtle">{p.style}</span>
            </h1>
            <p>
              {p.scenes.length} {uiCopy["个分镜"]}<span>·</span>{" "}
              {timecode(p.scenes.reduce((n, s) => n + s.durationSec, 0))}{" "}
              <span>·</span> {p.ratio}
            </p>
          </div>
        </div>
        <div className="workspace-tabs">
          <Link href="/studio" className="active">
            <Film size={15} />
            {uiCopy["分镜"]}</Link>
          <Link href="/director">
            <Camera size={15} />
            {uiCopy["导演台"]}</Link>
          <Link href="/queue">
            <Rows3 size={15} />
            {uiCopy["队列"]}</Link>
        </div>
        <div className="button-row">
          <span className="save-status">
            <Check size={13} />
            {uiCopy["已自动保存"]}</span>
          <Link href="/export" className="btn primary small">
            <Download size={15} />
            {uiCopy["导出"]}</Link>
        </div>
      </header>
      <div
        className={`studio-layout ${left ? "" : "no-left"} ${right ? "" : "no-right"}`}
      >
        <aside className="outline-panel">
          {left ? (
            <>
              <div className="panel-top">
                <div className="filter-tabs">
                  {[uiCopy["大纲"], uiCopy["角色"]].map((t) => (
                    <button
                      className={tab === t ? "active" : ""}
                      key={t}
                      onClick={() => setTab(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                <button
                  className="icon-btn"
                  aria-label={uiCopy["收起大纲面板"]}
                  onClick={() => setLeft(false)}
                >
                  <PanelLeftClose size={16} />
                </button>
              </div>
              {tab === uiCopy["大纲"] ? (
                <div className="outline-content">
                  <span className="eyebrow">{uiCopy["STORY OVERVIEW"]}</span>
                  <label className="field">
                    {uiCopy["故事梗概"]}<textarea
                      rows={6}
                      value={p.description}
                      onChange={(e) =>
                        useStore
                          .getState()
                          .patchProject(p.id, { description: e.target.value })
                      }
                    />
                  </label>
                  <div className="tag-row">
                    <span>{p.style}</span>
                    <span>{uiCopy["短剧"]}</span>
                    <span>{p.ratio}</span>
                  </div>
                  <button
                    className="btn ai full"
                    onClick={() => setRegenerate(true)}
                  >
                    <Sparkles size={14} />
                    {uiCopy["重新生成剧本"]}</button>
                  <div className="outline-divider" />
                  <span className="eyebrow">
                    {uiCopy["SCENE LIST"]}<span>{p.scenes.length}</span>
                  </span>
                  <div className="scene-list">
                    {p.scenes.map((s, i) => (
                      <button
                        key={s.id}
                        className={sc?.id === s.id ? "active" : ""}
                        onClick={() => useStore.getState().selectScene(s.id)}
                      >
                        <span className="mono">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <div>
                          <strong>{s.title}</strong>
                          <small>
                            {s.shotType} · {s.cameraMove}
                          </small>
                        </div>
                        <span className="mono">{s.durationSec}{uiCopy["s"]}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="outline-content">
                  <div className="character-minis">
                    {p.characters.map((c) => (
                      <button key={c.id} onClick={() => setEditing(c)}>
                        <img src={c.image} alt={c.name} />
                        <span>
                          <strong>{c.name}</strong>
                          <small>{c.voice}</small>
                        </span>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  </div>
                  <Link href="/characters" className="btn secondary full">
                    <Plus size={14} />
                    {uiCopy["管理角色"]}</Link>
                </div>
              )}
            </>
          ) : (
            <button
              className="icon-btn collapsed-handle"
              aria-label={uiCopy["展开大纲面板"]}
              onClick={() => setLeft(true)}
            >
              <PanelLeftOpen size={16} />
            </button>
          )}
        </aside>
        <section className="storyboard-center">
          <div className="board-toolbar">
            <div>
              <h2>{uiCopy["分镜脚本"]}</h2>
              <span>{p.scenes.length} {uiCopy[" SHOTS"]}</span>
            </div>
            <div className="button-row">
              <button
                className="btn secondary small"
                onClick={() => useStore.getState().addScene()}
              >
                <Plus size={14} />
                {uiCopy["添加分镜"]}</button>
              <button
                className="btn ai small"
                onClick={() =>
                  useStore.getState().enqueue(
                    p.scenes.filter((s) => !s.image).map((s) => s.id),
                    uiCopy["图片"],
                  )
                }
              >
                <Sparkles size={14} />
                {uiCopy["批量生图"]}</button>
              <button
                className="btn ai small"
                onClick={() =>
                  useStore.getState().enqueue(
                    p.scenes
                      .filter((s) => s.image && s.status !== "done")
                      .map((s) => s.id),
                    uiCopy["视频"],
                  )
                }
              >
                <Video size={14} />
                {uiCopy["批量生视频"]}</button>
              <button
                className="icon-btn"
                aria-label={layout ? uiCopy["切换网格"] : uiCopy["切换列表"]}
                onClick={() => setLayout(!layout)}
              >
                {layout ? <LayoutGrid size={16} /> : <Rows3 size={16} />}
              </button>
            </div>
          </div>
          <div className="board-hint">
            <span>
              <i />
              {uiCopy["镜头准备就绪，故事正在发生"]}</span>
            <span>{uiCopy["拖动卡片可调整顺序"]}</span>
          </div>
          <div className={`shot-grid ${layout ? "shot-list-view" : ""}`}>
            {p.scenes.map((s, i) => {
              const progress =
                tasks.findLast(
                  (t) =>
                    t.sceneId === s.id &&
                    ["queued", "running"].includes(t.status),
                )?.progress || 0;
              return (
                <article
                  key={s.id}
                  className={`shot-card ${sc?.id === s.id ? "selected" : ""}`}
                  draggable
                  onDragStart={(e) =>
                    e.dataTransfer.setData("text/plain", s.id)
                  }
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    useStore
                      .getState()
                      .reorderScene(e.dataTransfer.getData("text/plain"), s.id);
                  }}
                  onClick={() => useStore.getState().selectScene(s.id)}
                >
                  <div className="shot-image">
                    {s.image ? (
                      <img
                        src={s.image}
                        alt={formatCopy("镜头{0}：{1}", i + 1, s.imagePrompt)}
                        loading="lazy"
                      />
                    ) : (
                      <div className="shot-placeholder">
                        <Film size={25} />
                        <span>{uiCopy["等待画面诞生"]}</span>
                      </div>
                    )}
                    <button
                      className="shot-number"
                      aria-label={formatCopy("选择分镜 {0}", i + 1)}
                      onClick={() => useStore.getState().selectScene(s.id)}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </button>
                    <span className="shot-duration mono">{s.durationSec}{uiCopy["s"]}</span>
                    {s.status === "failed" ? (
                      <div className="shot-failure">
                        <button
                          className="btn small danger-solid"
                          onClick={(e) => {
                            e.stopPropagation();
                            const t = tasks.findLast(
                              (t) =>
                                t.sceneId === s.id && t.status === "failed",
                            );
                            if (t) useStore.getState().retry(t.id);
                            else useStore.getState().enqueue([s.id], uiCopy["图片"]);
                          }}
                        >
                          <RotateCcw size={13} />
                          {uiCopy["重新生成"]}</button>
                      </div>
                    ) : s.image ? (
                      <button
                        aria-label={formatCopy("预览分镜 {0}", i + 1)}
                        className="shot-play"
                        onClick={(e) => {
                          e.stopPropagation();
                          play([s]);
                        }}
                      >
                        <Play size={21} />
                      </button>
                    ) : null}
                    {["image_pending", "video_pending"].includes(s.status) ? (
                      <div className="shot-generating">
                        <div className="shimmer" />
                        <span>
                          <Sparkles size={12} />
                          {remoteMode ? uiCopy["生成中"] : uiCopy["演示生成中"]}{" "}
                          <b>{progress}%</b>
                        </span>
                        <div className="progress-track">
                          <span
                            style={{ transform: `scaleX(${progress / 100})` }}
                          />
                        </div>
                      </div>
                    ) : null}
                    {s.directorData ? (
                      <span className="director-pin">
                        <MapPin size={13} />
                        {uiCopy["已摆位"]}</span>
                    ) : null}
                  </div>
                  <div className="shot-body">
                    <div className="shot-meta">
                      <span>{s.shotType}</span>
                      <span>{s.cameraMove}</span>
                      <span className={`state-dot ${s.status}`} />
                    </div>
                    <p className="shot-description">
                      {s.imagePrompt || uiCopy["点击分镜，在右侧描述你想呈现的画面。"]}
                    </p>
                    <div className="shot-dialogue">
                      <span>
                        {s.dialogue
                          ? `「${s.dialogue}」`
                          : s.narration
                            ? formatCopy("旁白：{0}", s.narration)
                            : uiCopy["暂无台词 / 环境声"]}
                      </span>
                      {s.dialogue || s.narration ? (
                        <button
                          className="icon-btn"
                          aria-label={formatCopy("试听分镜 {0} 台词", i + 1)}
                          onClick={(e) => {
                            e.stopPropagation();
                            playSceneVoice(s);
                          }}
                        >
                          <Volume2 size={13} />
                        </button>
                      ) : null}
                    </div>
                    <div className="shot-actions">
                      <button
                        onClick={() =>
                          useStore.getState().enqueue([s.id], uiCopy["图片"])
                        }
                        title={uiCopy["生成图片"]}
                      >
                        <Sparkles size={13} />
                        {uiCopy["生图"]}</button>
                      <button
                        disabled={!s.image}
                        onClick={() =>
                          useStore.getState().enqueue([s.id], uiCopy["视频"])
                        }
                        title={uiCopy["生成视频"]}
                      >
                        <Video size={13} />
                        {uiCopy["生视频"]}</button>
                      <button
                        aria-label={formatCopy("复制分镜 {0}", i + 1)}
                        onClick={() => useStore.getState().copyScene(s.id)}
                      >
                        <Copy size={13} />
                      </button>
                      <button
                        aria-label={formatCopy("删除分镜 {0}", i + 1)}
                        onClick={() => setRemove(s)}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
            <button
              className="add-shot"
              onClick={() => useStore.getState().addScene()}
            >
              <Plus size={28} />
              <span>{uiCopy["添加一个新镜头"]}</span>
            </button>
          </div>
        </section>
        <aside className="inspector-panel">
          {right ? (
            <>
              <div className="panel-top">
                <h3>
                  {uiCopy["分镜详情"]}{" "}
                  <span className="mono">
                    {sc
                      ? String(p.scenes.indexOf(sc) + 1).padStart(2, "0")
                      : ""}
                  </span>
                </h3>
                <button
                  className="icon-btn"
                  aria-label={uiCopy["收起详情面板"]}
                  onClick={() => setRight(false)}
                >
                  <PanelRightClose size={16} />
                </button>
              </div>
              {sc ? (
                <div className="inspector-content">
                  <Badge status={sc.status} />
                  <label className="field">
                    {uiCopy["镜头名称"]}<input
                      value={sc.title}
                      onChange={(e) => patch({ title: e.target.value })}
                    />
                  </label>
                  <div className="inspector-section">
                    <h4>
                      <Camera size={14} />
                      {uiCopy["镜头语言"]}</h4>
                    <label className="field">{uiCopy["景别"]}</label>
                    <div className="shot-type-buttons">
                      {[uiCopy["远景"], uiCopy["全景"], uiCopy["中景"], uiCopy["近景"], uiCopy["特写"]].map((t) => (
                        <button
                          key={t}
                          className={sc.shotType === t ? "active" : ""}
                          onClick={() => patch({ shotType: t })}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    <label className="field">
                      {uiCopy["运镜"]}<select
                        value={sc.cameraMove}
                        onChange={(e) => patch({ cameraMove: e.target.value })}
                      >
                        {Array.from(
                          new Set([
                            uiCopy["固定"],
                            uiCopy["缓推"],
                            uiCopy["拉远"],
                            uiCopy["摇镜"],
                            uiCopy["缓慢横移"],
                            uiCopy["跟随"],
                            sc.cameraMove,
                          ]),
                        ).map((t) => (
                          <option key={t}>{t}</option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      {uiCopy["镜头时长"]}<b className="mono">{sc.durationSec}{uiCopy["s"]}</b>
                      <input
                        type="range"
                        min={3}
                        max={10}
                        step={0.5}
                        value={sc.durationSec}
                        onChange={(e) =>
                          patch({ durationSec: +e.target.value })
                        }
                      />
                    </label>
                  </div>
                  <div className="inspector-section">
                    <h4>
                      {uiCopy["画面描述"]}{" "}
                      <button
                        className="text-action"
                        onClick={() => {
                          if (remoteMode) {
                            useStore.getState().notify(uiCopy["正在优化画面描述"]);
                            void aiTask<{ text: string }>("optimize-prompt", {
                              projectId: p.id,
                              sceneId: sc.id,
                            })
                              .then((result) =>
                                patch({ imagePrompt: result.text }),
                              )
                              .catch((e) =>
                                useStore.getState().notify(errorText(e)),
                              );
                            return;
                          }
                          patch({
                            imagePrompt:
                              sc.imagePrompt +
                              uiCopy[" 电影级构图，自然侧光，浅景深，细腻胶片质感。"],
                          });
                          useStore.getState().notify(uiCopy["已添加演示提示词优化"]);
                        }}
                      >
                        <Sparkles size={12} />
                        {uiCopy["AI 优化"]}</button>
                    </h4>
                    <textarea
                      aria-label={uiCopy["画面 Prompt"]}
                      rows={5}
                      value={sc.imagePrompt}
                      maxLength={2000}
                      onChange={(e) => patch({ imagePrompt: e.target.value })}
                    />
                    <span className="field-counter mono">
                      {sc.imagePrompt.length} / 2000
                    </span>
                  </div>
                  <div className="inspector-section">
                    <h4>
                      {uiCopy["台词 / 旁白"]}{" "}
                      <button
                        className="icon-btn"
                        aria-label={uiCopy["试听当前台词"]}
                        onClick={() => playSceneVoice(sc)}
                      >
                        <Volume2 size={14} />
                      </button>
                    </h4>
                    <textarea
                      aria-label={uiCopy["台词或旁白"]}
                      rows={3}
                      value={sc.dialogue}
                      onChange={(e) => patch({ dialogue: e.target.value })}
                    />
                    {remoteMode ? (
                      <label>
                        {uiCopy["旁白"]}<textarea
                          aria-label={uiCopy["旁白"]}
                          rows={2}
                          value={sc.narration || ""}
                          onChange={(e) => patch({ narration: e.target.value })}
                        />
                      </label>
                    ) : null}
                  </div>
                  <Link className="director-link" href="/director">
                    <Camera size={18} />
                    <span>
                      {sc.directorData
                        ? uiCopy["已设置场景与走位"]
                        : uiCopy["去 3D 导演台摆位"]}
                      <small>{uiCopy["让镜头，准确传达你的意图"]}</small>
                    </span>
                    <ChevronRight size={16} />
                  </Link>
                  <div className="inspector-section">
                    <h4>{uiCopy["生成参数"]}</h4>
                    <label className="field">
                      {uiCopy["模型档位"]}<select
                        value={sc.model}
                        onChange={(e) => patch({ model: e.target.value })}
                      >
                        <option
                          value={remoteMode ? "standard" : uiCopy["CineAI · 电影写实"]}
                        >
                          {uiCopy["CineAI · 电影写实"]}</option>
                        <option
                          value={remoteMode ? "turbo" : uiCopy["CineAI · 快速预览"]}
                        >
                          {uiCopy["CineAI · 快速预览"]}</option>
                      </select>
                    </label>
                    <label className="field">
                      {uiCopy["随机种子"]}<input
                        value={sc.seed}
                        onChange={(e) => patch({ seed: e.target.value })}
                      />
                    </label>
                  </div>
                  <button
                    className="btn primary full"
                    onClick={() =>
                      useStore
                        .getState()
                        .enqueue([sc.id], sc.image ? uiCopy["视频"] : uiCopy["图片"])
                    }
                  >
                    <Sparkles size={15} />
                    {sc.image ? uiCopy["生成视频片段"] : uiCopy["生成首帧画面"]}
                  </button>
                </div>
              ) : (
                <Empty />
              )}
            </>
          ) : (
            <button
              className="icon-btn collapsed-handle"
              aria-label={uiCopy["展开详情面板"]}
              onClick={() => setRight(true)}
            >
              <PanelRightOpen size={16} />
            </button>
          )}
        </aside>
      </div>
      <div className="studio-timeline">
        <div className="timeline-play">
          <button
            aria-label={uiCopy["全片预演"]}
            className="round-play"
            onClick={() => play(p.scenes)}
          >
            <Play size={16} />
          </button>
          <span>
            <b className="mono">
              {timecode(p.scenes.reduce((n, s) => n + s.durationSec, 0))}
            </b>
            <small>{uiCopy["全片预演"]}</small>
          </span>
        </div>
        <div className="timeline-clips">
          {p.scenes.map((s, i) => (
            <button
              key={s.id}
              className={`timeline-clip ${s.status} ${sc?.id === s.id ? "active" : ""}`}
              style={{ flexBasis: Math.max(65, s.durationSec * 12) }}
              onClick={() => useStore.getState().selectScene(s.id)}
            >
              {s.image ? <img src={s.image} alt="" /> : <Film size={16} />}
              <span className="mono">
                {String(i + 1).padStart(2, "0")}
                <small>{s.durationSec}{uiCopy["s"]}</small>
              </span>
            </button>
          ))}
        </div>
        <button
          className="icon-btn"
          aria-label={uiCopy["添加分镜到时间轴"]}
          onClick={() => useStore.getState().addScene()}
        >
          <Plus size={20} />
        </button>
      </div>
      {preview ? (
        <Modal
          title={uiCopy["分镜预演"]}
          wide
          onClose={() => {
            setPreview(null);
            setPlaying(false);
          }}
        >
          <div className="modal-body">
            <Preview
              scenes={preview}
              playing={playing}
              setPlaying={setPlaying}
              seconds={seconds}
              setSeconds={setSeconds}
            />
          </div>
        </Modal>
      ) : null}
      {editing ? (
        <CharacterEditor
          character={editing}
          onClose={() => setEditing(null)}
          onSave={(c) => {
            useStore.getState().saveCharacter(c);
            setEditing(null);
          }}
        />
      ) : null}
      {remove ? (
        <Modal title={uiCopy["删除这个分镜？"]} onClose={() => setRemove(null)}>
          <div className="modal-body">
            <p>「{remove.title}{uiCopy["」将从当前项目移除。"]}</p>
            <button
              className="btn danger-solid"
              onClick={() => {
                useStore.getState().removeScene(remove.id);
                setRemove(null);
              }}
            >
              {uiCopy["删除分镜"]}</button>
          </div>
        </Modal>
      ) : null}
      {regenerate ? (
        <Modal title={uiCopy["重新构思剧本"]} onClose={() => setRegenerate(false)}>
          <div className="modal-body">
            <p>{uiCopy["根据当前大纲开启一个新的创作向导，原项目继续保留。"]}</p>
            <Link
              className="btn primary"
              href="/new"
              onClick={() => useStore.getState().setIdea(p.description)}
            >
              <Sparkles size={16} />
              {uiCopy["开始重新创作"]}</Link>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

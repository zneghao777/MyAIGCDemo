"use client";
import { copy } from "./creative/copy";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { ActionBar } from "./creative/shared";
import { ReadinessRows } from "./creative/ReadinessRows";
import { TechnicalDetails } from "./creative/TechnicalDetails";
import { taskStatusLabel } from "./creative/copy";
import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { api, apiBase, remoteMode, waitTask } from "@/lib/api";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Download,
  Film,
  Music2,
  Sparkles,
  ImageDown,
  FileJson,
  Settings2,
  X,
  MonitorPlay,
} from "lucide-react";
import { refreshRemote } from "@/lib/remote-store";
import type { Project } from "@/lib/types";
import { useProject, useStore } from "@/lib/store";
import { Empty, Preview } from "@/components/ui";
import {
  coverImage,
  downloadBlob,
  downloadProject,
  recordPreview,
} from "@/lib/export";
type SavedExport = {
  id: string;
  status: string;
  url: string;
  coverUrl: string;
  stale?: boolean;
  label?: string;
  manualAcceptance?: boolean;
  durationSec?: number;
  settings: {
    format: string;
    manifest?: unknown;
    resolution?: string;
    fit_mode?: "pad" | "crop";
    fitMode?: "pad" | "crop";
    timing_mode?: "source" | "planned";
    timingMode?: "source" | "planned";
    fps?: number;
    subtitles?: boolean;
    music?: boolean;
    mood?: string;
    bgm_asset_id?: string;
    intro?: boolean;
    watermark?: boolean;
    purpose?: "preview" | "export";
    source_mode?: "auto" | "storyboard";
    sourceMode?: "auto" | "storyboard";
    acceptanceLabel?: string;
    renderLog?: { sceneId?: string; startSec?: number; endSec?: number; outputWidth?: number; outputHeight?: number }[];
    wholeAcceptance?: { status: string; notes: string; checked_at: string };
  };
};
export function Export() {
  const project = useProject();
  return <ExportWorkspace key={project?.id || "empty"}/>;
}
function ExportWorkspace() {
  const p = useProject();
  const [resolution, setResolution] = useState("source");
  const [fitMode, setFitMode] = useState<"pad" | "crop">("pad");
  const [timingMode, setTimingMode] = useState<"source" | "planned">("source");
  const [fps, setFps] = useState(24);
  const [format, setFormat] = useState("MP4");
  const [subtitles, setSubtitles] = useState(true);
  const [music, setMusic] = useState(false);
  const [bgmAssetId, setBgmAssetId] = useState("");
  const [bgms, setBgms] = useState<
    { id: string; url: string; createdAt: string }[]
  >([]);
  const [watermark, setWatermark] = useState(false);
  const [intro, setIntro] = useState(false);
  const [mood, setMood] = useState<string>(uiCopy["悬疑"]);
  const [playing, setPlaying] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [progress, setProgress] = useState(-1);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<unknown>("");
  const [outputUrl, setOutputUrl] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewMode, setPreviewMode] = useState<"auto" | "storyboard">(p?.scenes.some(scene => scene.videoUrl) ? "auto" : "storyboard");
  const [rendering, setRendering] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [coverUrl, setCoverUrl] = useState("");
  const [history, setHistory] = useState<SavedExport[]>([]);
  const [capabilities, setCapabilities] = useState({ intro: false, watermark: false, bgmPresets: false });
  const [issues, setIssues] = useState<string[]>([]);
  const taskIdRef = useRef("");
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    setBlob(null);
    setOutputUrl("");
    setPreviewUrl("");
    setProgress(-1);
    setPlaying(false);
    setSeconds(0);
    abort.current?.abort();
  }, [p?.id]);
  useEffect(() => {
    if (!remoteMode || !p?.id) return;
    const controller = new AbortController();
    void api<SavedExport[]>(
      `/projects/${p.id}/exports`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((jobs) => {
        setHistory(jobs);
        const latest = jobs.find((job) => job.status === "done" && job.url);
        if (latest) {
          const lastPreview = jobs.find(job => job.status === "done" && job.url && job.settings.purpose === "preview");
          setPreviewUrl(latest.settings.purpose === "preview" ? latest.url : "");

          setPreviewMode(lastPreview?.settings.source_mode || lastPreview?.settings.sourceMode || (p.scenes.some(scene=>scene.videoUrl) ? "auto" : "storyboard"));
          setOutputUrl(jobs.find(job => job.status === "done" && job.url && job.settings.purpose !== "preview")?.url || "");
          setCoverUrl(latest.coverUrl);
          setFormat(latest.settings.format);
          setResolution(latest.settings.resolution || "source");
          setFitMode(latest.settings.fit_mode || latest.settings.fitMode || "pad");
          setTimingMode(latest.settings.timing_mode || latest.settings.timingMode || "source");
          setFps(latest.settings.fps || 24);
          setSubtitles(latest.settings.subtitles ?? true);
          setMusic(latest.settings.music || false);
          setBgmAssetId(latest.settings.bgm_asset_id || "");
          setMood(latest.settings.mood || uiCopy["悬疑"]);
          setIntro(latest.settings.intro || false);
          setWatermark(latest.settings.watermark || false);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => controller.abort();
  }, [p?.id, p?.status]);
  useEffect(() => {
    if (remoteMode && p?.id)
      void api<{ id: string; url: string; createdAt: string }[]>(
        `/projects/${p.id}/bgm`,
      )
        .then(setBgms)
        .catch(() => {});
  }, [p?.id]);
  useEffect(() => {
    if (!remoteMode || !p?.creative) return;
    const controller = new AbortController();
    void api<{ issues: string[]; capabilities: typeof capabilities }>(
      `/creative/projects/${p.id}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((x) => { setIssues(x.issues); setCapabilities(x.capabilities); })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => controller.abort();
  }, [p?.id, p?.creative]);
  if (!p)
    return (
      <Empty
        title={uiCopy["还没有可以预演的故事"]}
        action={
          <Link href="/new" className="btn primary">
            {uiCopy["创建项目"]}</Link>
        }
      />
    );
  const settings = {
    resolution,
    fitMode,
    timingMode,
    fps,
    format,
    subtitles,
    music,
    bgmAssetId: bgmAssetId || null,
    mood,
    watermark: watermark && capabilities.watermark,
    intro: intro && capabilities.intro,
  };
  const ready = p.scenes.filter((s) => s.videoUrl).length;
  const previewReady = p.scenes.filter(s => previewMode === "storyboard" ? s.image : s.videoUrl).length;
  const activeUrl = previewUrl || outputUrl;
  const displayedJob = history.find(job => job.url === activeUrl);
  function sceneRange(index: number) {
    const rendered = displayedJob?.settings.renderLog?.find(log => log.sceneId === p!.scenes[index].id && log.startSec != null);
    const start = rendered?.startSec ?? p!.scenes.slice(0, index).reduce((sum, scene) => sum + scene.durationSec, 0);
    return { start, end: rendered?.endSec ?? start + p!.scenes[index].durationSec };
  }
  async function record(preview = false) {
    if (!p) return;
    setPlaying(false);
    setError("");
    setBlob(null);
    setProgress(0);
    setRendering(true);
    abort.current = new AbortController();
    try {
      if (remoteMode) {
        const job = await api<{ exportJobId: string; taskId: string }>(
          `/projects/${p.id}/${preview ? "preview" : "exports"}`,
          "POST",
          { ...settings, sourceMode: preview ? previewMode : "auto" },
        );
        taskIdRef.current = job.taskId;
        await waitTask(job.taskId, setProgress, abort.current.signal);
        const result = await api<{ url: string; coverUrl: string }>(
          `/exports/${job.exportJobId}`,
        );
        if (preview) { setPreviewUrl(result.url); }
        else { setOutputUrl(result.url); setPreviewUrl(""); setCoverUrl(result.coverUrl); }
        setHistory(await api<SavedExport[]>(`/projects/${p.id}/exports`));
        useStore.getState().notify(preview ? formatCopy("{0}已就绪，请播放检查", previewMode === "storyboard" ? uiCopy["静态分镜配声预演"] : uiCopy["动态带声预览"]) : "成片已合成，可以预览与下载");
        return;
      }
      const b = await recordPreview(
        p,
        setProgress,
        subtitles,
        fps,
        abort.current.signal,
      );
      setBlob(b);
      useStore.getState().patchProject(p.id, { status: uiCopy["已导出"] });
      useStore.getState().notify(uiCopy["分镜预演已录制完成"]);
    } catch (e) {
      setError(e);
      setProgress(-1);
    } finally {
      setRendering(false);
    }
  }
  return (
    <div className="standard-page export-page">
      <div className="page-breadcrumb">
        <Link href="/studio">
          <ArrowLeft size={15} />
          {uiCopy["返回工作台"]}</Link>
        <span>/</span>
        <span>{uiCopy["预览与导出"]}</span>
      </div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">{uiCopy["THE FINAL CUT"]}</span>
          <h1>预览与导出</h1>
          <p>{p.name} {uiCopy["· 合成预览与导出设置"]}</p>
        </div>
        <span className="badge subtle">
          <Film size={13} />
          {ready} / {p.scenes.length} {"镜已采用视频"}</span>
      </div>
      <div className="export-columns">
        <section className="export-preview-panel">
          <div className="panel-heading">
            <MonitorPlay size={16} />
            <h2>{uiCopy["全片带声预览"]}</h2>
            <span className="mono">
              {p.ratio} · {fps} {uiCopy["FPS"]}</span>
          </div>
          <div className={`cinema-preview ${previewUrl || outputUrl ? "has-video" : ""}`}>
            {(previewUrl || outputUrl) ? <video ref={videoRef} controls playsInline preload="metadata" src={previewUrl || outputUrl}
              aria-label={uiCopy["全片带声预览"]} style={{width: "100%", height: "min(68vh, 720px)", objectFit: "contain", background: "#080a0d"}}
              onTimeUpdate={e => { setSeconds(e.currentTarget.currentTime); }} /> :
            <Preview
              scenes={p.scenes}
              ratio={p.ratio}
              playing={playing}
              setPlaying={setPlaying}
              seconds={seconds}
              setSeconds={setSeconds}
              subtitles={subtitles}
            />
            }
          </div>
          <div className="film-strip">
            {p.scenes.map((s, i) => (
              <button
                key={s.id}
                onClick={() => {
                  const time = sceneRange(i).start;
                  if (videoRef.current) videoRef.current.currentTime = time;
                  setSeconds(
                    p.scenes.slice(0, i).reduce((n, s) => n + s.durationSec, 0),
                  );
                  setPlaying(false);
                }}
                aria-label={formatCopy("跳到分镜 {0}", i + 1)}
              >
                {s.image ? <img src={s.image} alt="" /> : <Film size={15} />}
                <span>{String(i + 1).padStart(2, "0")}</span>
              </button>
            ))}
          </div>
          {remoteMode && <div className="cs-preview-actions">
            <label className="creative-field">{uiCopy["预演画面来源"]}<select value={previewMode} onChange={e => setPreviewMode(e.target.value as "auto" | "storyboard")}><option value="storyboard">{uiCopy["静态分镜配声预演 · 强制使用当前静帧"]}</option><option value="auto">{uiCopy["动态带声预览 · 优先使用已生成视频"]}</option></select></label>
            <button className="btn primary" disabled={rendering || previewReady !== p.scenes.length || !previewReady || issues.length > 0 || (!!p.creative && !p.creative.shots_confirmed)} onClick={() => void record(true)}>
              {rendering ? formatCopy("合成中 {0}%", progress) : formatCopy("更新{0}", previewMode === "storyboard" ? uiCopy["静态分镜配声预演"] : uiCopy["动态带声预览"])}
            </button>
            <p className="helper">{uiCopy["本地合成，复用已有对白、字幕与可播放音效，不调用远端生成。已有视频也可检查当前静帧与配声时序。"]}</p>
            {history.some(job => job.url === (previewUrl || outputUrl) && job.stale) && <p className="creative-warning">{uiCopy["当前播放的是旧版本，请更新预演并重新确认。"]}</p>}
          </div>}
          <section className="export-readiness-panel">
            {p.creative && (
              <div>
                <h3>{"作品素材就绪情况"}</h3>
                <ReadinessRows locationDone={(p.creative.plan?.locations || []).filter(location => p.creative?.locations?.[location.id]?.confirmed).length} locationTotal={p.creative.plan?.locations.length || 0} previewConfirmed={!!p.creative.preview_confirmation && !p.creative.preview_confirmation.stale} accepted={p.scenes.filter(scene => !!scene.videoUrl).length} total={p.scenes.length} />
                {issues.length ? (
                  <ul>
                    {issues.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                ) : (
                  <p>{uiCopy["结构检查通过，请自行预览确认外观与表演。"]}</p>
                )}
                <p>
                  {"按当前采用区间合成视频，保留所选原声或后期配音，不会重复加入同一句台词。"}</p>
                <Link href="/studio">{uiCopy["返回处理过期资产"]}</Link>
              </div>
            )}

          </section>
          <details className="creative-editor"><summary>{uiCopy["每镜时间线与问题定位"]}</summary>{p.scenes.map((scene, index) => {
            const { start, end } = sceneRange(index);
            const shot = scene.creative?.shot;
            return <article key={scene.id}><h4>{index + 1}. {scene.title} · {start.toFixed(2)}–{end.toFixed(2)}{uiCopy["s · 成片本镜"]}{(end - start).toFixed(2)}{uiCopy["s（计划"]}{scene.durationSec.toFixed(2)}{uiCopy["s）"]}</h4>
              {(shot?.action_steps || []).map(step => <p key={step.id}>{uiCopy["动作"]}{step.start_sec.toFixed(2)}–{step.end_sec.toFixed(2)}{uiCopy["s："]}{step.description}{step.trigger_sec != null ? formatCopy(" · 触发 {0}s", step.trigger_sec.toFixed(2)) : ""}</p>)}
              {(shot?.subtitle_cues || []).map(cue => <p key={cue.id}>{uiCopy["字幕"]}{cue.start_sec.toFixed(2)}–{cue.end_sec.toFixed(2)}{uiCopy["s："]}{cue.text}</p>)}
              {!![...shot?.lines || [], ...shot?.narration || []].length && !shot?.subtitles_calibrated && <p className="creative-warning">{uiCopy["字幕分句时间待人工校准；未声明自动精确对齐。"]}</p>}

              <Link href={`/studio?project=${encodeURIComponent(p.id)}&scene=${encodeURIComponent(scene.id)}`} onClick={() => useStore.setState({ sceneId: scene.id })}>{uiCopy["定位本镜编辑与问题记录"]}</Link>
            </article>;
          })}</details>
          <p className="preview-note">
            <Sparkles size={14} />
            {remoteMode
              ? p.scenes.some((s) => s.videoUrl)
                ? uiCopy["使用已生成的视频镜头合成，保留配音、字幕与音效。"]
                : uiCopy["服务端合成支持真实配音与字幕，画面为静帧运镜的分镜动态预演。"]
              : uiCopy["当前展示静帧分镜预演。真实视频、配音与混音将在后端接入后生成。"]}
          </p>
        </section>
        <section className="export-settings">
          <div className="form-panel">
            <div className="panel-heading">
              <Settings2 size={17} />
              <h2>{uiCopy["导出设置"]}</h2>
              <span className="badge subtle">
                {remoteMode ? "成片规格" : uiCopy["保存到项目文件"]}
              </span>
            </div>
            <label className="field">分辨率<select aria-label="分辨率" value={resolution === "1080p" ? "1080P" : resolution} onChange={e => setResolution(e.target.value)}>{["source", "480P", "768P", "1080P", "2K", "4K", "720p"].map(r => <option key={r} value={r}>{r === "source" ? "保留原片尺寸（推荐）" : r}</option>)}</select></label>
            <details className="export-note"><summary>尺寸与本地放大说明</summary><p className="helper">{uiCopy["原片尺寸按第一镜实际视频读取；不同尺寸镜头统一到同一画布。480P、768P、1080P、2K、4K 均可导出。本地放大不会增加原片细节，也不会调用云端超分。"]}</p></details>
            <div className="field-grid">
              <label className="field">{uiCopy["画面适配"]}<select aria-label={uiCopy["画面适配"]} value={fitMode} onChange={e => setFitMode(e.target.value as "pad" | "crop")}><option value="pad">{uiCopy["完整画面 · 等比缩放与留边"]}</option><option value="crop">{uiCopy["铺满画布 · 等比缩放并裁边"]}</option></select></label>
              <label className="field">{uiCopy["镜头时长"]}<select aria-label={uiCopy["镜头时长"]} value={timingMode} onChange={e => setTimingMode(e.target.value as "source" | "planned")}><option value="source">{uiCopy["原速 · 保留原视频完整时长"]}</option><option value="planned">{uiCopy["原速 · 按分镜时长裁尾或补静止尾帧"]}</option></select></label>
            </div>
            <details className="export-note"><summary>原速与完整镜长说明</summary><p className="helper">{uiCopy["导出不自动调整视频或配声速度。保留完整原片时，全片时长可能与分镜计划不同；请按新成片重新检查口型、字幕与衔接。配声过长会提示修正，避免暗中慢放视频或截断台词。"]}</p></details>
            <div className="field-grid">
              <label className="field">
                {uiCopy["帧率"]}<select value={fps} onChange={(e) => setFps(+e.target.value)}>
                  <option value={24}>{uiCopy["24 fps · 电影感"]}</option>
                  <option value={30}>{uiCopy["30 fps · 流畅"]}</option>
                </select>
              </label>
              <label className="field">
                {uiCopy["目标格式"]}<select
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                >
                  <option>{uiCopy["MP4"]}</option>
                  <option>{uiCopy["WebM"]}</option>
                </select>
              </label>
            </div>
            <div className="settings-switches">
              {[
                {
                  label: uiCopy["硬字幕"],
                  desc: uiCopy["将台词显示在画面底部"],
                  value: subtitles,
                  set: setSubtitles,
                },
                {
                  available: true,
                  label: uiCopy["背景音乐"],
                  desc: remoteMode
                    ? uiCopy["使用服务端 BGM 素材混音"]
                    : uiCopy["随项目设置保存，待后端混音"],
                  value: music,
                  set: setMusic,
                },
                {
                  available: capabilities.intro,
                  label: uiCopy["片头片尾"],
                  desc: remoteMode ? uiCopy["使用服务端已配置素材"] : uiCopy["随项目设置保存"],
                  value: intro,
                  set: setIntro,
                },
                {
                  available: capabilities.watermark,
                  label: uiCopy["品牌水印"],
                  desc: remoteMode ? uiCopy["使用服务端已配置素材"] : uiCopy["随项目设置保存"],
                  value: watermark,
                  set: setWatermark,
                },
              ].filter(o => o.available !== false).map((o) => (
                <label className="switch-row" key={o.label}>
                  <span>
                    {o.label}
                    <small>{o.desc}</small>
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    checked={o.value}
                    onChange={(e) => o.set(e.target.checked)}
                  />
                </label>
              ))}
            </div>
            {!capabilities.intro && <p className="helper">{copy.noIntro}</p>}
            {!capabilities.watermark && <p className="helper">{copy.noWatermark}</p>}
            {!capabilities.bgmPresets && <p className="helper">{copy.noBgmPresets}</p>}
            {music ? (
              <div className="music-choices">
                {remoteMode && (
                  <>
                    <label className="field">
                      {uiCopy["上传背景音乐（最多20MB；只重新混音）"]}<input
                        type="file"
                        accept="audio/*"
                        onChange={async (e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          const data = new FormData();
                          data.append("file", file);
                          try {
                            const r = await fetch(
                              `${apiBase}/api/projects/${p.id}/bgm`,
                              { method: "POST", body: data },
                            );
                            const a = await r.json();
                            if (!r.ok)
                              throw new Error(a.error?.message || uiCopy["上传失败"]);
                            setBgms((current) => [a, ...current]);
                            setBgmAssetId(a.id);
                          } catch (err) {
                            setError(err);
                          }
                        }}
                      />
                    </label>
                    <select
                      aria-label={uiCopy["已上传背景音乐"]}
                      value={bgmAssetId}
                      onChange={(e) => setBgmAssetId(e.target.value)}
                    >
                      <option value="">{capabilities.bgmPresets ? uiCopy["使用服务端曲风素材"] : copy.selectUploadedMusic}</option>
                      {bgms.map((a, index) => (
                        <option key={a.id} value={a.id}>
                          {new Date(a.createdAt).toLocaleString()} ·{" "}
                          {copy.musicItem(index + 1)}
                        </option>
                      ))}
                    </select>
                    {bgms.find((a) => a.id === bgmAssetId) && (
                      <audio
                        controls
                        src={bgms.find((a) => a.id === bgmAssetId)!.url}
                      />
                    )}
                  </>
                )}

                {capabilities.bgmPresets && <>
                <label className="field">{uiCopy["背景音乐曲风"]}</label>
                <div className="tag-row">
                  {[uiCopy["悬疑"], uiCopy["温情"], uiCopy["热血"], uiCopy["轻快"]].map((m) => (
                    <button
                      className={mood === m ? "active" : ""}
                      key={m}
                      onClick={() => setMood(m)}
                    >
                      <Music2 size={13} />
                      {m}
                    </button>
                  ))}
                </div>
                </>}
                {!capabilities.bgmPresets && !bgmAssetId && <p className="helper">{copy.chooseMusic}</p>}
              </div>
            ) : null}
          </div>
          <div className="export-action-panel">
            <span className="eyebrow">{uiCopy["READY WHEN YOU ARE"]}</span>
            <h3>
              {blob || outputUrl
                ? "成片文件已生成，可以预览与下载。"
                : uiCopy["先看看，故事在画面里是什么样子。"]}
            </h3>
            <p>
              {remoteMode
                ? uiCopy["按所选设置在本机生成成片；配音按实际时长对齐，结果保存到本地。"]
                : uiCopy["本地录制：720p WebM，每镜 1 秒，无声。上方设置仅保存在项目文件中。"]}
            </p>
            {outputUrl ? (
              <>
                <p>{uiCopy["完整成片可在左侧播放器检查。"]}</p>
                <a
                  className="btn secondary full"
                  href={outputUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {uiCopy["打开 / 下载"]}{format} {uiCopy["成片"]}</a>
                {coverUrl ? (
                  <CoverDownload url={coverUrl} />
                ) : null}
              </>
            ) : rendering ? (
              <div className="export-progress">
                <div>
                  <span>
                    {remoteMode ? "正在本机合成…" : uiCopy["正在录制分镜预演…"]}
                  </span>
                  <b className="mono">{progress}%</b>
                </div>
                <div className="progress-track">
                  <span style={{ transform: `scaleX(${progress / 100})` }} />
                </div>
                <button
                  className="text-action"
                  onClick={() => {
                    abort.current?.abort();
                    if (remoteMode && taskIdRef.current)
                      void api(
                        `/tasks/${taskIdRef.current}/cancel`,
                        "POST",
                      ).catch((e) => setError(e));
                  }}
                >
                  <X size={13} />
                  {uiCopy["取消录制"]}</button>
              </div>
            ) : blob ? (
              <button
                className="btn secondary full"
                onClick={() => downloadBlob(blob, formatCopy("{0}-分镜预演.webm", p.name))}
              >
                <Download size={18} />
                {uiCopy["下载预演 WebM"]}</button>
            ) : <p className="helper">使用底部导出按钮按当前设置合成，文件生成后可在这里播放与下载。</p>}
            {history.length > 0 && (
              <details>
                <summary>{uiCopy["历史成片与实际版本引用（"]}{history.length}）</summary>
                {history.map((job) => (
                  <div key={job.id}>
                    <p>
                      {job.label || (job.settings.purpose === "preview" ? uiCopy["带声预览"] : uiCopy["成片"])} · {taskStatusLabel(job.status)} · {job.stale ? "素材已更新" : "可预览"} ·{" "}
                      {job.stale ? uiCopy["已过期，旧成片保留"] : uiCopy["当前版本"]}
                    </p>
                    {job.url && (
                      <button
                        className="btn"
                        onClick={() => {
                          setPreviewUrl(job.url);
                          setCoverUrl(job.coverUrl);
                        }}
                      >
                        {uiCopy["播放此版本"]}</button>
                    )}
                    <TechnicalDetails data={job} />
                  </div>
                ))}
              </details>
            )}
            <ErrorNotice error={error} />
            <div className="export-secondary">
              <button
                className="btn secondary"
                onClick={() => downloadProject(p, settings)}
              >
                <FileJson size={15} />
                {uiCopy["项目文件"]}</button>
              <button
                className="btn secondary"
                onClick={() =>
                  coverImage(p.cover, p.name).catch(() =>
                    useStore.getState().notify(uiCopy["封面导出失败，请重试"]),
                  )
                }
              >
                <ImageDown size={15} />
                {uiCopy["导出封面"]}</button>
            </div>
            {blob ? (
              <button
                className="text-action"
                onClick={() => {
                  setBlob(null);
                  setProgress(-1);
                }}
              >
                {uiCopy["重新录制"]}</button>
            ) : null}
          </div>
        </section>
      </div>
      <ActionBar status={<><b>预览并导出作品</b><small>{issues.length ? issues.join("；") : "本地合成 · 保留原片尺寸、原速与完整镜长"}</small></>}><button className="btn primary" disabled={rendering || ready !== p.scenes.length || !ready || issues.length > 0 || (!!p.creative && !p.creative.shots_confirmed)} onClick={() => void record()}>{rendering ? `合成中 ${progress}%` : p.scenes.every(s=>s.creative?.review_current) ? "导出成片" : "导出待检查版本"}</button></ActionBar>
    </div>
  );
}

export function CoverDownload({ url }: { url: string }) {
  return <a className="btn secondary full" href={url} target="_blank" rel="noreferrer"><ImageDown size={16} />{uiCopy["下载封面"]}</a>;
}

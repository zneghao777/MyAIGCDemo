"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { errorText } from "@/features/creative/copy";
import { api, remoteMode, waitTask } from "@/lib/api";
import { useEffect, useRef } from "react";
import { X, Film, Play, Pause, Volume2, VolumeX } from "lucide-react";
import { statusText, timecode, type Scene } from "@/lib/types";
import { useStore } from "@/lib/store";
export function Badge({ status }: { status: Scene["status"] }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {statusText[status]}
    </span>
  );
}
export function Empty({
  title = uiCopy["还没有分镜"],
  description = uiCopy["添加第一个分镜，让故事开始。"],
  action,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Film size={40} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      className={`modal ${wide ? "wide" : ""}`}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button aria-label={uiCopy["关闭弹窗"]} className="icon-btn" onClick={onClose}>
          <X size={19} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function speak(text: string, voice: string = uiCopy["女声 · 冷静"]) {
  if (remoteMode) {
    const projectId = useStore.getState().activeId;
    if (!projectId) { useStore.getState().notify(uiCopy["请先保存项目，再试听真实配音"]); return; }
    void (async () => {
      const voices = await api<{ label: string; voiceId: string }[]>("/tts/voices");
      const voiceId = voices.find(v => v.label === voice)?.voiceId;
      useStore.getState().notify(uiCopy["正在合成试听配音"]);
      const { taskId } = await api<{ taskId: string }>("/tts/preview", "POST", { projectId, text: text || uiCopy["总有人，在等一封信。"], voiceId });
      const task = await waitTask(taskId);
      if (task.result?.url) await new Audio(task.result.url).play();
    })().catch(e => useStore.getState().notify(errorText(e)));
    return;
  }
  if (!("speechSynthesis" in window)) {
    useStore.getState().notify(uiCopy["当前浏览器不支持语音试听"]);
    return;
  }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text || uiCopy["总有人，在等一封信。"]);
  u.lang = "zh-CN";
  u.rate = 0.88;
  u.pitch = voice.startsWith(uiCopy["男"]) ? 0.8 : 1.1;
  speechSynthesis.speak(u);
}
export function Preview({
  scenes,
  playing,
  setPlaying,
  seconds,
  setSeconds,
  ratio = "16:9",
  subtitles = true,
}: {
  scenes: Scene[];
  playing: boolean;
  setPlaying: (b: boolean) => void;
  seconds: number;
  setSeconds: (n: number) => void;
  ratio?: string;
  subtitles?: boolean;
}) {
  const total = scenes.reduce((n, s) => n + s.durationSec, 0);
  const [w, h] = ratio.split(":").map(Number);
  let elapsed = 0;
  const scene =
    scenes.find((s) => {
      elapsed += s.durationSec;
      return seconds < elapsed;
    }) || scenes.at(-1);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      if (seconds + 0.1 >= total) {
        setSeconds(0);
        setPlaying(false);
      } else setSeconds(seconds + 0.1);
    }, 100);
    return () => clearInterval(timer);
  }, [playing, seconds, total, setSeconds, setPlaying]);
  return (
    <div className="preview">
      <div
        className={`preview-frame ${playing ? "playing" : ""}`}
        style={{ aspectRatio: `${w}/${h}` }}
      >
        {scene?.image ? (
          <img src={scene.image} alt={scene.imagePrompt} />
        ) : (
          <div className="empty">
            <Film />
            <p>{uiCopy["此分镜尚无画面"]}</p>
          </div>
        )}
        <span className="preview-label">{uiCopy["STORYBOARD PREVIEW"]}</span>
        {subtitles && scene?.dialogue ? (
          <p className="subtitle">{scene.dialogue}</p>
        ) : null}
        <button
          className="big-play"
          aria-label={playing ? uiCopy["暂停预演"] : uiCopy["播放预演"]}
          onClick={() => setPlaying(!playing)}
        >
          {playing ? <Pause /> : <Play />}
        </button>
      </div>
      <div className="player-controls">
        <button
          className="icon-btn"
          aria-label={playing ? uiCopy["暂停"] : uiCopy["播放"]}
          onClick={() => setPlaying(!playing)}
        >
          {playing ? <Pause size={17} /> : <Play size={17} />}
        </button>
        <span className="mono">
          {timecode(seconds)} <small>/ {timecode(total)}</small>
        </span>
        <input
          aria-label={uiCopy["预览进度"]}
          type="range"
          min={0}
          max={total || 1}
          step={0.1}
          value={seconds}
          onChange={(e) => setSeconds(+e.target.value)}
        />
        <Film size={16} />
      </div>
      <p className="helper">{remoteMode ? uiCopy["静帧草览 · 在预览与导出页生成带声预览，检查完整配音与字幕"] : uiCopy["分镜静帧预演 · 视频生成使用演示数据"]}</p>
    </div>
  );
}

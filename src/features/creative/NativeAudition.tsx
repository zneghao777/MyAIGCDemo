"use client";
import { useEffect, useRef, useState } from "react";
import type { Project } from "@/lib/types";

type AuditionScene = {
  title: string; videoUrl?: string;
  creative?: {
    video?: { [key: string]: unknown };
    edit?: { in_sec: number; out_sec: number };
    shot?: { lines?: { speaker_id?: string | null; text?: string }[]; narration?: { speaker_id?: string | null; text?: string }[] };
  };
};
export function nativeAuditionClips(scenes: AuditionScene[], speaker: string) {
  const relevant = new Set(scenes.filter(scene =>
    [...scene.creative?.shot?.lines || [], ...scene.creative?.shot?.narration || []]
      .some(line => (line.speaker_id || "narrator") === speaker),
  ).map(scene => scene.videoUrl));
  const clips: { url: string; start: number; end: number; title: string }[] = [];
  for (const scene of scenes) {
    if (!scene.videoUrl || !relevant.has(scene.videoUrl) || scene.creative?.video?.sound_strategy !== "model_audio") continue;
    const start = scene.creative.edit?.in_sec || 0;
    const end = scene.creative.edit?.out_sec || Number(scene.creative.video.duration || 0);
    const previous = clips.at(-1);
    if (previous?.url === scene.videoUrl && Math.abs(previous.end - start) < .01) {
      previous.end = end;
      previous.title += ` → ${scene.title}`;
    } else clips.push({ url: scene.videoUrl, start, end, title: scene.title });
  }
  return clips;
}

export function NativeAudition({ project, speaker }: { project: Project; speaker: string }) {
  const clips = nativeAuditionClips(project.scenes, speaker);
  const [index, setIndex] = useState(0), [playing, setPlaying] = useState(false);
  const ref = useRef<HTMLVideoElement>(null);
  const key = clips.map(clip => `${clip.url}:${clip.start}:${clip.end}`).join("|");
  useEffect(() => { setPlaying(false); setIndex(0); }, [speaker, key]);
  useEffect(() => { if (playing) void ref.current?.play().catch(() => setPlaying(false)); }, [playing, index]);
  if (!clips.length) return null;
  const clip = clips[index] || clips[0];
  function advance() {
    if (!playing) return;
    if (index + 1 < clips.length) setIndex(index + 1);
    else { ref.current?.pause(); setPlaying(false); }
  }
  return <section><h4>当前采用的视频原声 · {clips.length} 段</h4>
    <p className="helper">按本片采用区间连听实际音轨，包含同段其他人物与环境声。音色参考不等于生成声音已一致，请逐段对照。</p>
    <video ref={ref} controls playsInline preload="metadata" src={`${clip.url}#t=${clip.start}${clip.end ? `,${clip.end}` : ""}`}
      onEnded={advance} onTimeUpdate={event => { if (clip.end && event.currentTarget.currentTime >= clip.end - .03) advance(); }}
      aria-label="角色视频原声连听" style={{ width: "100%", maxHeight: 280 }} />
    <button className="btn" onClick={() => { setIndex(0); setPlaying(true); if (ref.current) { ref.current.currentTime = clips[0].start; void ref.current.play().catch(() => setPlaying(false)); } }}>从头连听视频原声</button>
    <p>{clip.title}</p>
  </section>;
}

"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Preview } from "@/components/ui";
import { ErrorNotice } from "./ErrorNotice";
export type ReviewOutput = { id: string; status: string; url: string; stale?: boolean; settings: { purpose?: string; source_mode?: string; sourceMode?: string } };
export function currentDynamicOutput(outputs: ReviewOutput[]) {
  return outputs.find(output => output.status === "done" && output.url && !output.stale && (output.settings.source_mode || output.settings.sourceMode) !== "storyboard");
}
export function ReviewPlayer({ project }: { project: Project }) {
  const [mode, setMode] = useState(project.scenes.some(scene => scene.videoUrl) ? "dynamic" : "static");
  const [playing, setPlaying] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [outputs, setOutputs] = useState<ReviewOutput[]>([]);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    setOutputs([]); setError(null); setPlaying(false); setSeconds(0);
    const controller = new AbortController();
    void api<ReviewOutput[]>(`/projects/${project.id}/exports`, "GET", undefined, controller.signal).then(setOutputs).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [project.id]);
  const output = project.scenes.some(scene => scene.videoUrl) ? currentDynamicOutput(outputs) : undefined;
  return <section className="review-player" aria-label="成片播放器"><div className="cw-tabs"><button aria-pressed={mode === "static"} className={mode === "static" ? "active" : ""} onClick={() => { setMode("static"); setPlaying(false); }}>静态预演</button><button aria-pressed={mode === "dynamic"} className={mode === "dynamic" ? "active" : ""} onClick={() => { setMode("dynamic"); setPlaying(false); }}>动态预览</button></div>
    <ErrorNotice error={error}/>
    {mode === "static" ? <Preview scenes={project.scenes} playing={playing} setPlaying={setPlaying} seconds={seconds} setSeconds={setSeconds} ratio={project.ratio}/> : output ? <><video key={output.id} src={output.url} controls preload="metadata" aria-label="当前版本动态成片"/><p className="helper">播放已有本地成片。可前往导出页保存作品。</p></> : <div className="empty"><h3>尚无当前版本的动态成片</h3><p>进入导出页，使用现有素材进行本地合成。</p><Link className="btn" href="/export">打开预览与导出</Link></div>}
  </section>;
}

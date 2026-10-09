"use client";
import { useState } from "react";
import { copy } from "./copy";
export function CurrentVoice({ url, durationMs }: { url: string; durationMs?: number }) {
  const [load, setLoad] = useState(false);
  if (!url) return null;
  return (durationMs || 0) > 0 || load ? <audio controls preload="metadata" src={url} autoPlay={load} /> : <><span>{copy.voiceSample}</span><button className="btn" onClick={() => setLoad(true)}>{copy.audition}</button></>;
}

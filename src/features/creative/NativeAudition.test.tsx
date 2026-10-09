import { expect, it } from "vitest";
import { nativeAuditionClips } from "./NativeAudition";

it("audition joins adjacent adopted ranges and leaves discarded gaps out", () => {
  const scene = (title: string, start: number, end: number) => ({
    title, videoUrl: "/take.mp4", creative: {
      video: { sound_strategy: "model_audio", duration: 20 },
      edit: { in_sec: start, out_sec: end },
      shot: { lines: [{ speaker_id: "阿茶" }] },
    },
  });
  const rows = [scene("开场", 2, 5), scene("回答", 5, 8), scene("结尾", 12, 15)];
  expect(nativeAuditionClips(rows, "阿茶")).toEqual([
    { url: "/take.mp4", start: 2, end: 8, title: "开场 → 回答" },
    { url: "/take.mp4", start: 12, end: 15, title: "结尾" },
  ]);
  expect(nativeAuditionClips(rows, "月神")).toEqual([]);
});

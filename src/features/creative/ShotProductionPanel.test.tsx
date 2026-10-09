import { expect, it } from "vitest";
import { productionState } from "./ShotProductionPanel";
import { initialProjects } from "@/lib/data";
import type { Project, Scene } from "@/lib/types";
import type { Shot } from "@/lib/creative-types";

const shot: Shot = { title: "第一镜", cast: {}, variants: {}, location_id: "room", location_description: "房间", action: "走入房间", expression: "平静", composition: "中景", shot_type: "中景", camera_angle: "平视", camera_move: "固定", duration: 5, image_prompt: "房间", sound_notes: "", lines: [], narration: [{ id: "n1", speaker_id: null, text: "夜色渐深", emotion: "calm", speed: 1, pause_after: 0 }] };
const project: Project = { ...initialProjects[0], creative: { version: 1, revision: "r1", plan: null, plan_confirmed: true, cast_confirmed: true, shots_confirmed: false, narrator: { voice_id: "narrator", speed: 1 } } };
const scene: Scene = { ...initialProjects[0].scenes[0], image: "", creative: { version: 1, revision: "s1", shot } };
const status = { id: scene.id, image_stale: true, audio_stale: true, segments: [] };

it("explains confirmation first, then image selection; missing audio is a recommendation", () => {
  expect(productionState(project, scene, status).videoBlock).toContain("确认分镜");
  const confirmed = { ...project, creative: { ...project.creative!, shots_confirmed: true } };
  expect(productionState(confirmed, scene, status).videoBlock).toContain("选用本镜画面");
  const ready = productionState(confirmed, { ...scene, image: "/selected.png" }, { ...status, image_stale: false });
  expect(ready.confirmed).toBe(true);
  expect(ready.imageReady).toBe(true);
  expect(ready.audioReady).toBe(false);
  expect(ready.videoBlock).toBe("");
});

it("only requires a tail in first-last mode and treats silent shots as audio-ready", () => {
  const confirmed = { ...project, creative: { ...project.creative!, shots_confirmed: true } };
  const withTailMode: Scene = { ...scene, image: "/selected.png", creative: { ...scene.creative!, shot: { ...shot, narration: [], video_input: { mode: "first_last_frame", sound_strategy: "post_audio", references: [] } } } };
  const pending = productionState(confirmed, withTailMode, { ...status, image_stale: false });
  expect(pending.videoBlock).toContain("结束画面");
  expect(pending.audioReady).toBe(true);
  const ready = { ...withTailMode, creative: { ...withTailMode.creative!, shot: { ...withTailMode.creative!.shot!, last_frame_asset_id: "tail" } } };
  expect(productionState(confirmed, ready, { ...status, image_stale: false }).videoBlock).toBe("");
});

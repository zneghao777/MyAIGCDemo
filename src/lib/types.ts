import type {
  CharacterState,
  SceneState,
  ProjectState,
} from "./creative-types";
export type SceneStatus =
  | "draft"
  | "image_pending"
  | "video_pending"
  | "image_ready"
  | "done"
  | "failed";
export type Vector = [number, number, number];
export type StageObject = {
  characterId?: string | null;
  id: string;
  name: string;
  kind: "actor" | "prop" | "camera";
  position: Vector;
  rotation: Vector;
  scale: number;
  color: string;
  action: string;
};
export type Keyframe = {
  id: string;
  objectId: string;
  t: number;
  position: Vector;
};
export type DirectorData = {
  template: string;
  objects: StageObject[];
  keyframes: Keyframe[];
  fov: number;
};
export type Scene = {
  creative?: SceneState;
  id: string;
  title: string;
  shotType: string;
  cameraMove: string;
  durationSec: number;
  narration?: string;
  videoPrompt?: string;
  videoUrl?: string;
  audioUrl?: string;
  narrationUrl?: string;
  lastError?: string;
  imagePrompt: string;
  dialogue: string;
  image: string;
  status: SceneStatus;
  directorData?: DirectorData;
  model: string;
  seed: string;
};
export type Character = {
  creative?: CharacterState;
  id: string;
  name: string;
  age: string;
  description: string;
  clothing: string;
  voice: string;
  voiceId?: string;
  image: string;
  consistency: string;
};
export type Project = {
  creative?: ProjectState;
  id: string;
  name: string;
  description: string;
  style: string;
  ratio: string;
  updatedAt: number;
  cover: string;
  status: "剪辑中" | "草稿" | "已导出";
  scenes: Scene[];
  characters: Character[];
};
export type Task = {
  id: string;
  projectId: string;
  sceneId: string;
  type: "图片" | "视频" | "配音" | "合成" | "剧本";
  kind?: "image" | "video" | "tts" | "compose" | "script";
  costCents?: number;
  provider?: string;
  typeLabel?: string;
  generationRequest?: import("@/features/creative/types").Request;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  createdAt: number;
  error?: string;
  providerTaskId?: string;
  operation?: string;
  targetId?: string;
  logs?: unknown[];
  result?: { operation?: string; draft?: boolean; message?: string; [key: string]: unknown };
};
export type Toast = { id: number; message: string };
export const statusText: Record<SceneStatus, string> = {
  draft: "待生成",
  image_pending: "图片生成中",
  video_pending: "视频生成中",
  image_ready: "首帧就绪",
  done: "已完成",
  failed: "生成失败",
};
export const uid = () => crypto.randomUUID();
export function timecode(seconds: number) {
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
}

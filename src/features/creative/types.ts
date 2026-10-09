import type { Project } from "@/lib/types";
import type { Candidate, Line } from "@/lib/creative-types";
import type { Readiness } from "./shared";
export type Flow = {
  project: Project;
  candidates: Candidate[];
  pacing?: { planned_seconds: number; measured_seconds: number; target_seconds: number; warnings: string[]; note: string };
  issues: string[];
  readiness: Readiness[];
  workflowReadiness: { plan: boolean; cast: boolean; locations: boolean; shots: boolean; export: boolean; structure_ready: boolean; preview_confirmed: boolean; video_accepted: boolean; media_complete?: boolean };
  stageStates: Record<string, string>;
  scenes: {
    id: string;
    video_ready?: boolean;
    video_stale?: boolean;
    video_block?: string;
    image_stale: boolean;
    audio_stale: boolean;
    error?: string;
    segments?: {
      url: string;
      line: Line;
      voice_id: string;
      duration_ms: number;
      start_ms: number;
      speed?: number;
      emotion?: string;
      strategy?: string;
    }[];
  }[];
  revisions: {
    id: string;
    kind: string;
    entityId: string;
    data: unknown;
    createdAt: string;
  }[];
  capabilities: {
    intro: boolean; watermark: boolean; bgmPresets: boolean;
    videoGeneration: boolean;
    maxImageReferences: number;
    voiceDesign: boolean;
    referenceVoiceLock: boolean;
    voiceClone: boolean;
    roleAudio: boolean;
    ttsModel: string;
    defaultVoice: string;
  };
};
export type Request = {
  operation: string;
  target?: string;
  voice_id?: string;
  variant?: string;
  view?: string;
  use_reference?: boolean;
  auto_apply?: boolean;
  state?: string;
  frame?: "first" | "last";
  nonce?: string;
  text?: string;
  regenerate_line_ids?: string[];
};
export type Task = {
  operation?: string;
  targetId?: string;
  id: string;
  status: string;
  progress: number;
  error?: string;
  logs?: unknown[];
  result?: { operation?: string; draft?: boolean; applied?: boolean; message?: string };
};

import type { Project, Scene } from "./types";

export function effectiveVideoInput(project: Project, scene?: Scene) {
  if (!scene) return undefined;
  const group = project.creative?.production_segments?.find(segment => segment.scene_ids.includes(scene.id));
  const leader = group && project.scenes.find(row => row.id === group.scene_ids[0]);
  return (leader || scene).creative?.shot?.video_input;
}

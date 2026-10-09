"use client";
import { errorText } from "@/features/creative/copy";
import { api, apiBase, isRateLimited } from "./api";
import { createReadObserver } from "./read-observer";
import { useStore } from "./store";
import type { Project, Scene, Character, Task } from "./types";

let chain = Promise.resolve();
let pending = 0;
let installed = false;
let refreshInFlight: Promise<void> | undefined;
let refreshTarget: string | undefined;
const changeListeners = new Map<string, Set<() => void>>();
export function subscribeRemoteChanges(projectId: string, listener: () => void) {
  const listeners = changeListeners.get(projectId) || new Set();
  listeners.add(listener); changeListeners.set(projectId, listeners);
  return () => { listeners.delete(listener); if (!listeners.size) changeListeners.delete(projectId); };
}
function changed(projectId: string) { changeListeners.get(projectId)?.forEach(listener => listener()); }
function normalizeTask(t: Task): Task {
  return { ...t, createdAt: typeof t.createdAt === "string" ? Date.parse(t.createdAt) : t.createdAt };
}
function observationError(error: unknown) {
  // A read cooldown does not mean that any queued or remote task has failed.
  useStore.setState({ syncState: isRateLimited(error) ? "loading" : "error", readRetryUntil: isRateLimited(error) ? Date.now() + error.retryAfterMs : undefined });
}
const projectBody = (p: Project) => ({ id: p.id, name: p.name, description: p.description,
  style: p.style, ratio: p.ratio, scenes: p.scenes.map(sceneBody), characters: p.characters.map(characterBody) });
const sceneBody = (s: Scene) => ({ id: s.id, title: s.title, shotType: s.shotType,
  cameraMove: s.cameraMove, durationSec: s.durationSec, imagePrompt: s.imagePrompt,
  dialogue: s.dialogue, narration: s.narration || "", directorData: s.directorData, model: s.model, seed: s.seed });
const characterBody = (c: Character) => ({ id: c.id, name: c.name, age: c.age,
  description: c.description, clothing: c.clothing, voice: c.voice, voiceId: c.voiceId,
  consistency: c.consistency, image: c.image.startsWith("/assets/") ? "" : c.image });
function normalize(p: Project): Project {
  return { ...p, updatedAt: typeof p.updatedAt === "string" ? Date.parse(p.updatedAt) : p.updatedAt };
}
async function fetchRemote(preferredProjectId?: string) {
  const projects = (await api<Project[]>("/projects")).map(normalize);
  if (pending) return;
  const state = useStore.getState();
  const active = projects.find(p => p.id === preferredProjectId) || projects.find(p => p.id === state.activeId) || projects[0];
  const [tasks, queue] = active ? await Promise.all([
    api<Task[]>(`/projects/${active.id}/tasks`), api<{ paused: boolean }>(`/projects/${active.id}/queue`),
  ]) : [[], { paused: false }];
  if (pending) return;
  const latest = useStore.getState();
  // A task refresh can finish after the user chooses another shot/project.
  // Preserve the live selection instead of restoring the request-time one.
  if (latest.activeId !== state.activeId && latest.activeId !== active?.id) return;
  useStore.setState({ projects, activeId: active?.id || "", sceneId: active?.scenes.some(s => s.id === latest.sceneId) ? latest.sceneId : active?.scenes[0]?.id || "",
    tasks: tasks.map(normalizeTask), paused: queue.paused, syncState: "synced", readRetryUntil: undefined });
}
export async function refreshRemote(preferredProjectId?: string): Promise<void> {
  if (refreshInFlight) {
    const target = refreshTarget;
    await refreshInFlight;
    if (preferredProjectId && preferredProjectId !== target && useStore.getState().activeId !== preferredProjectId) return refreshRemote(preferredProjectId);
    return;
  }
  refreshTarget = preferredProjectId || useStore.getState().activeId;
  refreshInFlight = fetchRemote(preferredProjectId);
  try { await refreshInFlight; }
  finally { refreshInFlight = undefined; refreshTarget = undefined; }
}
function mutate(action: () => Promise<unknown>, optimistic?: () => void) {
  optimistic?.(); pending++; useStore.setState({ syncState: "saving" });
  chain = chain.then(action).then(() => undefined).catch(e => {
    useStore.getState().notify(errorText(e));
    useStore.setState({ syncState: "error" });
  }).finally(async () => {
    pending--;
    if (!pending) await refreshRemote().catch(() => useStore.setState({ syncState: "error" }));
  });
}
export function installRemoteActions() {
  if (installed) return;
  installed = true;
  const local = { ...useStore.getState() };
  useStore.setState({
    tick: () => {},
    addProject: p => mutate(async () => { await api("/projects", "POST", projectBody(p)); useStore.setState({ activeId: p.id }); }),
    patchProject: (id, patch) => mutate(() => api(`/projects/${id}`, "PATCH", patch), () => local.patchProject(id, patch)),
    removeProject: id => mutate(() => api(`/projects/${id}`, "DELETE")),
    copyProject: id => mutate(() => api(`/projects/${id}/copy`, "POST")),
    patchScene: (id, patch) => mutate(() => api(`/scenes/${id}`, "PATCH", patch), () => local.patchScene(id, patch)),
    addScene: () => { const id = useStore.getState().activeId; mutate(() => api(`/projects/${id}/scenes`, "POST", {})); },
    copyScene: id => mutate(() => api(`/scenes/${id}/copy`, "POST")),
    removeScene: id => mutate(() => api(`/scenes/${id}`, "DELETE")),
    reorderScene: (from, to) => {
      const state = useStore.getState(), p = state.projects.find(p => p.id === state.activeId);
      if (!p) return;
      const ids = p.scenes.map(s => s.id), a = ids.indexOf(from), b = ids.indexOf(to);
      if (a < 0 || b < 0) return;
      ids.splice(b, 0, ids.splice(a, 1)[0]);
      mutate(() => api(`/projects/${p.id}/scenes/order`, "PATCH", { ids }), () => local.reorderScene(from, to));
    },
    saveCharacter: c => {
      const p = useStore.getState().projects.find(p => p.id === useStore.getState().activeId);
      if (!p) return;
      const exists = p.characters.some(x => x.id === c.id);
      const body = characterBody(c);
      const { id, ...patch } = body;
      mutate(() => api(exists ? `/characters/${id}` : `/projects/${p.id}/characters`, exists ? "PATCH" : "POST", exists ? patch : body));
    },
    removeCharacter: id => mutate(() => api(`/characters/${id}`, "DELETE")),
    enqueue: (sceneIds, type) => {
      const projectId = useStore.getState().activeId;
      const kind = ({ 图片: "image", 视频: "video", 配音: "tts", 合成: "compose", 剧本: "script" } as const)[type];
      mutate(async () => {
        const result = await api<{ rejected: { code: string }[] }>("/tasks", "POST", { projectId, sceneIds, kind });
        if (result.rejected.length) useStore.getState().notify(`${result.rejected.length} 个任务未入队：请检查分镜状态`);
      });
    },
    retry: id => mutate(() => api(`/tasks/${id}/retry`, "POST")),
    cancel: id => mutate(() => api(`/tasks/${id}/cancel`, "POST")),
    togglePause: () => {
      const s = useStore.getState(); mutate(() => api(`/projects/${s.activeId}/queue/pause`, "POST", { paused: !s.paused }));
    },
  });
}
export function connectRemote(projectId: string) {
  if (!projectId) return () => {};
  const source = new EventSource(`${apiBase}/api/projects/${projectId}/events`);
  const metadata = createReadObserver(async signal => {
    const [project, queue] = await Promise.all([
      api<Project>(`/projects/${projectId}`, "GET", undefined, signal),
      api<{ paused: boolean }>(`/projects/${projectId}/queue`, "GET", undefined, signal),
    ]);
    if (signal.aborted || pending || useStore.getState().activeId !== projectId) return;
    useStore.setState(state => ({ projects: state.projects.map(p => p.id === projectId ? normalize(project) : p), paused: queue.paused, syncState: "synced" }));
  }, observationError, { intervalMs: 60000, minIntervalMs: 5000, initialDelayMs: 60000 });
  const invalidate = () => { metadata.request(); changed(projectId); };
  const receiveTasks = (tasks: Task[], replace = false) => {
    const state = useStore.getState();
    if (state.activeId !== projectId) return;
    const terminalChanged = tasks.some(task => ["done", "failed", "cancelled"].includes(task.status) && state.tasks.find(t => t.id === task.id)?.status !== task.status);
    const merged = new Map((replace ? [] : state.tasks).map(t => [t.id, t]));
    tasks.forEach(task => {
      const previous = state.tasks.find(row => row.id === task.id);
      // A fallback response started before an SSE terminal event may arrive later.
      const terminal = previous && ["done", "failed", "cancelled"].includes(previous.status);
      merged.set(task.id, terminal && ["queued", "running"].includes(task.status) ? previous : normalizeTask(task));
    });
    useStore.setState({ tasks: Array.from(merged.values()), syncState: "synced" });
    if (terminalChanged) invalidate();
  };
  // SSE carries complete task records; only one slow fallback poll reads tasks.
  const tasks = createReadObserver(async signal => {
    const rows = await api<Task[]>(`/projects/${projectId}/tasks`, "GET", undefined, signal);
    if (!signal.aborted) receiveTasks(rows, true);
  }, observationError, { intervalMs: 15000, initialDelayMs: 15000 });
  source.onopen = () => { tasks.request(); invalidate(); };
  source.addEventListener("task", event => {
    try {
      const task = JSON.parse((event as MessageEvent).data) as Task;
      if (task.id && task.status) receiveTasks([task]);
    } catch { tasks.request(); }
  });
  for (const event of ["scene", "project"]) source.addEventListener(event, invalidate);
  source.addEventListener("export", event => {
    try { const data = JSON.parse((event as MessageEvent).data); if (typeof data.progress !== "number" || data.progress >= 100) invalidate(); }
    catch { invalidate(); }
  });
  source.onerror = () => { tasks.request(); };
  return () => { source.close(); metadata.stop(); tasks.stop(); };
}

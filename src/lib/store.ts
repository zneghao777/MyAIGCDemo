"use client";
import { create } from "zustand";
import { remoteMode } from "./api";
import { persist, createJSONStorage } from "zustand/middleware";
import { assets, initialProjects, initialTasks } from "./data";
import {
  uid,
  type Character,
  type Project,
  type Scene,
  type Task,
  type Toast,
} from "./types";
type State = {
  syncState: "loading" | "saving" | "synced" | "error";
  readRetryUntil?: number;
  projects: Project[];
  activeId: string;
  sceneId: string;
  tasks: Task[];
  paused: boolean;
  toast: Toast | null;
  idea: string;
  notify: (message: string) => void;
  setIdea: (idea: string) => void;
  selectProject: (id: string) => void;
  selectScene: (id: string) => void;
  addProject: (project: Project) => void;
  patchProject: (id: string, patch: Partial<Project>) => void;
  removeProject: (id: string) => void;
  copyProject: (id: string) => void;
  patchScene: (id: string, patch: Partial<Scene>) => void;
  addScene: () => void;
  copyScene: (id: string) => void;
  removeScene: (id: string) => void;
  reorderScene: (from: string, to: string) => void;
  saveCharacter: (character: Character) => void;
  removeCharacter: (id: string) => void;
  enqueue: (ids: string[], type: Task["type"]) => void;
  retry: (id: string) => void;
  cancel: (id: string) => void;
  togglePause: () => void;
  tick: () => void;
};
export const useStore = create<State>()(
  persist(
    (set, get) => ({
      syncState: "loading",
      projects: remoteMode ? [] : initialProjects,
      activeId: remoteMode ? "" : "last-mail",
      sceneId: remoteMode ? "" : "last-mail-s1",
      tasks: remoteMode ? [] : initialTasks,
      paused: true,
      toast: null,
      idea: "",
      notify: (message) => set({ toast: { id: Date.now(), message } }),
      setIdea: (idea) => set({ idea }),
      selectProject: (id) => {
        const p = get().projects.find((p) => p.id === id);
        if (p) set({ activeId: id, sceneId: p.scenes[0]?.id || "" });
      },
      selectScene: (sceneId) => set({ sceneId }),
      addProject: (project) =>
        set((s) => ({
          projects: [project, ...s.projects],
          activeId: project.id,
          sceneId: project.scenes[0]?.id || "",
        })),
      patchProject: (id, patch) =>
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === id ? { ...p, ...patch, updatedAt: Date.now() } : p,
          ),
        })),
      removeProject: (id) =>
        set((s) => {
          const ps = s.projects.filter((p) => p.id !== id);
          return {
            projects: ps,
            tasks: s.tasks.filter((t) => t.projectId !== id),
            activeId: s.activeId === id ? ps[0]?.id || "" : s.activeId,
            sceneId: s.activeId === id ? ps[0]?.scenes[0]?.id || "" : s.sceneId,
          };
        }),
      copyProject: (id) => {
        const p = get().projects.find((p) => p.id === id);
        if (!p) return;
        const copy = structuredClone(p);
        copy.id = uid();
        copy.name += " · 副本";
        copy.status = "草稿";
        copy.updatedAt = Date.now();
        copy.scenes = copy.scenes.map((s) => ({
          ...s,
          id: uid(),
          status: s.image ? "image_ready" : "draft",
        }));
        copy.characters = copy.characters.map((c) => ({ ...c, id: uid() }));
        set((s) => ({ projects: [copy, ...s.projects] }));
        get().notify("已复制项目");
      },
      patchScene: (id, patch) =>
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === s.activeId
              ? {
                  ...p,
                  updatedAt: Date.now(),
                  scenes: p.scenes.map((sc) =>
                    sc.id === id ? { ...sc, ...patch } : sc,
                  ),
                }
              : p,
          ),
        })),
      addScene: () => {
        const id = uid();
        set((s) => ({
          sceneId: id,
          projects: s.projects.map((p) =>
            p.id === s.activeId
              ? {
                  ...p,
                  updatedAt: Date.now(),
                  scenes: [
                    ...p.scenes,
                    {
                      id,
                      title: "新的分镜",
                      shotType: "中景",
                      cameraMove: "固定",
                      durationSec: 5,
                      imagePrompt: "",
                      dialogue: "",
                      image: "",
                      status: "draft",
                      model: "CineAI · 电影写实",
                      seed: "420199",
                    },
                  ],
                }
              : p,
          ),
        }));
      },
      copyScene: (id) =>
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === s.activeId
              ? {
                  ...p,
                  scenes: p.scenes.flatMap((sc) =>
                    sc.id === id
                      ? [
                          sc,
                          {
                            ...structuredClone(sc),
                            id: uid(),
                            status: sc.image ? "image_ready" : "draft",
                          },
                        ]
                      : [sc],
                  ),
                }
              : p,
          ),
        })),
      removeScene: (id) =>
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === s.activeId
              ? { ...p, scenes: p.scenes.filter((sc) => sc.id !== id) }
              : p,
          ),
          sceneId: s.sceneId === id ? "" : s.sceneId,
          tasks: s.tasks.filter((t) => t.sceneId !== id),
        })),
      reorderScene: (from, to) =>
        set((s) => ({
          projects: s.projects.map((p) => {
            if (p.id !== s.activeId) return p;
            const list = [...p.scenes];
            const a = list.findIndex((sc) => sc.id === from),
              b = list.findIndex((sc) => sc.id === to);
            if (a < 0 || b < 0) return p;
            const [item] = list.splice(a, 1);
            list.splice(b, 0, item);
            return { ...p, scenes: list };
          }),
        })),
      saveCharacter: (character) =>
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === s.activeId
              ? {
                  ...p,
                  characters: p.characters.some((c) => c.id === character.id)
                    ? p.characters.map((c) =>
                        c.id === character.id ? character : c,
                      )
                    : [...p.characters, character],
                }
              : p,
          ),
        })),
      removeCharacter: (id) =>
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === s.activeId
              ? { ...p, characters: p.characters.filter((c) => c.id !== id) }
              : p,
          ),
        })),
      enqueue: (ids, type) => {
        const state = get();
        const p = state.projects.find((p) => p.id === state.activeId);
        if (!p) return;
        const allowed = ids.filter(
          (id) =>
            p.scenes.some(
              (sc) => sc.id === id && (type === "图片" || sc.image),
            ) &&
            !state.tasks.some(
              (t) =>
                t.sceneId === id && ["queued", "running"].includes(t.status),
            ),
        );
        if (!allowed.length) {
          state.notify(
            type === "视频"
              ? "请先生成首帧图片，或等待当前任务完成"
              : "所选分镜已有任务正在进行",
          );
          return;
        }
        set((s) => ({
          paused: false,
          tasks: [
            ...s.tasks,
            ...allowed.map((sceneId) => ({
              id: uid(),
              projectId: s.activeId,
              sceneId,
              type,
              status: "queued" as const,
              progress: 0,
              createdAt: Date.now(),
            })),
          ],
          projects: s.projects.map((pr) =>
            pr.id === s.activeId
              ? {
                  ...pr,
                  scenes: pr.scenes.map((sc) =>
                    allowed.includes(sc.id)
                      ? {
                          ...sc,
                          status:
                            type === "图片" ? "image_pending" : "video_pending",
                        }
                      : sc,
                  ),
                }
              : pr,
          ),
        }));
        state.notify(`已加入 ${allowed.length} 个${type}演示任务`);
      },
      retry: (id) => {
        const t = get().tasks.find((t) => t.id === id);
        if (!t) return;
        if (
          get().tasks.some(
            (other) =>
              other.id !== id &&
              other.sceneId === t.sceneId &&
              ["running", "queued"].includes(other.status),
          )
        ) {
          get().notify("这个分镜已有进行中的任务，请等待完成后重试。");
          return;
        }
        set((s) => ({
          paused: false,
          tasks: s.tasks.map((x) =>
            x.id === id
              ? { ...x, status: "queued", progress: 0, error: undefined }
              : x,
          ),
          projects: s.projects.map((p) =>
            p.id === t.projectId
              ? {
                  ...p,
                  scenes: p.scenes.map((sc) =>
                    sc.id === t.sceneId
                      ? {
                          ...sc,
                          status:
                            t.type === "图片"
                              ? "image_pending"
                              : "video_pending",
                        }
                      : sc,
                  ),
                }
              : p,
          ),
        }));
      },
      cancel: (id) => {
        const t = get().tasks.find((t) => t.id === id);
        if (!t) return;
        set((s) => ({
          tasks: s.tasks.map((x) =>
            x.id === id ? { ...x, status: "cancelled" } : x,
          ),
          projects: s.projects.map((p) =>
            p.id === t.projectId
              ? {
                  ...p,
                  scenes: p.scenes.map((sc) =>
                    sc.id === t.sceneId
                      ? { ...sc, status: sc.image ? "image_ready" : "draft" }
                      : sc,
                  ),
                }
              : p,
          ),
        }));
      },
      togglePause: () => set((s) => ({ paused: !s.paused })),
      tick: () => {
        const s = get();
        if (s.paused) return;
        let slots = 2 - s.tasks.filter((t) => t.status === "running").length;
        const completed: Task[] = [];
        const tasks = s.tasks.map((t) => {
          if (t.status === "queued" && slots > 0) {
            slots--;
            return { ...t, status: "running" as const };
          }
          if (t.status !== "running") return t;
          const progress = Math.min(100, t.progress + 8);
          const next = {
            ...t,
            progress,
            status: progress === 100 ? ("done" as const) : ("running" as const),
          };
          if (progress === 100) completed.push(next);
          return next;
        });
        if (!tasks.some((t, i) => t !== s.tasks[i])) return;
        set({
          tasks,
          projects: completed.length
            ? s.projects.map((p) => ({
                ...p,
                scenes: p.scenes.map((sc) => {
                  const t = completed.find(
                    (t) => t.projectId === p.id && t.sceneId === sc.id,
                  );
                  return t
                    ? {
                        ...sc,
                        status: t.type === "视频" ? "done" : "image_ready",
                        image: sc.image || p.cover || assets[0],
                      }
                    : sc;
                }),
              }))
            : s.projects,
        });
      },
    }),
    {
      name: remoteMode ? "cineai-studio-remote-v1" : "cineai-studio-v1",
      version: remoteMode ? 2 : 1,
      // Server records are authoritative; discard cached COS URLs from v1.
      migrate: () => ({ activeId: "", sceneId: "" }),
      storage: createJSONStorage(() => ({
        getItem: (key: string) =>
          typeof window !== "undefined"
            ? window.localStorage.getItem(key)
            : null,
        setItem: (key: string, value: string) => {
          if (typeof window === "undefined") return;
          try {
            window.localStorage.setItem(key, value);
          } catch {
            window.dispatchEvent(new Event("cineai-storage-error"));
          }
        },
        removeItem: (key: string) => {
          if (typeof window !== "undefined")
            window.localStorage.removeItem(key);
        },
      })),
      skipHydration: true,
      partialize: (s) => remoteMode ? ({ activeId: s.activeId, sceneId: s.sceneId }) : ({
        projects: s.projects,
        activeId: s.activeId,
        sceneId: s.sceneId,
        tasks: s.tasks,
        paused: s.paused,
      }),
    },
  ),
);
export function useProject() {
  return useStore((s) => s.projects.find((p) => p.id === s.activeId));
}

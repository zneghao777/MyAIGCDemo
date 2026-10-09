import { beforeEach, expect, it, vi } from "vitest";

const fixture = vi.hoisted(() => ({
  state: { activeId: "p", sceneId: "first" } as Record<string, unknown>,
  api: vi.fn(),
}));
vi.mock("./api", () => ({ api: fixture.api, apiBase: "", isRateLimited: () => false }));
vi.mock("./store", () => ({ useStore: {
  getState: () => fixture.state,
  setState: (patch: Record<string, unknown>) => { fixture.state = { ...fixture.state, ...patch }; },
} }));

beforeEach(() => {
  vi.resetModules();
  fixture.api.mockReset();
  fixture.state = { activeId: "p", sceneId: "first" };
});

it.each(["shot", "project"])("a delayed task refresh preserves the user's newer %s selection", async kind => {
  let release!: (tasks: unknown[]) => void;
  const tasks = new Promise<unknown[]>(resolve => { release = resolve; });
  fixture.api.mockImplementation((path: string) => {
    if (path === "/projects") return Promise.resolve([{ id: "p", updatedAt: 0, scenes: [{ id: "first" }, { id: "second" }] }]);
    if (path.endsWith("/tasks")) return tasks;
    return Promise.resolve({ paused: false });
  });
  const { refreshRemote } = await import("./remote-store");
  const refresh = refreshRemote();
  await vi.waitFor(() => expect(fixture.api).toHaveBeenCalledWith("/projects/p/tasks"));
  fixture.state = { ...fixture.state, sceneId: "second", activeId: kind === "project" ? "another-project" : "p" };
  release([]);
  await refresh;
  expect(fixture.state.sceneId).toBe("second");
  expect(fixture.state.activeId).toBe(kind === "project" ? "another-project" : "p");
});

import { describe, expect, it } from "vitest";
import { currentDynamicOutput, type ReviewOutput } from "./ReviewPlayer";
describe("review source selection", () => {
  it("never presents an expired output or a static preview as current dynamic output", () => {
    const outputs: ReviewOutput[] = [
      { id: "stale", status: "done", url: "/stale.mp4", stale: true, settings: { source_mode: "auto" } },
      { id: "static", status: "done", url: "/static.mp4", settings: { source_mode: "storyboard" } },
      { id: "pending", status: "running", url: "", settings: {} },
      { id: "current", status: "done", url: "/current.mp4", settings: { sourceMode: "auto" } },
    ];
    expect(currentDynamicOutput(outputs)?.id).toBe("current");
    expect(currentDynamicOutput(outputs.slice(0, 3))).toBeUndefined();
  });
});

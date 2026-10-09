import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GenerationStatus } from "./GenerationStatus";
it("queued tasks expose indeterminate progress without inventing a percentage", () => {
  const html = renderToStaticMarkup(<GenerationStatus label="角色形象" status="queued" progress={0} />);
  expect(html).toContain('role="progressbar"'); expect(html).toContain("等待开始");
  expect(html).not.toContain("aria-valuenow"); expect(html).not.toContain("0%");
});
it("running tasks use real bounded progress and completed tasks stop loading", () => {
  const html = renderToStaticMarkup(<GenerationStatus label="角色形象" status="running" progress={55} />);
  expect(html).toContain('aria-valuenow="55"'); expect(html).toContain("55%");
  expect(renderToStaticMarkup(<GenerationStatus label="形象" status="running" progress={150} />)).toContain('aria-valuenow="100"');
  const done = renderToStaticMarkup(<GenerationStatus label="角色形象" status="done" progress={100} />);
  expect(done).toContain("生成完成"); expect(done).not.toContain("progressbar"); expect(done).not.toContain("generation-pixels");
});

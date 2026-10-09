import { describe, it, expect, vi } from "vitest";
import { act } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { StageNavigation, confirmedStageCount } from "./StageNavigation";
import { EmptyStoryboardAction } from "./EmptyStoryboardAction";
import type { Flow } from "./types";
import { uiCopy } from "./copy";
const flow = (complete = false): Pick<Flow, "workflowReadiness" | "stageStates"> => ({ workflowReadiness: { plan: true, cast: true, locations: true, shots: complete, export: complete, structure_ready: complete, preview_confirmed: complete, video_accepted: complete }, stageStates: { plan: uiCopy["已确认"], characters: uiCopy["已确认"], storyboard: complete ? uiCopy["已确认"] : uiCopy["待确认"] } });
describe("five-stage workflow", () => {
  it("B2: server booleans yield 3 / 5 and three confirmed navigation labels", () => {
    const current = flow(); const markup = renderToStaticMarkup(<StageNavigation flow={current} onSelect={() => {}} />);
    expect(confirmedStageCount(current.workflowReadiness)).toBe(3);
    expect(markup.match(/<small>已确认<\/small>/g)).toHaveLength(3);
    const labels = ["01 故事", "02 角色与声音", "03 场景", "04 分镜", "05 成片"];
    expect(labels.map(label => markup.indexOf(label))).toEqual([...labels.map(label => markup.indexOf(label))].sort((a,b)=>a-b));
    labels.forEach(label => expect(markup).toContain(label));
  });
  it("B2: all five confirmations show ready export, without pending artistic review", () => {
    const current = flow(true); const markup = renderToStaticMarkup(<StageNavigation flow={current} onSelect={() => {}} />);
    expect(confirmedStageCount(current.workflowReadiness)).toBe(5);
    expect(markup).toContain("<small>已就绪</small>"); expect(markup).not.toContain("待艺术验收");
  });
  it.each([[false,false,"plan","开始故事方案"],[true,false,"generate","生成分镜草案"],[true,true,"generate","生成分镜草案"]])("empty storyboard %s / %s goes to %s", (plan,cast,destination,label) => {
    const onPhase = vi.fn(), onGenerate = vi.fn();
    const element = EmptyStoryboardAction({ planConfirmed: !!plan, castConfirmed: !!cast, onPhase, onGenerate });
    expect(renderToStaticMarkup(element)).toContain(String(label)); act(() => element.props.onClick());
    if(destination === "generate") { expect(onGenerate).toHaveBeenCalledOnce(); expect(onPhase).not.toHaveBeenCalled(); }
    else { expect(onPhase).toHaveBeenCalledWith(destination); expect(onGenerate).not.toHaveBeenCalled(); }
  });
});
it("switching stages calls only navigation and preserves server readiness", () => {
  const current=flow(); const before=JSON.stringify(current); const onSelect=vi.fn();
  const tree=StageNavigation({flow:current,current:"plan",onSelect});
  const buttons=tree.props.children;
  buttons[3].props.onClick();
  expect(onSelect).toHaveBeenCalledWith("storyboard");
  expect(JSON.stringify(current)).toBe(before);
});

it("icon-only navigation retains stage names for keyboard and assistive technology", () => {
  const markup=renderToStaticMarkup(<StageNavigation flow={flow()} current="plan" onSelect={() => {}}/>);
  expect(markup).toContain('aria-label="04 分镜 待确认"');
  expect(markup).toContain('aria-current="step"');
});

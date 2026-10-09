import { expect,it,vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CostQuote, type Estimate } from "./CostQuote";
import { ReadinessRows } from "./ReadinessRows";
const quote:Estimate={calls:0,estimateCents:null,label:"",note:"",targets:[{id:"shot",title:"微光亮起",orderIndex:3,operation:"shot_image",kind:"image"}]};
function element(consent:boolean,targets=quote.targets){return CostQuote({quote:{...quote,targets},consent,onConsent:vi.fn(),busy:false,onConfirm:vi.fn(),onBack:vi.fn()});}
it("unpriced quote lists targets, hides call counts and requires explicit consent",()=> { const tree=element(false); const html=renderToStaticMarkup(tree); expect(html).toContain("镜头 03 · 微光亮起"); expect(html).toContain("未配置计价规则"); expect(html).not.toContain("0 次调用"); expect(html).not.toContain("调用模型"); expect(html).toContain('disabled=""'); expect(renderToStaticMarkup(element(true))).not.toContain('disabled=""'); });
it("an empty quote cannot start even with consent",()=> { expect(renderToStaticMarkup(element(true,[]))).toContain('disabled=""'); });
it("readiness shows materials without human checklists",()=> { const html=renderToStaticMarkup(<ReadinessRows locationDone={1} locationTotal={1} previewConfirmed={true} accepted={5} total={5}/>); expect(html.match(/<dt>/g)).toHaveLength(2); expect(html).toContain("场景素材"); expect(html).toContain("分镜视频"); expect(html).not.toContain("验收"); expect(html).not.toContain("；"); });
it("cancelling a priced confirmation never submits generation", () => {
  const onConfirm=vi.fn(), onBack=vi.fn();
  const tree=CostQuote({quote:{...quote,estimateCents:11,calls:1},consent:false,onConsent:vi.fn(),busy:false,onConfirm,onBack});
  const actions=tree.props.children.at(-1);
  actions.props.children[0].props.onClick();
  expect(onBack).toHaveBeenCalledOnce(); expect(onConfirm).not.toHaveBeenCalled();
  actions.props.children[1].props.onClick(); expect(onConfirm).toHaveBeenCalledOnce();
});

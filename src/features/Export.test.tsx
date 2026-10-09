import { expect,it,vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Export, CoverDownload } from "./Export";
import { useStore } from "@/lib/store";
import type { Project } from "@/lib/types";
vi.mock("@/lib/store",async importOriginal=> { const original=await importOriginal<typeof import("@/lib/store")>(); return {...original,useProject:()=>original.useStore.getState().projects.find(project=>project.id===original.useStore.getState().activeId)}; });
function markup(){ const old=useStore.getState(); const project={id:"export-project",name:"给夜晚留一盏灯",scenes:[],characters:[],cover:"",ratio:"16:9",style:"写实",creative:{shots_confirmed:true,locations:{}}} as unknown as Project; useStore.setState({projects:[project],activeId:project.id}); const html=renderToStaticMarkup(<Export/>); useStore.setState(old); return html; }
it("B8: unavailable music presets are explained and no preset buttons render",()=> { const html=markup(); expect(html).toContain("本部署未配置音乐预设"); expect(html).not.toContain("背景音乐曲风"); });
it("B9: unavailable intro and watermark show explanations without their switches",()=> { const html=markup(); expect(html).toContain("本部署未配置片头素材"); expect(html).toContain("本部署未配置水印素材"); expect(html).not.toContain("品牌水印<small>"); expect(html).not.toContain("片头片尾<small>"); });
it("acceptance panel stays inside preview column before the filmstrip",()=> { const html=markup(); expect(html.indexOf("export-readiness-panel")).toBeGreaterThan(html.indexOf("export-preview-panel")); expect(html.indexOf("export-readiness-panel")).toBeLessThan(html.indexOf("export-settings")); });

it("cover download has a visible secondary button surface and icon",()=> { const html=renderToStaticMarkup(<CoverDownload url="/cover.png"/>); expect(html).toContain('class="btn secondary full"'); expect(html).toContain('href="/cover.png"'); expect(html).toContain("lucide-image-down"); expect(html).toContain("下载封面"); });

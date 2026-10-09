import { expect,it,vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Home,ProjectCover } from "./Home";
import { useStore } from "@/lib/store";
import type { Project } from "@/lib/types";
vi.mock("@/lib/store",async importOriginal=>{ const original=await importOriginal<typeof import("@/lib/store")>(); const mocked=Object.assign((selector:(state:ReturnType<typeof original.useStore.getState>)=>unknown)=>selector(original.useStore.getState()), original.useStore); return {...original,useStore:mocked}; });
vi.mock("next/navigation",()=>({useRouter:()=>({push:vi.fn()})}));
it("B4: empty cover renders the actual project title without an image",()=> { const html=renderToStaticMarkup(<ProjectCover cover="" name="宿舍八卦风暴"/>); expect(html).not.toContain("<img"); expect(html).toContain("project-cover-placeholder"); expect(html).toContain(">宿舍八卦风暴</span>"); });
it("B5: actual home card displays project name instead of unrelated English title",()=> { const project={id:"p",name:"宿舍八卦风暴",description:"",scenes:[],characters:[],cover:"",ratio:"9:16",style:"写实",status:"草稿",updatedAt:Date.now()} as Project; const old=useStore.getState(); useStore.setState({projects:[project],activeId:"p"}); const html=renderToStaticMarkup(<Home/>); useStore.setState(old); expect(html).toContain("宿舍八卦风暴"); expect(html).not.toContain("THE LAST DELIVERY"); expect(html).toContain('class="cover-title"'); });

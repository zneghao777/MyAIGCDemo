import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TaskFeedback, taskTitle, relativeTime, type CreativeTask } from "./shared";
import type { Task, Project } from "@/lib/types";
const project={ scenes:[{id:"shot",title:"微光亮起",image:"/frame.png"}] } as Project;
const task={id:"task",status:"done",progress:100,typeLabel:"视频",sceneId:"shot",createdAt:10000,operation:null} as CreativeTask;
it("B3: missing operation uses backend typeLabel plus shot title",()=> { expect(taskTitle(task,project)).toBe("视频 · 镜头 01 · 微光亮起"); const html=renderToStaticMarkup(<TaskFeedback tasks={[task]} project={project}/>); expect(html).toContain('width="40"'); expect(html).toContain("微光亮起"); expect(html).not.toContain("类型未知"); });
it("B3: full list sorts failures first and distinguishes repeated attempts",()=> { const html=renderToStaticMarkup(<TaskFeedback tasks={[{...task,id:"f",status:"failed"}, task,{...task,id:"q",status:"queued"}]} project={project} maxItems={100}/>); expect(html.indexOf('cw-task failed')).toBeLessThan(html.indexOf('cw-task queued')); expect(html.indexOf('cw-task queued')).toBeLessThan(html.indexOf('cw-task done')); expect(html).toContain("第 1 次"); expect(html).toContain("第 3 次"); });
it("default task list stays at one item and relative time is meaningful",()=> { const html=renderToStaticMarkup(<TaskFeedback tasks={[task,{...task,id:"other"}]} project={project}/>); expect(html.match(/class="cw-task done"/g)).toHaveLength(1); expect(relativeTime(10000,730000)).toBe("12 分钟前"); });

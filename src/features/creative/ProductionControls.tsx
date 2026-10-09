"use client";
import { useEffect, useState } from "react";
import { api, apiBase } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Project, Scene } from "@/lib/types";
import type { VideoInput } from "@/lib/creative-types";
import { ErrorNotice } from "./ErrorNotice";
import { ShotReviewEditor } from "./ShotReview";

type Reference = VideoInput["references"][number] & { name: string; url: string; duration?: number };
type Take = { take: string; asset_id: string; url: string; key: string; duration: number; width: number; height: number; stale_at_completion?: boolean; sound_strategy?: string; audio_cleanup?: { audio_from_take?: string; ranges: {start:number;end:number}[] } };
type Production = { capabilities?: { resolutions: string[]; min_duration: number; max_duration: number; max_references: {total:number} }; suggestions: Reference[]; leader_id: string; takes: Take[]; segment?: { scene_ids: string[] } };
export const inputNames = { first_frame: "首帧精控", first_last_frame: "首尾帧过渡", references: "多素材联合参考", text: "纯文字预演" };

export function ProductionControls({ project, scene, reload }: { project: Project; scene: Scene; reload: () => Promise<void> }) {
  const [input, setInput] = useState<VideoInput>(scene.creative?.shot?.video_input || { mode: "first_frame", references: [], sound_strategy: "post_audio" });
  const [data, setData] = useState<Production | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const [audioOnly,setAudioOnly]=useState(false);
  const [excerpt, setExcerpt] = useState({id:"",start:0,end:5});
  const [library, setLibrary] = useState<Reference[]>([]), [extra, setExtra] = useState("");
  const index = project.scenes.findIndex(row => row.id === scene.id);
  const [last, setLast] = useState(project.scenes[index + 1]?.id || "");
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api<Production>(`/creative/scenes/${scene.id}/production`, "GET", undefined, controller.signal), api<{ id: string; kind: string; url: string; contentType: string; createdAt: string }[]>(`/projects/${project.id}/assets`, "GET", undefined, controller.signal)]).then(([value, assets]) => {
      setData(value);
      const namedAsset = (id: string) => { for (const row of project.scenes) { const i = row.creative?.video_takes?.findIndex(take => take.asset_id === id) ?? -1; if (i >= 0) return `${row.title} · 视频版本 ${i + 1}`; } return undefined; };
      setLibrary(assets.filter(asset => /^(image|video|audio)\//.test(asset.contentType)).map((asset, i) => ({ asset_id: asset.id, kind: asset.contentType.split("/")[0] as Reference["kind"], name: namedAsset(asset.id) || `${asset.contentType.startsWith("image") ? "图片" : asset.contentType.startsWith("audio") ? "声音" : "视频"} · ${new Date(asset.createdAt).toLocaleDateString()} · ${i + 1}`, purpose: "", url: asset.url })));
    }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [project.id, project.creative?.version, scene.id, scene.creative?.version]);
  const selected = new Map(input.references.map(ref => [ref.asset_id, ref]));
  const all = new Map(library.map(ref => [ref.asset_id, ref]));
  data?.suggestions.forEach(ref => all.set(ref.asset_id, ref));
  input.references.forEach(ref => { const media = all.get(ref.asset_id); if (media && !data?.suggestions.some(item => item.asset_id === ref.asset_id)) all.set(ref.asset_id, {...media, name: ref.purpose.split(/[；。]/)[0] || media.name}); });
  const update = (patch: Partial<VideoInput>) => setInput(value => ({ ...value, ...patch }));
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await action(); await reload(); useStore.getState().notify("已保存制作安排"); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  const member = data && data.leader_id !== scene.id;
  return <section className="production-settings" aria-label="本段制作方式">
    <h4>制作方式</h4>
    {data?.segment && <p className="helper">本段包含 {data.segment.scene_ids.map(id => project.scenes.find(row => row.id === id)?.title).join(" → ")}</p>}
    {member ? <button className="btn" onClick={() => useStore.setState({sceneId: data.leader_id})}>前往片段首镜设置与生成</button> : <>
      <div className="production-form-grid">
        <label className="creative-field">输入方式<select value={input.mode} onChange={e => update({ mode: e.target.value as VideoInput["mode"], references: [], first_frame_asset_id: undefined, last_frame_asset_id: undefined })}>{Object.entries(inputNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
        <label className="creative-field">声音方式<select value={input.sound_strategy} onChange={e => update({sound_strategy: e.target.value as VideoInput["sound_strategy"]})}><option value="model_audio">模型原声 · 无需先做配音</option><option value="post_audio">后期配音 · 使用独立录音</option></select></label>
      </div>
      {input.mode === "text" && <p className="helper">用于概念预演。正式角色片段建议选用形象参考，以帮助保持人物一致。</p>}
      {input.mode.startsWith("first") && <p className="helper">首尾帧在“编辑镜头与台词 → 起止画面”中选择。需要有效起始画面。</p>}
      {input.mode === "references" && <>
        <h4>本次参考 · 已选 {input.references.length} 项</h4>
        <p className="helper">下列勾选项才会发送给模型。声音参考只定义音色，实际台词来自本段设计。</p>
        <div className="production-reference-list">{Array.from(new Map([...(data?.suggestions || []), ...input.references.map(ref => all.get(ref.asset_id)).filter((ref): ref is Reference => !!ref)].map(ref => [ref.asset_id, ref])).values()).map(ref => <article key={ref.asset_id} className={selected.has(ref.asset_id) ? "is-selected" : ""}>
          {ref.kind === "image" ? <img src={ref.url} alt={ref.name}/> : ref.kind === "audio" ? <audio controls preload="none" src={ref.url} aria-label={ref.name}/> : <video controls preload="metadata" src={ref.url} aria-label={ref.name}/>}
          <label><input type="checkbox" checked={selected.has(ref.asset_id)} onChange={e => update({references: e.target.checked ? [...input.references, {kind:ref.kind,asset_id:ref.asset_id,purpose:ref.purpose || ref.name}] : input.references.filter(x => x.asset_id !== ref.asset_id)})}/> {ref.name}<small>{selected.has(ref.asset_id) ? "已选用于本次" : "建议用于本次"}</small></label>
          {ref.kind !== "image" && <button className="btn" onClick={()=>{setAudioOnly(false);setExcerpt({id:ref.asset_id,start:0,end:Math.min(5,ref.duration || 5)});}}>截取较短参考</button>}
          {selected.has(ref.asset_id) && <label className="creative-field">参考用途<input value={selected.get(ref.asset_id)?.purpose || ""} onChange={e => update({references: input.references.map(x => x.asset_id === ref.asset_id ? {...x,purpose:e.target.value} : x)})}/></label>}
        </article>)}</div>
        {excerpt.id && <section><h4>截取参考 · 原素材保留</h4>{all.get(excerpt.id)?.kind === "video" && <label><input type="checkbox" checked={audioOnly} onChange={e=>setAudioOnly(e.target.checked)}/>只取声音，作为音色参考</label>}<div className="production-form-grid"><label className="creative-field">参考开始秒<input type="number" step="0.1" min="0" value={excerpt.start} onChange={e=>setExcerpt({...excerpt,start:Number(e.target.value)})}/></label><label className="creative-field">参考结束秒<input type="number" step="0.1" value={excerpt.end} onChange={e=>setExcerpt({...excerpt,end:Number(e.target.value)})}/></label></div><button className="btn" disabled={busy} onClick={async()=>{setBusy(true);setError(null);try{const source=all.get(excerpt.id)!;const ref=await api<Reference>(`/creative/projects/${project.id}/reference-excerpt`,"POST",{expected:project.creative?.version,data:{asset_id:excerpt.id,start_sec:excerpt.start,end_sec:excerpt.end,audio_only:audioOnly,purpose:selected.get(excerpt.id)?.purpose || source.purpose || source.name}});setLibrary(rows=>[...rows,{...ref,name:source.name+" · 节选"}]);update({references:[...input.references.filter(x=>x.asset_id!==excerpt.id),{kind:ref.kind,asset_id:ref.asset_id,purpose:ref.purpose}]});setExcerpt({id:"",start:0,end:5});}catch(e){setError(e);}finally{setBusy(false);}}}>截取并选入本次</button><button className="btn" onClick={()=>setExcerpt({id:"",start:0,end:5})}>取消截取</button></section>}
        <details><summary>上传补充参考</summary><label className="creative-field">图片、声音或视频<input type="file" accept="image/*,audio/*,video/*" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;setBusy(true);setError(null);try{const body=new FormData();body.append("file",file);const response=await fetch(`${apiBase}/api/creative/projects/${project.id}/reference-media`,{method:"POST",body});const value=await response.json();if(!response.ok)throw new Error(value.error?.message || "上传失败");setLibrary(rows=>[...rows,value]);update({references:[...input.references,{kind:value.kind,asset_id:value.asset_id,purpose:file.name}]});}catch(error){setError(error);}finally{setBusy(false);}}}/></label></details>
        <details><summary>从项目素材补充</summary><label className="creative-field">已有素材<select value={extra} onChange={e => setExtra(e.target.value)}><option value="">选择可预览的素材</option>{Array.from(all.values()).filter(ref => !selected.has(ref.asset_id)).map(ref => <option key={ref.asset_id} value={ref.asset_id}>{ref.name}</option>)}</select></label>{extra && all.get(extra) && <><a href={all.get(extra)!.url} target="_blank" rel="noreferrer">预览选中的素材</a><button className="btn" onClick={() => {const ref=all.get(extra)!;update({references:[...input.references,{kind:ref.kind,asset_id:extra,purpose:ref.name}]});setExtra("");}}>加入本次参考</button></>}</details>
      </>}
      <label className="creative-field">补充生成要求<textarea rows={3} value={input.prompt || ""} onChange={e => update({prompt:e.target.value})}/></label>
      <details><summary>生成规格</summary><label className="creative-check"><input type="checkbox" checked={input.use_context_ir || false} onChange={e=>update({use_context_ir:e.target.checked})}/>整理参考关系与对白要求</label><label className="creative-field">分辨率<select value={input.resolution || "480P"} onChange={e => update({resolution:e.target.value as VideoInput["resolution"]})}>{(data?.capabilities?.resolutions || [input.resolution || "480P"]).map(value => <option key={value}>{value}</option>)}</select></label><p className="helper">当前渠道每段 {data?.capabilities?.min_duration || 4}–{data?.capabilities?.max_duration || 30} 整数秒；1080P、2K、4K 使用后置超分，实际尺寸以输出为准。</p></details>
      <button className="btn primary" disabled={busy} onClick={() => void run(() => api(`/creative/scenes/${scene.id}/production-settings`, "POST", {expected:scene.creative?.version || 0,data:input}))}>保存制作方式与参考</button>
    </>}
    <details><summary>相邻镜头组成生成片段</summary><p className="helper">一次生成多镜连贯表演。回放后可调整采用区间；切镜时刻不是逐帧保证。</p>{data?.segment ? <button className="btn" disabled={busy} onClick={() => void run(() => api(`/creative/projects/${project.id}/segments`, "POST", {expected:project.creative?.version,data:{scene_ids:data.segment!.scene_ids,action:"split"}}))}>取消组合，恢复单镜制作</button> : <><label className="creative-field">从本镜组合到<select value={last} onChange={e => setLast(e.target.value)}>{project.scenes.slice(index+1).map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select></label><button className="btn" disabled={busy || !last} onClick={() => void run(() => api(`/creative/projects/${project.id}/segments`, "POST", {expected:project.creative?.version,data:{scene_ids:project.scenes.slice(index,project.scenes.findIndex(row => row.id === last)+1).map(row=>row.id)}}))}>组合为一个生成片段</button></>}</details>
    <ErrorNotice error={error}/>
  </section>;
}

export function VideoTakes({project, scene, reload}: {project:Project; scene:Scene; reload:()=>Promise<void>}) {
  const [data,setData]=useState<Production|null>(null),[error,setError]=useState<unknown>(null),[busy,setBusy]=useState(false);
  const [audioFrom,setAudioFrom]=useState("");
  const [muteStart,setMuteStart]=useState(0),[muteEnd,setMuteEnd]=useState(1);
  const [start,setStart]=useState(scene.creative?.edit?.in_sec || 0),[end,setEnd]=useState(scene.creative?.edit?.out_sec || 0);
  useEffect(()=>{const controller=new AbortController();void api<Production>(`/creative/scenes/${scene.id}/production`,"GET",undefined,controller.signal).then(setData).catch(e=>{if(!controller.signal.aborted)setError(e);});return()=>controller.abort();},[scene.id, scene.creative?.version, project.creative?.version]);
  async function run(action:()=>Promise<unknown>){setBusy(true);setError(null);try{await action();await reload();useStore.getState().notify("已保存视频选择与检查");}catch(e){setError(e);}finally{setBusy(false);}}
  return <section className="video-takes"><h4>视频版本与回放</h4><ErrorNotice error={error}/>{!data?.takes.length && <p className="helper">生成完成后，先播放候选，再选入本片。</p>}{data?.takes.slice().reverse().map((take,i)=><details key={take.take} open={i===0}><summary>视频版本 {data.takes.length-i} · 实测 {take.duration?.toFixed(2)} 秒 {scene.creative?.video?.take === take.take ? "· 已选用" : "· 候选待选"}</summary><video controls playsInline preload="metadata" src={take.url} aria-label={`视频版本 ${data.takes.length-i}`}/><p>{take.width} × {take.height} · {take.stale_at_completion ? "生成期间设计已变更，保留原片供比较" : "请试听台词、说话人与音色，检查口型和切镜"}</p><button className="btn primary" disabled={busy || scene.creative?.video?.take===take.take || data.leader_id!==scene.id} onClick={()=>void run(()=>api(`/creative/scenes/${scene.id}/select-video`,"POST",{expected:scene.creative?.version,data:{take:take.take}}))}>选用此视频版本</button></details>)}
    {scene.videoUrl && <>{data?.leader_id === scene.id && <details><summary>局部声音清理 · 本地处理</summary><p className="helper">针对已选视频中的杂音或多余声音，将指定区间静音，画面与速度保持原样。时间从原视频开头计算。也可复用相同时长的历史音轨，处理后请重新检查音画同步。原片保留，另存候选。</p><label className="creative-field">声音来源<select value={audioFrom} onChange={e=>setAudioFrom(e.target.value)}><option value="">当前选中视频的原声</option>{data.takes.filter(take=>take.sound_strategy === "model_audio" && Math.abs(take.duration-Number(scene.creative?.video?.duration || 0)) < .1).map(take=><option key={take.take} value={take.take}>视频版本 {data.takes.indexOf(take)+1} 的声音</option>)}</select></label><div className="production-form-grid"><label className="creative-field">静音开始秒<input type="number" min="0" step="0.01" value={muteStart} onChange={e=>setMuteStart(Number(e.target.value))}/></label><label className="creative-field">静音结束秒<input type="number" step="0.01" value={muteEnd} onChange={e=>setMuteEnd(Number(e.target.value))}/></label></div><button className="btn" disabled={busy} onClick={()=>void run(()=>api(`/creative/scenes/${scene.id}/clean-video-audio`,"POST",{expected:scene.creative?.version,data:{take:scene.creative?.video?.take,...(audioFrom ? {audio_from_take:audioFrom} : {}),ranges:[{start:muteStart,end:muteEnd}]}}))}>另存声音清理候选 · 不调用模型</button></details>}<details><summary>调整本镜采用区间</summary><p className="helper">默认按设计分配，最后一镜保留完整尾段。调整区间不会改变播放速度；请回放确认台词未截断。</p><div className="production-form-grid"><label className="creative-field">入点（秒）<input type="number" min="0" step="0.01" value={start} onChange={e=>setStart(Number(e.target.value))}/></label><label className="creative-field">出点（秒）<input type="number" min="0" step="0.01" value={end} onChange={e=>setEnd(Number(e.target.value))}/></label></div><button className="btn" disabled={busy} onClick={()=>void run(()=>api(`/creative/scenes/${scene.id}/edit-range`,"POST",{expected:scene.creative?.version,data:{in_sec:start,out_sec:end}}))}>保存采用区间</button></details><ShotReviewEditor key={scene.creative?.version} allowRetake={false} scene={scene} busy={busy} run={run}/></>}
  </section>;
}

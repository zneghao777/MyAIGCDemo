"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { errorText } from "@/features/creative/copy";
import { remoteMode, aiTask, api } from "@/lib/api";
import dynamic from "next/dynamic";
import { refreshRemote } from "@/lib/remote-store";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Plus,
  Play,
  Pause,
  Check,
  Move3D,
  Rotate3D,
  Scaling,
  Camera,
  Sparkles,
  Box,
  UsersRound,
  Grid3X3,
  Trash2,
  Diamond,
  RotateCcw,
  X,
  Maximize2,
} from "lucide-react";
import { useProject, useStore } from "@/lib/store";
import { defaultStage } from "@/lib/data";
import {
  type DirectorData,
  type StageObject,
  type Vector,
  uid,
  timecode,
} from "@/lib/types";
import { Empty, Modal } from "@/components/ui";
const StageCanvas = dynamic(() => import("./StageCanvas"), {
  ssr: false,
  loading: () => (
    <div className="stage-loading">
      <Box size={35} />
      <p>{uiCopy["正在准备 3D 创作空间…"]}</p>
      <div className="skeleton" />
    </div>
  ),
});
export function Director() {
  const p = useProject();
  const id = useStore((s) => s.sceneId);
  const scene = p?.scenes.find((s) => s.id === id) || p?.scenes[0];
  if (!p || !scene)
    return (
      <Empty
        title={uiCopy["先为故事添加一个镜头"]}
        action={
          <Link className="btn primary" href="/studio">
            {uiCopy["前往分镜"]}</Link>
        }
      />
    );
  const initial = scene.directorData || defaultStage();
  const cast = p.characters.filter(
    (c) => !scene.creative || !!scene.creative.shot?.cast[c.id],
  );
  if (!scene.directorData && scene.creative) {
    let actorIndex = 0;
    initial.objects = initial.objects
      .filter((o) => o.kind !== "actor" || actorIndex++ < cast.length)
      .map((o) =>
        o.kind === "actor" ? { ...o, characterId: cast.shift()?.id } : o,
      );
    for (const o of initial.objects)
      if (o.characterId)
        o.name =
          p.characters.find((c) => c.id === o.characterId)?.name || o.name;
    initial.keyframes = initial.keyframes.filter((k) =>
      initial.objects.some((o) => o.id === k.objectId),
    );
  }
  return (
    <DirectorEditor
      key={scene.id}
      initial={initial}
      creativeVersion={scene.creative?.version}
      characterIds={Object.fromEntries(
        p.characters
          .filter((c) => !scene.creative || !!scene.creative.shot?.cast[c.id])
          .map((c) => [c.name, c.id]),
      )}
      sceneId={scene.id}
      title={scene.title}
      duration={scene.durationSec}
      names={p.characters.map((c) => c.name)}
    />
  );
}
function DirectorEditor({
  initial,
  sceneId,
  title,
  duration,
  names,
  creativeVersion,
  characterIds,
}: {
  initial: DirectorData;
  sceneId: string;
  title: string;
  duration: number;
  names: string[];
  creativeVersion?: number;
  characterIds: Record<string, string>;
}) {
  const [data, setData] = useState<DirectorData>(() =>
    structuredClone(initial),
  );
  const [selected, setSelected] = useState(initial.objects[0]?.id || "");
  const [mode, setMode] = useState<"translate" | "rotate" | "scale">(
    "translate",
  );
  const [assetTab, setAssetTab] = useState<string>(uiCopy["场景"]);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [keyId, setKeyId] = useState("");
  const [big, setBig] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const obj = data.objects.find((o) => o.id === selected);
  const key = data.keyframes.find((k) => k.id === keyId);
  const [camDescription, setCamDescription] = useState("");
  const update = (fn: (d: DirectorData) => DirectorData) => {
    setData(fn);
    setDirty(true);
  };
  useEffect(() => {
    if (!playing) return;
    let start = performance.now() - time * 1000;
    const timer = setInterval(() => {
      const next = (performance.now() - start) / 1000;
      if (next >= duration) {
        setTime(0);
        setPlaying(false);
      } else setTime(next);
    }, 33);
    return () => clearInterval(timer);
  }, [playing, duration]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  const patchObject = (id: string, p: Partial<StageObject>) =>
    update((d) => ({
      ...d,
      objects: d.objects.map((o) => (o.id === id ? { ...o, ...p } : o)),
    }));
  const addObject = (kind: StageObject["kind"], name: string) => {
    const id = uid();
    update((d) => ({
      ...d,
      objects: [
        ...d.objects,
        {
          id,
          name,
          kind,
          characterId: kind === "actor" ? characterIds[name] : undefined,
          position: [0, kind === "camera" ? 1.5 : 0, 0],
          rotation: [0, 0, 0],
          scale: 1,
          color: kind === "actor" ? "#f5b942" : "#9c8be8",
          action: uiCopy["站立"],
        },
      ],
    }));
    setSelected(id);
  };
  const addKey = (objectId = selected, t = time) => {
    const o = data.objects.find((o) => o.id === objectId);
    if (!o) return;
    const id = uid();
    update((d) => ({
      ...d,
      keyframes: [
        ...d.keyframes.filter(
          (k) => !(k.objectId === objectId && Math.abs(k.t - t) < 0.1),
        ),
        {
          id,
          objectId,
          t: Math.round(t * 10) / 10,
          position: [...o.position] as Vector,
        },
      ],
    }));
    setKeyId(id);
  };
  const apply = async () => {
    if (remoteMode && creativeVersion !== undefined) {
      try {
        await api(`/scenes/${sceneId}`, "PATCH", {
          directorData: data,
          expectedVersion: creativeVersion,
        });
        await refreshRemote();
        setDirty(false);
        useStore
          .getState()
          .notify(uiCopy["导演台数据已保存；相关画面需重新确认，人物身份保持引用版本"]);
      } catch (e) {
        useStore.getState().notify(errorText(e));
      }
      return;
    }
    const actor = data.objects.find((o) => o.kind === "actor");
    const description =
      camDescription ||
      formatCopy("镜头以 {0}° 视角{1}，聚焦{2}。", data.fov, data.keyframes.filter((k) => k.objectId === data.objects.find((o) => o.kind === "camera")?.id).length > 1 ? uiCopy["缓慢推近"] : uiCopy["固定拍摄"], actor?.name || uiCopy["场景主体"]);
    useStore.getState().patchScene(sceneId, {
      directorData: data,
      ...(remoteMode ? { videoPrompt: description } : {}),
      cameraMove: description.includes(uiCopy["推近"]) ? uiCopy["缓推"] : uiCopy["固定"],
    });
    useStore.getState().notify(uiCopy["场景摆位与关键帧已应用到当前分镜"]);
    setDirty(false);
  };
  const viewportProps = {
    data,
    selected,
    onSelect: (id: string) => {
      setSelected(id);
      setKeyId("");
    },
    onChange: patchObject,
    mode,
    time,
    playing,
  };
  return (
    <div className="director-page">
      {confirmApply && <Modal title="应用导演台到当前分镜" onClose={() => setConfirmApply(false)}><div className="modal-body"><h3>{title}</h3><p>本次保存 {data.objects.length} 个对象与 {data.keyframes.length} 个关键帧，相机视角 {data.fov}°。</p><p>{camDescription || "使用当前相机位置、朝向和关键帧表达构图与运镜意图。"}</p><p className="helper">仅更新当前镜头的灰盒导演数据；人物身份保持引用版本，相关画面需要重新检查。不会调用生成服务。</p><div className="button-row"><button className="btn" onClick={() => setConfirmApply(false)}>取消</button><button className="btn primary" onClick={async () => { await apply(); setConfirmApply(false); }}>确认应用到分镜</button></div></div></Modal>}

      <header className="workspace-header">
        <div className="workspace-title">
          <Link
            href="/studio"
            className="icon-btn"
            aria-label={uiCopy["返回分镜"]}
          >
            <ArrowLeft size={18} />
          </Link>
          <div>
            <h1>
              {uiCopy["3D 导演台"]}<span className="badge subtle">{title}</span>
            </h1>
            <p>
              <span className="status-dot" />
              灰盒构图与走位预演 · 角色代理不代表最终渲染</p>
          </div>
        </div>
        <div className="button-row">
          <span className="save-status">
            {dirty ? uiCopy["有待应用的修改"] : uiCopy["场景已就绪"]}
          </span>
          <button className="btn primary small" onClick={() => setConfirmApply(true)}>
            <Check size={15} />
            {uiCopy["应用到分镜"]}</button>
        </div>
      </header>
      <div className="director-layout">
        <aside className="stage-assets">
          <div className="panel-top">
            <h3>{uiCopy["场景资产"]}</h3>
            <span className="mono">{uiCopy["LIBRARY"]}</span>
          </div>
          <div className="filter-tabs">
            {[uiCopy["场景"], uiCopy["道具"], uiCopy["人物"]].map((s) => (
              <button
                key={s}
                className={assetTab === s ? "active" : ""}
                onClick={() => setAssetTab(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="stage-asset-content">
            {assetTab === uiCopy["场景"] ? (
              <>
                <span className="eyebrow">{uiCopy["SCENE TEMPLATES"]}</span>
                <div className="template-grid">
                  {[uiCopy["空房间"], uiCopy["街道"], uiCopy["办公室"], uiCopy["天台"], uiCopy["废墟"], uiCopy["森林"]].map(
                    (s, i) => (
                      <button
                        key={s}
                        className={data.template === s ? "active" : ""}
                        onClick={() => update((d) => ({ ...d, template: s }))}
                      >
                        <div className={`template-art template-${i}`}>
                          <Box size={i % 2 ? 36 : 28} />
                          <Grid3X3 size={25} />
                        </div>
                        <span>
                          {s}
                          {data.template === s ? <Check size={12} /> : null}
                        </span>
                      </button>
                    ),
                  )}
                </div>
                <p className="helper">
                  {uiCopy["灰盒场景用于规划构图，点击切换场景氛围。"]}</p>
              </>
            ) : assetTab === uiCopy["道具"] ? (
              <div className="prop-buttons">
                {[uiCopy["桌子"], uiCopy["工作台"], uiCopy["长椅"], uiCopy["柜台"]].map((s) => (
                  <button
                    className="btn secondary"
                    key={s}
                    onClick={() => addObject("prop", s)}
                  >
                    <Box size={20} />
                    {s}
                    <Plus size={14} />
                  </button>
                ))}
              </div>
            ) : (
              <div className="prop-buttons">
                {(creativeVersion !== undefined
                  ? Object.keys(characterIds)
                  : names
                ).map((s) => (
                  <button
                    className="btn secondary"
                    key={s}
                    onClick={() => addObject("actor", s)}
                  >
                    <UsersRound size={20} />
                    {s}
                    <Plus size={14} />
                  </button>
                ))}
              </div>
            )}
            <div className="outline-divider" />
            <div className="section-heading">
              <span className="eyebrow">{uiCopy["SCENE OBJECTS"]}</span>
              <span className="count">{data.objects.length}</span>
            </div>
            <div className="object-list">
              {data.objects.map((o) => (
                <button
                  className={selected === o.id ? "active" : ""}
                  key={o.id}
                  onClick={() => {
                    setSelected(o.id);
                    setKeyId("");
                  }}
                >
                  <span style={{ color: o.color }}>
                    {o.kind === "camera" ? (
                      <Camera size={16} />
                    ) : o.kind === "actor" ? (
                      <UsersRound size={16} />
                    ) : (
                      <Box size={16} />
                    )}
                  </span>
                  <span>{o.name}</span>
                  <small>
                    {o.kind === "camera"
                      ? "CAM"
                      : o.kind === "actor"
                        ? "ACTOR"
                        : "PROP"}
                  </small>
                </button>
              ))}
            </div>
          </div>
          <div className="stage-assets-footer">
            <button
              className="btn ai full small"
              onClick={() => {
                if (remoteMode) {
                  void aiTask<DirectorData>("stage-layout", {
                    projectId: useStore.getState().activeId,
                    sceneId,
                  })
                    .then((result) => {
                      update(() => result);
                      setSelected(result.objects[0]?.id || "");
                    })
                    .catch((e) => useStore.getState().notify(errorText(e)));
                  return;
                }
                update(() => defaultStage());
                setSelected("actor-1");
                useStore.getState().notify(uiCopy["已载入演示摆位方案"]);
              }}
            >
              <Sparkles size={14} />
              {remoteMode ? uiCopy["AI 自动摆位"] : uiCopy["载入示例摆位"]}
            </button>
          </div>
        </aside>
        <section className={`stage-viewport ${big ? "expanded" : ""}`}>
          <div className="viewport-top">
            <div className="viewport-tabs">
              <span>
                <i />
                {uiCopy["透视视图"]}</span>
              <span>{uiCopy["网格吸附 0.25m"]}</span>
            </div>
            <div className="segmented">
              {(
                [
                  { m: "translate", icon: Move3D, label: uiCopy["移动工具"] },
                  { m: "rotate", icon: Rotate3D, label: uiCopy["旋转工具"] },
                  { m: "scale", icon: Scaling, label: uiCopy["缩放工具"] },
                ] as const
              ).map((o) => (
                <button
                  title={o.label}
                  aria-label={o.label}
                  key={o.m}
                  className={mode === o.m ? "active" : ""}
                  onClick={() => setMode(o.m)}
                >
                  <o.icon size={17} />
                </button>
              ))}
              <button
                aria-label={big ? uiCopy["退出放大"] : uiCopy["放大视口"]}
                onClick={() => setBig(!big)}
              >
                {big ? <X size={16} /> : <Maximize2 size={16} />}
              </button>
            </div>
          </div>
          <StageCanvas {...viewportProps} />
          <div className="viewport-instructions">
            {uiCopy["拖动旋转视角 · 滚轮缩放 · 点击物体显示变换手柄"]}</div>
          <div className="camera-preview">
            <header>
              <Camera size={12} />
              {uiCopy["主机位预览"]}<span>{data.fov}°</span>
            </header>
            <StageCanvas {...viewportProps} preview />
          </div>
          <div className="viewport-transport">
            <button
              className="round-play"
              aria-label={playing ? uiCopy["暂停走位预演"] : uiCopy["播放走位预演"]}
              onClick={() => setPlaying(!playing)}
            >
              {playing ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <span className="mono">
              {timecode(time)}.{Math.floor((time % 1) * 10)}{" "}
              <small>/ {timecode(duration)}</small>
            </span>
          </div>
        </section>
        <aside className="stage-inspector">
          <div className="panel-top">
            <h3>{key ? uiCopy["关键帧属性"] : uiCopy["对象属性"]}</h3>
            <span className="mono">{uiCopy["INSPECTOR"]}</span>
          </div>
          <div className="inspector-content">
            {key ? (
              <>
                <div className="inspector-section">
                  <h4>
                    <Diamond size={15} />
                    {uiCopy["关键帧"]}</h4>
                  <label className="field">
                    {uiCopy["时间（秒）"]}<input
                      type="number"
                      min={0}
                      max={duration}
                      step={0.1}
                      value={key.t}
                      onChange={(e) =>
                        update((d) => ({
                          ...d,
                          keyframes: d.keyframes.map((k) =>
                            k.id === key.id
                              ? {
                                  ...k,
                                  t: Math.max(
                                    0,
                                    Math.min(duration, +e.target.value),
                                  ),
                                }
                              : k,
                          ),
                        }))
                      }
                    />
                  </label>
                  <label className="field">{uiCopy["位置 X / Y / Z"]}</label>
                  <div className="vector-input">
                    {key.position.map((v, i) => (
                      <input
                        aria-label={formatCopy("关键帧 {0} 坐标", "XYZ"[i])}
                        key={i}
                        type="number"
                        step={0.25}
                        value={v}
                        onChange={(e) =>
                          update((d) => ({
                            ...d,
                            keyframes: d.keyframes.map((k) =>
                              k.id === key.id
                                ? {
                                    ...k,
                                    position: k.position.map((x, j) =>
                                      j === i ? +e.target.value : x,
                                    ) as Vector,
                                  }
                                : k,
                            ),
                          }))
                        }
                      />
                    ))}
                  </div>
                  <p className="helper">{uiCopy["线性插值 · 播放时在关键帧之间移动。"]}</p>
                  <button
                    className="btn secondary danger full"
                    onClick={() => {
                      update((d) => ({
                        ...d,
                        keyframes: d.keyframes.filter((k) => k.id !== key.id),
                      }));
                      setKeyId("");
                    }}
                  >
                    <Trash2 size={14} />
                    {uiCopy["删除关键帧"]}</button>
                </div>
              </>
            ) : obj ? (
              <>
                <div className="selected-object">
                  <span style={{ background: obj.color }} />
                  <strong>{obj.name}</strong>
                  <span className="badge subtle">
                    {obj.kind === "actor"
                      ? uiCopy["人物"]
                      : obj.kind === "camera"
                        ? uiCopy["机位"]
                        : uiCopy["道具"]}
                  </span>
                </div>
                <label className="field">
                  {uiCopy["对象名称"]}<input
                    value={obj.name}
                    onChange={(e) =>
                      patchObject(obj.id, { name: e.target.value })
                    }
                  />
                </label>
                <div className="inspector-section">
                  <h4>
                    {uiCopy["变换"]}<small>{uiCopy["TRANSFORM"]}</small>
                  </h4>
                  <label className="field">
                    {uiCopy["位置"]}<span className="muted">{uiCopy["m"]}</span>
                  </label>
                  <div className="vector-input">
                    {obj.position.map((n, i) => (
                      <label key={i}>
                        <span>{"XYZ"[i]}</span>
                        <input
                          aria-label={formatCopy("对象 {0} 坐标", "XYZ"[i])}
                          type="number"
                          step={0.25}
                          value={Math.round(n * 100) / 100}
                          onChange={(e) =>
                            patchObject(obj.id, {
                              position: obj.position.map((x, j) =>
                                i === j ? +e.target.value : x,
                              ) as Vector,
                            })
                          }
                        />
                      </label>
                    ))}
                  </div>
                  <div className="field-grid">
                    <label className="field">
                      {uiCopy["朝向角度"]}<input
                        type="number"
                        step={15}
                        value={Math.round((obj.rotation[1] * 180) / Math.PI)}
                        onChange={(e) =>
                          patchObject(obj.id, {
                            rotation: [0, (+e.target.value * Math.PI) / 180, 0],
                          })
                        }
                      />
                    </label>
                    <label className="field">
                      {uiCopy["缩放"]}<input
                        type="number"
                        min={0.1}
                        max={5}
                        step={0.1}
                        value={Math.round(obj.scale * 10) / 10}
                        onChange={(e) =>
                          patchObject(obj.id, {
                            scale: Math.max(0.1, +e.target.value),
                          })
                        }
                      />
                    </label>
                  </div>
                </div>
                {obj.kind === "actor" ? (
                  <label className="field">
                    {uiCopy["动作"]}<select
                      value={obj.action}
                      onChange={(e) =>
                        patchObject(obj.id, { action: e.target.value })
                      }
                    >
                      {[uiCopy["站立"], uiCopy["走路"], uiCopy["奔跑"], uiCopy["坐下"]].map((a) => (
                        <option key={a}>{a}</option>
                      ))}
                    </select>
                    <span className="helper">
                      {uiCopy["动作标签随导演数据保存，胶囊代理仅预演位置。"]}</span>
                  </label>
                ) : null}
                {obj.kind === "camera" ? (
                  <div className="inspector-section">
                    <h4>{uiCopy["镜头设置"]}</h4>
                    <label className="field">
                      {uiCopy["视野角度"]}<b className="mono">{data.fov}°</b>
                      <input
                        type="range"
                        min={20}
                        max={100}
                        value={data.fov}
                        onChange={(e) =>
                          update((d) => ({ ...d, fov: +e.target.value }))
                        }
                      />
                    </label>
                    <div className="shot-type-buttons">
                      {[24, 35, 50, 85].map((f, i) => (
                        <button
                          key={f}
                          onClick={() =>
                            update((d) => ({ ...d, fov: [74, 54, 40, 24][i] }))
                          }
                        >
                          {f}{uiCopy["mm"]}</button>
                      ))}
                    </div>
                  </div>
                ) : null}
                <button className="btn secondary full" onClick={() => addKey()}>
                  <Diamond size={13} />{uiCopy["在"]}{time.toFixed(1)}{uiCopy["s 添加关键帧"]}</button>
                <button
                  className="text-action danger"
                  onClick={() => {
                    update((d) => ({
                      ...d,
                      objects: d.objects.filter((o) => o.id !== selected),
                      keyframes: d.keyframes.filter(
                        (k) => k.objectId !== selected,
                      ),
                    }));
                    setSelected("");
                  }}
                >
                  <Trash2 size={13} />
                  {uiCopy["移除对象"]}</button>
              </>
            ) : (
              <p className="muted">{uiCopy["选择场景中的对象以编辑属性。"]}</p>
            )}
            <div className="inspector-section">
              <h4>
                <Sparkles size={14} />
                {uiCopy["运镜意图"]}</h4>
              <button
                className="btn ai full small"
                onClick={() => {
                  if (remoteMode) {
                    void aiTask<{ text: string }>("camera-description", {
                      projectId: useStore.getState().activeId,
                      sceneId,
                      directorData: data,
                    })
                      .then((result) => setCamDescription(result.text))
                      .catch((e) => useStore.getState().notify(errorText(e)));
                    return;
                  }
                  setCamDescription(
                    formatCopy("镜头以 {0}° 视角，跟随{1}缓慢推近，突出人物与{2}环境的关系。", data.fov, data.objects.find((o) => o.kind === "actor")?.name || uiCopy["人物"], data.template),
                  );
                }}
              >
                {remoteMode ? uiCopy["生成运镜描述"] : uiCopy["生成示例运镜描述"]}
              </button>
              {camDescription ? (
                <p className="camera-description">{camDescription}</p>
              ) : (
                <p className="helper">
                  {uiCopy["从摆位和轨迹中提取镜头语言，应用后写回分镜。"]}</p>
              )}
            </div>
          </div>
        </aside>
      </div>
      <div className="keyframe-timeline" ref={trackRef}>
        <div className="keyframe-toolbar">
          <button
            className="icon-btn"
            aria-label={uiCopy["重置播放头"]}
            onClick={() => {
              setTime(0);
              setPlaying(false);
            }}
          >
            <RotateCcw size={14} />
          </button>
          <span className="mono gold">
            {time.toFixed(1)}{uiCopy["s "]}<small>/ {duration}{uiCopy["s"]}</small>
          </span>
          <input
            aria-label={uiCopy["导演台播放进度"]}
            type="range"
            min={0}
            max={duration}
            step={0.1}
            value={time}
            onChange={(e) => {
              setPlaying(false);
              setTime(+e.target.value);
            }}
          />
          <span>{uiCopy["双击轨道添加关键帧 · 拖动节点调整时间"]}</span>
        </div>
        <div className="tracks">
          {data.objects
            .filter((o) => o.kind !== "prop")
            .map((o) => (
              <div className="keyframe-track" key={o.id}>
                <button
                  className={selected === o.id ? "active" : ""}
                  onClick={() => setSelected(o.id)}
                >
                  <i style={{ background: o.color }} />
                  {o.name}
                  <span>{o.kind === "camera" ? "CAMERA" : "ACTOR"}</span>
                </button>
                <div
                  className="track-lane"
                  onDoubleClick={(e) => {
                    const r = e.currentTarget.getBoundingClientRect();
                    addKey(
                      o.id,
                      Math.max(
                        0,
                        Math.min(
                          duration,
                          ((e.clientX - r.left) / r.width) * duration,
                        ),
                      ),
                    );
                  }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const id = e.dataTransfer.getData("text/plain");
                    const r = e.currentTarget.getBoundingClientRect();
                    update((d) => ({
                      ...d,
                      keyframes: d.keyframes.map((k) =>
                        k.id === id
                          ? {
                              ...k,
                              t:
                                Math.round(
                                  Math.max(
                                    0,
                                    Math.min(
                                      duration,
                                      ((e.clientX - r.left) / r.width) *
                                        duration,
                                    ),
                                  ) * 10,
                                ) / 10,
                            }
                          : k,
                      ),
                    }));
                  }}
                >
                  <div
                    className="playhead"
                    style={{ left: `${(time / duration) * 100}%` }}
                  />
                  {data.keyframes
                    .filter((k) => k.objectId === o.id)
                    .map((k) => (
                      <button
                        draggable
                        onDragStart={(e) =>
                          e.dataTransfer.setData("text/plain", k.id)
                        }
                        className={`keyframe ${keyId === k.id ? "active" : ""}`}
                        aria-label={formatCopy("{0} {1}s 关键帧", o.name, k.t)}
                        key={k.id}
                        style={{
                          left: `${Math.min(99, Math.max(1, (k.t / duration) * 100))}%`,
                          color: o.color,
                        }}
                        onClick={() => {
                          setKeyId(k.id);
                          setSelected(o.id);
                          setTime(k.t);
                        }}
                      >
                        <Diamond size={13} fill="currentColor" />
                      </button>
                    ))}
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, remoteMode, waitTask } from "@/lib/api";
import { refreshRemote } from "@/lib/remote-store";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Sparkles,
  Shuffle,
  Check,
  Plus,
  Film,
  Settings2,
  Upload,
  Play,
  Trash2,
  Pencil,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { assets, defaultCharacters, makeScenes } from "@/lib/data";
import { uid, type Character } from "@/lib/types";
import { speak } from "@/components/ui";
import { CreativeNew } from "./Creative";
import { CharacterEditor } from "./Characters";
const styles: string[] = [
  uiCopy["电影写实"],
  uiCopy["国风古韵"],
  uiCopy["赛博朋克"],
  uiCopy["日式动漫"],
  uiCopy["3D 卡通渲染"],
  uiCopy["水墨黑白"],
];
const stages = [
  uiCopy["正在构思故事梗概"],
  uiCopy["正在设计角色关系"],
  uiCopy["正在拆分分镜画面"],
  uiCopy["正在匹配镜头语言"],
];
export function Wizard() {
  return remoteMode ? <CreativeNew /> : <LegacyWizard />;
}
function LegacyWizard() {
  const initialIdea = useStore((s) => s.idea);
  const [idea, setIdea] = useState(initialIdea);
  const [name, setName] = useState("");
  const [step, setStep] = useState(0);
  const [style, setStyle] = useState<string>(uiCopy["电影写实"]);
  const [ratio, setRatio] = useState("9:16");
  const [duration, setDuration] = useState(60);
  const [count, setCount] = useState<string>(uiCopy["自动"]);
  const [advanced, setAdvanced] = useState(false);
  const [characters, setCharacters] = useState<Character[]>(() =>
    structuredClone(defaultCharacters),
  );
  const [editing, setEditing] = useState<Character | null>(null);
  const [progress, setProgress] = useState(-1);
  const [error, setError] = useState<unknown>("");
  const router = useRouter();
  const completed = useRef(false);
  useEffect(() => {
    if (remoteMode || progress < 0 || progress >= 100) return;
    const t = setTimeout(() => setProgress((p) => Math.min(100, p + 5)), 180);
    return () => clearTimeout(t);
  }, [progress]);
  useEffect(() => {
    if (remoteMode || progress !== 100 || completed.current) return;
    completed.current = true;
    const id = uid();
    const num =
      count === uiCopy["自动"]
        ? Math.max(8, Math.min(24, Math.round(duration / 7)))
        : +count;
    const scenes = makeScenes(id, assets[0], num);
    scenes.forEach((s, i) => {
      const base = Math.floor((duration / num) * 10) / 10;
      s.durationSec =
        i === num - 1
          ? Math.round((duration - base * (num - 1)) * 10) / 10
          : base;
      s.imagePrompt = formatCopy("{0}。{1}，{2}风格。", idea.slice(0, 180), i === 0 ? uiCopy["开场建立环境与主角"] : i === num - 1 ? uiCopy["收束故事，留下一丝余韵"] : formatCopy("第 {0} 镜：推进人物行动与故事冲突", i + 1), style);
      s.dialogue = i === 0 ? uiCopy["故事，就从这里开始。"] : "";
    });
    useStore.getState().addProject({
      id,
      name: name.trim() || idea.slice(0, 12) || uiCopy["未命名的故事"],
      description: idea,
      style,
      ratio,
      updatedAt: Date.now(),
      cover: assets[styles.indexOf(style) % assets.length],
      status: uiCopy["草稿"],
      scenes,
      characters: characters.map((c) => ({ ...c, id: uid() })),
    });
    useStore.getState().setIdea("");
    useStore.getState().notify(uiCopy["演示分镜已生成，可以开始编辑"]);
    router.push("/studio");
  }, [progress, idea, name, count, duration, style, ratio, characters, router]);
  async function generateRemote() {
    setProgress(0);
    setError("");
    try {
      const id = uid();
      await api("/projects", "POST", {
        id,
        name: name.trim() || idea.slice(0, 12),
        description: idea,
        style,
        ratio,
        characters: characters.map((c) => ({
          ...c,
          id: uid(),
          image: c.image.startsWith("/assets/") ? "" : c.image,
        })),
      });
      useStore.setState({ activeId: id });
      const sceneCount =
        count === uiCopy["自动"]
          ? Math.max(8, Math.min(24, Math.round(duration / 7)))
          : +count;
      const { taskId } = await api<{ taskId: string }>(
        `/projects/${id}/script/generate`,
        "POST",
        { idea, sceneCount, durationSec: duration },
      );
      await waitTask(taskId, setProgress);
      await refreshRemote();
      useStore.getState().setIdea("");
      useStore.getState().notify(uiCopy["分镜剧本已生成"]);
      router.push("/studio");
    } catch (e) {
      setError(e);
      setProgress(-1);
    }
  }
  const next = () => {
    if (step === 0 && !idea.trim()) {
      setError(uiCopy["先描述一下你的故事，哪怕只有一句话。"]);
      return;
    }
    if (
      step === 0 &&
      count !== uiCopy["自动"] &&
      (duration / +count < 3 || duration / +count > 10)
    ) {
      setError(
        uiCopy["请调整时长或分镜数量，让每个镜头保持 3–10 秒，或选择自动分镜。"],
      );
      return;
    }
    setError("");
    setStep(step + 1);
  };
  return (
    <div className="wizard-page">
      <div className="page-breadcrumb">
        <Link href="/">
          <ArrowLeft size={15} />
          {uiCopy["项目工作台"]}</Link>
        <span>/</span>
        <span>{uiCopy["新建项目"]}</span>
      </div>
      <div className="wizard-heading">
        <span className="eyebrow">
          <Sparkles size={14} /> {uiCopy["CINEAI STUDIO · PRODUCTION PIPELINE"]}</span>
        <h1>{uiCopy["让新故事，开始发生。"]}</h1>
        <p>{uiCopy["从一句创意到完整分镜，把脑海中的画面变成看得见的故事。"]}</p>
      </div>
      <div className="wizard-steps">
        {[uiCopy["故事创意"], uiCopy["视觉风格"], uiCopy["角色设定"]].map((s, i) => (
          <button
            key={s}
            className={`${step === i ? "active" : ""} ${step > i ? "complete" : ""}`}
            disabled={i > step || progress >= 0}
            onClick={() => setStep(i)}
          >
            <span>
              {step > i ? <Check size={17} /> : String(i + 1).padStart(2, "0")}
            </span>
            <div>
              <small>{uiCopy["STEP 0"]}{i + 1}</small>
              <strong>{s}</strong>
            </div>
            {i === step ? <span className="step-live">{uiCopy["进行中"]}</span> : null}
          </button>
        ))}
      </div>
      {progress >= 0 ? (
        <div className="generation-screen">
          <div className="generation-icon">
            <ClapIcon />
          </div>
          <span className="eyebrow">{uiCopy["YOUR STORY IS TAKING SHAPE"]}</span>
          <h2>{stages[Math.min(3, Math.floor(progress / 25))]}…</h2>
          <p>
            {remoteMode
              ? uiCopy["正在调用 DeepSeek 生成并校验分镜"]
              : uiCopy["正在用演示数据构建你的创作空间"]}
          </p>
          <div className="progress-track">
            <span style={{ transform: `scaleX(${progress / 100})` }} />
          </div>
          <b className="mono">{progress}%</b>
          <div className="generation-stages">
            {stages.map((s, i) => (
              <span className={progress >= i * 25 ? "done" : ""} key={s}>
                {progress > (i + 1) * 25 ? <Check size={14} /> : <i />}
                {s}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <>
          {step === 0 ? (
            <div className="wizard-columns">
              <section className="form-panel">
                <div className="panel-heading">
                  <span className="number-label">01</span>
                  <h2>{uiCopy["描述你的故事"]}</h2>
                  <button
                    className="text-action"
                    onClick={() =>
                      setIdea(
                        [
                          uiCopy["在午夜最后一班地铁上，一个失眠的作家遇到了自己笔下的人物。"],
                          uiCopy["末世废土中，一个快递机器人学会了说谎，却只是为了保护最后一位收件人。"],
                          uiCopy["江南小镇的旧照相馆里，每一张照片都通往一个未完成的心愿。"],
                        ][Math.floor(Math.random() * 3)],
                      )
                    }
                  >
                    <Shuffle size={14} />
                    {uiCopy["换个灵感"]}</button>
                </div>
                <label className="field">
                  {uiCopy["项目名称"]}<span className="muted">{uiCopy["选填"]}</span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={uiCopy["为你的故事起一个名字"]}
                    maxLength={50}
                  />
                </label>
                <label className="field">
                  {uiCopy["故事创意"]}<textarea
                    className="idea-textarea"
                    value={idea}
                    maxLength={2000}
                    onChange={(e) => {
                      setIdea(e.target.value);
                      setError("");
                    }}
                    placeholder={
                      uiCopy["主角是谁？故事发生在哪里？有什么意想不到的转折？\n\n试着告诉我们你脑海中的画面…"]
                    }
                  />
                </label>
                <div className="textarea-footer">
                  <label className="upload-text">
                    <Upload size={14} />
                    {uiCopy["导入 TXT 剧本"]}<input
                      type="file"
                      accept=".txt"
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          if (file.size > 200000) {
                            setError(uiCopy["请上传 200KB 以内的文本"]);
                            return;
                          }
                          setIdea((await file.text()).slice(0, 2000));
                        }
                      }}
                    />
                  </label>
                  <span className="mono">{idea.length} / 2000</span>
                </div>
                <ErrorNotice error={error} />
                <button
                  className="advanced-toggle"
                  onClick={() => setAdvanced(!advanced)}
                >
                  <Settings2 size={16} />
                  {uiCopy["高级创作选项"]}<span>{advanced ? uiCopy["收起"] : uiCopy["展开"]}</span>
                </button>
                {advanced ? (
                  <div className="advanced-fields">
                    <label className="field">
                      {uiCopy["目标时长"]}<b>{duration}{uiCopy["s"]}</b>
                      <input
                        type="range"
                        min={30}
                        max={180}
                        step={5}
                        value={duration}
                        onChange={(e) => setDuration(+e.target.value)}
                      />
                    </label>
                    <label className="field">
                      {uiCopy["分镜数量"]}<select
                        value={count}
                        onChange={(e) => setCount(e.target.value)}
                      >
                        {[uiCopy["自动"], "8", "12", "16"].map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                ) : null}
                <div className="info-box">
                  <Sparkles size={20} />
                  <div>
                    <strong>{uiCopy["让 AI 帮你理清故事脉络"]}</strong>
                    <p>
                      {uiCopy["拆分场景、安排角色、匹配镜头语言，每一处细节都由你掌控。"]}</p>
                  </div>
                </div>
              </section>
              <aside className="inspiration-panel">
                <span className="eyebrow">{uiCopy["DIRECTOR'S NOTES"]}</span>
                <h2>
                  {uiCopy["每个伟大的故事，"]}<br />
                  {uiCopy["都始于一个「如果」。"]}</h2>
                <img src={assets[0]} alt={uiCopy["雨夜城市里的电影叙事灵感"]} />
                <div className="inspiration-caption">
                  <span>{uiCopy["构建世界，创造情绪。"]}</span>
                  <small>{uiCopy["电影写实 · CINEMATIC REALISM"]}</small>
                </div>
                <div className="writing-tips">
                  <h4>{uiCopy["给灵感一点方向"]}</h4>
                  <p>
                    <span>01</span>{uiCopy["一个鲜明的角色，一种强烈的渴望。"]}</p>
                  <p>
                    <span>02</span>{uiCopy["一次意外，让平静的生活偏离轨道。"]}</p>
                  <p>
                    <span>03</span>{uiCopy["一个选择，改变故事最终的方向。"]}</p>
                </div>
              </aside>
            </div>
          ) : null}
          {step === 1 ? (
            <section className="form-panel style-panel">
              <div className="panel-heading">
                <span className="number-label">02</span>
                <h2>{uiCopy["选择画面风格"]}</h2>
                <span className="muted">{uiCopy["统一全片视觉，让故事更有辨识度"]}</span>
              </div>
              <div className="style-grid">
                {styles.map((s, i) => (
                  <button
                    className={`style-card ${s === style ? "active" : ""}`}
                    key={s}
                    onClick={() => setStyle(s)}
                  >
                    <img
                      src={assets[[0, 2, 3, 1, 4, 0][i]]}
                      alt={formatCopy("{0}风格参考", s)}
                      style={{ filter: i === 5 ? "grayscale(1)" : undefined }}
                    />
                    <div>
                      <span>{s}</span>
                      {s === style ? (
                        <Check size={18} />
                      ) : (
                        <span className="choice-circle" />
                      )}
                    </div>
                  </button>
                ))}
              </div>
              <div className="ratio-picker">
                <div>
                  <h3>{uiCopy["画面比例"]}</h3>
                  <p>{uiCopy["选择适合你作品的银幕。"]}</p>
                </div>
                {["9:16", "16:9", "1:1"].map((r, i) => (
                  <button
                    className={ratio === r ? "active" : ""}
                    key={r}
                    onClick={() => setRatio(r)}
                  >
                    <span className={`ratio-icon ratio-${i}`} />
                    <span>
                      {r}
                      <small>{[uiCopy["竖屏短剧"], uiCopy["横屏电影"], uiCopy["方形画面"]][i]}</small>
                    </span>
                    {ratio === r ? <Check size={16} /> : null}
                  </button>
                ))}
              </div>
            </section>
          ) : null}
          {step === 2 ? (
            <section className="form-panel">
              <div className="panel-heading">
                <span className="number-label">03</span>
                <h2>{uiCopy["认识故事里的主角"]}</h2>
                <span className="muted">{uiCopy["示例角色 · 可自由修改"]}</span>
              </div>
              <div className="character-grid">
                {characters.map((c, i) => (
                  <article className="character-card" key={c.id}>
                    <div className="character-image">
                      <img src={c.image} alt={formatCopy("{0}角色参考画面", c.name)} />
                      <span className="badge">{i === 0 ? uiCopy["主角"] : uiCopy["配角"]}</span>
                    </div>
                    <div className="character-body">
                      <h3>
                        {c.name}
                        <small>{c.age} {uiCopy["岁"]}</small>
                      </h3>
                      <p>{c.description}</p>
                      <div className="button-row">
                        <button
                          className="btn secondary small"
                          onClick={() => setEditing(c)}
                        >
                          <Pencil size={13} />
                          {uiCopy["编辑"]}</button>
                        <button
                          className="icon-btn"
                          aria-label={formatCopy("试听{0}音色", c.name)}
                          onClick={() => speak(uiCopy["总有人，在等一封信。"], c.voice)}
                        >
                          <Play size={15} />
                        </button>
                        <button
                          className="icon-btn danger"
                          aria-label={formatCopy("删除角色{0}", c.name)}
                          onClick={() =>
                            setCharacters((cs) =>
                              cs.filter((x) => x.id !== c.id),
                            )
                          }
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
                <button
                  className="new-character-card"
                  onClick={() =>
                    setEditing({
                      id: uid(),
                      name: uiCopy["新角色"],
                      age: "25",
                      description: "",
                      clothing: "",
                      voice: uiCopy["女声 · 冷静"],
                      image: assets[0],
                      consistency: uiCopy["参考图模式"],
                    })
                  }
                >
                  <Plus size={28} />
                  <strong>{uiCopy["添加角色"]}</strong>
                  <span>{uiCopy["让故事更加丰富"]}</span>
                </button>
              </div>
            </section>
          ) : null}
          <div className="wizard-footer">
            <div>
              <Sparkles size={19} />
              <span>
                {duration} {uiCopy["秒 ·"]}{" "}
                {count === uiCopy["自动"] ? uiCopy["智能分镜"] : formatCopy("{0} 个分镜", count)} · {ratio}
                <small>{uiCopy["演示生成，无需接入模型服务"]}</small>
              </span>
            </div>
            <div className="button-row">
              {step > 0 ? (
                <button
                  className="btn secondary"
                  onClick={() => setStep(step - 1)}
                >
                  <ArrowLeft size={16} />
                  {uiCopy["上一步"]}</button>
              ) : (
                <Link className="btn ghost" href="/">
                  {uiCopy["取消"]}</Link>
              )}
              <button
                className="btn primary"
                disabled={step === 2 && !characters.length}
                onClick={() =>
                  step < 2
                    ? next()
                    : remoteMode
                      ? void generateRemote()
                      : setProgress(0)
                }
              >
                {step === 2 ? (
                  <>
                    <Sparkles size={17} />
                    {uiCopy["生成分镜剧本"]}</>
                ) : (
                  <>
                    {uiCopy["下一步 ·"]}{step === 0 ? uiCopy["视觉风格"] : uiCopy["角色设定"]}
                    <ArrowRight size={17} />
                  </>
                )}
              </button>
            </div>
          </div>
        </>
      )}
      {editing ? (
        <CharacterEditor
          character={editing}
          onClose={() => setEditing(null)}
          onSave={(c) => {
            setCharacters((cs) =>
              cs.some((x) => x.id === c.id)
                ? cs.map((x) => (x.id === c.id ? c : x))
                : [...cs, c],
            );
            setEditing(null);
          }}
        />
      ) : null}
    </div>
  );
}
function ClapIcon() {
  return <Film size={42} />;
}

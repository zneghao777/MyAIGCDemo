"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { remoteMode } from "@/lib/api";
import { CreativeEntry } from "./Creative";
import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  Plus,
  Pencil,
  Play,
  Upload,
  Save,
  Shuffle,
  Trash2,
  UsersRound,
} from "lucide-react";
import { useProject, useStore } from "@/lib/store";
import { assets } from "@/lib/data";
import { uid, type Character } from "@/lib/types";
import { Modal, Empty, speak } from "@/components/ui";
export function CharacterEditor({
  character,
  onClose,
  onSave,
}: {
  character: Character;
  onClose: () => void;
  onSave: (c: Character) => void;
}) {
  const [c, setC] = useState(() => ({ ...character }));
  const [error, setError] = useState("");
  const patch = (p: Partial<Character>) => setC((c) => ({ ...c, ...p }));
  return (
    <Modal title={uiCopy["角色设定"]} onClose={onClose} wide>
      <form
        className="character-editor"
        onSubmit={(e) => {
          e.preventDefault();
          if (!c.name.trim()) return;
          onSave({ ...c, name: c.name.trim() });
        }}
      >
        <div className="character-reference">
          <img src={c.image} alt={formatCopy("{0}参考形象", c.name)} />
          <div className="button-row">
            <label className="btn secondary small">
              <Upload size={14} />
              {uiCopy["上传参考图"]}<input
                type="file"
                hidden
                accept="image/*"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  if (f.size > 1200000) {
                    setError(uiCopy["请使用小于 1.2MB 的参考图"]);
                    return;
                  }
                  const r = new FileReader();
                  r.onload = () => {
                    patch({ image: String(r.result) });
                    setError("");
                  };
                  r.readAsDataURL(f);
                }}
              />
            </label>
            <button
              type="button"
              className="icon-btn"
              aria-label={uiCopy["切换示例参考图"]}
              onClick={() =>
                patch({
                  image: assets[(assets.indexOf(c.image) + 1) % assets.length],
                })
              }
            >
              <Shuffle size={15} />
            </button>
          </div>
          <p className="helper">
            {uiCopy["参考画面用于保持角色形象一致。演示图来自 Stitch 原型素材。"]}</p>
        </div>
        <div className="character-fields">
          <div className="field-grid">
            <label className="field">
              {uiCopy["姓名"]}<input
                required
                value={c.name}
                onChange={(e) => patch({ name: e.target.value })}
              />
            </label>
            <label className="field">
              {uiCopy["年龄"]}<input
                type="number"
                min={1}
                max={120}
                value={c.age}
                onChange={(e) => patch({ age: e.target.value })}
              />
            </label>
          </div>
          <label className="field">
            {uiCopy["角色人设"]}<textarea
              rows={4}
              value={c.description}
              onChange={(e) => patch({ description: e.target.value })}
            />
          </label>
          <label className="field">
            {uiCopy["服装描述"]}<textarea
              rows={2}
              value={c.clothing}
              onChange={(e) => patch({ clothing: e.target.value })}
            />
          </label>
          <label className="field">
            {uiCopy["一致性设置"]}<select
              value={c.consistency}
              onChange={(e) => patch({ consistency: e.target.value })}
            >
              <option>{uiCopy["参考图模式"]}</option>
              <option disabled>{uiCopy["专属 LoRA · 待接入"]}</option>
            </select>
          </label>
          <label className="field">
            {uiCopy["角色音色"]}<select
              value={c.voice}
              onChange={(e) => patch({ voice: e.target.value })}
            >
              {[uiCopy["女声 · 冷静"], uiCopy["女声 · 温柔"], uiCopy["男声 · 沉稳"], uiCopy["男声 · 青年"]].map(
                (s) => (
                  <option key={s}>{s}</option>
                ),
              )}
            </select>
          </label>
          <button
            className="text-action"
            type="button"
            onClick={() => speak(uiCopy["这封信，一定会送到你的手上。"], c.voice)}
          >
            <Play size={14} />
            {uiCopy["试听台词"]}<span className="muted">{uiCopy["浏览器合成音色"]}</span>
          </button>
          {error ? <p className="error-text">{error}</p> : null}
          <button type="submit" className="btn primary">
            <Save size={16} />
            {uiCopy["保存角色"]}</button>
        </div>
      </form>
    </Modal>
  );
}
export function Characters() {
  return remoteMode ? <CreativeEntry charactersOnly /> : <LegacyCharacters />;
}
function LegacyCharacters() {
  const p = useProject();
  const [editing, setEditing] = useState<Character | null>(null);
  const [remove, setRemove] = useState<Character | null>(null);
  return (
    <div className="standard-page">
      <div className="page-breadcrumb">
        <Link href="/studio">
          <ArrowLeft size={15} />
          {uiCopy["返回分镜"]}</Link>
        <span>/</span>
        <span>{uiCopy["角色资产库"]}</span>
      </div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">{uiCopy["CHARACTER VAULT"]}</span>
          <h1>{uiCopy["每个角色，都有自己的故事。"]}</h1>
          <p>{p?.name || uiCopy["项目"]} {uiCopy["· 管理角色形象、人设与音色"]}</p>
        </div>
        {p ? (
          <button
            className="btn primary"
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
            <Plus size={16} />
            {uiCopy["添加角色"]}</button>
        ) : null}
      </div>
      <div className="character-grid">
        {p?.characters.map((c, i) => (
          <article key={c.id} className="character-card">
            <div className="character-image">
              <img src={c.image} alt={formatCopy("{0}参考画面", c.name)} />
              <span className="badge">{i === 0 ? uiCopy["主角"] : uiCopy["配角"]}</span>
            </div>
            <div className="character-body">
              <h3>
                {c.name}
                <small>{c.age} {uiCopy["岁"]}</small>
              </h3>
              <p>{c.description}</p>
              <span className="muted small-text">
                {c.voice} · {c.consistency}
              </span>
              <div className="button-row">
                <button
                  className="btn secondary small"
                  onClick={() => setEditing(c)}
                >
                  <Pencil size={14} />
                  {uiCopy["编辑角色"]}</button>
                <button
                  aria-label={formatCopy("试听{0}", c.name)}
                  className="icon-btn"
                  onClick={() => speak(uiCopy["总有人，在等一封信。"], c.voice)}
                >
                  <Play size={16} />
                </button>
                <button
                  aria-label={formatCopy("删除{0}", c.name)}
                  className="icon-btn danger"
                  onClick={() => setRemove(c)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
      {!p || !p.characters.length ? (
        <Empty
          title={uiCopy["角色等待登场"]}
          description={uiCopy["先创建项目，再为你的故事添加角色。"]}
          action={
            <Link href="/new" className="btn primary">
              {uiCopy["新建项目"]}</Link>
          }
        />
      ) : null}
      {editing ? (
        <CharacterEditor
          character={editing}
          onClose={() => setEditing(null)}
          onSave={(c) => {
            useStore.getState().saveCharacter(c);
            setEditing(null);
            useStore.getState().notify(uiCopy["角色已保存"]);
          }}
        />
      ) : null}
      {remove ? (
        <Modal
          title={formatCopy("删除角色「{0}」？", remove.name)}
          onClose={() => setRemove(null)}
        >
          <div className="modal-body">
            <p>{uiCopy["删除后，该角色将从当前项目的角色资产库移除。"]}</p>
            <button
              className="btn danger-solid"
              onClick={() => {
                useStore.getState().removeCharacter(remove.id);
                setRemove(null);
              }}
            >
              {uiCopy["确认删除"]}</button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

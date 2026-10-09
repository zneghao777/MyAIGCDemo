"use client";
import { copy } from "./creative/copy";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { remoteMode } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Sparkles,
  Plus,
  Search,
  Grid2X2,
  List,
  MoreHorizontal,
  Clock3,
  ArrowUpRight,
  Copy,
  Pencil,
  Trash2,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { timecode, type Project } from "@/lib/types";
import { Empty, Modal } from "@/components/ui";
export function Home() {
  const projects = useStore((s) => s.projects);
  const idea = useStore((s) => s.idea);
  const [filter, setFilter] = useState<string>(uiCopy["全部项目"]);
  const [query, setQuery] = useState("");
  const [list, setList] = useState(false);
  const [sort, setSort] = useState("recent");
  const [menu, setMenu] = useState<string | null>(null);
  const [edit, setEdit] = useState<Project | null>(null);
  const [name, setName] = useState("");
  const [remove, setRemove] = useState<Project | null>(null);
  const router = useRouter();
  const shown = projects
    .filter(
      (p) =>
        (filter === uiCopy["全部项目"] || p.status === filter) &&
        p.name.toLowerCase().includes(query.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "recent"
        ? b.updatedAt - a.updatedAt
        : a.name.localeCompare(b.name, "zh"),
    );
  const open = (id: string) => {
    useStore.getState().selectProject(id);
    router.push(`/studio?project=${id}`);
  };
  return (
    <div className="home-page">
      <header className="project-home-heading"><h1>我的项目</h1><p>{projects.length} 个项目</p></header>
      <form className="idea-launcher" onSubmit={e => { e.preventDefault(); useStore.setState({ idea }); router.push("/new"); }}>
        <Sparkles size={19}/><input aria-label="输入故事创意" placeholder="输入故事创意…" value={idea} onChange={e => useStore.setState({ idea: e.target.value })}/>
        <button className="btn primary" type="submit"><Plus size={17}/>新建项目</button>
      </form>
      <section className="projects-section">
        <div className="section-heading">
          <div className="heading-title">
            <h2>{uiCopy["我的项目"]}</h2>
            <span className="count">{projects.length}</span>
          </div>
          <span className="muted small-text">{uiCopy["好故事，从这里开始"]}</span>
        </div>
        <div className="project-toolbar">
          <div className="filter-tabs">
            {[uiCopy["全部项目"], uiCopy["剪辑中"], uiCopy["草稿"], uiCopy["已导出"]].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={filter === f ? "active" : ""}
              >
                {f}
                <span>
                  {f === uiCopy["全部项目"]
                    ? projects.length
                    : projects.filter((p) => p.status === f).length}
                </span>
              </button>
            ))}
          </div>
          <div className="toolbar-right">
            <label className="search">
              <Search size={15} />
              <input
                aria-label={uiCopy["搜索项目"]}
                placeholder={uiCopy["搜索项目…"]}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <select
              className="sort-select"
              aria-label={uiCopy["项目排序"]}
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="recent">{uiCopy["最近更新"]}</option>
              <option value="name">{uiCopy["项目名称"]}</option>
            </select>
            <div className="segmented">
              <button
                aria-label={uiCopy["网格视图"]}
                aria-pressed={!list}
                className={!list ? "active" : ""}
                onClick={() => setList(false)}
              >
                <Grid2X2 size={16} />
              </button>
              <button
                aria-label={uiCopy["列表视图"]}
                aria-pressed={list}
                className={list ? "active" : ""}
                onClick={() => setList(true)}
              >
                <List size={16} />
              </button>
            </div>
          </div>
        </div>
        <div className={`project-grid ${list ? "list-view" : ""}`}>
          {shown.map((p, i) => {
            return (
              <article
                className="project-card"
                key={p.id}
                style={{ animationDelay: `${i * 45}ms` }}
              >
                <button
                  className="project-cover"
                  onClick={() => open(p.id)}
                  aria-label={formatCopy("打开项目 {0}", p.name)}
                >
                  <ProjectCover cover={p.cover} name={p.name} eager={i <= 2} />
                  <span
                    className={`project-status ${p.status === uiCopy["已导出"] ? "exported" : p.status === uiCopy["草稿"] ? "draft" : "editing"}`}
                  >
                    <i />
                    {p.status}
                  </span>
                  <span className="cover-ratio">{p.ratio}</span>
                  <span className="cover-open">
                    <span>
                      <ArrowUpRight size={20} />
                    </span>
                    {uiCopy["继续创作"]}</span>
                  <span className="cover-title">{p.name}</span>
                </button>
                <div className="project-body">
                  <div className="project-title-row">
                    <button
                      className="text-button"
                      aria-label={formatCopy("编辑项目 {0}", p.name)}
                      onClick={() => open(p.id)}
                    >
                      <h3>{p.name}</h3>
                    </button>
                    <div className="menu-wrap">
                      <button
                        className="icon-btn"
                        aria-label={formatCopy("{0} 更多操作", p.name)}
                        onClick={() => setMenu(menu === p.id ? null : p.id)}
                      >
                        <MoreHorizontal size={19} />
                      </button>
                      {menu === p.id ? (
                        <>
                          <button
                            className="menu-dismiss"
                            aria-label={uiCopy["关闭菜单"]}
                            onClick={() => setMenu(null)}
                          />
                          <div className="dropdown">
                            <button
                              onClick={() => {
                                setEdit(p);
                                setName(p.name);
                                setMenu(null);
                              }}
                            >
                              <Pencil size={14} />
                              {uiCopy["重命名"]}</button>
                            <button
                              onClick={() => {
                                useStore.getState().copyProject(p.id);
                                setMenu(null);
                              }}
                            >
                              <Copy size={14} />
                              {uiCopy["复制项目"]}</button>
                            <button
                              className="danger"
                              onClick={() => {
                                setRemove(p);
                                setMenu(null);
                              }}
                            >
                              <Trash2 size={14} />
                              {uiCopy["删除项目"]}</button>
                          </div>
                        </>
                      ) : null}
                    </div>
                  </div>

                  <div className="project-meta">
                    <span>{p.ratio}</span>
                    <i />
                    <span>{p.scenes.length} {uiCopy["个分镜"]}</span>
                    <i />
                    <span className="mono">
                      {timecode(
                        p.scenes.reduce((n, s) => n + s.durationSec, 0),
                      )}
                    </span>
                  </div>
                  <footer>
                    <span>
                      <Clock3 size={12} />
                      {Date.now() - p.updatedAt < 60000
                        ? uiCopy["刚刚更新"]
                        : Date.now() - p.updatedAt < 3600000
                          ? formatCopy("{0} 分钟前更新", Math.floor((Date.now() - p.updatedAt) / 60000))
                          : formatCopy("{0} 小时前更新", Math.floor((Date.now() - p.updatedAt) / 3600000))}
                    </span>
                    <button onClick={() => open(p.id)}>
                      {uiCopy["进入工作台"]}<ArrowUpRight size={13} />
                    </button>
                  </footer>
                </div>
              </article>
            );
          })}
        </div>
        {!shown.length ? (
          <Empty
            title={query ? uiCopy["没有找到相关项目"] : uiCopy["这里还没有作品"]}
            description={
              query
                ? uiCopy["换个关键词试试，或创建一个新故事。"]
                : uiCopy["输入一个灵感，开始你的第一部短剧。"]
            }
            action={
              <Link href="/new" className="btn primary">
                <Plus size={16} />
                {uiCopy["开始创作"]}</Link>
            }
          />
        ) : null}
      </section>
      <footer className="home-footer">
        <span>
          <i />
          {remoteMode ? uiCopy["服务端工作台 · 项目持久化保存"] : uiCopy["所有创作，已在本地妥善保存"]}
        </span>
        <span>
          {uiCopy["CINEAI STUDIO"]}<span className="muted">/</span> {uiCopy["MAKE YOUR NEXT SCENE."]}</span>
      </footer>
      {edit ? (
        <Modal title={uiCopy["重命名项目"]} onClose={() => setEdit(null)}>
          <form
            className="modal-body"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              useStore.getState().patchProject(edit.id, { name: name.trim() });
              setEdit(null);
            }}
          >
            <label className="field">
              {uiCopy["项目名称"]}<input
                autoFocus
                required
                maxLength={50}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button className="btn primary" type="submit">
              {uiCopy["保存名称"]}</button>
          </form>
        </Modal>
      ) : null}
      {remove ? (
        <Modal title={uiCopy["删除这个项目？"]} onClose={() => setRemove(null)}>
          <div className="modal-body">
            <p>「{remove.name}{uiCopy["」及其本地分镜将被删除。"]}</p>
            <div className="button-row">
              <button className="btn secondary" onClick={() => setRemove(null)}>
                {uiCopy["保留项目"]}</button>
              <button
                className="btn danger-solid"
                onClick={() => {
                  useStore.getState().removeProject(remove.id);
                  setRemove(null);
                }}
              >
                {uiCopy["删除项目"]}</button>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

export function ProjectCover({ cover, name, eager = false }: { cover?: string; name: string; eager?: boolean }) {
  return cover ? <img src={cover} alt={copy.projectCover(name)} loading={eager ? "eager" : "lazy"} /> : <span className="project-cover-placeholder" aria-label={copy.projectCover(name)}>{name}</span>;
}

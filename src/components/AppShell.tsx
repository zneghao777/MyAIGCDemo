"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import Link from "next/link";
import styles from "./cinema.module.css";
import { remoteMode } from "@/lib/api";
import {
  installRemoteActions,
  refreshRemote,
  connectRemote,
} from "@/lib/remote-store";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Clapperboard,
  LayoutDashboard,
  BookOpen,
  Video,
  ListVideo,
  UsersRound,
  Plus,
  Bell,
  ChevronDown,
  CircleHelp,
  PanelLeftClose,
  PanelLeftOpen,
  Check,
  HardDrive,
  Menu,
  X,
  Sparkles,
  ArrowLeft,
  ImageIcon,
  Play as PlayIcon,
} from "lucide-react";
import { useProject, useStore } from "@/lib/store";
import { timecode } from "@/lib/types";
import { Modal } from "./ui";
const globalNav = [
  { href: "/", label: "我的项目", icon: LayoutDashboard },
  { href: "/new", label: "新建项目", icon: Plus },
  { href: "/characters", label: "本片角色", icon: UsersRound },
  { href: "/queue", label: "生成任务", icon: ListVideo },
];
const projectStages = [
  { key: "plan", label: "01 故事", icon: BookOpen },
  { key: "characters", label: "02 角色与声音", icon: UsersRound },
  { key: "locations", label: "03 场景", icon: ImageIcon },
  { key: "storyboard", label: "04 分镜", icon: Clapperboard },
  { key: "generation", label: "05 成片", icon: PlayIcon },
];
export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const project = useProject();
  const inProject = !!project && !["/", "/new"].includes(path);
  const inWorkbench = ["/studio", "/characters"].includes(path);
  const syncState = useStore((s) => s.syncState);
  const readRetryUntil = useStore((s) => s.readRetryUntil);
  const projects = useStore((s) => s.projects);
  const toast = useStore((s) => s.toast);
  const [ready, setReady] = useState(false);
  const [storageError, setStorageError] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [help, setHelp] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const tasks = useStore((s) => s.tasks);
  const pending = tasks.filter((t) =>
    ["running", "queued"].includes(t.status),
  ).length;
  useEffect(() => {
    let disposed = false;
    async function initialize() {
      if (remoteMode) {
        await useStore.persist.rehydrate();
        useStore.setState({ projects: [], tasks: [] });
        installRemoteActions();
        try {
          const requestedProject = new URLSearchParams(window.location.search).get("project");
          await refreshRemote(requestedProject || undefined);
          if (requestedProject && !useStore.getState().projects.some(project => project.id === requestedProject)) useStore.getState().notify(uiCopy["项目入口已失效或该项目不可访问，保留当前项目。"]);
        } catch {
          useStore.setState({ syncState: "error" });
          useStore.getState().notify(uiCopy["后端连接失败，请检查服务与配置"]);
        }
      } else {
        await useStore.persist.rehydrate();
      }
      if (!disposed) setReady(true);
    }
    void initialize();
    const warn = () => setStorageError(true);
    window.addEventListener("cineai-storage-error", warn);
    return () => {
      disposed = true;
      window.removeEventListener("cineai-storage-error", warn);
    };
  }, []);
  useEffect(() => {
    if (!ready) return;
    const applyLink = () => {
      const query = new URLSearchParams(window.location.search);
      const requestedProject = query.get("project");
      const state = useStore.getState();
      const target = state.projects.find(project => project.id === requestedProject);
      if (target && state.activeId !== target.id) {
        state.selectProject(target.id);
        if (remoteMode) void refreshRemote(target.id).catch(() => useStore.setState({ syncState: "error" }));
      }
      const requestedScene = query.get("scene");
      const current = target || state.projects.find(project => project.id === state.activeId);
      if (requestedScene && current?.scenes.some(scene => scene.id === requestedScene)) useStore.setState({ sceneId: requestedScene });
    };
    applyLink();
    window.addEventListener("popstate", applyLink);
    return () => window.removeEventListener("popstate", applyLink);
  }, [ready, path]);
  useEffect(() => {
    if (!ready || !inProject || !project?.id) return;
    const url = new URL(window.location.href);
    if (!url.searchParams.has("project")) {
      url.searchParams.set("project", project.id);
      window.history.replaceState(window.history.state, "", url);
    }
  }, [ready, inProject, project?.id, path]);
  useEffect(() => {
    if (!ready || remoteMode) return;
    const timer = setInterval(() => useStore.getState().tick(), 700);
    return () => clearInterval(timer);
  }, [ready]);
  useEffect(() => {
    if (!remoteMode || !ready) return;
    return connectRemote(project?.id || "");
  }, [ready, project?.id]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => useStore.setState({ toast: null }), 4200);
    return () => clearTimeout(t);
  }, [toast]);
  if (!ready)
    return (
      <div className="boot">
        <Clapperboard size={38} />
        <span>{uiCopy["CineAI Studio"]}</span>
        <div className="skeleton" />
      </div>
    );
  return (
    <div className={`app-shell cinema-shell ${styles.root} ${inProject ? "project-shell" : "global-shell"} ${collapsed ? "sidebar-collapsed" : ""}`}>
      <header className={`global-header ${styles.chrome}`}>
        <Link href="/" className="brand" aria-label="CineAI Studio · 返回首页">
          <span className="brand-icon">
            <Clapperboard size={23} />
          </span>
          <span>
            {uiCopy["CineAI"]}<b>{uiCopy["Studio"]}</b>
            <small>{uiCopy["CREATIVE WORKSPACE"]}</small>
          </span>
        </Link>
        <span className="header-divider" />
        <div className="project-switch">
          <Clapperboard size={15} />
          <select
            aria-label={uiCopy["切换项目"]}
            value={project?.id || ""}
            onChange={(e) => { useStore.getState().selectProject(e.target.value); const url = new URL(window.location.href); if (inProject) { url.searchParams.set("project", e.target.value); url.searchParams.delete("scene"); window.history.replaceState(window.history.state, "", url); } }}
          >
            {!projects.length ? (
              <option value="">{uiCopy["暂无项目"]}</option>
            ) : (
              projects.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.name}
                </option>
              ))
            )}
          </select>
          <ChevronDown size={14} />
        </div>
        <div className="header-actions">
          <span className="local-status">
            <i />
            {remoteMode ? uiCopy["已连接工作台"] : uiCopy["本地演示"]}{" "}
            <span>
              ·{" "}
              {remoteMode
                ? readRetryUntil && readRetryUntil > Date.now() ? uiCopy["请求限流，等待自动恢复"] : {
                    loading: uiCopy["连接中"],
                    saving: uiCopy["保存中"],
                    synced: uiCopy["已同步"],
                    error: uiCopy["连接或保存失败"],
                  }[syncState]
                : storageError
                  ? uiCopy["保存失败"]
                  : uiCopy["自动保存"]}
            </span>
          </span>
          <Link className="btn primary small" href="/new">
            <Plus size={16} />
            {uiCopy["新建项目"]}</Link>
          <button
            className="icon-btn notification"
            aria-label={uiCopy["查看通知"]}
            onClick={() => setNotifications(!notifications)}
          >
            <Bell size={18} />
            {pending > 0 ? <i /> : null}
          </button>
          <img
            className="avatar"
            src="/assets/director-avatar.png"
            alt={uiCopy["导演头像"]}
          />
        </div>
      </header>
      <aside className={`sidebar ${styles.chrome}`}>
        {inProject ? <>
          <Link className="back-projects" href="/" aria-label="返回项目"><ArrowLeft size={17} /><span>返回项目</span></Link>
          <div className="side-label"><span>创作流程</span></div>
          {inWorkbench ? <div id="project-stage-navigation" /> : <nav aria-label="创作阶段">{projectStages.map(stage => <Link aria-label={stage.label} title={stage.label} key={stage.key} href={`/studio?stage=${stage.key}`} className={(path === "/export" && stage.key === "generation") || (path === "/director" && stage.key === "storyboard") ? "active" : ""}><stage.icon size={18}/><span>{stage.label}</span></Link>)}</nav>}
          <nav className="project-tools" aria-label="项目工具">
            <Link href="/director" aria-label="3D 导演台" className={path === "/director" ? "active" : ""}><Video size={18}/><span>3D 导演台</span></Link>
            {!inWorkbench && <Link href="/queue" aria-label="生成任务" className={path === "/queue" ? "active" : ""}><ListVideo size={18}/><span>生成任务</span>{pending > 0 && <small>{pending}</small>}</Link>}
            <Link href="/characters" aria-label="本片角色"><UsersRound size={18}/><span>本片角色</span></Link>
          </nav>
          <div id="project-workspace-tools"/>
        </> : <nav aria-label="全局导航">{globalNav.map(n => <Link href={n.href} aria-label={n.label} title={n.label} key={n.href} className={path === n.href ? "active" : ""}><n.icon size={18}/><span>{n.label}</span></Link>)}</nav>}
        <button aria-label="使用指南" className="sidebar-help" onClick={() => setHelp(true)}><CircleHelp size={17}/><span>使用指南</span></button>
        <div className="side-bottom">
          <div className="workspace-note">
            <span className="tiny-label">{uiCopy["YOUR CREATIVE SPACE"]}</span>
            <div>
              <span className="storage-icon">
                <HardDrive size={18} />
              </span>
              <span>
                {uiCopy["灵感，随时续写"]}<small>
                  {remoteMode
                    ? uiCopy["作品已在本机保存"]
                    : uiCopy["作品保存在当前浏览器"]}
                </small>
              </span>
            </div>
          </div>
          <div className="duration-widget">
            <span>
              <small>{uiCopy["当前项目时长"]}</small>
              <b className="mono">
                {timecode(
                  project?.scenes.reduce((n, s) => n + s.durationSec, 0) || 0,
                )}
                <i>:00</i>
              </b>
            </span>
            <span className="ratio-tag">{project?.ratio || "9:16"}</span>
          </div>
          <button
            className="collapse-button"
            aria-label={collapsed ? uiCopy["展开侧栏"] : uiCopy["收起侧栏"]}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <PanelLeftClose size={17} />
            )}
            <span>{uiCopy["收起侧栏"]}</span>
          </button>
        </div>
      </aside>
      <div className={`main-content ${path === "/" ? "home-main" : ""}`}>
        {children}
      </div>
      <div className="mobile-notice">
        <Menu size={16} />
        {uiCopy["建议使用桌面端，获得完整创作体验"]}</div>
      {toast || storageError ? (
        <div className="toast" role="status">
          <Check size={17} />
          {storageError
            ? uiCopy["本地空间不足，最新修改未保存。请下载项目文件备份。"]
            : toast?.message}
          <button
            aria-label={uiCopy["关闭通知"]}
            className="icon-btn"
            onClick={() => {
              setStorageError(false);
              useStore.setState({ toast: null });
            }}
          >
            <X size={14} />
          </button>
        </div>
      ) : null}
      {notifications ? (
        <div className="notifications">
          <div className="section-heading">
            <h3>{uiCopy["任务通知"]}</h3>
            <button
              className="icon-btn"
              aria-label={uiCopy["关闭任务通知"]}
              onClick={() => setNotifications(false)}
            >
              <X size={16} />
            </button>
          </div>
          <p>
            {pending
              ? formatCopy("{0} 个{1}任务正在等待或处理中", pending, remoteMode ? "" : uiCopy["演示"])
              : uiCopy["暂时没有进行中的任务"]}
          </p>
          <Link href="/queue" onClick={() => setNotifications(false)}>
            {uiCopy["查看渲染队列 →"]}</Link>
        </div>
      ) : null}
      {help ? (
        <Modal title={uiCopy["欢迎来到 CineAI Studio"]} onClose={() => setHelp(false)}>
          <div className="modal-body">
            <p>{uiCopy["从一句创意开始，完成你的短剧分镜。"]}</p>
            <ol className="help-list">
              <li>{uiCopy["新建项目，选择画面风格与角色。"]}</li>
              <li>{uiCopy["在剧本分镜中编辑画面、台词和镜头语言。"]}</li>
              <li>{uiCopy["在 3D 导演台调整人物、道具和相机，应用到分镜。"]}</li>
              <li>{uiCopy["通过渲染队列体验生成、暂停和失败重试。"]}</li>
              <li>{uiCopy["在导出页预演分镜，并下载演示视频或项目文件。"]}</li>
            </ol>
            <div className="info-box">
              <Sparkles size={18} />
              {remoteMode
                ? uiCopy["已连接工作台使用真实模型接口与数据库。未启用视频模型时，导出为静帧运镜的分镜动态预演。"]
                : uiCopy["当前为前端演示。AI 生成与任务进度为 Mock；项目自动保存在当前浏览器。"]}
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

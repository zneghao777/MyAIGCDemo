"use client";
import { uiCopy } from "@/features/creative/copy";

import { TechnicalDetails } from "./TechnicalDetails";
import { ErrorNotice } from "@/features/creative/ErrorNotice";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Modal } from "@/components/ui";

type Media = {
  image?: string;
  voice?: string;
  audio?: { url: string; text: string }[];
};
type HistoryItem = {
  id: string;
  kind: string;
  entityId: string;
  name: string;
  summary: string;
  createdAt: string;
  event?: { id: string };
  changes: { field: string; label: string; before: string; after: string }[];
  beforeMedia?: Media;
  afterMedia?: Media;
  current: boolean;
  usedBy?: string[];
  restorable: boolean;
  url?: string;
  data: unknown;
};
export function HistoryWorkspace({
  projectId,
  version,
  reload,
}: {
  projectId: string;
  version: number;
  reload: () => Promise<void>;
}) {
  const [items, setItems] = useState<HistoryItem[]>([]),
    [loading, setLoading] = useState(true),
    [kind, setKind] = useState("all"),
    [entity, setEntity] = useState("all"),
    [selected, setSelected] = useState(""),
    [error, setError] = useState<unknown>(""),
    [busy, setBusy] = useState(false),
    [impact, setImpact] = useState<{
      expected: number;
      projectExpected: number;
      messages: string[];
    } | null>(null);
  const path = `/creative/projects/${projectId}/history`;
  useEffect(() => {
    let live = true;
    api<HistoryItem[]>(path)
      .then((x) => {
        if (live) {
          setItems(x);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (live) {
          setError(e);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [path, version]);
  const filtered = items.filter(
    (x) =>
      (kind === "all" || x.kind === kind) &&
      (entity === "all" || x.entityId === entity),
  );
  const groups = useMemo(() => {
    const groups = new Map<string, HistoryItem[]>();
    filtered.forEach((x) => {
      const key = x.event?.id || x.id;
      groups.set(key, [...(groups.get(key) || []), x]);
    });
    return [...groups.values()];
  }, [filtered]);
  const active = filtered.find((x) => x.id === selected) || filtered[0];
  const objects = [
    ...new Map(
      items
        .filter((x) => kind === "all" || x.kind === kind)
        .map((x) => [x.entityId, x.name]),
    ).entries(),
  ];
  return (
    <section className="cw-history">
      <div className="cw-section-heading">
        <div>
          <span className="cs-kicker">{uiCopy["CREATIVE HISTORY"]}</span>
          <h2>版本记录</h2>
        </div>
        <p>{uiCopy["基于历史创建新版本，原始记录始终保留。"]}</p>
      </div>
      <div className="cw-history-filters">
        <nav className="cw-tabs" aria-label={uiCopy["历史类型"]}>
          {[
            ["all", uiCopy["全部"]],
            ["project", uiCopy["故事"]],
            ["character", uiCopy["角色"]],
            ["scene", uiCopy["分镜"]],
            ["export", uiCopy["导出"]],
          ].map(([k, l]) => (
            <button
              key={k}
              className={kind === k ? "active" : ""}
              onClick={() => {
                setKind(k);
                setEntity("all");
              }}
            >
              {l}
            </button>
          ))}
        </nav>
        <label className="creative-field">
          <span>{uiCopy["具体对象"]}</span>
          <select value={entity} onChange={(e) => setEntity(e.target.value)}>
            <option value="all">{uiCopy["全部对象"]}</option>
            {objects.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ErrorNotice error={error} />
      <div className="cw-history-layout">
        <div className="cw-history-list" aria-label={uiCopy["创作变化时间线"]}>
          {groups.map((group) => (
            <section key={group[0].event?.id || group[0].id}>
              <time>
                {new Date(group[0].createdAt).toLocaleString("zh-CN")}
              </time>
              {group.length > 1 && (
                <small>{uiCopy["同一次操作 ·"]}{group.length} {uiCopy["条内容变化"]}</small>
              )}
              {group.map((x) => (
                <button
                  key={x.id}
                  className={active?.id === x.id ? "active" : ""}
                  onClick={() => {
                    setSelected(x.id);
                    setImpact(null);
                  }}
                >
                  <strong>{x.summary}</strong>
                  <span>{x.current ? uiCopy["当前使用"] : uiCopy["历史记录"]}</span>
                </button>
              ))}
            </section>
          ))}
          {!filtered.length && (
            <p>{loading ? uiCopy["正在读取创作历史…"] : uiCopy["暂无此类创作记录。"]}</p>
          )}
        </div>
        {active && (
          <article className="cw-history-detail">
            <span className="cs-kicker">
              {active.current ? uiCopy["当前使用版本"] : uiCopy["历史快照"]}
            </span>
            <h3>{active.summary}</h3>
            <p>{new Date(active.createdAt).toLocaleString("zh-CN")}</p>
            {!!active.usedBy?.length && (
              <p className="creative-warning">
                {uiCopy["当前引用此版本的镜头："]}{active.usedBy.join("、")}
              </p>
            )}
            {(active.beforeMedia?.image || active.afterMedia?.image) && (
              <div className="cw-media-diff">
                <figure>
                  {active.beforeMedia?.image ? (
                    <img src={active.beforeMedia.image} alt={uiCopy["变更前图片"]} />
                  ) : (
                    <p>{uiCopy["没有图片"]}</p>
                  )}
                  <figcaption>{uiCopy["之前"]}</figcaption>
                </figure>
                <figure>
                  {active.afterMedia?.image ? (
                    <img src={active.afterMedia.image} alt={uiCopy["变更后图片"]} />
                  ) : (
                    <p>{uiCopy["没有图片"]}</p>
                  )}
                  <figcaption>{uiCopy["本次选用"]}</figcaption>
                </figure>
              </div>
            )}
            <div className="cw-diff-head">
              <span>{uiCopy["之前"]}</span>
              <span>{uiCopy["这次变化"]}</span>
            </div>
            {active.changes.map((c) => (
              <section className="cw-text-diff" key={c.field}>
                <h4>{c.label}</h4>
                <div>
                  <p>{c.before}</p>
                  <p>{c.after}</p>
                </div>
              </section>
            ))}
            {(active.beforeMedia?.voice || active.afterMedia?.voice) && (
              <div className="cw-media-diff">
                <section>
                  <p>{uiCopy["之前的声音样本"]}</p>
                  {active.beforeMedia?.voice && (
                    <audio controls src={active.beforeMedia.voice} />
                  )}
                </section>
                <section>
                  <p>{uiCopy["本次声音样本"]}</p>
                  {active.afterMedia?.voice && (
                    <audio controls src={active.afterMedia.voice} />
                  )}
                </section>
              </div>
            )}
            {([active.beforeMedia, active.afterMedia] as const).some(
              (x) => x?.audio?.length,
            ) && (
              <div className="cw-media-diff">
                {[active.beforeMedia, active.afterMedia].map((m, i) => (
                  <section key={i}>
                    <h4>{i ? uiCopy["本次配音"] : uiCopy["之前配音"]}</h4>
                    {m?.audio?.map((a, j) => (
                      <div key={j}>
                        <p>{a.text}</p>
                        <audio controls src={a.url} />
                      </div>
                    ))}
                  </section>
                ))}
              </div>
            )}
            {active.url && (
              <video controls src={active.url} className="cw-history-video" />
            )}
            {active.restorable && (
              <button
                className="btn"
                disabled={busy}
                onClick={async () => {
                  setError("");
                  setBusy(true);
                  try {
                    setImpact(await api(`${path}/${active.id}/impact`));
                  } catch (e) {
                    setError(e);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {uiCopy["基于此版本创建新版本…"]}</button>
            )}
            <TechnicalDetails data={active} />
          </article>
        )}
      </div>
      {impact && active && (
        <Modal title={uiCopy["恢复影响确认"]} onClose={() => setImpact(null)}>
          <div className="cw-sync">
            <h3>{active.name}</h3>
            {impact.messages.map((x) => (
              <p key={x}>{x}</p>
            ))}
            <p>{uiCopy["历史与媒体保留，不执行生成服务。"]}</p>
            <ErrorNotice error={error} />
            <button
              className="btn primary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await api(`${path}/${active.id}/restore`, "POST", {
                    expected: impact.expected,
                    data: { projectExpected: impact.projectExpected },
                  });
                  setImpact(null);
                  await reload();
                  setItems(await api(path));
                } catch (e) {
                  setError(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {uiCopy["创建新版本"]}</button>
          </div>
        </Modal>
      )}
    </section>
  );
}

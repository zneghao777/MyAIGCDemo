"use client";
import { StoryboardCandidates } from "./StoryboardCandidates";
import { viewLabels } from "./copy";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { TechnicalDetails } from "./TechnicalDetails";
import { useStore } from "@/lib/store";
import type { Project } from "@/lib/types";
import type { Candidate } from "@/lib/creative-types";
import { operationNames } from "./shared";
import { CandidateRepair, type RepairResult } from "./CandidateRepair";
import { CandidateDraft } from "../CreativeStudio";
export function CandidateList({
  items,
  project: p,
  busy,
  onSelect: select,
  onRepair,
  onRecover,
  onAiRepair,
}: {
  items: Candidate[];
  project: Project;
  busy: boolean;
  onSelect: (c: Candidate) => void;
  onRepair?: (c: Candidate, value: unknown) => Promise<RepairResult>;
  onRecover?: (c: Candidate) => Promise<RepairResult & { ready: boolean }>;
  onAiRepair?: (c: Candidate) => void;
}) {
  const tasks = useStore(state => state.tasks);
  if (items.length > 0 && items.every(candidate => candidate.kind === "storyboard")) return <StoryboardCandidates items={items} project={p} busy={busy} onSelect={select} onAiRepair={onAiRepair} onRepair={onRepair} />;
  const packageRunning = (candidate: Candidate) => !!candidate.data.package_pending && tasks.some(task => task.id === candidate.taskId && ["queued", "running"].includes(task.status));
  const resolved = new Set(items.filter(c => c.kind === "storyboard" && !c.stale && !c.data.draft && !c.data.validation_issues?.length && c.data.parent_candidate_id).map(c => c.data.parent_candidate_id));
  const isHistorical = (c: Candidate) => c.kind === "storyboard" && !c.selected && (resolved.has(c.id) || (!!c.data.draft && !!c.data.parent_candidate_id && resolved.has(c.data.parent_candidate_id)));
  const current = items.filter(c => !isHistorical(c));
  const historical = items.filter(isHistorical);
  const cards = (list: Candidate[]) => (
    <div className="creative-candidates">
      {list.map((c) => (
        <article
          key={c.id}
          data-candidate-id={c.id}
          className={`creative-candidate ${c.stale ? "stale" : ""}`}
        >
          <b>{operationNames[c.kind]}</b>
          <small>
            {c.selected
              ? uiCopy["已选用 ✓"]
              : c.stale
                ? uiCopy["输入已变更 · 历史候选"]
                : c.data.validation_issues?.length ? uiCopy["草稿已保存 · 有待处理问题"] : uiCopy["可选用候选"]}
          </small>
          {c.url &&
            (c.kind === "video_correction" ? (
              <video controls playsInline preload="metadata" src={c.url} aria-label={uiCopy["本地修正版候选视频"]} style={{ width: "100%" }} />
            ) : c.kind.includes("image") ? (
              <img src={c.url} alt={uiCopy["生成的候选参考图"]} />
            ) : (
              <audio controls src={c.url} />
            ))}
          {c.data.package_pending && <p className="creative-warning">{packageRunning(c) ? "主形象已完成，三视图正在生成" : "主形象已保存，三视图尚未完成。可先选用形象，再单独生成三视图。"}</p>}
          {c.data.turnaround?.url && <figure className="cw-candidate-turnaround"><img src={c.data.turnaround.url} alt="与候选主形象配套的三视图" /><figcaption>正面 · 侧面 · 背面</figcaption></figure>}
          {c.kind === "video_correction" && <>
            <p className="helper">{uiCopy["来源：本项目已生成的原片 · 本地导入，不调用生成模型、不扣积分。"]}</p>
            {c.data.reason && <p>{uiCopy["修正理由："]}{c.data.reason}</p>}
            {c.data.duration_ms != null && <p>{uiCopy["修正版实际时长"]}{(c.data.duration_ms / 1000).toFixed(2)}{uiCopy["s"]}</p>}
            
            <p className="helper">{"播放候选并选用后，即可在当前分镜中预览；原视频保留。"}</p>
          </>}
          {c.kind === "shot_image" && (
            <>
              <p className="helper">
                {uiCopy["已提交"]}{c.data.reference_count ?? "—"} {uiCopy["张角色参考图 · 选用前对照脸部、发型与服装"]}</p>
              <div className="cs-reference-strip">
                {p.characters
                  .filter(
                    (ch) =>
                      p.scenes.find((s) => s.id === c.entityId)?.creative?.shot
                        ?.cast[ch.id],
                  )
                  .map((ch) => (
                    <figure key={ch.id}>
                      <img src={ch.image} alt={formatCopy("{0}定稿参考图", ch.name)} />
                      <figcaption>{ch.name} {uiCopy["· 定稿参考"]}</figcaption>
                    </figure>
                  ))}
              </div>
            </>
          )}
          {c.kind !== "video_correction" && (c.data.request?.view || c.data.request?.variant || c.data.request?.frame || c.data.source) && <p className="helper">{uiCopy["素材用途："]}{c.data.request?.frame === "last" ? uiCopy["结束状态尾帧"] : viewLabels[c.data.request?.view || ""] || c.data.request?.variant || uiCopy["主素材"]} {uiCopy["· 来源"]}{c.data.source === "provider" || !c.data.source ? "AI生成" : ["manual-reuse", "upload"].includes(c.data.source) ? "上传 / 复用" : "参考素材"}</p>}
          {c.data.voice_id && (
            <p>
              {c.data.mode === "original"
                ? uiCopy["原声录音（按句导入）"]
                : c.data.mode === "clone"
                  ? uiCopy["参考录音复刻音色"]
                  : c.data.mode === "design"
                    ? uiCopy["AI 设计音色"]
                    : c.data.mode === "continuous"
                      ? uiCopy["已锁定音色"]
                      : uiCopy["预设音色"]}
              ：
              {p.characters.find((x) => x.id === c.entityId)?.creative?.persona
                .voice_description || uiCopy["试听后选择"]}
            </p>
          )}
          {c.data.reference && c.data.model === "mimo-v2.5-tts-voiceclone" && (
            <p className="helper">
              {uiCopy["选用后固定声音样本 · 后续台词使用同一参考生成。相似度与表演请试听确认。"]}</p>
          )}
          {!!c.data.validation_issues?.length && <div className="creative-warning" role="alert"><b>{uiCopy["候选需修正，原始输出已保留"]}</b><ul>{c.data.validation_issues.map((issue, index) => {
            

            return <li key={`${issue.code || issue.type || "issue"}-${index}`}>{issue.scene_index !== undefined ? formatCopy("镜头 {0} · ", issue.scene_index + 1) : ""}{issue.title ? `${issue.title}：` : ""}{uiCopy["请检查并修正这部分内容。"]}</li>;
          })}</ul><p>{c.stale ? uiCopy["历史检查结果。可本地恢复并按当前角色、环境重新检查。"] : uiCopy["先尝试本地自动修复；无法确定的内容再选择发言人或使用 AI 纠错。"]}</p></div>}
          {!!c.data.corrections?.length && <details><summary>{uiCopy["系统修复了"]}{c.data.corrections.length} {uiCopy["项 · 查看修改记录"]}</summary><ul>{c.data.corrections.map((note, i) => <li key={i}>{note}</li>)}</ul></details>}
          {c.kind === "storyboard" && onRepair && !c.selected && <CandidateRepair candidate={c} project={p} busy={busy} repair={onRepair} recover={onRecover} aiRepair={onAiRepair} />}
          {c.data.value !== undefined && (
            <details>
              <summary>{uiCopy["查看完整草案"]}</summary>
              <CandidateDraft value={c.data.value} />
            </details>
          )}
          {c.data.segments && (
            <p>
              {c.data.segments.length} {uiCopy["句 ·"]}{" "}
              {c.data.segments
                .map(
                  (x) =>
                    `${p.characters.find((c) => c.id === x.line.speaker_id)?.name || uiCopy["旁白"]}`,
                )
                .join("；")}
            </p>
          )}
          {c.data.segments?.map((seg, i) => (
            <div key={i}>
              <small>{seg.line.text}</small>
              {seg.url && <audio controls src={seg.url} />}
            </div>
          ))}
          {c.kind.startsWith("voice_") && c.data.request?.text && (
            <p className="helper">{uiCopy["试听文本："]}{c.data.request.text}</p>
          )}
          <TechnicalDetails data={c} />
          {c.kind !== "voice_match" && (
            <button
              className="btn"
              disabled={busy || c.stale || c.selected || packageRunning(c) || !!c.data.validation_issues?.length}
              onClick={() => select(c)}
            >
              {uiCopy["选用此候选"]}</button>
          )}
        </article>
      ))}
    </div>
  );
  return <>{cards(current)}{historical.length > 0 && <details className="creative-editor"><summary>{uiCopy["原始草稿与历史恢复记录（"]}{historical.length}）</summary><p className="helper">{uiCopy["可用恢复版已显示在上方。以下记录保留原始输出和此前检查结果，不表示当前分镜仍被这些问题阻塞。"]}</p>{cards(historical)}</details>}</>;
}

import { uiCopy } from "./copy";
export function EmptyStoryboardAction({ planConfirmed, castConfirmed, onPhase, onGenerate }: { planConfirmed: boolean; castConfirmed: boolean; onPhase: (phase: string) => void; onGenerate: () => void }) {
  return <button className="btn primary" onClick={() => !planConfirmed ? onPhase("plan") : onGenerate()}>{!planConfirmed ? uiCopy["开始故事方案"] : uiCopy["生成分镜草案"]}</button>;
}

import { copy, assetKindLabels, operationLabels } from "./copy";
export type EstimateTarget = { id: string; title: string; operation: string; kind: string; orderIndex?: number };
export type Estimate = { calls: number; estimateCents: number | null; targets: EstimateTarget[]; label: string; note: string };
export function quoteNeedsConsent(quote: Pick<Estimate, "estimateCents">) { return quote.estimateCents === null; }
export function CostQuote({ quote, consent, onConsent, busy, onConfirm, onBack }: { quote: Estimate; consent: boolean; onConsent: (value: boolean) => void; busy: boolean; onConfirm: () => void; onBack: () => void }) {
  return <div className="cw-cost-quote"><h3>{copy.generatedObjects}</h3>{quote.targets.length ? <ul>{quote.targets.map((target, index) => <li key={`${target.id}-${target.operation}-${index}`}>{target.orderIndex != null ? `${copy.shot} ${String(target.orderIndex).padStart(2, "0")} · ` : ""}{target.title} · {target.operation === "character_image" && quote.calls === 2 && quote.targets.length === 1 ? "主形象 + 正面 / 侧面 / 背面三视图" : operationLabels[target.operation] || assetKindLabels[target.kind]}</li>)}</ul> : <p>{copy.targetEmpty}</p>}
    {quoteNeedsConsent(quote) ? <><p>{copy.unpriced}</p><label><input type="checkbox" checked={consent} onChange={e => onConsent(e.target.checked)} />{copy.unpricedConsent}</label></> : <><p>{`预计生成 ${quote.calls} 项素材`}</p><p>{copy.estimatedPrice(quote.estimateCents!)}</p></>}
    <p className="helper">{quote.targets.some(target => target.operation === "storyboard") ? "生成完成后自动应用分镜，之前的方案保留在历史中，可随时切换。" : copy.candidateConsequence}</p><p className="helper">{copy.priceNote}</p>
    <div className="creative-actions"><button className="btn" onClick={onBack}>{copy.back}</button><button className="btn primary" disabled={busy || !quote.targets.length || (quoteNeedsConsent(quote) && !consent)} onClick={onConfirm}>{copy.startCandidates}</button></div>
  </div>;
}

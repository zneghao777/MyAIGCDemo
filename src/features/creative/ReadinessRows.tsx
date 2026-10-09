export function ReadinessRows({ locationDone, locationTotal, accepted, total }: { locationDone: number; locationTotal: number; previewConfirmed: boolean; accepted: number; total: number }) {
  const rows = [["场景素材", `${locationDone} / ${locationTotal} 个场景已选定`, locationTotal > 0 && locationDone === locationTotal], ["分镜视频", `${accepted} / ${total} 个镜头可预览`, total > 0 && accepted === total]] as const;
  return <dl className="cw-readiness-rows">{rows.map(([label, value, ready]) => <div key={label}><dt>{label}</dt><dd>{value}</dd><dd className={ready ? "ready" : "pending"}>{ready ? "就绪" : "待生成"}</dd></div>)}</dl>;
}

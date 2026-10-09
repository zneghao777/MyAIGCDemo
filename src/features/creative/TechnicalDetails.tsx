import type { ReactNode } from "react";
// Keep product actions available while omitting internal diagnostic data.
export function TechnicalDetails({ extra }: { title?: string; data: unknown; extra?: ReactNode }) {
  return extra ? <div className="cw-workspace-actions">{extra}</div> : null;
}

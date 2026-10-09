"use client";
import { copy, errorMessage } from "./copy";
import { TechnicalDetails } from "./TechnicalDetails";
export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const message = errorMessage(error);
  return <div className="cw-error"><p role="alert" className="creative-warning">{message.title}</p><p className="helper">{message.detail}</p>{message.action && <button className="btn" onClick={() => window.location.reload()}>{message.action}</button>}<TechnicalDetails title={copy.errorDetails} data={error} /></div>;
}

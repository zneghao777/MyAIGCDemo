"use client";
import { useState } from "react";
import { copy } from "./copy";
export function NarrowScreenNotice() {
  const [dismissed, setDismissed] = useState(false);
  return dismissed ? null : <aside className="cw-narrow-notice" role="status"><span>{copy.narrowScreen}</span><button className="btn" onClick={() => setDismissed(true)}>{copy.continueUsing}</button></aside>;
}

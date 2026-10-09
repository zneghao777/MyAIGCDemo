import { isRateLimited, retryDelay } from "./api";

/** One reader, one timer: coalesce event bursts and respect a server cooldown. */
export function createReadObserver(
  read: (signal: AbortSignal) => Promise<void>,
  onError: (error: unknown) => void,
  { intervalMs = 15000, minIntervalMs = 5000, initialDelayMs = 0 } = {},
) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let due = Infinity, running = false, requested = false, lastStart = -Infinity, blockedUntil = 0;
  const schedule = (delay: number) => {
    if (controller.signal.aborted) return;
    const when = Math.max(Date.now() + delay, lastStart + minIntervalMs, blockedUntil);
    if (timer !== undefined && due <= when) return;
    if (timer !== undefined) clearTimeout(timer);
    due = when;
    timer = setTimeout(() => void poll(), Math.max(0, when - Date.now()));
  };
  const poll = async () => {
    timer = undefined; due = Infinity;
    if (controller.signal.aborted || running) return;
    if (Date.now() < blockedUntil) { schedule(blockedUntil - Date.now()); return; }
    running = true; requested = false; lastStart = Date.now();
    try { await read(controller.signal); }
    catch (error) {
      if (!controller.signal.aborted) {
        if (isRateLimited(error)) blockedUntil = Date.now() + retryDelay(error);
        onError(error);
      }
    } finally {
      running = false;
      if (!controller.signal.aborted) schedule(requested ? 0 : intervalMs);
    }
  };
  schedule(initialDelayMs);
  return {
    request() { if (running) requested = true; else schedule(0); },
    stop() { controller.abort(); if (timer !== undefined) clearTimeout(timer); },
  };
}

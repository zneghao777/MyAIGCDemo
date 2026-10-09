import { copy } from "@/features/creative/copy";
export const remoteMode = process.env.NEXT_PUBLIC_API_MODE === "remote";
export const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "";
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string,
    readonly retryAfterMs = 0, readonly details?: Record<string, unknown>) {
    super(message); this.name = "ApiError";
  }
}
const readCooldowns = new Map<string, number>();
const scope = (path: string) => path.match(/\/projects\/([^/?]+)/)?.[1] || "global";
export const isRateLimited = (error: unknown): error is ApiError => error instanceof ApiError && error.status === 429;
export function retryDelay(error: unknown, fallback = 15000) {
  return isRateLimited(error) ? Math.max(1000, error.retryAfterMs) : fallback;
}
export function waitForRetry(delayMs: number, signal?: AbortSignal): Promise<void> {
  signal?.throwIfAborted();
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException("已取消", "AbortError")); };
    const timer = setTimeout(() => { signal?.removeEventListener("abort", abort); resolve(); }, delayMs);
    signal?.addEventListener("abort", abort, { once: true });
  });
}
export async function api<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  const key = scope(path), remaining = (readCooldowns.get(key) || 0) - Date.now();
  // A known server cooldown applies to all readers of this project, without retrying writes.
  if (method === "GET" && remaining > 0) throw new ApiError("请求限流，正在等待自动恢复", 429, "RATE_LIMITED", remaining);
  let response: Response;
  try {
    response = await fetch(`${apiBase}/api${path}`, {
    method, signal, cache: "no-store",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  } catch (error) {
    if (signal?.aborted) throw new DOMException("已取消", "AbortError");
    if (error instanceof TypeError || error instanceof DOMException) throw new ApiError(copy.networkFailure, 0, "NETWORK_ERROR");
    throw error;
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const header = response.headers.get("Retry-After");
    const seconds = header ? Number(header) : NaN;
    const delay = Number.isFinite(seconds) ? seconds * 1000 : header ? Date.parse(header) - Date.now() : Number(data?.error?.details?.retry_after || data?.retry_after || 60) * 1000;
    const retryAfterMs = response.status === 429 ? Math.max(1000, Number.isFinite(delay) ? delay : 60000) : 0;
    if (response.status === 429) readCooldowns.set(key, Date.now() + retryAfterMs);
    throw new ApiError(data?.error?.message || `请求失败 (${response.status})`, response.status, data?.error?.code, retryAfterMs, data?.error?.details);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export type RemoteTask = {
  id: string; status: string; progress: number; error?: string;
  result?: { text?: string; url?: string; durationMs?: number; [key: string]: unknown };
};
export async function waitTask(id: string, progress?: (value: number) => void, signal?: AbortSignal): Promise<RemoteTask> {
  for (;;) {
    signal?.throwIfAborted();
    let task: RemoteTask;
    try { task = await api<RemoteTask>(`/tasks/${id}`, "GET", undefined, signal); }
    catch (error) { if (!isRateLimited(error)) throw error; await waitForRetry(retryDelay(error), signal); continue; }
    progress?.(task.progress);
    if (task.status === "done") return task;
    if (["failed", "cancelled"].includes(task.status)) throw new Error(task.error || "任务已取消");
    await waitForRetry(2000, signal);
  }
}
export async function aiTask<T>(operation: string, body: unknown): Promise<T> {
  const { taskId } = await api<{ taskId: string }>(`/ai/${operation}`, "POST", body);
  return (await waitTask(taskId)).result as T;
}

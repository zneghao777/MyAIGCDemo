/** Playback coverage records only intervals traversed during continuous playback. */
export type PlayedInterval = [number, number];
export type PlaybackSample = { position: number; clockMs: number; rate: number };
export function addPlayedInterval(intervals: PlayedInterval[], start: number, end: number, duration: number): PlayedInterval[] {
  if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) return intervals;
  const next: PlayedInterval[] = [...intervals, [Math.max(0, start), Math.min(duration, end)]];
  next.sort((a, b) => a[0] - b[0]);
  const merged: PlayedInterval[] = [];
  for (const range of next) {
    if (range[1] <= range[0]) continue;
    const previous = merged[merged.length - 1];
    if (previous && range[0] <= previous[1] + 0.001) previous[1] = Math.max(previous[1], range[1]);
    else merged.push([...range]);
  }
  return merged;
}
export function recordPlaybackStep(intervals: PlayedInterval[], previous: PlaybackSample | null, current: PlaybackSample, duration: number): PlayedInterval[] {
  if (!previous) return intervals;
  const movement = current.position - previous.position;
  const elapsed = (current.clockMs - previous.clockMs) / 1000;
  // A seek or source switch cannot credit the skipped part of the media timeline.
  if (movement <= 0 || elapsed <= 0 || movement > elapsed * Math.max(0.25, previous.rate) * 1.6 + 0.3) return intervals;
  return addPlayedInterval(intervals, previous.position, current.position, duration);
}
export function playbackCoverage(intervals: PlayedInterval[], duration: number): number {
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  return Math.min(1, intervals.reduce((total, [start, end]) => total + end - start, 0) / duration);
}

/** Reaching the end and covering the timeline are independent requirements. */
export function canConfirmPlayback(coverage: number, ended: boolean): boolean {
  return ended && Number.isFinite(coverage) && coverage >= 0.95;
}

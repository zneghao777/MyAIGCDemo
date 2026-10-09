export function shotStatusClass(status?: { image_stale: boolean; audio_stale: boolean }) {
  return status?.image_stale || status?.audio_stale ? "creative-warning" : "helper";
}

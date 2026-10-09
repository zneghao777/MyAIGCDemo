import type { Project } from "./types";
export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
export function downloadProject(p: Project, settings: unknown) {
  downloadBlob(
    new Blob(
      [
        JSON.stringify(
          {
            version: 1,
            kind: "cineai-project",
            project: p,
            exportSettings: settings,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    ),
    `${p.name}.cineai.json`,
  );
}
export async function coverImage(src: string, name: string) {
  const img = await loadImage(src);
  const c = document.createElement("canvas");
  c.width = img.naturalWidth;
  c.height = img.naturalHeight;
  c.getContext("2d")!.drawImage(img, 0, 0);
  c.toBlob((b) => {
    if (b) downloadBlob(b, `${name}-封面.png`);
  }, "image/png");
}
function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = () => reject(new Error("画面加载失败"));
    i.src = src;
  });
}
// Browser-only storyboard recording. Deliberately excludes claims of AI video or MP4 encoding.
export async function recordPreview(
  p: Project,
  onProgress: (n: number) => void,
  subtitles: boolean,
  fps: number,
  signal: AbortSignal,
): Promise<Blob> {
  if (!("MediaRecorder" in window))
    throw new Error("当前浏览器不支持本地录制，请下载项目文件。");
  const mime = [
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/webm",
  ].find((m) => MediaRecorder.isTypeSupported(m));
  if (!mime)
    throw new Error("当前浏览器不支持 WebM，请使用 Chrome 或下载项目文件。");
  const scenes = p.scenes.filter((s) => s.image);
  if (!scenes.length) throw new Error("先生成至少一张分镜画面。");
  const images = await Promise.all(scenes.map((s) => loadImage(s.image)));
  if (signal.aborted) throw new Error("已取消导出");
  const c = document.createElement("canvas");
  const vertical = p.ratio === "9:16";
  c.width = vertical ? 406 : 720;
  c.height = p.ratio === "1:1" ? 720 : vertical ? 720 : 406;
  const ctx = c.getContext("2d")!;
  const stream = c.captureStream(fps);
  const rec = new MediaRecorder(stream, {
    mimeType: mime,
    videoBitsPerSecond: 2500000,
  });
  const chunks: BlobPart[] = [];
  const total = scenes.length * 1000;
  const start = performance.now();
  return new Promise((resolve, reject) => {
    let raf = 0;
    const clean = () => {
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      if (rec.state !== "inactive") rec.stop();
      clean();
      reject(new Error("已取消导出"));
    };
    signal.addEventListener("abort", abort, { once: true });
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    rec.onerror = () => {
      clean();
      reject(new Error("录制失败，请重试"));
    };
    rec.onstop = () => {
      clean();
      if (!signal.aborted) resolve(new Blob(chunks, { type: "video/webm" }));
    };
    const draw = () => {
      if (signal.aborted) return;
      const ms = performance.now() - start;
      const i = Math.min(scenes.length - 1, Math.floor(ms / 1000));
      const img = images[i];
      const zoom = 1 + ((ms % 1000) / 1000) * 0.025;
      const scale = Math.max(c.width / img.width, c.height / img.height) * zoom;
      ctx.fillStyle = "#0e0f13";
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(
        img,
        (c.width - img.width * scale) / 2,
        (c.height - img.height * scale) / 2,
        img.width * scale,
        img.height * scale,
      );
      ctx.fillStyle = "rgba(14,15,19,.75)";
      ctx.fillRect(0, c.height - 75, c.width, 75);
      ctx.fillStyle = "#f5b942";
      ctx.font = "13px sans-serif";
      ctx.fillText(
        `CINEAI · 分镜预演 ${i + 1}/${scenes.length}`,
        20,
        c.height - 48,
      );
      ctx.fillStyle = "#fff";
      ctx.font = "16px sans-serif";
      if (subtitles)
        ctx.fillText(
          scenes[i].dialogue.slice(0, 25),
          20,
          c.height - 20,
          c.width - 40,
        );
      onProgress(Math.min(99, Math.round((ms / total) * 100)));
      if (ms >= total) {
        rec.stop();
        onProgress(100);
      } else raf = requestAnimationFrame(draw);
    };
    rec.start();
    draw();
  });
}

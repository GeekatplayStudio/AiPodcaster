import type { ApiInfo } from "../api/types";

/** Expected processing seconds (low, high) for a recording of `durationSeconds`. */
export function processingRange(durationSeconds: number, info: ApiInfo | null): [number, number] {
  const rtf = info?.estimates.analysis_rtf ?? 0.5;
  const llm = info?.estimates.llm_seconds ?? 30;
  const base = durationSeconds * rtf + llm;
  return [Math.max(10, Math.round(base * 0.7)), Math.max(20, Math.round(base * 1.5))];
}

export function isLongRecording(durationSeconds: number, sizeBytes: number, info: ApiInfo | null): boolean {
  const threshold = info?.estimates.long_recording_seconds ?? 1800;
  return durationSeconds >= threshold || sizeBytes >= 1024 * 1024 * 1024;
}

/** Human friendly minutes, e.g. 75 -> "1 min", 3600 -> "60 min", 7300 -> "2 h 2 min". */
export function friendlyDuration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 90) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

/** Read a local media file's duration in the browser without uploading it. */
export function readMediaDuration(file: File, timeoutMs = 6000): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const element = document.createElement(file.type.startsWith("video") ? "video" : "audio");
    let settled = false;
    const finish = (value: number | null) => {
      if (settled) return;
      settled = true;
      URL.revokeObjectURL(url);
      element.removeAttribute("src");
      resolve(value);
    };
    element.preload = "metadata";
    element.onloadedmetadata = () => finish(Number.isFinite(element.duration) && element.duration > 0 ? element.duration : null);
    element.onerror = () => finish(null);
    window.setTimeout(() => finish(null), timeoutMs);
    element.src = url;
  });
}

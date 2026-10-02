import type { EditKind, JobStage } from "../api/types";

export function formatTime(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const mmss = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours ? `${hours}:${mmss}` : mmss;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return formatTime(ms);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

export const STAGE_LABELS: Record<JobStage, string> = {
  uploaded: "Uploaded",
  ingest: "Preparing audio",
  transcribe: "Transcribing",
  propose_edits: "Analysing",
  waiting_for_approval: "Ready for review",
  render: "Producing",
  complete: "Complete",
  failed: "Failed",
};

export const KIND_LABELS: Record<EditKind, string> = {
  profanity: "Profanity",
  filler: "Filler",
  repeat: "Repeat",
  silence: "Pause",
  noise: "Noise",
};

export const PROCESSING_STAGES: JobStage[] = ["uploaded", "ingest", "transcribe", "propose_edits", "render"];

export function isProcessing(stage: JobStage): boolean {
  return PROCESSING_STAGES.includes(stage);
}

export function stepIndex(stage: JobStage): number {
  switch (stage) {
    case "uploaded":
    case "ingest":
    case "transcribe":
    case "propose_edits":
      return 1;
    case "waiting_for_approval":
      return 2;
    case "render":
      return 3;
    case "complete":
      return 4;
    case "failed":
      return 0;
  }
}

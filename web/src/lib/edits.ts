import i18n from "../i18n";
import type { EditKind, EditProposal, TranscriptSegment, Word } from "../api/types";

export interface WordView {
  word: Word;
  proposal: EditProposal | null;
}

/** Attach the proposal (if any) that covers each word so the editor can highlight it. */
export function annotateSegment(segment: TranscriptSegment, proposals: EditProposal[]): WordView[] {
  const relevant = proposals.filter((p) => p.kind !== "silence" && p.end_ms >= segment.start_ms && p.start_ms <= segment.end_ms);
  return segment.words.map((word) => ({
    word,
    proposal: relevant.find((p) => p.start_ms <= word.start_ms + 1 && word.end_ms <= p.end_ms + 1) ?? null,
  }));
}

export function summarise(proposals: EditProposal[]): Record<EditKind, { total: number; accepted: number; ms: number }> {
  const base: Record<EditKind, { total: number; accepted: number; ms: number }> = {
    profanity: { total: 0, accepted: 0, ms: 0 },
    filler: { total: 0, accepted: 0, ms: 0 },
    repeat: { total: 0, accepted: 0, ms: 0 },
    silence: { total: 0, accepted: 0, ms: 0 },
    noise: { total: 0, accepted: 0, ms: 0 },
  };
  for (const p of proposals) {
    base[p.kind].total += 1;
    if (p.accepted) {
      base[p.kind].accepted += 1;
      base[p.kind].ms += p.end_ms - p.start_ms;
    }
  }
  return base;
}

export function totalRemovedMs(proposals: EditProposal[]): number {
  return mergeRanges(proposals.filter((p) => p.accepted).map((p) => [p.start_ms, p.end_ms])).reduce((sum, [s, e]) => sum + (e - s), 0);
}

export function mergeRanges(ranges: [number, number][]): [number, number][] {
  const sorted = [...ranges].filter(([s, e]) => e > s).sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [start, end] of sorted) {
    const last = merged[merged.length - 1];
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  return merged;
}

export function toggleProposal(proposals: EditProposal[], id: string, accepted?: boolean): EditProposal[] {
  return proposals.map((p) => (p.id === id ? { ...p, accepted: accepted ?? !p.accepted } : p));
}

export function setKind(proposals: EditProposal[], kind: EditKind, accepted: boolean): EditProposal[] {
  return proposals.map((p) => (p.kind === kind ? { ...p, accepted } : p));
}

export function segmentDirty(original: TranscriptSegment[], edited: TranscriptSegment[]): { id: number; text: string }[] {
  const byId = new Map(original.map((s) => [s.id, s.text]));
  return edited.filter((s) => byId.get(s.id) !== s.text).map((s) => ({ id: s.id, text: s.text }));
}

/** Validate a file before upload so the user gets instant feedback. */
export function validateFile(file: File, maxBytes: number): string | null {
  const allowed = [".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".mp4", ".mov", ".wma", ".aiff", ".aif"];
  const lower = file.name.toLowerCase();
  const t = (key: string, options?: Record<string, unknown>) => i18n.t(key, { ns: "library", ...options });
  if (!allowed.some((ext) => lower.endsWith(ext))) return t("Unsupported file type. Use {{types}}.", { types: allowed.join(", ") });
  if (file.size === 0) return t("The file is empty.");
  if (file.size > maxBytes) return t("File is larger than the {{size}} MB limit.", { size: Math.round(maxBytes / 1024 / 1024) });
  return null;
}

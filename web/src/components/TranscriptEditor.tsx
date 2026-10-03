import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { EditProposal, TranscriptSegment } from "../api/types";
import { annotateSegment } from "../lib/edits";
import { KIND_LABELS, formatTime } from "../lib/format";

interface Props {
  segments: TranscriptSegment[];
  proposals: EditProposal[];
  readOnly?: boolean;
  flaggedSegments?: Set<number>;
  onSeek: (ms: number) => void;
  onToggle: (id: string) => void;
  onEditSegment: (id: number, text: string) => void;
}

export function TranscriptEditor({ segments, proposals, readOnly, flaggedSegments, onSeek, onToggle, onEditSegment }: Props) {
  const { t } = useTranslation("job");
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  function startEdit(segment: TranscriptSegment) {
    setEditing(segment.id);
    setDraft(segment.text);
  }

  function commit(segment: TranscriptSegment) {
    const text = draft.replace(/\s+/g, " ").trim();
    if (text && text !== segment.text) onEditSegment(segment.id, text);
    setEditing(null);
  }

  function wordTitle(proposal: EditProposal) {
    const values = { kind: t(KIND_LABELS[proposal.kind]), reason: proposal.reason, confidence: Math.round(proposal.confidence * 100) };
    return proposal.accepted ? t("{{kind}}: {{reason}} ({{confidence}}%) – click to keep", values) : t("{{kind}}: {{reason}} ({{confidence}}%) – click to remove", values);
  }

  if (segments.length === 0) return <p className="muted">{t("No transcript yet.")}</p>;

  return (
    <div role="list" aria-label={t("Transcript")}>
      {segments.map((segment) => {
        const words = annotateSegment(segment, proposals);
        const isEditing = editing === segment.id;
        const flagged = flaggedSegments?.has(segment.id) ?? false;
        const time = formatTime(segment.start_ms);
        return (
          <div className={`segment${flagged ? " fact-flag" : ""}`} role="listitem" key={segment.id} title={flagged ? t("A fact check flagged a statement in this passage") : undefined}>
            <time title={t("Jump to this point")} onClick={() => onSeek(segment.start_ms)} dateTime={`PT${Math.floor(segment.start_ms / 1000)}S`}>
              {time}
            </time>
            <div>
              {isEditing ? (
                <>
                  <textarea aria-label={t("Edit transcript at {{time}}", { time })} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
                  <div className="segment-actions">
                    <button type="button" className="btn sm primary" onClick={() => commit(segment)}>
                      {t("Save")}
                    </button>
                    <button type="button" className="btn sm" onClick={() => setEditing(null)}>
                      {t("Cancel")}
                    </button>
                  </div>
                </>
              ) : (
                <div className="words" dir="auto" onDoubleClick={() => !readOnly && startEdit(segment)} title={readOnly ? undefined : t("Double-click to edit text")}>
                  {words.length > 0
                    ? words.map(({ word, proposal }, index) => (
                        <span key={`${segment.id}-${index}`}>
                          {proposal ? (
                            <button
                              type="button"
                              className={`word flag kind-${proposal.kind}${proposal.accepted ? " accepted" : ""}`}
                              style={{ background: "transparent", border: "none", font: "inherit" }}
                              title={wordTitle(proposal)}
                              onClick={() => onToggle(proposal.id)}
                              disabled={readOnly}
                            >
                              {word.text}
                            </button>
                          ) : (
                            <span className="word">{word.text}</span>
                          )}{" "}
                        </span>
                      ))
                    : segment.text}
                  {!readOnly && (
                    <button type="button" className="btn sm" style={{ marginLeft: 6, verticalAlign: "middle" }} onClick={() => startEdit(segment)} aria-label={t("Edit text at {{time}}", { time })}>
                      {t("Edit")}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

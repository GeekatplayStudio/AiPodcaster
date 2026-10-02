import { useState } from "react";
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

  if (segments.length === 0) return <p className="muted">No transcript yet.</p>;

  return (
    <div role="list" aria-label="Transcript">
      {segments.map((segment) => {
        const words = annotateSegment(segment, proposals);
        const isEditing = editing === segment.id;
        const flagged = flaggedSegments?.has(segment.id) ?? false;
        return (
          <div className={`segment${flagged ? " fact-flag" : ""}`} role="listitem" key={segment.id} title={flagged ? "A fact check flagged a statement in this passage" : undefined}>
            <time title="Jump to this point" onClick={() => onSeek(segment.start_ms)} dateTime={`PT${Math.floor(segment.start_ms / 1000)}S`}>
              {formatTime(segment.start_ms)}
            </time>
            <div>
              {isEditing ? (
                <>
                  <textarea aria-label={`Edit transcript at ${formatTime(segment.start_ms)}`} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
                  <div className="segment-actions">
                    <button type="button" className="btn sm primary" onClick={() => commit(segment)}>
                      Save
                    </button>
                    <button type="button" className="btn sm" onClick={() => setEditing(null)}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <div className="words" onDoubleClick={() => !readOnly && startEdit(segment)} title={readOnly ? undefined : "Double-click to edit text"}>
                  {words.length > 0
                    ? words.map(({ word, proposal }, index) => (
                        <span key={`${segment.id}-${index}`}>
                          {proposal ? (
                            <button
                              type="button"
                              className={`word flag kind-${proposal.kind}${proposal.accepted ? " accepted" : ""}`}
                              style={{ background: "transparent", border: "none", font: "inherit" }}
                              title={`${KIND_LABELS[proposal.kind]}: ${proposal.reason} (${Math.round(proposal.confidence * 100)}%) – click to ${proposal.accepted ? "keep" : "remove"}`}
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
                    <button type="button" className="btn sm" style={{ marginLeft: 6, verticalAlign: "middle" }} onClick={() => startEdit(segment)} aria-label={`Edit text at ${formatTime(segment.start_ms)}`}>
                      Edit
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

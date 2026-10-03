import { useTranslation } from "react-i18next";
import type { EditKind, EditProposal } from "../api/types";
import { summarise, totalRemovedMs } from "../lib/edits";
import { KIND_LABELS, formatDuration, formatTime } from "../lib/format";

interface Props {
  proposals: EditProposal[];
  readOnly?: boolean;
  onToggle: (id: string, accepted?: boolean) => void;
  onKind: (kind: EditKind, accepted: boolean) => void;
  onPreview: (proposal: EditProposal) => void;
}

const ORDER: EditKind[] = ["profanity", "repeat", "filler", "silence", "noise"];

export function ProposalPanel({ proposals, readOnly, onToggle, onKind, onPreview }: Props) {
  const { t } = useTranslation("job");
  const summary = summarise(proposals);
  const removed = totalRemovedMs(proposals);
  const accepted = proposals.filter((p) => p.accepted).length;

  return (
    <>
      <div className="stats" style={{ marginBottom: "0.75rem" }}>
        <div className="stat">
          <strong>{accepted}</strong>
          <span>{t("of {{total}} edits accepted", { total: proposals.length })}</span>
        </div>
        <div className="stat">
          <strong>{formatDuration(removed)}</strong>
          <span>{t("will be removed")}</span>
        </div>
      </div>
      <div className="grid-3" style={{ marginBottom: "0.75rem" }}>
        {ORDER.filter((kind) => summary[kind].total > 0).map((kind) => (
          <div key={kind} className="btn-row" style={{ justifyContent: "space-between" }}>
            <span className={`badge kind-${kind}`}>
              {t(KIND_LABELS[kind])} {summary[kind].accepted}/{summary[kind].total}
            </span>
            {!readOnly && (
              <span className="btn-row">
                <button type="button" className="btn sm" onClick={() => onKind(kind, true)}>
                  {t("All")}
                </button>
                <button type="button" className="btn sm" onClick={() => onKind(kind, false)}>
                  {t("None")}
                </button>
              </span>
            )}
          </div>
        ))}
      </div>
      {proposals.length === 0 && <p className="muted">{t("No cleanup suggestions. The recording already sounds tidy.")}</p>}
      <div className="proposal-list">
        {proposals.map((p) => (
          <label key={p.id} className={`proposal${p.accepted ? "" : " rejected"}`}>
            <input type="checkbox" checked={p.accepted} onChange={(e) => onToggle(p.id, e.target.checked)} disabled={readOnly} aria-label={t("{{kind}} at {{time}}", { kind: t(KIND_LABELS[p.kind]), time: formatTime(p.start_ms) })} />
            <span className="text">
              <strong>{p.text ? `“${p.text}”` : p.reason}</strong>
              <span>
                {t(KIND_LABELS[p.kind])} · {p.text ? p.reason : formatDuration(p.end_ms - p.start_ms)} · {Math.round(p.confidence * 100)}%
              </span>
            </span>
            <button type="button" className="time" onClick={() => onPreview(p)} title={t("Listen in context")}>
              ▶ {formatTime(p.start_ms)}
            </button>
          </label>
        ))}
      </div>
    </>
  );
}

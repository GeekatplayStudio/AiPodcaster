import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { JobSummary, Project } from "../api/types";
import { formatTime, uiLocale } from "../lib/format";
import { StageBadge } from "./StageBadge";

interface Props {
  items: JobSummary[];
  projects: Project[];
  selected: Set<string>;
  manualOrder: boolean;
  onSelect: (id: string, checked: boolean) => void;
  onOpen: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onMove: (id: string, direction: -1 | 1) => void;
  onDrop: (fromId: string, toId: string) => void;
  onProject: (id: string, projectId: string | null) => void;
}

export function EpisodeTable({ items, projects, selected, manualOrder, onSelect, onOpen, onRename, onMove, onDrop, onProject }: Props) {
  const { t } = useTranslation("library");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [dragging, setDragging] = useState<string | null>(null);

  function commit(item: JobSummary) {
    const name = draft.trim();
    if (name && name !== item.display_name) onRename(item.id, name);
    setEditing(null);
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="job-table episodes">
        <thead>
          <tr>
            <th style={{ width: 32 }}>
              <span className="sr-only">{t("Select")}</span>
            </th>
            {manualOrder && (
              <th style={{ width: 70 }}>
                <span className="sr-only">{t("Order")}</span>
              </th>
            )}
            <th>{t("Episode")}</th>
            <th>{t("Project")}</th>
            <th>{t("Length")}</th>
            <th>{t("Words")}</th>
            <th>{t("Status")}</th>
            <th>{t("Updated")}</th>
            <th>
              <span className="sr-only">{t("Actions")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr
              key={item.id}
              className={`${item.archived ? "archived" : ""}${dragging === item.id ? " dragging" : ""}`}
              draggable={manualOrder}
              onDragStart={() => setDragging(item.id)}
              onDragEnd={() => setDragging(null)}
              onDragOver={(e) => manualOrder && e.preventDefault()}
              onDrop={() => dragging && dragging !== item.id && onDrop(dragging, item.id)}
            >
              <td>
                <input type="checkbox" checked={selected.has(item.id)} onChange={(e) => onSelect(item.id, e.target.checked)} aria-label={t("Select {{name}}", { name: item.display_name })} />
              </td>
              {manualOrder && (
                <td>
                  <span className="btn-row" style={{ gap: 2 }}>
                    <button type="button" className="btn sm" onClick={() => onMove(item.id, -1)} disabled={index === 0} aria-label={t("Move up")}>
                      ↑
                    </button>
                    <button type="button" className="btn sm" onClick={() => onMove(item.id, 1)} disabled={index === items.length - 1} aria-label={t("Move down")}>
                      ↓
                    </button>
                  </span>
                </td>
              )}
              <td className="name" style={{ maxWidth: 360 }}>
                {editing === item.id ? (
                  <input
                    className="input"
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={() => commit(item)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commit(item);
                      if (e.key === "Escape") setEditing(null);
                    }}
                    aria-label={t("Episode name")}
                  />
                ) : (
                  <>
                    <a href={`#/jobs/${item.id}`} title={item.asset_name}>
                      {item.display_name}
                    </a>
                    <button
                      type="button"
                      className="btn sm icon"
                      onClick={() => {
                        setEditing(item.id);
                        setDraft(item.display_name);
                      }}
                      aria-label={t("Rename {{name}}", { name: item.display_name })}
                      title={t("Rename")}
                    >
                      ✎
                    </button>
                    <div className="muted small">
                      <span className={`badge kind-${item.source_kind === "text" ? "silence" : "repeat"}`}>{item.source_kind === "text" ? t("text") : t("audio")}</span> {item.asset_name}
                      {item.tags.length ? ` · ${item.tags.map((tag) => `#${tag}`).join(" ")}` : ""}
                      {item.archived ? ` · ${t("archived")}` : ""}
                    </div>
                  </>
                )}
              </td>
              <td>
                <select className="input" style={{ minHeight: 30, padding: "2px 6px" }} value={item.project_id ?? ""} onChange={(e) => onProject(item.id, e.target.value || null)} aria-label={t("Project for {{name}}", { name: item.display_name })}>
                  <option value="">—</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                {item.duration_ms ? formatTime(item.final_duration_ms || item.duration_ms) : "–"}
                {item.final_duration_ms && item.final_duration_ms !== item.duration_ms ? <div className="muted small">{t("was {{time}}", { time: formatTime(item.duration_ms) })}</div> : null}
              </td>
              <td>
                {item.word_count ? item.word_count.toLocaleString(uiLocale()) : "–"}
                {item.proposal_count ? <div className="muted small">{t("{{accepted}}/{{total}} edits", { accepted: item.accepted_edits, total: item.proposal_count })}</div> : null}
              </td>
              <td>
                <StageBadge stage={item.stage} progress={item.progress} />
                {item.flagged_claims > 0 && <div className="badge fail small" style={{ marginTop: 4 }}>⚑ {t("{{count}} fact flags", { count: item.flagged_claims })}</div>}
                {item.published > 0 && <div className="badge ok small" style={{ marginTop: 4 }}>{t("published ×{{count}}", { count: item.published })}</div>}
              </td>
              <td className="muted small">{new Date(item.updated_at).toLocaleString(uiLocale())}</td>
              <td>
                <div className="btn-row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                  <button type="button" className="btn sm" onClick={() => onOpen(item.id)}>
                    {t("Open")}
                  </button>
                  <a className="btn sm" href={`#/jobs/${item.id}/stats`}>
                    {t("Stats")}
                  </a>
                  <a className="btn sm" href={`#/jobs/${item.id}/publish`}>
                    {t("Publish")}
                  </a>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ragApi } from "../api/rag";
import type { FactCheck, ProcessingJob, Project, Verdict } from "../api/types";
import { formatTime } from "../lib/format";

interface Props {
  job: ProcessingJob;
  project: Project | null;
  projects: Project[];
  onJob: (job: ProcessingJob) => void;
  onSeek: (ms: number) => void;
  onError: (message: string) => void;
}

// English labels; translated at render time (keys live in locales/*/job.json).
const VERDICT_LABEL: Record<Verdict, string> = { supported: "Supported", contradicted: "Contradicted", unsupported: "No evidence", uncertain: "Uncertain" };
const VERDICT_CLASS: Record<Verdict, string> = { supported: "ok", contradicted: "fail", unsupported: "", uncertain: "review" };

export function sortChecks(checks: FactCheck[]): FactCheck[] {
  const weight = (c: FactCheck) => (c.flagged && !c.dismissed ? 0 : c.verdict === "uncertain" ? 1 : c.verdict === "unsupported" ? 2 : 3);
  return [...checks].sort((a, b) => weight(a) - weight(b) || a.start_ms - b.start_ms);
}

export function FactCheckPanel({ job, project, projects, onJob, onSeek, onError }: Props) {
  const { t } = useTranslation("job");
  const report = job.verification;
  const [useLibraries, setUseLibraries] = useState(true);
  const [useOnline, setUseOnline] = useState(project?.online_fact_check ?? false);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const running = report.status === "running";
  const hasLibraries = (project?.library_ids.length ?? 0) + (project?.linked_project_ids.length ?? 0) > 0;

  async function run() {
    setBusy(true);
    try {
      onJob(await ragApi.verify(job.id, { use_libraries: useLibraries && hasLibraries, use_online: useOnline }));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("Could not start fact check"));
    } finally {
      setBusy(false);
    }
  }

  async function assignProject(projectId: string) {
    try {
      onJob(await ragApi.setJobProject(job.id, projectId || null));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("Could not change project"));
    }
  }

  async function dismiss(check: FactCheck, dismissed: boolean) {
    try {
      onJob(await ragApi.factCheckDecisions(job.id, [{ id: check.id, dismissed }]));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("Could not update"));
    }
  }

  const open = report.checks.filter((c) => c.flagged && !c.dismissed).length;
  const visible = showAll ? sortChecks(report.checks) : sortChecks(report.checks).filter((c) => c.flagged || c.verdict === "uncertain");
  const librariesHint = project
    ? project.linked_project_ids.length
      ? t("Libraries: {{libraries}} + {{linked}} linked project(s)", { libraries: project.library_ids.length, linked: project.linked_project_ids.length })
      : t("Libraries: {{libraries}}", { libraries: project.library_ids.length })
    : t("Assign a project to use its knowledge libraries.");
  const sources = `${report.used_libraries.join(", ") || t("none")}${report.used_online ? " + Wikipedia" : ""}`;

  return (
    <section className="card" aria-labelledby="factcheck-title">
      <div className="card-title">
        <h2 id="factcheck-title">{t("Fact check")}</h2>
        {report.status === "complete" && <span className={`badge ${open ? "fail" : "ok"}`}>{open ? t("{{flagged}} flagged", { flagged: open }) : t("No open flags")}</span>}
        {running && (
          <span className="badge busy">
            <span className="spinner" aria-hidden="true" style={{ width: 10, height: 10 }} /> {t("Checking…")}
          </span>
        )}
      </div>
      <div className="field">
        <label htmlFor="job-project">{t("Project")}</label>
        <select id="job-project" value={job.project_id ?? ""} onChange={(e) => void assignProject(e.target.value)} disabled={running}>
          <option value="">{t("No project (library check unavailable)")}</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <span className="hint">{librariesHint}</span>
      </div>
      <label className="checkbox" style={{ marginBottom: 6 }}>
        <input type="checkbox" checked={useLibraries && hasLibraries} disabled={!hasLibraries || running} onChange={(e) => setUseLibraries(e.target.checked)} />
        {t("Check against project libraries")}
      </label>
      <label className="checkbox" style={{ marginBottom: 12 }}>
        <input type="checkbox" checked={useOnline} disabled={running} onChange={(e) => setUseOnline(e.target.checked)} />
        {t("Check against Wikipedia (online)")}
      </label>
      <button type="button" className="btn primary" style={{ width: "100%" }} onClick={() => void run()} disabled={busy || running || (!(useLibraries && hasLibraries) && !useOnline)}>
        {report.status === "complete" ? t("Run fact check again") : t("Run fact check")}
      </button>
      {report.status === "failed" && (
        <div className="alert error" role="alert" style={{ marginTop: 10 }}>
          {report.error}
        </div>
      )}
      {report.status === "complete" && (
        <>
          <p className="muted small" style={{ marginTop: 10 }}>
            {t("{{claims}} claims checked · sources: {{sources}} · judge: {{judge}}", { claims: report.claims_checked, sources, judge: report.judge })}
          </p>
          {report.judge.startsWith("heuristic") && <div className="alert warn small">{t("Heuristic mode compares numbers and keywords only. Configure a language model in Settings for full reasoning.")}</div>}
          <div className="btn-row" style={{ marginBottom: 8 }}>
            <button type="button" className="btn sm" onClick={() => setShowAll((v) => !v)}>
              {showAll ? t("Show flagged only") : t("Show all {{total}}", { total: report.checks.length })}
            </button>
          </div>
          {visible.length === 0 && (
            <p className="muted">
              {t("Nothing flagged.")} {report.checks.length ? t("Every checkable claim was supported or had no conflicting evidence.") : ""}
            </p>
          )}
          <div className="proposal-list">
            {visible.map((check) => (
              <FactCheckItem key={check.id} check={check} onSeek={onSeek} onDismiss={dismiss} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function FactCheckItem({ check, onSeek, onDismiss }: { check: FactCheck; onSeek: (ms: number) => void; onDismiss: (check: FactCheck, dismissed: boolean) => void }) {
  const { t } = useTranslation("job");
  const [openEvidence, setOpenEvidence] = useState(false);
  return (
    <div className={`proposal${check.dismissed ? " rejected" : ""}`} style={{ gridTemplateColumns: "1fr", borderColor: check.flagged && !check.dismissed ? "var(--danger)" : undefined }}>
      <div className="btn-row" style={{ justifyContent: "space-between" }}>
        <span className={`badge ${VERDICT_CLASS[check.verdict]}`}>
          {t(VERDICT_LABEL[check.verdict])} · {Math.round(check.confidence * 100)}%
        </span>
        <button type="button" className="time" onClick={() => onSeek(check.start_ms)} title={t("Jump to this point")}>
          ▶ {formatTime(check.start_ms)}
        </button>
      </div>
      <div className="text" style={{ whiteSpace: "normal" }}>
        <strong style={{ whiteSpace: "normal" }}>“{check.claim}”</strong>
        <span style={{ display: "block", whiteSpace: "normal" }}>{check.explanation}</span>
        {check.suggested_correction && (
          <span style={{ display: "block", whiteSpace: "normal", color: "var(--success)" }}>
            {t("Suggested: {{correction}}", { correction: check.suggested_correction })}
          </span>
        )}
      </div>
      <div className="btn-row">
        {check.evidence.length > 0 && (
          <button type="button" className="btn sm" onClick={() => setOpenEvidence((v) => !v)}>
            {openEvidence ? t("Hide evidence") : t("Evidence ({{total}})", { total: check.evidence.length })}
          </button>
        )}
        {check.flagged && (
          <button type="button" className="btn sm" onClick={() => onDismiss(check, !check.dismissed)}>
            {check.dismissed ? t("Re-open") : t("Dismiss")}
          </button>
        )}
      </div>
      {openEvidence &&
        check.evidence.map((evidence, index) => (
          <blockquote key={index} className="small" style={{ margin: "4px 0 0", padding: "6px 10px", borderLeft: "3px solid var(--border)", whiteSpace: "normal" }}>
            <strong>
              {evidence.url ? (
                <a href={evidence.url} target="_blank" rel="noreferrer">
                  {evidence.source}
                </a>
              ) : (
                evidence.source
              )}
            </strong>{" "}
            <span className="muted">{t("({{score}}% match)", { score: Math.round(evidence.score * 100) })}</span>
            <br />
            {evidence.excerpt.slice(0, 500)}
          </blockquote>
        ))}
    </div>
  );
}

import { useTranslation } from "react-i18next";
import type { ProcessingJob } from "../api/types";
import { useNow } from "../lib/autosave";
import { friendlyDuration } from "../lib/estimate";
import { formatTime } from "../lib/format";

const LONG_MS = 30 * 60 * 1000;

/** Progress, elapsed time and an honest time-remaining estimate while a job runs. */
export function ProcessingCard({ job }: { job: ProcessingJob }) {
  const { t } = useTranslation("job");
  const now = useNow(1000);
  const started = job.processing_started_at ? Date.parse(job.processing_started_at) : null;
  const elapsed = started ? Math.max(0, (now - started) / 1000) : null;
  const remaining = elapsed !== null && job.eta_seconds ? job.eta_seconds - elapsed : null;
  const long = job.media.duration_ms >= LONG_MS;

  return (
    <div className="card processing-card">
      <div className="btn-row">
        <span className="spinner" aria-hidden="true" />
        <strong>{job.message}</strong>
      </div>
      <div className="progress" style={{ marginTop: 10 }} role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${job.progress}%` }} />
      </div>
      <p className="small" style={{ marginTop: 8, marginBottom: 4 }}>
        {elapsed !== null && t("Elapsed: {{time}}", { time: formatTime(elapsed * 1000) })}
        {remaining !== null && remaining > 0 && <> · {t("About {{time}} left (estimate)", { time: friendlyDuration(remaining) })}</>}
        {remaining !== null && remaining <= 0 && <> · {t("Taking longer than estimated, still working…")}</>}
      </p>
      {long && (
        <div className="alert warn small" role="note">
          {t("This is a long recording ({{length}}). Processing can take a while; it continues on the server even if you close this tab, and resumes automatically after a restart.", {
            length: formatTime(job.media.duration_ms),
          })}
        </div>
      )}
      {!long && <p className="muted small">{t("You can leave this page; the job keeps running and resumes automatically after a restart.")}</p>}
    </div>
  );
}

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { episodesApi } from "../api/episodes";
import type { ProcessingJob } from "../api/types";

/** Shows the recognised spoken language and lets the user force another one and re-analyse. */
export function EpisodeLanguage({ job, disabled, onJob, onError }: { job: ProcessingJob; disabled: boolean; onJob: (job: ProcessingJob) => void; onError: (message: string) => void }) {
  const { t } = useTranslation("job");
  const [names, setNames] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .info()
      .then((info) => !cancelled && setNames(info.languages))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const value = job.language_override ?? "auto";
  const detected = job.language ? names[job.language.split("-")[0]] ?? job.language.toUpperCase() : null;
  const needsReanalysis = Boolean(job.language_override && job.language && job.language_override.split("-")[0] !== job.language.split("-")[0]);

  async function change(next: string) {
    setBusy(true);
    try {
      onJob(await episodesApi.updateMeta(job.id, { language: next }));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("Could not change the language"));
    } finally {
      setBusy(false);
    }
  }

  async function reanalyse() {
    setBusy(true);
    try {
      onJob(await episodesApi.reanalyze(job.id));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("Could not restart analysis"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="episode-language">
      <label htmlFor="episode-language">{t("Spoken language")}</label>
      <select id="episode-language" value={value} disabled={disabled || busy} onChange={(e) => void change(e.target.value)}>
        <option value="auto">{detected ? t("Auto-detected: {{language}}", { language: detected }) : t("Auto-detect")}</option>
        {Object.entries(names).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
      {needsReanalysis && (
        <button type="button" className="btn sm primary" onClick={() => void reanalyse()} disabled={disabled || busy}>
          {t("Re-analyse in {{language}}", { language: names[job.language_override!] ?? job.language_override })}
        </button>
      )}
    </span>
  );
}

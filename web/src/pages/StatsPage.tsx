import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { episodesApi } from "../api/episodes";
import type { EditKind, JobStats, ProcessingJob } from "../api/types";
import { BarChart, Donut, LineChart, SERIES, StatTile } from "../components/charts/Charts";
import { JobTabs } from "../components/JobTabs";
import { rememberPlace } from "../lib/session";
import { KIND_LABELS, formatDuration, formatTime, uiLocale } from "../lib/format";

const KIND_ORDER: EditKind[] = ["filler", "repeat", "profanity", "silence"];
const VERDICT_COLORS: Record<string, string> = { supported: "var(--status-good)", contradicted: "var(--status-critical)", unsupported: "var(--chart-4)", uncertain: "var(--status-warning)" };
// Server-provided verdict keys mapped to English display labels (translated at render).
const VERDICT_LABELS: Record<string, string> = { supported: "supported", contradicted: "contradicted", unsupported: "unsupported", uncertain: "uncertain" };

export function StatsPage({ id }: { id: string }) {
  const { t } = useTranslation("insights");
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (job) rememberPlace({ hash: `#/jobs/${job.id}/stats`, title: job.display_name || job.show_notes.title || job.asset_name, section: "stats" });
  }, [job]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      Promise.all([api.getJob(id), episodesApi.stats(id)])
        .then(([j, s]) => {
          setJob(j);
          setStats(s);
        })
        .catch((err: Error) => setError(err.message));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [id]);

  if (error)
    return (
      <div className="alert error" role="alert">
        {error}
      </div>
    );
  if (!job || !stats) return <p className="muted">{t("Loading statistics…")}</p>;

  const o = stats.overview as Record<string, number | string | null>;
  const num = (key: string) => Number(o[key] ?? 0);
  const removedPct = num("original_duration_ms") ? Math.round((num("removed_ms") / num("original_duration_ms")) * 100) : 0;
  const kinds = KIND_ORDER.filter((k) => stats.edits_by_kind[k].proposed > 0);
  const verdicts = Object.entries(stats.fact_check.verdicts);
  const speakers = Object.entries((stats.overview.speakers as Record<string, number>) ?? {});

  return (
    <>
      <div className="page-header">
        <div>
          <h1 style={{ wordBreak: "break-word" }}>{job.display_name || job.show_notes.title || job.asset_name}</h1>
          <p>{t("Statistics and quality report")}</p>
        </div>
      </div>
      <JobTabs id={id} active="stats" />

      <section className="card" aria-labelledby="stats-overview">
        <h2 id="stats-overview">{t("Overview")}</h2>
        <div className="stats">
          <StatTile label={t("original length")} value={formatTime(num("original_duration_ms"))} />
          <StatTile label={t("final length")} value={formatTime(num("final_duration_ms"))} hint={`−${removedPct}%`} />
          <StatTile label={t("words spoken")} value={num("words_original").toLocaleString(uiLocale())} hint={t("{{value}} kept", { value: num("words_final").toLocaleString(uiLocale()) })} />
          <StatTile label={t("words / minute")} value={num("words_per_minute")} tone={num("words_per_minute") > 185 ? "warning" : undefined} />
          <StatTile label={t("unique words")} value={num("unique_words").toLocaleString(uiLocale())} hint={t("richness {{percent}}%", { percent: (Number(o.vocabulary_richness) * 100).toFixed(0) })} />
          <StatTile label={t("fillers / 100 words")} value={num("filler_rate_per_100_words")} tone={num("filler_rate_per_100_words") > 3 ? "warning" : "good"} />
          <StatTile label={t("edits accepted")} value={`${num("accepted_edits")}/${num("proposals")}`} />
          <StatTile label={t("text edits")} value={num("text_edits")} />
          <StatTile label={t("long pauses")} value={num("long_pauses")} hint={num("longest_pause_ms") ? t("longest {{duration}}", { duration: formatDuration(num("longest_pause_ms")) }) : undefined} />
          <StatTile label={t("fact-check flags")} value={num("fact_flags_open")} hint={t("{{n}} claims", { n: num("fact_checks") })} tone={num("fact_flags_open") ? "serious" : undefined} />
          <StatTile label={t("loudness")} value={o.output_lufs !== null && o.output_lufs !== undefined ? `${Number(o.output_lufs).toFixed(1)} LUFS` : "–"} hint={o.true_peak_dbtp !== null && o.true_peak_dbtp !== undefined ? `${Number(o.true_peak_dbtp).toFixed(1)} dBTP` : undefined} />
          <StatTile label={t("published")} value={num("published")} hint={t("{{n}} files", { n: num("outputs") })} />
        </div>
      </section>

      <div className="grid-2" style={{ marginTop: "1rem" }}>
        <section className="card" aria-labelledby="chart-timeline">
          <h2 id="chart-timeline">{t("Speaking pace per minute")}</h2>
          <p className="muted small">{t("Words spoken in each minute of the original recording.")}</p>
          <LineChart labels={stats.timeline.labels} series={[{ name: t("Words"), values: stats.timeline.words }]} />
        </section>
        <section className="card" aria-labelledby="chart-edits-time">
          <h2 id="chart-edits-time">{t("Edits per minute")}</h2>
          <p className="muted small">{t("Where the cleanup suggestions cluster.")}</p>
          <BarChart labels={stats.timeline.labels} stacked series={kinds.map((k, i) => ({ name: t(KIND_LABELS[k]), values: stats.timeline.edits[k], color: SERIES[i] }))} />
        </section>
        <section className="card" aria-labelledby="chart-kinds">
          <h2 id="chart-kinds">{t("Suggestions by type")}</h2>
          <BarChart
            labels={kinds.map((k) => t(KIND_LABELS[k]))}
            series={[
              { name: t("Accepted"), values: kinds.map((k) => stats.edits_by_kind[k].accepted) },
              { name: t("Rejected"), values: kinds.map((k) => stats.edits_by_kind[k].rejected) },
            ]}
            height={180}
          />
          <table className="job-table small" style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>{t("Type")}</th>
                <th>{t("Proposed")}</th>
                <th>{t("Accepted")}</th>
                <th>{t("Removed")}</th>
                <th>{t("Avg. confidence")}</th>
              </tr>
            </thead>
            <tbody>
              {kinds.map((k) => (
                <tr key={k}>
                  <td>{t(KIND_LABELS[k])}</td>
                  <td>{stats.edits_by_kind[k].proposed}</td>
                  <td>{stats.edits_by_kind[k].accepted}</td>
                  <td>{formatDuration(stats.edits_by_kind[k].removed_ms)}</td>
                  <td>{stats.edits_by_kind[k].avg_confidence !== null ? `${Math.round(stats.edits_by_kind[k].avg_confidence * 100)}%` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="card" aria-labelledby="chart-removed">
          <h2 id="chart-removed">{t("Time removed per minute")}</h2>
          <BarChart labels={stats.timeline.labels} series={[{ name: t("Removed"), values: stats.timeline.removed_ms.map((v) => Math.round(v / 100) / 10) }]} formatValue={(v) => t("{{value}}s", { value: v })} />
        </section>
        <section className="card" aria-labelledby="chart-words">
          <h2 id="chart-words">{t("Most used words")}</h2>
          <BarChart horizontal labels={stats.top_words.map((w) => w.word)} series={[{ name: t("Count"), values: stats.top_words.map((w) => w.count) }]} height={Math.max(160, stats.top_words.length * 22 + 40)} />
        </section>
        <section className="card" aria-labelledby="chart-fillers">
          <h2 id="chart-fillers">{t("Fillers and flagged words")}</h2>
          {stats.filler_terms.length + stats.profanity_terms.length === 0 ? (
            <p className="muted">{t("Nothing flagged.")}</p>
          ) : (
            <BarChart
              horizontal
              labels={[...stats.filler_terms.map((w) => w.word), ...stats.profanity_terms.map((w) => t("{{word}} (profanity)", { word: w.word }))]}
              series={[{ name: t("Occurrences"), values: [...stats.filler_terms.map((w) => w.count), ...stats.profanity_terms.map((w) => w.count)], color: SERIES[1] }]}
              height={Math.max(140, (stats.filler_terms.length + stats.profanity_terms.length) * 22 + 40)}
            />
          )}
        </section>
        <section className="card" aria-labelledby="chart-segments">
          <h2 id="chart-segments">{t("Sentence length (words)")}</h2>
          <BarChart labels={stats.segment_length_histogram.map((b) => b.label)} series={[{ name: t("Segments"), values: stats.segment_length_histogram.map((b) => b.count), color: SERIES[2] }]} height={170} />
        </section>
        <section className="card" aria-labelledby="chart-pauses">
          <h2 id="chart-pauses">{t("Pause length (seconds)")}</h2>
          <BarChart labels={stats.pause_histogram.map((b) => b.label)} series={[{ name: t("Pauses"), values: stats.pause_histogram.map((b) => b.count), color: SERIES[3] }]} height={170} />
        </section>
        <section className="card" aria-labelledby="chart-confidence">
          <h2 id="chart-confidence">{t("Suggestion confidence")}</h2>
          <BarChart labels={stats.proposals_confidence.map((b) => b.label)} series={[{ name: t("Suggestions"), values: stats.proposals_confidence.map((b) => b.count), color: SERIES[4] }]} height={170} />
        </section>
        <section className="card" aria-labelledby="chart-facts">
          <h2 id="chart-facts">{t("Fact check verdicts")}</h2>
          {verdicts.length === 0 ? <p className="muted">{t("No fact check has been run.")}</p> : <Donut items={verdicts.map(([label, value]) => ({ label: VERDICT_LABELS[label] ? t(VERDICT_LABELS[label]) : label, value, color: VERDICT_COLORS[label] }))} />}
          {stats.fact_check.judge && (
            <p className="muted small">
              {t("Judge: {{judge}} · sources: {{sources}}", { judge: stats.fact_check.judge, sources: stats.fact_check.sources.join(", ") || t("online only") })}
            </p>
          )}
        </section>
        {speakers.length > 0 && (
          <section className="card" aria-labelledby="chart-speakers">
            <h2 id="chart-speakers">{t("Segments per speaker")}</h2>
            <Donut items={speakers.map(([label, value]) => ({ label, value }))} />
          </section>
        )}
      </div>
    </>
  );
}

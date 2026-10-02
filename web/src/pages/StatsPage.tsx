import { useEffect, useState } from "react";
import { api } from "../api/client";
import { episodesApi } from "../api/episodes";
import type { EditKind, JobStats, ProcessingJob } from "../api/types";
import { BarChart, Donut, LineChart, SERIES, StatTile } from "../components/charts/Charts";
import { JobTabs } from "../components/JobTabs";
import { KIND_LABELS, formatDuration, formatTime } from "../lib/format";

const KIND_ORDER: EditKind[] = ["filler", "repeat", "profanity", "silence"];
const VERDICT_COLORS: Record<string, string> = { supported: "var(--status-good)", contradicted: "var(--status-critical)", unsupported: "var(--chart-4)", uncertain: "var(--status-warning)" };

export function StatsPage({ id }: { id: string }) {
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  if (!job || !stats) return <p className="muted">Loading statistics…</p>;

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
          <p>Statistics and quality report</p>
        </div>
      </div>
      <JobTabs id={id} active="stats" />

      <section className="card" aria-labelledby="stats-overview">
        <h2 id="stats-overview">Overview</h2>
        <div className="stats">
          <StatTile label="original length" value={formatTime(num("original_duration_ms"))} />
          <StatTile label="final length" value={formatTime(num("final_duration_ms"))} hint={`−${removedPct}%`} />
          <StatTile label="words spoken" value={num("words_original").toLocaleString()} hint={`${num("words_final").toLocaleString()} kept`} />
          <StatTile label="words / minute" value={num("words_per_minute")} tone={num("words_per_minute") > 185 ? "warning" : undefined} />
          <StatTile label="unique words" value={num("unique_words").toLocaleString()} hint={`richness ${(Number(o.vocabulary_richness) * 100).toFixed(0)}%`} />
          <StatTile label="fillers / 100 words" value={num("filler_rate_per_100_words")} tone={num("filler_rate_per_100_words") > 3 ? "warning" : "good"} />
          <StatTile label="edits accepted" value={`${num("accepted_edits")}/${num("proposals")}`} />
          <StatTile label="text edits" value={num("text_edits")} />
          <StatTile label="long pauses" value={num("long_pauses")} hint={num("longest_pause_ms") ? `longest ${formatDuration(num("longest_pause_ms"))}` : undefined} />
          <StatTile label="fact-check flags" value={num("fact_flags_open")} hint={`${num("fact_checks")} claims`} tone={num("fact_flags_open") ? "serious" : undefined} />
          <StatTile label="loudness" value={o.output_lufs !== null && o.output_lufs !== undefined ? `${Number(o.output_lufs).toFixed(1)} LUFS` : "–"} hint={o.true_peak_dbtp !== null && o.true_peak_dbtp !== undefined ? `${Number(o.true_peak_dbtp).toFixed(1)} dBTP` : undefined} />
          <StatTile label="published" value={num("published")} hint={`${num("outputs")} files`} />
        </div>
      </section>

      <div className="grid-2" style={{ marginTop: "1rem" }}>
        <section className="card" aria-labelledby="chart-timeline">
          <h2 id="chart-timeline">Speaking pace per minute</h2>
          <p className="muted small">Words spoken in each minute of the original recording.</p>
          <LineChart labels={stats.timeline.labels} series={[{ name: "Words", values: stats.timeline.words }]} />
        </section>
        <section className="card" aria-labelledby="chart-edits-time">
          <h2 id="chart-edits-time">Edits per minute</h2>
          <p className="muted small">Where the cleanup suggestions cluster.</p>
          <BarChart labels={stats.timeline.labels} stacked series={kinds.map((k, i) => ({ name: KIND_LABELS[k], values: stats.timeline.edits[k], color: SERIES[i] }))} />
        </section>
        <section className="card" aria-labelledby="chart-kinds">
          <h2 id="chart-kinds">Suggestions by type</h2>
          <BarChart
            labels={kinds.map((k) => KIND_LABELS[k])}
            series={[
              { name: "Accepted", values: kinds.map((k) => stats.edits_by_kind[k].accepted) },
              { name: "Rejected", values: kinds.map((k) => stats.edits_by_kind[k].rejected) },
            ]}
            height={180}
          />
          <table className="job-table small" style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>Type</th>
                <th>Proposed</th>
                <th>Accepted</th>
                <th>Removed</th>
                <th>Avg. confidence</th>
              </tr>
            </thead>
            <tbody>
              {kinds.map((k) => (
                <tr key={k}>
                  <td>{KIND_LABELS[k]}</td>
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
          <h2 id="chart-removed">Time removed per minute</h2>
          <BarChart labels={stats.timeline.labels} series={[{ name: "Removed", values: stats.timeline.removed_ms.map((v) => Math.round(v / 100) / 10) }]} formatValue={(v) => `${v}s`} />
        </section>
        <section className="card" aria-labelledby="chart-words">
          <h2 id="chart-words">Most used words</h2>
          <BarChart horizontal labels={stats.top_words.map((w) => w.word)} series={[{ name: "Count", values: stats.top_words.map((w) => w.count) }]} height={Math.max(160, stats.top_words.length * 22 + 40)} />
        </section>
        <section className="card" aria-labelledby="chart-fillers">
          <h2 id="chart-fillers">Fillers and flagged words</h2>
          {stats.filler_terms.length + stats.profanity_terms.length === 0 ? (
            <p className="muted">Nothing flagged.</p>
          ) : (
            <BarChart
              horizontal
              labels={[...stats.filler_terms.map((w) => w.word), ...stats.profanity_terms.map((w) => `${w.word} (profanity)`)]}
              series={[{ name: "Occurrences", values: [...stats.filler_terms.map((w) => w.count), ...stats.profanity_terms.map((w) => w.count)], color: SERIES[1] }]}
              height={Math.max(140, (stats.filler_terms.length + stats.profanity_terms.length) * 22 + 40)}
            />
          )}
        </section>
        <section className="card" aria-labelledby="chart-segments">
          <h2 id="chart-segments">Sentence length (words)</h2>
          <BarChart labels={stats.segment_length_histogram.map((b) => b.label)} series={[{ name: "Segments", values: stats.segment_length_histogram.map((b) => b.count), color: SERIES[2] }]} height={170} />
        </section>
        <section className="card" aria-labelledby="chart-pauses">
          <h2 id="chart-pauses">Pause length (seconds)</h2>
          <BarChart labels={stats.pause_histogram.map((b) => b.label)} series={[{ name: "Pauses", values: stats.pause_histogram.map((b) => b.count), color: SERIES[3] }]} height={170} />
        </section>
        <section className="card" aria-labelledby="chart-confidence">
          <h2 id="chart-confidence">Suggestion confidence</h2>
          <BarChart labels={stats.proposals_confidence.map((b) => b.label)} series={[{ name: "Suggestions", values: stats.proposals_confidence.map((b) => b.count), color: SERIES[4] }]} height={170} />
        </section>
        <section className="card" aria-labelledby="chart-facts">
          <h2 id="chart-facts">Fact check verdicts</h2>
          {verdicts.length === 0 ? <p className="muted">No fact check has been run.</p> : <Donut items={verdicts.map(([label, value]) => ({ label, value, color: VERDICT_COLORS[label] }))} />}
          {stats.fact_check.judge && (
            <p className="muted small">
              Judge: {stats.fact_check.judge} · sources: {stats.fact_check.sources.join(", ") || "online only"}
            </p>
          )}
        </section>
        {speakers.length > 0 && (
          <section className="card" aria-labelledby="chart-speakers">
            <h2 id="chart-speakers">Segments per speaker</h2>
            <Donut items={speakers.map(([label, value]) => ({ label, value }))} />
          </section>
        )}
      </div>
    </>
  );
}

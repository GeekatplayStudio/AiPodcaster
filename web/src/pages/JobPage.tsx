import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { ragApi } from "../api/rag";
import type { EditKind, EditProposal, ProcessingJob, Project, TranscriptSegment, VoiceMode } from "../api/types";
import { AudioPlayer, type PlayerHandle } from "../components/AudioPlayer";
import { FactCheckPanel } from "../components/FactCheckPanel";
import { JobTabs } from "../components/JobTabs";
import { OutputsPanel, ShowNotesPanel } from "../components/OutputsPanel";
import { ProposalPanel } from "../components/ProposalPanel";
import { StageBadge, Steps } from "../components/StageBadge";
import { TranscriptEditor } from "../components/TranscriptEditor";
import { VoiceCloneButton } from "../components/VoiceCloneButton";
import { segmentDirty, setKind, toggleProposal } from "../lib/edits";
import { formatBytes, formatTime, isProcessing } from "../lib/format";

export function JobPage({ id, onBack }: { id: string; onBack: () => void }) {
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [proposals, setProposals] = useState<EditProposal[]>([]);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("original");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const player = useRef<PlayerHandle>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => void ragApi.listProjects().then(setProjects).catch(() => undefined), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const load = useCallback(async () => {
    try {
      const next = await api.getJob(id);
      setJob((prev) => {
        if (!prev || prev.stage !== next.stage || prev.updated_at !== next.updated_at) {
          setProposals(next.proposals);
          setSegments(next.segments);
          setTitle((t) => t || next.show_notes.title);
          setVoiceMode(next.voice_mode);
        }
        return next;
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load job");
    }
  }, [id]);

  const polling = job ? isProcessing(job.stage) || job.verification.status === "running" : false;
  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    const interval = polling ? window.setInterval(load, 1500) : undefined;
    return () => {
      window.clearTimeout(timer);
      if (interval) window.clearInterval(interval);
    };
  }, [polling, load]);

  if (error && !job)
    return (
      <div className="alert error" role="alert">
        {error}{" "}
        <button type="button" className="btn sm" onClick={onBack}>
          Back
        </button>
      </div>
    );
  if (!job) return <p className="muted">Loading…</p>;

  const reviewable = job.stage === "waiting_for_approval" || job.stage === "complete" || job.stage === "failed";
  const readOnly = !reviewable || busy;
  const dirty = segmentDirty(job.segments, segments);

  async function approve() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.approve(job.id, {
        decisions: proposals.map((p) => ({ id: p.id, accepted: p.accepted })),
        segments: dirty,
        voice_mode: job.source_kind === "text" ? "synthetic" : voiceMode,
        title: title.trim(),
      });
      setJob(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveText(segmentId: number, text: string) {
    setSegments((current) => current.map((s) => (s.id === segmentId ? { ...s, text } : s)));
    if (!job) return;
    try {
      const updated = await api.updateTranscript(job.id, [{ id: segmentId, text }]);
      setJob(updated);
      setSegments(updated.segments);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save text");
    }
  }

  async function reanalyze() {
    if (!job) return;
    setBusy(true);
    try {
      setJob(await api.reanalyze(job.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not restart analysis");
    } finally {
      setBusy(false);
    }
  }

  const preview = (p: EditProposal) => player.current?.seek(Math.max(0, p.start_ms - 1200), true);
  const project = projects.find((p) => p.id === job.project_id) ?? null;
  const flaggedSegments = new Set(job.verification.checks.filter((c) => c.flagged && !c.dismissed).map((c) => c.segment_id));

  return (
    <>
      <div className="page-header">
        <div>
          <button type="button" className="btn sm" onClick={onBack} style={{ marginBottom: 8 }}>
            ← Episodes
          </button>
          <h1 title={job.asset_name} style={{ wordBreak: "break-word" }}>
            {job.display_name || job.asset_name}
          </h1>
          <p>
            {job.media.duration_ms ? `${formatTime(job.media.duration_ms)} · ` : ""}
            {job.media.codec ? `${job.media.codec.toUpperCase()} · ${job.media.sample_rate} Hz · ` : ""}
            {formatBytes(job.media.size_bytes)}
            {job.language ? ` · ${job.language.toUpperCase()}` : ""}
            {job.transcription_provider ? ` · ${job.transcription_provider}` : ""}
            {job.source_url ? (
              <>
                {" · "}
                <a href={job.source_url} target="_blank" rel="noreferrer">
                  source link
                </a>
              </>
            ) : null}
          </p>
        </div>
        <StageBadge stage={job.stage} progress={job.progress} />
      </div>
      <JobTabs id={job.id} active="edit" />
      <Steps stage={job.stage} />
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {job.stage === "failed" && (
        <div className="alert error" role="alert">
          <strong>Processing failed:</strong> {job.error}
          <div className="btn-row" style={{ marginTop: 8 }}>
            <button type="button" className="btn sm" onClick={() => void reanalyze()} disabled={busy}>
              Retry analysis
            </button>
          </div>
        </div>
      )}
      {isProcessing(job.stage) && (
        <div className="card">
          <div className="btn-row">
            <span className="spinner" aria-hidden="true" />
            <strong>{job.message}</strong>
          </div>
          <div className="progress" style={{ marginTop: 10 }} role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${job.progress}%` }} />
          </div>
          <p className="muted small" style={{ marginTop: 8 }}>
            Local transcription of long recordings can take a few minutes. You can leave this page; the job keeps running.
          </p>
        </div>
      )}
      {job.stage === "complete" && (
        <section className="card" aria-labelledby="outputs-title">
          <div className="card-title">
            <h2 id="outputs-title">Episode ready</h2>
            <span className="badge ok">Voice: {job.voice_mode}</span>
          </div>
          <div className="review-layout">
            <div>
              <OutputsPanel job={job} />
            </div>
            <div>
              <ShowNotesPanel job={job} />
            </div>
          </div>
        </section>
      )}
      {job.segments.length > 0 && (
        <div className="review-layout" style={{ marginTop: "1rem" }}>
          <section className="card" aria-labelledby="transcript-title">
            <div className="card-title">
              <h2 id="transcript-title">Transcript</h2>
              <span className="muted small">Click a highlighted word to keep or remove it. Double-click text to edit.</span>
            </div>
            {job.source_kind === "text" ? (
              <div className="alert info small">Text episode: timing is estimated from the speaking pace, so there is no original audio to play. Produce it with a synthetic voice to hear it.</div>
            ) : (
              <AudioPlayer ref={player} src={api.originalAudioUrl(job.id)} durationMs={job.media.duration_ms} proposals={proposals} />
            )}
            <div style={{ marginTop: "0.75rem" }}>
              <TranscriptEditor segments={segments} proposals={proposals} readOnly={readOnly} flaggedSegments={flaggedSegments} onSeek={(ms) => player.current?.seek(ms, true)} onToggle={(pid) => setProposals((c) => toggleProposal(c, pid))} onEditSegment={(sid, text) => void saveText(sid, text)} />
            </div>
          </section>
          <div>
            <FactCheckPanel job={job} project={project} projects={projects} onJob={setJob} onSeek={(ms) => player.current?.seek(ms, true)} onError={setError} />
            <section className="card" aria-labelledby="edits-title">
              <div className="card-title">
                <h2 id="edits-title">Suggested edits</h2>
              </div>
              <ProposalPanel proposals={proposals} readOnly={readOnly} onToggle={(pid, accepted) => setProposals((c) => toggleProposal(c, pid, accepted))} onKind={(kind: EditKind, accepted) => setProposals((c) => setKind(c, kind, accepted))} onPreview={preview} />
            </section>
            <section className="card" aria-labelledby="produce-title">
              <div className="card-title">
                <h2 id="produce-title">{job.stage === "complete" ? "Produce again" : "Approve & produce"}</h2>
              </div>
              <div className="field">
                <label htmlFor="episode-title">Episode title</label>
                <input id="episode-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} disabled={readOnly} />
              </div>
              <div className="field">
                <label htmlFor="voice-mode">Voice</label>
                <select id="voice-mode" value={job.source_kind === "text" ? "synthetic" : voiceMode} onChange={(e) => setVoiceMode(e.target.value as VoiceMode)} disabled={readOnly || job.source_kind === "text"}>
                  {job.source_kind !== "text" && <option value="original">Original voice (cleaned recording)</option>}
                  <option value="synthetic">Synthetic voice (reads the approved text)</option>
                </select>
                <span className="hint">{voiceMode === "synthetic" ? "Requires a speech provider in Settings. Listeners should be told the voice is synthetic." : "Accepted edits are cut from your recording, then loudness is mastered for podcast delivery."}</span>
              </div>
              <button type="button" className="btn primary" style={{ width: "100%" }} onClick={() => void approve()} disabled={readOnly || job.stage === "failed"}>
                {busy ? "Working…" : job.stage === "complete" ? "Re-render with these choices" : "Approve transcript & produce episode"}
              </button>
              <button type="button" className="btn" style={{ width: "100%", marginTop: 8 }} onClick={() => void reanalyze()} disabled={readOnly}>
                Re-run analysis with current settings
              </button>
              <VoiceCloneButton jobId={job.id} assetName={job.asset_name} />
            </section>
          </div>
        </div>
      )}
    </>
  );
}

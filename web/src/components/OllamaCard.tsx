import { useCallback, useEffect, useState } from "react";
import { ragApi } from "../api/rag";
import type { OllamaStatus } from "../api/types";
import { formatBytes } from "../lib/format";

/** Shows Ollama health, installed models and a one-click "prepare best model" action. */
export function OllamaCard({ currentModel, onModelChosen }: { currentModel: string; onModelChosen: (model: string) => void }) {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await ragApi.ollamaStatus());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not query Ollama");
    }
  }, []);

  const pulling = status?.pull.status === "pulling";
  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);
    const interval = pulling ? window.setInterval(refresh, 2000) : undefined;
    return () => {
      window.clearTimeout(timer);
      if (interval) window.clearInterval(interval);
    };
  }, [refresh, pulling]);

  async function setup(model?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await ragApi.ollamaSetup(model);
      setMessage(result.message + (result.reason ? ` (${result.reason})` : ""));
      if (result.model) onModelChosen(result.model);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    try {
      await ragApi.ollamaStart();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Ollama");
    } finally {
      setBusy(false);
    }
  }

  if (!status) return <div className="alert info">{error ?? "Checking Ollama…"}</div>;
  const pull = status.pull;
  const percent = pull.total ? Math.round((pull.completed / pull.total) * 100) : 0;
  return (
    <div className="card" style={{ marginTop: "0.75rem", boxShadow: "none" }} data-testid="ollama-card">
      <div className="card-title">
        <h3 style={{ margin: 0 }}>Ollama</h3>
        <span className={`badge ${status.running ? "ok" : "fail"}`}>{status.running ? "running" : status.installed_binary ? "stopped" : "not installed"}</span>
      </div>
      <p className="muted small">
        {status.url} · budget {status.budget_gb} GB{status.gpu_gb ? ` (GPU ${status.gpu_gb} GB)` : " (CPU/RAM)"}
      </p>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {!status.running && (
        <div className="btn-row" style={{ marginBottom: 8 }}>
          {status.installed_binary ? (
            <button type="button" className="btn" onClick={() => void start()} disabled={busy}>
              Start Ollama
            </button>
          ) : (
            <a className="btn" href="https://ollama.com/download" target="_blank" rel="noreferrer">
              Install Ollama
            </a>
          )}
        </div>
      )}
      {status.running && (
        <>
          <p className="small">
            Recommended: <strong>{status.recommended || "–"}</strong>
            {status.needs_pull ? " (needs download)" : " (installed)"} · {status.reason}
          </p>
          <div className="btn-row" style={{ marginBottom: 8 }}>
            <button type="button" className="btn primary" onClick={() => void setup()} disabled={busy || pulling}>
              {busy ? "Working…" : "Prepare best model & use it"}
            </button>
            <button type="button" className="btn sm" onClick={() => void refresh()}>
              Refresh
            </button>
          </div>
          {pulling && (
            <div style={{ marginBottom: 8 }}>
              <div className="muted small">
                Downloading {pull.model}: {pull.message} {pull.total ? `${formatBytes(pull.completed)} / ${formatBytes(pull.total)}` : ""}
              </div>
              <div className="progress" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${percent}%` }} />
              </div>
            </div>
          )}
          {pull.status === "done" && <div className="alert success small">{pull.model} downloaded. Click “Prepare” again to warm it up, or it will load on first use.</div>}
          {pull.status === "failed" && <div className="alert error small">Download failed: {pull.message}</div>}
          {message && <div className="alert info small">{message}</div>}
          <strong className="small">Installed models</strong>
          {status.models.length === 0 && <p className="muted small">None yet.</p>}
          <div className="outputs">
            {status.models.map((model) => (
              <div className="output" key={model.name}>
                <div className="meta">
                  <strong>
                    {model.name}
                    {model.name === currentModel ? " ✓" : ""}
                  </strong>
                  <span className="muted small">
                    {model.parameter_size} · {model.size_gb} GB · fit score {model.score}
                  </span>
                </div>
                <button type="button" className="btn sm" onClick={() => void setup(model.name)} disabled={busy || pulling}>
                  Use
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

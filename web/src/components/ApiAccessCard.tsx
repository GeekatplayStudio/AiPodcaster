import { useCallback, useEffect, useState } from "react";
import { getUiApiKey, setUiApiKey } from "../api/auth";
import { ragApi } from "../api/rag";
import type { ApiKeyInfo } from "../api/types";

/** Manage external API keys and show how to connect the MCP server. */
export function ApiAccessCard({ requireForUi, onRequireForUi }: { requireForUi: boolean; onRequireForUi: (value: boolean) => void }) {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [label, setLabel] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [uiKey, setUiKeyState] = useState(getUiApiKey());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setKeys(await ragApi.listApiKeys());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load keys");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  async function create() {
    try {
      const result = await ragApi.createApiKey(label.trim());
      setCreated(result.key);
      setLabel("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create key");
    }
  }

  async function remove(prefix: string) {
    if (!window.confirm("Revoke this key? Clients using it will stop working.")) return;
    try {
      await ragApi.deleteApiKey(prefix);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke key");
    }
  }

  function saveUiKey(value: string) {
    setUiKeyState(value);
    setUiApiKey(value.trim());
  }

  const origin = window.location.origin.replace(/:\d+$/, ":8000");
  const snippet = JSON.stringify(
    { mcpServers: { aipodcaster: { command: "python", args: ["<path-to-repo>/backend/mcp_server.py"], env: { AIPODCASTER_URL: origin, AIPODCASTER_API_KEY: created ?? "<your key>" } } } },
    null,
    2,
  );

  return (
    <section className="card" aria-labelledby="api-title">
      <h2 id="api-title">API & MCP access</h2>
      <p className="muted small">
        The REST API is documented at <a href={`${origin}/docs`}>{origin}/docs</a>. When at least one key exists, external clients must send it as <code>X-API-Key</code>. The browser UI on this origin stays allowed unless you require a key for it too.
      </p>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      <div className="btn-row" style={{ marginBottom: 8 }}>
        <input className="input" style={{ flex: 1, minWidth: 160 }} type="text" placeholder="Label (e.g. desktop assistant)" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} aria-label="Key label" />
        <button type="button" className="btn primary" onClick={() => void create()}>
          Generate key
        </button>
      </div>
      {created && (
        <div className="alert success small">
          New key (shown once): <code>{created}</code>
        </div>
      )}
      {keys.length > 0 && (
        <div className="outputs" style={{ marginBottom: 8 }}>
          {keys.map((key) => (
            <div className="output" key={key.prefix}>
              <code>{key.hint}</code>
              <button type="button" className="btn sm danger" onClick={() => void remove(key.prefix)}>
                Revoke
              </button>
            </div>
          ))}
        </div>
      )}
      <label className="checkbox" style={{ marginBottom: 8 }}>
        <input type="checkbox" checked={requireForUi} onChange={(e) => onRequireForUi(e.target.checked)} />
        Also require a key for this web UI (enter it below)
      </label>
      <div className="field">
        <label htmlFor="ui-key">Key used by this browser</label>
        <input id="ui-key" type="password" autoComplete="off" value={uiKey} onChange={(e) => saveUiKey(e.target.value)} placeholder="stored only in this browser" />
      </div>
      <details>
        <summary className="small" style={{ cursor: "pointer" }}>
          MCP server setup (desktop assistants and IDE agents)
        </summary>
        <p className="small muted" style={{ marginTop: 6 }}>
          Run <code>python backend/mcp_server.py</code> (stdio) or <code>python backend/mcp_server.py --http --port 8765</code>. Example client configuration:
        </p>
        <pre className="small" style={{ overflowX: "auto", background: "var(--surface-2)", padding: 10, borderRadius: 8 }}>{snippet}</pre>
      </details>
    </section>
  );
}

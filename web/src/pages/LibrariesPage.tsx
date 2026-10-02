import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ragApi } from "../api/rag";
import type { Library, LibrarySummary, SearchHit } from "../api/types";
import { formatBytes } from "../lib/format";

const ACCEPT = ".pdf,.docx,.txt,.md,.markdown,.html,.htm,.epub,.csv,.json,.rtf";

export function LibrariesPage() {
  const [libraries, setLibraries] = useState<LibrarySummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const refresh = useCallback(async () => {
    try {
      setLibraries(await ragApi.listLibraries());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load libraries");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const library = await ragApi.createLibrary(name.trim(), description.trim());
      setName("");
      setDescription("");
      await refresh();
      setSelected(library.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create library");
    }
  }

  async function remove(library: LibrarySummary) {
    if (!window.confirm(`Delete library "${library.name}" and its ${library.document_count} documents?`)) return;
    try {
      await ragApi.deleteLibrary(library.id);
      if (selected === library.id) setSelected(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Knowledge libraries</h1>
          <p>Upload books, papers, notes and web pages. They are indexed into a local vector database and used to fact-check transcripts.</p>
        </div>
      </div>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      <div className="review-layout">
        <div>
          <section className="card" aria-labelledby="new-library">
            <h2 id="new-library">New library</h2>
            <form onSubmit={create} className="grid-2" style={{ alignItems: "end" }}>
              <div className="field" style={{ marginBottom: 0 }}>
                <label htmlFor="lib-name">Name</label>
                <input id="lib-name" type="text" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required placeholder="e.g. Habits research" />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <label htmlFor="lib-desc">Description (optional)</label>
                <input id="lib-desc" type="text" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={1000} />
              </div>
              <div>
                <button type="submit" className="btn primary">
                  Create library
                </button>
              </div>
            </form>
          </section>
          <section className="card" aria-labelledby="library-list">
            <div className="card-title">
              <h2 id="library-list">Libraries</h2>
              <button type="button" className="btn sm" onClick={() => void refresh()}>
                Refresh
              </button>
            </div>
            {libraries === null && <p className="muted">Loading…</p>}
            {libraries && libraries.length === 0 && <div className="empty">No libraries yet. Create one above, then add documents.</div>}
            {libraries && libraries.length > 0 && (
              <table className="job-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Documents</th>
                    <th>Chunks</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {libraries.map((library) => (
                    <tr key={library.id} style={selected === library.id ? { outline: "2px solid var(--accent)", outlineOffset: -2 } : undefined}>
                      <td className="name">
                        <button type="button" className="btn sm" style={{ background: "transparent", border: "none", padding: 0, fontWeight: 600 }} onClick={() => setSelected(library.id)}>
                          {library.name}
                        </button>
                        <div className="muted small">{library.description}</div>
                      </td>
                      <td>
                        {library.ready_count}/{library.document_count} ready
                      </td>
                      <td>{library.chunk_count}</td>
                      <td>
                        <div className="btn-row" style={{ justifyContent: "flex-end" }}>
                          <button type="button" className="btn sm" onClick={() => setSelected(library.id)}>
                            Open
                          </button>
                          <button type="button" className="btn sm danger" onClick={() => void remove(library)}>
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
        <div>{selected ? <LibraryDetail id={selected} onChanged={refresh} /> : <section className="card empty">Select a library to add documents.</section>}</div>
      </div>
    </>
  );
}

function LibraryDetail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [library, setLibrary] = useState<Library | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setLibrary(await ragApi.getLibrary(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load library");
    }
  }, [id]);

  const indexing = library?.documents.some((d) => d.status === "queued" || d.status === "indexing") ?? false;
  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    const interval = indexing ? window.setInterval(load, 1500) : undefined;
    return () => {
      window.clearTimeout(timer);
      if (interval) window.clearInterval(interval);
    };
  }, [load, indexing]);

  async function upload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      await ragApi.uploadDocuments(id, Array.from(files));
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function addUrl(event: FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    try {
      await ragApi.addUrl(id, url.trim(), "");
      setUrl("");
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add URL");
    } finally {
      setBusy(false);
    }
  }

  async function removeDocument(documentId: string) {
    try {
      await ragApi.deleteDocument(id, documentId);
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    try {
      setHits(await ragApi.searchLibrary(id, query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  if (!library) return <section className="card">{error ?? "Loading…"}</section>;
  return (
    <section className="card" aria-labelledby="library-detail">
      <div className="card-title">
        <h2 id="library-detail">{library.name}</h2>
        <span className="badge">{library.embedding} embeddings</span>
      </div>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      <div className="field">
        <label htmlFor="doc-upload">Add documents</label>
        <input id="doc-upload" ref={input} type="file" multiple accept={ACCEPT} onChange={(e) => void upload(e.target.files)} disabled={busy} className="input" />
        <span className="hint">PDF, Word (.docx), EPUB, Markdown, text, HTML, CSV, JSON. Several files at once are fine.</span>
      </div>
      <form onSubmit={addUrl} className="field">
        <label htmlFor="doc-url">Add a web page or online PDF</label>
        <div className="btn-row">
          <input id="doc-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" className="input" style={{ flex: 1, minWidth: 200 }} />
          <button type="submit" className="btn" disabled={busy}>
            Add URL
          </button>
        </div>
      </form>
      <h3>Documents ({library.documents.length})</h3>
      {library.documents.length === 0 && <p className="muted">No documents yet.</p>}
      <div className="outputs">
        {library.documents.map((document) => (
          <div className="output" key={document.id}>
            <div className="meta">
              <strong title={document.source_url ?? document.name}>{document.name}</strong>
              <span className="muted small">
                {document.kind === "url" ? "web" : formatBytes(document.size_bytes)} · {document.status === "ready" ? `${document.chunk_count} chunks` : document.status}
                {document.error ? ` · ${document.error}` : ""}
              </span>
            </div>
            <div className="btn-row">
              <span className={`badge ${document.status === "ready" ? "ok" : document.status === "failed" ? "fail" : "busy"}`}>{document.status}</span>
              {document.status === "failed" && (
                <button type="button" className="btn sm" onClick={() => void ragApi.reindexDocument(id, document.id).then(load)}>
                  Retry
                </button>
              )}
              <button type="button" className="btn sm danger" onClick={() => void removeDocument(document.id)} aria-label={`Delete ${document.name}`}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={search} className="field" style={{ marginTop: "1rem" }}>
        <label htmlFor="lib-search">Test a search</label>
        <div className="btn-row">
          <input id="lib-search" type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask something the documents should answer" className="input" style={{ flex: 1, minWidth: 200 }} />
          <button type="submit" className="btn">
            Search
          </button>
        </div>
      </form>
      {hits && hits.length === 0 && <p className="muted">No matches.</p>}
      {hits &&
        hits.map((hit, index) => (
          <div key={`${hit.document_id}-${hit.chunk_index}-${index}`} className="proposal" style={{ gridTemplateColumns: "1fr auto", marginBottom: 6 }}>
            <span className="text">
              <strong>{hit.document_name}</strong>
              <span style={{ whiteSpace: "normal", display: "block" }}>{hit.text.slice(0, 300)}</span>
            </span>
            <span className="badge">{Math.round(hit.score * 100)}%</span>
          </div>
        ))}
    </section>
  );
}

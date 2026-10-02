import { useState, type FormEvent } from "react";
import { episodesApi } from "../api/episodes";
import type { ProcessingJob } from "../api/types";

/** Import from a link (YouTube, Vimeo, podcast page, direct media URL) or from a file path on the server machine. */
export function LinkImportPanel({ projectId, onCreated }: { projectId: string | null; onCreated: (job: ProcessingJob) => void }) {
  const [url, setUrl] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState<"url" | "path" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitUrl(event: FormEvent) {
    event.preventDefault();
    setBusy("url");
    setError(null);
    try {
      onCreated(await episodesApi.importUrl(url.trim(), projectId));
      setUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(null);
    }
  }

  async function submitPath(event: FormEvent) {
    event.preventDefault();
    setBusy("path");
    setError(null);
    try {
      onCreated(await episodesApi.importLocalPath(path.trim(), projectId));
      setPath("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="text-import">
      <form onSubmit={submitUrl} className="field">
        <label htmlFor="import-url">Link to a video, podcast or audio file</label>
        <div className="btn-row">
          <input id="import-url" type="url" required className="input" style={{ flex: 1, minWidth: 240 }} placeholder="https://www.youtube.com/watch?v=… · https://vimeo.com/… · https://example.com/show.mp3" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button type="submit" className="btn primary" disabled={busy !== null || !url.trim()}>
            {busy === "url" ? "Starting…" : "Import link"}
          </button>
        </div>
        <span className="hint">YouTube, Vimeo, SoundCloud, podcast pages and thousands of other sites, plus direct MP3/MP4 links. Only the audio stream is downloaded when the site offers one. Download progress appears on the episode page.</span>
      </form>
      <form onSubmit={submitPath} className="field" style={{ marginTop: 6 }}>
        <label htmlFor="import-path">Large file already on this computer (no upload)</label>
        <div className="btn-row">
          <input id="import-path" type="text" required className="input" style={{ flex: 1, minWidth: 240 }} placeholder="D:\Recordings\episode-14.mp4" value={path} onChange={(e) => setPath(e.target.value)} />
          <button type="submit" className="btn" disabled={busy !== null || !path.trim()}>
            {busy === "path" ? "Importing…" : "Import file"}
          </button>
        </div>
        <span className="hint">Best for multi-gigabyte videos: the file is read directly from disk by the server, which runs on this machine. Video containers (MP4, MOV, WEBM) are accepted; the audio track is extracted.</span>
      </form>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

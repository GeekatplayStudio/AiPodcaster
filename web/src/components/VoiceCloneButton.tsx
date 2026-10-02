import { useEffect, useState } from "react";
import { ragApi } from "../api/rag";

/** Creates a cloned voice from the episode's own recording when the speech provider supports it. */
export function VoiceCloneButton({ jobId, assetName }: { jobId: string; assetName: string }) {
  const [supported, setSupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(
      () =>
        void ragApi
          .catalog()
          .then((catalog) => setSupported(catalog.speech.some((p) => p.id === catalog.current_speech && p.supports_cloning && p.configured && p.id === "elevenlabs")))
          .catch(() => undefined),
      0,
    );
    return () => window.clearTimeout(timer);
  }, []);

  if (!supported) return null;

  async function clone() {
    const name = window.prompt("Name for the cloned voice", assetName.replace(/\.[^.]+$/, ""));
    if (!name) return;
    setBusy(true);
    try {
      const created = await ragApi.cloneVoice(jobId, name);
      setResult(`Voice “${created.name}” created (${created.voice_id}) and set as the default synthetic voice.`);
    } catch (err) {
      setResult(err instanceof Error ? err.message : "Cloning failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      <button type="button" className="btn" style={{ width: "100%" }} onClick={() => void clone()} disabled={busy}>
        {busy ? "Cloning…" : "Clone my voice from this recording"}
      </button>
      {result && <p className="hint">{result}</p>}
    </div>
  );
}

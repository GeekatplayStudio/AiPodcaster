import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ragApi } from "../api/rag";

/** Creates a cloned voice from the episode's own recording when the speech provider supports it. */
export function VoiceCloneButton({ jobId, assetName }: { jobId: string; assetName: string }) {
  const { t } = useTranslation("job");
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
    const name = window.prompt(t("Name for the cloned voice"), assetName.replace(/\.[^.]+$/, ""));
    if (!name) return;
    setBusy(true);
    try {
      const created = await ragApi.cloneVoice(jobId, name);
      setResult(t("Voice “{{name}}” created ({{id}}) and set as the default synthetic voice.", { name: created.name, id: created.voice_id }));
    } catch (err) {
      setResult(err instanceof Error ? err.message : t("Cloning failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      <button type="button" className="btn" style={{ width: "100%" }} onClick={() => void clone()} disabled={busy}>
        {busy ? t("Cloning…") : t("Clone my voice from this recording")}
      </button>
      {result && <p className="hint">{result}</p>}
    </div>
  );
}

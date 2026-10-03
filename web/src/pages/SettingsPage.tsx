import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { AppSettings, ProviderStatus } from "../api/types";
import { ApiAccessCard } from "../components/ApiAccessCard";
import { ProviderSettings } from "../components/ProviderSettings";
import { TargetsSettings } from "../components/TargetsSettings";

const WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3", "distil-large-v3"];

export function SettingsPage() {
  const { t } = useTranslation("settings");
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loaded, setLoaded] = useState<string>("");
  const dirty = settings !== null && loaded !== "" && JSON.stringify(settings) !== loaded;

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [status, setStatus] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((value) => {
        setSettings(value);
        setLoaded(JSON.stringify(value));
      })
      .catch((err: Error) => setStatus({ kind: "error", text: err.message }));
    api.providers().then(setProviders).catch(() => undefined);
  }, []);

  if (!settings) return status ? <div className={`alert ${status.kind}`}>{status.text}</div> : <p className="muted">{t("Loading settings…")}</p>;

  const s = settings;
  const patch = <K extends keyof AppSettings>(key: K, value: Partial<AppSettings[K]>) => setSettings({ ...s, [key]: { ...s[key], ...value } });

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      const saved = await api.saveSettings(s);
      setSettings(saved);
      setLoaded(JSON.stringify(saved));
      setProviders(await api.providers());
      setStatus({ kind: "success", text: t("Settings saved. New uploads will use them; existing jobs can be re-analysed.") });
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : t("Save failed") });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{t("Settings")}</h1>
          <p>{t("Choose which AI services do the work. Keys are stored on the server only and are never sent back to the browser.")}</p>
        </div>
        <button type="button" className="btn primary" onClick={() => void save()} disabled={saving}>
          {saving ? t("Saving…") : t("Save settings")}
        </button>
      </div>
      {dirty && (
        <div className="alert warn unsaved-bar">
          {t("Unsaved changes. Press “Save settings” to apply them; leaving this page discards them.")}
        </div>
      )}
      {status && (
        <div className={`alert ${status.kind}`} role="status">
          {status.text}
        </div>
      )}
      <section className="card" aria-labelledby="providers-title">
        <h2 id="providers-title">{t("Service status")}</h2>
        <div className="provider-grid">
          {providers.map((p) => (
            <div key={p.name} className={`provider${p.available ? " ok" : ""}`}>
              <span className="dot" aria-hidden="true" />
              <span>
                <strong>{p.name}</strong>
                <br />
                <span className="muted small">{p.detail}</span>
              </span>
            </div>
          ))}
        </div>
      </section>
      <div className="grid-2" style={{ marginTop: "1rem" }}>
        <section className="card" aria-labelledby="transcription-title">
          <h2 id="transcription-title">{t("Transcription")}</h2>
          <div className="field">
            <label htmlFor="tr-provider">{t("Provider")}</label>
            <select id="tr-provider" value={s.transcription.provider} onChange={(e) => patch("transcription", { provider: e.target.value as AppSettings["transcription"]["provider"] })}>
              <option value="faster_whisper">{t("Local Whisper (faster-whisper, private)")}</option>
              <option value="openai">{t("OpenAI transcription API")}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="tr-model">{t("Model")}</label>
            {s.transcription.provider === "faster_whisper" ? (
              <select id="tr-model" value={s.transcription.model} onChange={(e) => patch("transcription", { model: e.target.value })}>
                {WHISPER_MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <input id="tr-model" type="text" value={s.transcription.model} placeholder="whisper-1" onChange={(e) => patch("transcription", { model: e.target.value })} />
            )}
            <span className="hint">{t('Larger local models are more accurate but slower. "small" is a good default on GPU.')}</span>
          </div>
          <div className="field">
            <label htmlFor="tr-lang">{t("Language (optional)")}</label>
            <input id="tr-lang" type="text" value={s.transcription.language ?? ""} placeholder={t("auto-detect, e.g. en, ru, es")} maxLength={10} onChange={(e) => patch("transcription", { language: e.target.value.trim() || null })} />
            <span className="hint">{t("Leave empty to detect the language of every recording. Each episode can also override it on its own page.")}</span>
          </div>
          <div className="field">
            <label className="checkbox">
              <input type="checkbox" checked={s.transcription.verbatim} onChange={(e) => patch("transcription", { verbatim: e.target.checked })} /> {t("Verbatim transcription")}
            </label>
            <span className="hint">{t("Keeps hesitations such as “um”, “hmm”, “ээ”, “eeh” in the transcript (Whisper normally drops them) so they can be cleaned out of the audio.")}</span>
          </div>
        </section>
        <section className="card" aria-labelledby="cleanup-title">
          <h2 id="cleanup-title">{t("Cleanup rules")}</h2>
          {(
            [
              ["remove_profanity", "Flag profanity"],
              ["remove_fillers", "Flag filler words (um, uh, you know…)"],
              ["remove_repeats", "Flag repeated words and phrases"],
              ["tighten_silence", "Tighten long pauses"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="checkbox" style={{ marginBottom: 8 }}>
              <input type="checkbox" checked={s.cleanup[key]} onChange={(e) => patch("cleanup", { [key]: e.target.checked })} />
              {t(label)}
            </label>
          ))}
          <div className="grid-2" style={{ marginTop: 8 }}>
            <div className="field">
              <label htmlFor="max-pause">{t("Pause longer than (ms)")}</label>
              <input id="max-pause" type="number" min={300} max={10000} step={100} value={s.cleanup.max_pause_ms} onChange={(e) => patch("cleanup", { max_pause_ms: Number(e.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="keep-pause">{t("…shorten to (ms)")}</label>
              <input id="keep-pause" type="number" min={100} max={2000} step={50} value={s.cleanup.keep_pause_ms} onChange={(e) => patch("cleanup", { keep_pause_ms: Number(e.target.value) })} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="bad-words">{t("Extra words to remove (comma separated)")}</label>
            <input id="bad-words" type="text" value={s.cleanup.extra_bad_words.join(", ")} onChange={(e) => patch("cleanup", { extra_bad_words: splitList(e.target.value) })} />
          </div>
          <div className="field">
            <label htmlFor="filler-words">{t("Extra filler words")}</label>
            <input id="filler-words" type="text" value={s.cleanup.extra_filler_words.join(", ")} onChange={(e) => patch("cleanup", { extra_filler_words: splitList(e.target.value) })} />
          </div>
          <div className="field">
            <label htmlFor="lufs">{t("Target loudness (LUFS)")}</label>
            <input id="lufs" type="number" min={-30} max={-8} step={0.5} value={s.cleanup.target_lufs} onChange={(e) => patch("cleanup", { target_lufs: Number(e.target.value) })} />
            <span className="hint">{t("-16 LUFS stereo / -19 mono is the common podcast target; Apple and Spotify accept -16.")}</span>
          </div>
        </section>
        <ProviderSettings settings={s} patch={patch} onReload={() => void api.getSettings().then(setSettings)} />
        <section className="card" aria-labelledby="factcheck-settings">
          <h2 id="factcheck-settings">{t("Fact checking")}</h2>
          <div className="field">
            <label htmlFor="emb-provider">{t("Embeddings for new libraries")}</label>
            <select id="emb-provider" value={s.fact_check.embedding_provider} onChange={(e) => patch("fact_check", { embedding_provider: e.target.value as AppSettings["fact_check"]["embedding_provider"] })}>
              <option value="local">{t("Local MiniLM (private, free)")}</option>
              <option value="openai">{t("OpenAI embeddings")}</option>
            </select>
            <span className="hint">{t("Existing libraries keep the embedding model they were created with.")}</span>
          </div>
          {s.fact_check.embedding_provider === "openai" && (
            <div className="field">
              <label htmlFor="emb-model">{t("Embedding model")}</label>
              <input id="emb-model" type="text" value={s.fact_check.embedding_model} onChange={(e) => patch("fact_check", { embedding_model: e.target.value })} />
            </div>
          )}
          <label className="checkbox" style={{ marginBottom: 8 }}>
            <input type="checkbox" checked={s.fact_check.online_enabled} onChange={(e) => patch("fact_check", { online_enabled: e.target.checked })} />
            {t("Allow online checks against Wikipedia")}
          </label>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="wiki-lang">{t("Wikipedia language")}</label>
              <input id="wiki-lang" type="text" value={s.fact_check.wikipedia_language} maxLength={10} onChange={(e) => patch("fact_check", { wikipedia_language: e.target.value.trim().toLowerCase() || "auto" })} />
              <span className="hint">{t("“auto” uses each episode's spoken language.")}</span>
            </div>
            <div className="field">
              <label htmlFor="max-claims">{t("Max claims per episode")}</label>
              <input id="max-claims" type="number" min={1} max={200} value={s.fact_check.max_claims} onChange={(e) => patch("fact_check", { max_claims: Number(e.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="evidence-k">{t("Evidence passages per claim")}</label>
              <input id="evidence-k" type="number" min={1} max={10} value={s.fact_check.evidence_per_claim} onChange={(e) => patch("fact_check", { evidence_per_claim: Number(e.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="min-sim">{t("Minimum relevance (0-1)")}</label>
              <input id="min-sim" type="number" min={0} max={1} step={0.05} value={s.fact_check.min_similarity} onChange={(e) => patch("fact_check", { min_similarity: Number(e.target.value) })} />
            </div>
          </div>
          <span className="hint">{t("Verdicts use the language model chosen under Show notes & chapters; without one a transparent number/keyword heuristic is used.")}</span>
        </section>
        <section className="card" aria-labelledby="keys-title">
          <h2 id="keys-title">{t("API keys")}</h2>
          <p className="muted small">{t("Leave a field untouched to keep the stored key. Clear it to remove the key.")}</p>
          {(
            [
              ["openai_api_key", "OpenAI API key"],
              ["anthropic_api_key", "Anthropic API key"],
              ["gemini_api_key", "Google Gemini API key"],
              ["elevenlabs_api_key", "ElevenLabs API key"],
              ["descript_api_key", "Descript API key"],
              ["custom_llm_api_key", "OpenAI-compatible server key"],
              ["custom_tts_api_key", "Custom speech endpoint key"],
            ] as const
          ).map(([key, label]) => (
            <div className="field" key={key}>
              <label htmlFor={key}>{t(label)}</label>
              <input id={key} type="password" autoComplete="off" value={s.keys[key]} onChange={(e) => patch("keys", { [key]: e.target.value })} />
            </div>
          ))}
        </section>
        <section className="card" aria-labelledby="images-title">
          <h2 id="images-title">{t("Episode artwork (AI images)")}</h2>
          <div className="field">
            <label htmlFor="img-provider">{t("Image provider")}</label>
            <select id="img-provider" value={s.images.provider} onChange={(e) => patch("images", { provider: e.target.value as AppSettings["images"]["provider"] })}>
              <option value="none">{t("Generated cover with title (offline)")}</option>
              <option value="openai">{t("OpenAI images (gpt-image-1 / DALL·E)")}</option>
            </select>
          </div>
          {s.images.provider === "openai" && (
            <div className="field">
              <label htmlFor="img-model">{t("Model")}</label>
              <input id="img-model" type="text" value={s.images.model} onChange={(e) => patch("images", { model: e.target.value })} />
            </div>
          )}
        </section>
        <TargetsSettings />
        <ApiAccessCard requireForUi={s.api.require_for_ui} onRequireForUi={(value) => patch("api", { require_for_ui: value })} />
      </div>
    </>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 200);
}

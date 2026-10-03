import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ragApi } from "../api/rag";
import type { AppSettings, LlmProviderId, LlmTestResult, ProviderCatalog, SpeechProviderId } from "../api/types";
import { OllamaCard } from "./OllamaCard";

interface Props {
  settings: AppSettings;
  patch: <K extends keyof AppSettings>(key: K, value: Partial<AppSettings[K]>) => void;
  onReload: () => void;
}

/** Language-model and speech provider sections of the Settings page. */
export function ProviderSettings({ settings: s, patch, onReload }: Props) {
  const { t } = useTranslation("settings");
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);
  const [test, setTest] = useState<LlmTestResult | { error: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => void ragApi.catalog().then(setCatalog).catch(() => undefined), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const llmInfo = catalog?.llm.find((p) => p.id === s.language_model.provider);
  const speechInfo = catalog?.speech.find((p) => p.id === s.speech.provider);

  async function runTest() {
    setTesting(true);
    setTest(null);
    try {
      setTest(await ragApi.testLlm());
    } catch (err) {
      setTest({ error: err instanceof Error ? err.message : t("Test failed") });
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <section className="card" aria-labelledby="llm-title">
        <h2 id="llm-title">{t("Language model")}</h2>
        <p className="muted small">{t("Used for show notes, chapters, claim extraction and fact-check verdicts.")}</p>
        <div className="field">
          <label htmlFor="llm-provider">{t("Provider")}</label>
          <select id="llm-provider" value={s.language_model.provider} onChange={(e) => patch("language_model", { provider: e.target.value as LlmProviderId, model: "", base_url: "" })}>
            {(catalog?.llm ?? [{ id: "none", label: t("Built-in heuristics (offline)"), configured: true }]).map((p) => (
              <option key={p.id} value={p.id}>
                {"configured" in p && !p.configured && p.id !== "none" ? t("{{label}} (key missing)", { label: p.label }) : p.label}
              </option>
            ))}
          </select>
          {llmInfo?.notes && <span className="hint">{llmInfo.notes}</span>}
        </div>
        {s.language_model.provider !== "none" && (
          <>
            <div className="grid-2">
              <div className="field">
                <label htmlFor="llm-model">{t("Model")}</label>
                <input id="llm-model" type="text" value={s.language_model.model} placeholder={llmInfo?.default_model || (s.language_model.provider === "ollama" ? t("choose below") : t("model id"))} onChange={(e) => patch("language_model", { model: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="llm-temp">{t("Temperature")}</label>
                <input id="llm-temp" type="number" min={0} max={2} step={0.1} value={s.language_model.temperature} onChange={(e) => patch("language_model", { temperature: Number(e.target.value) })} />
              </div>
            </div>
            {(s.language_model.provider === "openai_compatible" || s.language_model.provider === "ollama" || s.language_model.base_url) && (
              <div className="field">
                <label htmlFor="llm-base">{t("Base URL")}</label>
                <input id="llm-base" type="text" value={s.language_model.base_url} placeholder={llmInfo?.default_base_url} onChange={(e) => patch("language_model", { base_url: e.target.value.trim() })} />
              </div>
            )}
            <div className="btn-row">
              <button type="button" className="btn" onClick={() => void runTest()} disabled={testing}>
                {testing ? t("Testing…") : t("Test connection (uses saved settings)")}
              </button>
              {test && "error" in test && <span className="badge fail">{test.error}</span>}
              {test && "ok" in test && (
                <span className={`badge ${test.ok ? "ok" : "review"}`}>
                  {test.ok
                    ? t("{{provider}}/{{model}} · {{latency}} ms · JSON ok", { provider: test.provider, model: test.model, latency: test.latency_ms })
                    : t("{{provider}}/{{model}} · {{latency}} ms · unexpected reply", { provider: test.provider, model: test.model, latency: test.latency_ms })}
                </span>
              )}
            </div>
            {s.language_model.provider === "ollama" && (
              <OllamaCard
                currentModel={s.language_model.model}
                onModelChosen={() => {
                  onReload();
                }}
              />
            )}
          </>
        )}
      </section>

      <section className="card" aria-labelledby="tts-title">
        <h2 id="tts-title">{t("Synthetic voice & voice cloning")}</h2>
        <div className="field">
          <label htmlFor="tts-provider">{t("Speech provider")}</label>
          <select id="tts-provider" value={s.speech.provider} onChange={(e) => patch("speech", { provider: e.target.value as SpeechProviderId, model: "", base_url: "" })}>
            {(catalog?.speech ?? [{ id: "none", label: t("Disabled"), configured: true }]).map((p) => (
              <option key={p.id} value={p.id}>
                {"configured" in p && !p.configured && p.id !== "none" ? t("{{label}} (key missing)", { label: p.label }) : p.label}
              </option>
            ))}
          </select>
          {speechInfo?.notes && <span className="hint">{speechInfo.notes}</span>}
        </div>
        {s.speech.provider !== "none" && (
          <>
            <div className="grid-2">
              <div className="field">
                <label htmlFor="tts-voice">{t("Voice / voice id")}</label>
                <input id="tts-voice" type="text" value={s.speech.voice} onChange={(e) => patch("speech", { voice: e.target.value })} />
                {speechInfo?.supports_cloning && <span className="hint">{t("Clone your own voice from an episode page (“Clone my voice”). The new voice id is filled in here automatically.")}</span>}
              </div>
              <div className="field">
                <label htmlFor="tts-model">{t("Model (optional)")}</label>
                <input id="tts-model" type="text" value={s.speech.model} placeholder={speechInfo?.default_model} onChange={(e) => patch("speech", { model: e.target.value })} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="tts-base">{s.speech.provider === "custom_http" ? t("Endpoint URL") : t("Base URL (optional)")}</label>
              <input id="tts-base" type="text" value={s.speech.base_url} placeholder={speechInfo?.default_base_url} onChange={(e) => patch("speech", { base_url: e.target.value.trim() })} />
            </div>
            {s.speech.provider === "custom_http" && (
              <>
                <div className="field">
                  <label htmlFor="tts-template">{t("JSON body template")}</label>
                  <textarea id="tts-template" value={s.speech.custom_body_template} onChange={(e) => patch("speech", { custom_body_template: e.target.value })} />
                  <span className="hint">{t("Placeholders: {text}, {voice}, {model}. The endpoint must return audio bytes.")}</span>
                </div>
                <div className="field">
                  <label htmlFor="tts-auth">{t("Auth header template")}</label>
                  <input id="tts-auth" type="text" value={s.speech.custom_auth_header} onChange={(e) => patch("speech", { custom_auth_header: e.target.value })} />
                  <span className="hint">{t("For example “Authorization: Bearer {key}” or “x-api-key: {key}”.")}</span>
                </div>
              </>
            )}
          </>
        )}
      </section>
    </>
  );
}

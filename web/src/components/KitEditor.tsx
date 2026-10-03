import { useState } from "react";
import { useTranslation } from "react-i18next";
import { episodesApi } from "../api/episodes";
import type { PublishKit } from "../api/types";
import { useAutosave } from "../lib/autosave";
import { AutosaveStatus } from "./AutosaveStatus";

const NETWORKS = ["x", "linkedin", "instagram", "threads"];

export function KitEditor({ jobId, kit, onSave, saving }: { jobId: string; kit: PublishKit; onSave: (kit: PublishKit) => void; saving: boolean }) {
  const { t } = useTranslation("insights");
  const [draft, setDraft] = useState<PublishKit>(kit);
  const [source, setSource] = useState<PublishKit>(kit);
  if (source !== kit) {
    // Parent delivered a new kit (generated or saved): reset the draft during render.
    setSource(kit);
    setDraft(kit);
  }
  // Autosave drafts without pushing them back into the parent, so typing is never interrupted.
  const saveState = useAutosave(draft, (value) => episodesApi.saveKit(jobId, value), { baseline: kit, enabled: !saving, delay: 1200 });
  const set = <K extends keyof PublishKit>(key: K, value: PublishKit[K]) => setDraft({ ...draft, [key]: value });
  const list = (value: string) =>
    value
      .split(/[,\s]+/)
      .map((item) => item.replace(/^#/, "").trim())
      .filter(Boolean)
      .slice(0, 40);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <section className="card" aria-labelledby="kit-title">
      <div className="card-title">
        <h2 id="kit-title">{t("Episode copy")}</h2>
        <AutosaveStatus state={saveState} />
        <button type="button" className="btn primary" onClick={() => onSave(draft)} disabled={saving}>
          {saving ? t("Saving…") : t("Save copy")}
        </button>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="kit-title-input">{t("Title")}</label>
          <input id="kit-title-input" type="text" maxLength={200} value={draft.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="kit-subtitle">{t("Subtitle")}</label>
          <input id="kit-subtitle" type="text" maxLength={300} value={draft.subtitle} onChange={(e) => set("subtitle", e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="kit-short">{t("Short description ({{length}}/600)", { length: draft.short_description.length })}</label>
        <textarea id="kit-short" maxLength={600} value={draft.short_description} onChange={(e) => set("short_description", e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="kit-long">{t("Long description / show notes")}</label>
        <textarea id="kit-long" maxLength={8000} style={{ minHeight: 160 }} value={draft.long_description} onChange={(e) => set("long_description", e.target.value)} />
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="kit-hashtags">{t("Hashtags")}</label>
          <input id="kit-hashtags" type="text" value={draft.hashtags.map((h) => `#${h}`).join(" ")} onChange={(e) => set("hashtags", list(e.target.value))} />
        </div>
        <div className="field">
          <label htmlFor="kit-keywords">{t("Keywords")}</label>
          <input id="kit-keywords" type="text" value={draft.keywords.join(", ")} onChange={(e) => set("keywords", list(e.target.value))} />
        </div>
      </div>
      <div className="grid-3">
        <div className="field">
          <label htmlFor="kit-season">{t("Season")}</label>
          <input id="kit-season" type="number" min={0} value={draft.season_number ?? ""} onChange={(e) => set("season_number", e.target.value === "" ? null : Number(e.target.value))} />
        </div>
        <div className="field">
          <label htmlFor="kit-episode">{t("Episode #")}</label>
          <input id="kit-episode" type="number" min={0} value={draft.episode_number ?? ""} onChange={(e) => set("episode_number", e.target.value === "" ? null : Number(e.target.value))} />
        </div>
        <div className="field">
          <label htmlFor="kit-category">{t("Category")}</label>
          <input id="kit-category" type="text" maxLength={100} value={draft.category} onChange={(e) => set("category", e.target.value)} />
        </div>
      </div>
      <label className="checkbox" style={{ marginBottom: 12 }}>
        <input type="checkbox" checked={draft.explicit} onChange={(e) => set("explicit", e.target.checked)} /> {t("Explicit content")}
      </label>
      <h3>{t("Social posts")}</h3>
      {NETWORKS.map((network) => (
        <div className="field" key={network}>
          <label htmlFor={`kit-social-${network}`}>
            {network === "x" ? "X / Twitter" : network.charAt(0).toUpperCase() + network.slice(1)} ({(draft.social_posts[network] ?? "").length}
            {network === "x" ? "/280" : ""})
          </label>
          <div className="btn-row" style={{ alignItems: "stretch" }}>
            <textarea id={`kit-social-${network}`} style={{ flex: 1, minHeight: 70 }} value={draft.social_posts[network] ?? ""} onChange={(e) => set("social_posts", { ...draft.social_posts, [network]: e.target.value })} />
            <button type="button" className="btn sm" onClick={() => void copy(draft.social_posts[network] ?? "")} aria-label={t("Copy {{network}} post", { network })}>
              {t("Copy")}
            </button>
          </div>
        </div>
      ))}
      <div className="field">
        <label htmlFor="kit-youtube">{t("YouTube description")}</label>
        <div className="btn-row" style={{ alignItems: "stretch" }}>
          <textarea id="kit-youtube" style={{ flex: 1, minHeight: 120 }} maxLength={5000} value={draft.youtube_description} onChange={(e) => set("youtube_description", e.target.value)} />
          <button type="button" className="btn sm" onClick={() => void copy(draft.youtube_description)}>
            {t("Copy")}
          </button>
        </div>
      </div>
    </section>
  );
}

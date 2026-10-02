import { useState } from "react";
import type { PublishKit } from "../api/types";

const NETWORKS = ["x", "linkedin", "instagram", "threads"];

export function KitEditor({ kit, onSave, saving }: { kit: PublishKit; onSave: (kit: PublishKit) => void; saving: boolean }) {
  const [draft, setDraft] = useState<PublishKit>(kit);
  const [source, setSource] = useState<PublishKit>(kit);
  if (source !== kit) {
    // Parent delivered a new kit (generated or saved): reset the draft during render.
    setSource(kit);
    setDraft(kit);
  }
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
        <h2 id="kit-title">Episode copy</h2>
        <button type="button" className="btn primary" onClick={() => onSave(draft)} disabled={saving}>
          {saving ? "Saving…" : "Save copy"}
        </button>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="kit-title-input">Title</label>
          <input id="kit-title-input" type="text" maxLength={200} value={draft.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="kit-subtitle">Subtitle</label>
          <input id="kit-subtitle" type="text" maxLength={300} value={draft.subtitle} onChange={(e) => set("subtitle", e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="kit-short">Short description ({draft.short_description.length}/600)</label>
        <textarea id="kit-short" maxLength={600} value={draft.short_description} onChange={(e) => set("short_description", e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="kit-long">Long description / show notes</label>
        <textarea id="kit-long" maxLength={8000} style={{ minHeight: 160 }} value={draft.long_description} onChange={(e) => set("long_description", e.target.value)} />
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="kit-hashtags">Hashtags</label>
          <input id="kit-hashtags" type="text" value={draft.hashtags.map((h) => `#${h}`).join(" ")} onChange={(e) => set("hashtags", list(e.target.value))} />
        </div>
        <div className="field">
          <label htmlFor="kit-keywords">Keywords</label>
          <input id="kit-keywords" type="text" value={draft.keywords.join(", ")} onChange={(e) => set("keywords", list(e.target.value))} />
        </div>
      </div>
      <div className="grid-3">
        <div className="field">
          <label htmlFor="kit-season">Season</label>
          <input id="kit-season" type="number" min={0} value={draft.season_number ?? ""} onChange={(e) => set("season_number", e.target.value === "" ? null : Number(e.target.value))} />
        </div>
        <div className="field">
          <label htmlFor="kit-episode">Episode #</label>
          <input id="kit-episode" type="number" min={0} value={draft.episode_number ?? ""} onChange={(e) => set("episode_number", e.target.value === "" ? null : Number(e.target.value))} />
        </div>
        <div className="field">
          <label htmlFor="kit-category">Category</label>
          <input id="kit-category" type="text" maxLength={100} value={draft.category} onChange={(e) => set("category", e.target.value)} />
        </div>
      </div>
      <label className="checkbox" style={{ marginBottom: 12 }}>
        <input type="checkbox" checked={draft.explicit} onChange={(e) => set("explicit", e.target.checked)} /> Explicit content
      </label>
      <h3>Social posts</h3>
      {NETWORKS.map((network) => (
        <div className="field" key={network}>
          <label htmlFor={`kit-social-${network}`}>
            {network === "x" ? "X / Twitter" : network.charAt(0).toUpperCase() + network.slice(1)} ({(draft.social_posts[network] ?? "").length}
            {network === "x" ? "/280" : ""})
          </label>
          <div className="btn-row" style={{ alignItems: "stretch" }}>
            <textarea id={`kit-social-${network}`} style={{ flex: 1, minHeight: 70 }} value={draft.social_posts[network] ?? ""} onChange={(e) => set("social_posts", { ...draft.social_posts, [network]: e.target.value })} />
            <button type="button" className="btn sm" onClick={() => void copy(draft.social_posts[network] ?? "")} aria-label={`Copy ${network} post`}>
              Copy
            </button>
          </div>
        </div>
      ))}
      <div className="field">
        <label htmlFor="kit-youtube">YouTube description</label>
        <div className="btn-row" style={{ alignItems: "stretch" }}>
          <textarea id="kit-youtube" style={{ flex: 1, minHeight: 120 }} maxLength={5000} value={draft.youtube_description} onChange={(e) => set("youtube_description", e.target.value)} />
          <button type="button" className="btn sm" onClick={() => void copy(draft.youtube_description)}>
            Copy
          </button>
        </div>
      </div>
    </section>
  );
}

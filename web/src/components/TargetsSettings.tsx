import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { episodesApi } from "../api/episodes";
import type { PublishTarget, TargetKind } from "../api/types";

/** Settings section: hosting services and website connectors used by the Publish page. */
export function TargetsSettings() {
  const { t } = useTranslation("settings");
  const [kinds, setKinds] = useState<TargetKind[]>([]);
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [editing, setEditing] = useState<PublishTarget | "new" | null>(null);
  const [form, setForm] = useState({ name: "", kind: "generic_webhook", config: {} as Record<string, string>, enabled: true });
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [k, t] = await Promise.all([episodesApi.publishCatalog(), episodesApi.listTargets()]);
      setKinds(k);
      setTargets(t);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Could not load publishing targets"));
    }
  }, [t]);

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const kind = kinds.find((k) => k.id === form.kind);

  function start(target: PublishTarget | "new") {
    setEditing(target);
    setForm(target === "new" ? { name: "", kind: "generic_webhook", config: {}, enabled: true } : { name: target.name, kind: target.kind, config: { ...target.config }, enabled: target.enabled });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      if (editing === "new") await episodesApi.createTarget(form);
      else if (editing) await episodesApi.updateTarget(editing.id, form);
      setEditing(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed"));
    }
  }

  async function remove(target: PublishTarget) {
    if (!window.confirm(t('Remove "{{name}}"?', { name: target.name }))) return;
    try {
      await episodesApi.deleteTarget(target.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Delete failed"));
    }
  }

  return (
    <section className="card" aria-labelledby="publishing-title">
      <div className="card-title">
        <h2 id="publishing-title">{t("Publishing services")}</h2>
        <button type="button" className="btn primary" onClick={() => start("new")}>
          {t("Add service")}
        </button>
      </div>
      <p className="muted small">{t("Connected services appear as Publish buttons on every episode. Credentials stay on the server.")}</p>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      <div className="outputs">
        {targets.map((target) => (
          <div className="output" key={target.id} style={{ alignItems: "flex-start" }}>
            <div className="meta" style={{ whiteSpace: "normal" }}>
              <strong>
                {target.name} <span className="badge">{kinds.find((k) => k.id === target.kind)?.label ?? target.kind}</span>
                {!target.enabled && <span className="badge fail">{t("disabled")}</span>}
              </strong>
              {target.last_result && <span className="muted small">{target.last_result}</span>}
            </div>
            <div className="btn-row">
              <button type="button" className="btn sm" onClick={() => start(target)}>
                {t("Edit")}
              </button>
              <button type="button" className="btn sm danger" onClick={() => void remove(target)}>
                {t("Remove")}
              </button>
            </div>
          </div>
        ))}
      </div>
      {editing && (
        <form onSubmit={save} style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="target-name">{t("Name")}</label>
              <input id="target-name" type="text" required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="target-kind">{t("Service")}</label>
              <select id="target-kind" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value, config: {} })} disabled={editing !== "new"}>
                {kinds.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.mode === "manual" ? t("{{label}} (manual)", { label: k.label }) : k.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {kind?.notes && <p className="hint">{kind.notes}</p>}
          {kind?.fields.map((field) => (
            <div className="field" key={field.name}>
              <label htmlFor={`target-${field.name}`}>
                {field.required ? field.label : t("{{label}} (optional)", { label: field.label })}
              </label>
              <input id={`target-${field.name}`} type={field.secret ? "password" : "text"} autoComplete="off" placeholder={field.placeholder} value={form.config[field.name] ?? ""} onChange={(e) => setForm({ ...form, config: { ...form.config, [field.name]: e.target.value } })} />
            </div>
          ))}
          <label className="checkbox" style={{ marginBottom: 10 }}>
            <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> {t("Enabled")}
          </label>
          <div className="btn-row">
            <button type="submit" className="btn primary">
              {t("Save service")}
            </button>
            <button type="button" className="btn" onClick={() => setEditing(null)}>
              {t("Cancel")}
            </button>
            {kind?.docs_url && (
              <a className="btn sm" href={kind.docs_url.startsWith("http") ? kind.docs_url : `https://github.com/`} target="_blank" rel="noreferrer">
                {t("Docs")}
              </a>
            )}
          </div>
        </form>
      )}
    </section>
  );
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { forgetPlace, lastPlace, relativeTime } from "../lib/session";

const SECTION_LABELS = { edit: "Edit & review", stats: "Statistics", publish: "Publish & export" } as const;

/** "Continue where you left off": the last episode screen the user worked on. */
export function ContinueCard({ existingIds }: { existingIds: string[] | null }) {
  const { t } = useTranslation("library");
  const [place, setPlace] = useState(lastPlace);
  if (!place) return null;
  const id = place.hash.split("/")[2];
  if (existingIds && !existingIds.includes(id)) return null;
  const ago = relativeTime(place.at);
  const when = ago.unit === "minute" ? t("{{count}} min ago", { count: ago.value }) : ago.unit === "hour" ? t("{{count}} h ago", { count: ago.value }) : t("{{count}} d ago", { count: ago.value });

  return (
    <section className="card continue-card" aria-label={t("Continue where you left off")}>
      <div>
        <strong>{t("Continue where you left off")}</strong>
        <div className="muted small">
          {place.title} · {t(SECTION_LABELS[place.section])} · {when}
        </div>
      </div>
      <div className="btn-row">
        <a className="btn primary" href={place.hash}>
          {t("Continue")}
        </a>
        <button
          type="button"
          className="btn sm"
          onClick={() => {
            forgetPlace();
            setPlace(null);
          }}
          aria-label={t("Dismiss")}
        >
          ×
        </button>
      </div>
    </section>
  );
}

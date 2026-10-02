export type JobTab = "edit" | "stats" | "publish";

export function JobTabs({ id, active }: { id: string; active: JobTab }) {
  const tabs: { key: JobTab; label: string; href: string }[] = [
    { key: "edit", label: "Edit & review", href: `#/jobs/${id}` },
    { key: "stats", label: "Statistics", href: `#/jobs/${id}/stats` },
    { key: "publish", label: "Publish & export", href: `#/jobs/${id}/publish` },
  ];
  return (
    <nav className="tabs" aria-label="Episode sections">
      {tabs.map((tab) => (
        <a key={tab.key} href={tab.href} className={`tab${tab.key === active ? " active" : ""}`} aria-current={tab.key === active ? "page" : undefined}>
          {tab.label}
        </a>
      ))}
      <a href="#/" className="tab" style={{ marginLeft: "auto" }}>
        ← All episodes
      </a>
    </nav>
  );
}

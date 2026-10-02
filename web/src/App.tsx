import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import { JobPage } from "./pages/JobPage";
import { LibrariesPage } from "./pages/LibrariesPage";
import { LibraryPage } from "./pages/LibraryPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { PublishPage } from "./pages/PublishPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatsPage } from "./pages/StatsPage";
import { ThemeMenu } from "./components/ThemeMenu";

export type Route =
  | { name: "library" }
  | { name: "job"; id: string }
  | { name: "stats"; id: string }
  | { name: "publish"; id: string }
  | { name: "settings" }
  | { name: "projects" }
  | { name: "libraries" };

export function parseHash(hash: string): Route {
  const clean = hash.replace(/^#\/?/, "");
  if (clean.startsWith("jobs/")) {
    const [id, section] = clean.slice(5).split("/");
    if (section === "stats") return { name: "stats", id };
    if (section === "publish") return { name: "publish", id };
    return { name: "job", id };
  }
  if (clean === "settings") return { name: "settings" };
  if (clean === "projects") return { name: "projects" };
  if (clean === "libraries") return { name: "libraries" };
  return { name: "library" };
}

export function routeHash(route: Route): string {
  if (route.name === "job") return `#/jobs/${route.id}`;
  if (route.name === "stats") return `#/jobs/${route.id}/stats`;
  if (route.name === "publish") return `#/jobs/${route.id}/publish`;
  if (route.name === "settings") return "#/settings";
  if (route.name === "projects") return "#/projects";
  if (route.name === "libraries") return "#/libraries";
  return "#/";
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((next: Route) => {
    window.location.hash = routeHash(next);
  }, []);
  return [route, navigate];
}

function useApiHealth(): boolean | null {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    const check = () =>
      api
        .health()
        .then(() => !cancelled && setOk(true))
        .catch(() => !cancelled && setOk(false));
    check();
    const timer = window.setInterval(check, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);
  return ok;
}

export function App() {
  const [route, navigate] = useRoute();
  const apiOk = useApiHealth();

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/" aria-label="AiPodcaster home">
          <img src="/favicon.svg" alt="" />
          AiPodcaster
        </a>
        <span className={`api-status${apiOk ? " ok" : ""}`} role="status">
          {apiOk === null ? "Connecting to API…" : apiOk ? "API online" : "API offline – start the backend"}
        </span>
        <nav className="nav" aria-label="Primary">
          <button type="button" aria-current={["library", "job", "stats", "publish"].includes(route.name) ? "page" : undefined} onClick={() => navigate({ name: "library" })}>
            Episodes
          </button>
          <button type="button" aria-current={route.name === "projects" ? "page" : undefined} onClick={() => navigate({ name: "projects" })}>
            Projects
          </button>
          <button type="button" aria-current={route.name === "libraries" ? "page" : undefined} onClick={() => navigate({ name: "libraries" })}>
            Libraries
          </button>
          <button type="button" aria-current={route.name === "settings" ? "page" : undefined} onClick={() => navigate({ name: "settings" })}>
            Settings
          </button>
        </nav>
        <ThemeMenu />
      </header>
      <main className="page">
        {route.name === "library" && <LibraryPage onOpen={(id) => navigate({ name: "job", id })} />}
        {route.name === "job" && <JobPage id={route.id} onBack={() => navigate({ name: "library" })} />}
        {route.name === "stats" && <StatsPage id={route.id} />}
        {route.name === "publish" && <PublishPage id={route.id} />}
        {route.name === "settings" && <SettingsPage />}
        {route.name === "projects" && <ProjectsPage />}
        {route.name === "libraries" && <LibrariesPage />}
      </main>
      <footer className="footer">
        <span>AiPodcaster</span>
        <span>
          by <a href="https://www.geekatplay.com" target="_blank" rel="noreferrer">Geekatplay Studio</a> · Vladimir Chopine
        </span>
        <a href="https://github.com/GeekatplayStudio/AiPodcaster" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </footer>
    </div>
  );
}

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App, parseHash, routeHash } from "./App";

describe("routing", () => {
  it("parses and builds hashes", () => {
    expect(parseHash("")).toEqual({ name: "library" });
    expect(parseHash("#/settings")).toEqual({ name: "settings" });
    expect(parseHash("#/jobs/abc")).toEqual({ name: "job", id: "abc" });
    expect(routeHash({ name: "job", id: "x" })).toBe("#/jobs/x");
  });
});

describe("App", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the library and API status", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/healthz")) return new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.includes("/v1/jobs") || url.includes("/v1/projects")) return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
      return new Response("{}", { status: 404 });
    });
    window.location.hash = "";
    render(<App />);
    expect(screen.getByRole("heading", { name: "Episodes" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("API online"));
    await waitFor(() => expect(screen.getByText(/No episodes yet/)).toBeInTheDocument());
  });
});

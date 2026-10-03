import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "../i18n";

// jsdom has no layout engine; scroll restoration is exercised in the browser tests.
window.scrollTo = (() => undefined) as typeof window.scrollTo;

afterEach(() => cleanup());

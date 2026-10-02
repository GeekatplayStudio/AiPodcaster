/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = process.env.AIPODCASTER_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // Loopback only. Browsers fall back from ::1 to 127.0.0.1 automatically; a 404 on
    // http://localhost:5173 means another process owns the IPv6 side of the port.
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
  preview: { port: 5173 },
  build: { sourcemap: false, target: "es2022" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: { provider: "v8", include: ["src/**"], exclude: ["src/test/**", "src/main.tsx"] },
  },
});

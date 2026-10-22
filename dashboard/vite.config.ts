import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The dashboard talks to the backend through /api (HTTP + WebSocket) so no CORS is needed.
const backend = process.env.PROMETHEUS_BACKEND ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": { target: backend, changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});

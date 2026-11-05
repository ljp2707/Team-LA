import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development, send API and sign in requests to the FastAPI server. This uses
// 127.0.0.1 because "localhost" can reach a different program using port 8000.
// API_PROXY lets a second copy of the app run against a backend on another port.
const api = process.env.API_PROXY ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": api,
      "/auth": api,
    },
  },
});

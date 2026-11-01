import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development, send API and sign in requests to the FastAPI server. This uses
// 127.0.0.1 because "localhost" can reach a different program using port 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
    },
  },
});

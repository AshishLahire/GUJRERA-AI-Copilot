import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Override with PRAMAAN_UI_PORT when 5173 is taken (scripts/run_gujrera.ps1 picks a free one).
    port: Number(process.env.PRAMAAN_UI_PORT ?? 5173),
    strictPort: true,
    proxy: {
      "/api": {
        // Override with PRAMAAN_API when port 8000 is taken by another backend.
        target: process.env.PRAMAAN_API ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});

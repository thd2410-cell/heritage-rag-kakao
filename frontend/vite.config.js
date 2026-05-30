import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// React + 개발 서버(포트 5173). 백엔드는 http://localhost:8000 (CORS 개방됨).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
  },
});

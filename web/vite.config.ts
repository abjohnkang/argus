import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// SPEC-UI-001: base '/' so the bundle is served from the api-served root.
// Dev-only proxy forwards /v1 and /health to the local FastAPI api on :8000,
// so `vite dev` matches production same-origin behavior (no CORS, the
// LocalhostOnlyMiddleware passes cleanly) without shipping anything to prod.
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: {
      '/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});

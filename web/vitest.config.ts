import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Separate Vitest config so the dev-server proxy in vite.config.ts is not
// pulled into the test environment. jsdom + global test APIs + RTL setup.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary'],
      include: ['src/lib/**', 'src/components/**'],
      exclude: [
        'src/test/**',
        'src/main.tsx',
        '**/*.d.ts',
        '**/*.test.{ts,tsx}',
        'src/lib/types.ts',
      ],
    },
  },
});

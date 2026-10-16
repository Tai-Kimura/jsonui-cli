import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';

/**
 * The host is a production build (`vite build`), so every `process.env.NODE_ENV`
 * gate is closed — the screen markers among them, which the suite does not use.
 * The test bridge (rjui's generated `jsonuiTestBridge`) is behind the same gate,
 * and the TestBridge fixtures (INTERACTIVE_HOST_CONTRACT.md §6) need it open:
 * a UI test runs against a build with the gate open. Opened for that one
 * generated module only, before Vite's own define folds it, so nothing else
 * in the build changes.
 */
function openTestBridgeGate(): Plugin {
  return {
    name: 'conformance-open-test-bridge-gate',
    enforce: 'pre',
    transform(code, id) {
      if (!/[\\/]src[\\/]generated[\\/]jsonuiTestBridge\.ts$/.test(id)) return null;
      const opened = code.split('process.env.NODE_ENV').join('"development"');
      if (opened === code) {
        this.error('jsonuiTestBridge.ts has no process.env.NODE_ENV gate to open — the helper changed shape');
      }
      return { code: opened, map: null };
    },
  };
}

export default defineConfig({
  plugins: [openTestBridgeGate(), react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    // 500 fixture components; chunk warnings are just noise here.
    chunkSizeWarningLimit: 4096,
  },
});

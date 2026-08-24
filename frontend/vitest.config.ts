import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import path from "node:path";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [{ find: "@", replacement: path.dirname(fileURLToPath(import.meta.url)) }],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});

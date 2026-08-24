import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [{ find: "@", replacement: "/Users/manti/publisher-intelligence/frontend/" }],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});

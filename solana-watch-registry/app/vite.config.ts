import { defineConfig } from "vitest/config";

export default defineConfig({
  server: { host: "127.0.0.1", port: 4178, strictPort: true },
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});

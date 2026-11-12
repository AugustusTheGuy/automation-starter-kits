import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4178 --strictPort",
    port: 4178,
    reuseExistingServer: false,
  },
  use: {
    baseURL: "http://127.0.0.1:4178",
    channel: "chrome",
  },
});

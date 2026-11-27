import os from "node:os";
import path from "node:path";

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./frontend/e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: "list",
  outputDir: path.join(os.tmpdir(), "travelmate-playwright-results"),
  use: {
    baseURL: "http://127.0.0.1:5501",
    channel: "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: [
    {
      command: "python -m http.server 5501 --bind 127.0.0.1",
      url: "http://127.0.0.1:5501/pages/home.html",
      reuseExistingServer: true,
      timeout: 120_000
    },
    {
      command: ".venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      cwd: "backend",
      env: { TRAVELMATE_LLM_PROVIDER: "local" },
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 120_000
    }
  ]
});

import os from "node:os";
import path from "node:path";
import fs from "node:fs";

import { defineConfig } from "@playwright/test";

const venvPython = process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python";
const python = process.env.TRAVELMATE_TEST_PYTHON || (fs.existsSync(path.join("backend", venvPython)) ? venvPython : "python");

export default defineConfig({
  testDir: "./frontend/e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: "list",
  outputDir: path.join(os.tmpdir(), "travelmate-playwright-results"),
  use: {
    baseURL: "http://127.0.0.1:5501",
    ...(process.env.TRAVELMATE_TEST_BROWSER ? { launchOptions: { executablePath: process.env.TRAVELMATE_TEST_BROWSER } } : {}),
    trace: "retain-on-failure",
    screenshot: process.env.TRAVELMATE_TEST_SCREENSHOTS ? "on" : "only-on-failure"
  },
  webServer: [
    {
      command: "python -m http.server 5501 --bind 127.0.0.1",
      url: "http://127.0.0.1:5501/pages/home.html",
      reuseExistingServer: true,
      timeout: 120_000
    },
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: "backend",
      env: { TRAVELMATE_LLM_PROVIDER: "local", TRAVELMATE_EMBEDDING_PROVIDER: "hash", TRAVELMATE_VECTOR_BACKEND: "json", TRAVELMATE_DB_PATH: ":memory:" },
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 120_000
    }
  ]
});

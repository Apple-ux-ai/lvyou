import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./frontend/tests/setup.js"],
    include: ["frontend/tests/**/*.test.{js,jsx}"]
  }
});

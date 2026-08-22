import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const pagesRoot = path.join(process.cwd(), "pages");
const interactivePages = ["home.html", "assistant.html", "planner.html", "profile.html"];

describe("GitHub Pages frontend assets", () => {
  it.each(interactivePages)("uses deployable CDN runtimes in %s", (pageName) => {
    const source = fs.readFileSync(path.join(pagesRoot, pageName), "utf8");

    expect(source).not.toMatch(/src="\.\.\/node_modules\//);
    expect(source).toContain("https://unpkg.com/react@18/umd/react.development.js");
    expect(source).toContain("https://unpkg.com/react-dom@18/umd/react-dom.development.js");
    expect(source).toContain("https://unpkg.com/@babel/standalone/babel.min.js");
  });
});

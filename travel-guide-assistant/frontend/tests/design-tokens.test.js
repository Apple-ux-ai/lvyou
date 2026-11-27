import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const testRoot = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(testRoot, "../..");
const pagesRoot = path.join(projectRoot, "pages");
const forbiddenTokens = /--(?:secondary|secondary-foreground|accent|accent-foreground|sidebar-accent|sidebar-accent-foreground|google-color-secondary|google-color-secondary-foreground|google-color-accent|google-color-accent-foreground|google-radius-xl)\b/;

test("all static pages share the external theme token file", () => {
  const pages = fs.readdirSync(pagesRoot).filter((name) => name.endsWith(".html"));
  expect(pages).toHaveLength(14);

  for (const page of pages) {
    const source = fs.readFileSync(path.join(pagesRoot, page), "utf8");
    expect(source).toContain('<link rel="stylesheet" href="../shared/theme.css">');
    expect(source).not.toContain('<style id="theme-vars">');
    expect(source).not.toContain('type="text/tailwindcss"');
    expect(source).not.toContain('semantic-token-fallback');
    expect(source).not.toMatch(/lucide(?:\.min)?\.js/);
    expect(source).not.toMatch(forbiddenTokens);
  }

  const theme = fs.readFileSync(path.join(projectRoot, "shared/theme.css"), "utf8");
  expect(theme).not.toMatch(forbiddenTokens);
  expect(theme).toContain("color-scheme: light");
  expect(theme).toContain("color-scheme: dark");
  expect(theme).toMatch(/select option\s*\{[\s\S]*background:\s*var\(--popover\)/);
  expect(theme).toContain("scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track)");
  expect(theme).toContain("::-webkit-scrollbar-thumb");
  expect(theme).toContain("/* Shared utility classes used by the static page shell. */");
  expect(theme).toContain("/* Shared page utility helpers. */");
  expect(theme).toContain(".topbar-left");
  expect(theme).toContain(".topbar-right");
  expect(theme).toContain(".icon-btn");
  expect(theme).toContain(".avatar");
  expect(theme).toContain(".brand");

  for (const page of pages) {
    const source = fs.readFileSync(path.join(pagesRoot, page), "utf8");
    expect(source).not.toContain(".topbar-left{display:flex;align-items:center;gap:calc(var(--spacing)*6)}");
    expect(source).not.toContain(".topbar-right{display:flex;align-items:center;gap:calc(var(--spacing)*3)}");
  }

  for (const page of pages) {
    const source = fs.readFileSync(path.join(pagesRoot, page), "utf8");
    expect(source).not.toContain(".icon-btn{width:40px;height:40px;display:grid;place-items:center;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);color:var(--foreground);cursor:pointer;transition:background .2s}");
    expect(source).not.toContain(".icon-btn:hover{background:var(--primary-soft)}");
    expect(source).not.toContain(".brand{display:flex;align-items:center;gap:calc(var(--spacing)*3);text-decoration:none;color:var(--foreground)}");
  }

  for (const selector of [":root", ".dark"]) {
    const block = theme.match(new RegExp(`${selector.replace(".", "\\.")}\\s*\\{([\\s\\S]*?)\\n\\}`));
    expect(block).not.toBeNull();
    for (const token of ["primary", "muted", "muted-foreground"]) {
      expect(block[1].match(new RegExp(`--${token}:`, "g")) || []).toHaveLength(1);
    }
  }

  const sourceTokens = fs.readFileSync(path.join(projectRoot, "colors_and_type.css"), "utf8");
  expect(sourceTokens).not.toMatch(forbiddenTokens);
});

import path from "node:path";
import { expect, test as base } from "@playwright/test";

// Keep the browser tests independent of CDN reachability, using locked packages.
export const test = base.extend({
  page: async ({ page }, use) => {
    const localAssets = [
      [/^https:\/\/unpkg\.com\/react@18\/umd\/react\.development\.js$/, "react/umd/react.development.js"],
      [/^https:\/\/unpkg\.com\/react-dom@18\/umd\/react-dom\.development\.js$/, "react-dom/umd/react-dom.development.js"],
      [/^https:\/\/unpkg\.com\/@babel\/standalone\/babel\.min\.js$/, "@babel/standalone/babel.min.js"]
    ];
    for (const [url, file] of localAssets) {
      await page.route(url, (route) => route.fulfill({
        path: path.resolve("node_modules", file),
        contentType: "application/javascript"
      }));
    }
    await page.route("https://images.unsplash.com/**", (route) => route.abort());
    await use(page);
  }
});
export { expect };

import fs from "node:fs";
import path from "node:path";

import { describe, expect, test } from "vitest";

const source = fs.readFileSync(path.join(process.cwd(), "pages", "profile.html"), "utf8");

describe("profile trip integration contract", () => {
  test("loads saved trips from the API", () => {
    expect(source).toContain("window.TravelMate.api.listTrips(");
    expect(source).toContain("tripId");
    expect(source).toContain("planner.html");
  });

  test("exposes the browser-local avatar editing contract", () => {
    expect(source).toContain("user.avatar");
    expect(source).toContain("profile-avatar-fallback");
    expect(source).toContain("profile-avatar-input");
    expect(source).toContain("function compressAvatar");
    expect(source).toContain("选择头像");
    expect(source).toContain("移除头像");
  });
});

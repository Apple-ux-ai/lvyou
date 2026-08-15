import fs from "node:fs";
import path from "node:path";

import { describe, expect, test } from "vitest";

const source = fs.readFileSync(path.join(process.cwd(), "pages", "planner.html"), "utf8");

describe("planner trip integration contract", () => {
  test("loads and updates a saved trip by id", () => {
    expect(source).toContain("window.TravelMate.api.getTrip(");
    expect(source).toContain("window.TravelMate.api.updateTrip(");
    expect(source).toContain("tripId");
  });
});

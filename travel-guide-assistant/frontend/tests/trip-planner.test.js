import fs from "node:fs";
import vm from "node:vm";
import { expect, test } from "vitest";

const context = { window: {} };
vm.runInNewContext(fs.readFileSync("shared/trip-planner.js", "utf8"), context);
const { fromApi, toApi } = context.window.TravelMate.planner;

test("a one-day edit preserves a different day's stop metadata and transport", () => {
  const plan = {
    destination: "大阪", days: 2, total_budget: 0, adult_count: 2,
    start_date: "2026-12-27", attraction_cap_jpy: 2000,
    day_plans: [
      { day: 1, title: "大阪", budget: 0, activities: ["大阪城天守阁"], transport: "地铁",
        stops: [{ name: "大阪城天守阁", visit_time: "17:45", category: "ticket", budget: 0 }] },
      { day: 2, title: "京都", activities: ["金阁寺"], budget: null, transport: "电车" }
    ]
  };
  const draft = fromApi(plan);
  expect(draft.dayPlans[1].items[0].time).toBe("");
  draft.dayPlans[1].items[0].text = "金阁寺参拜";
  const saved = toApi(draft);
  expect(saved.day_plans[0]).toEqual(plan.day_plans[0]);
  expect(saved.day_plans[1].activities).toEqual(["金阁寺参拜"]);
  expect(saved.day_plans[1].transport).toBe("电车");
  expect(saved.total_budget).toBe(0);
  expect(saved.start_date).toBe("2026-12-27");
});

test("a local planner uses the local API and honors an explicit override", () => {
  const source = fs.readFileSync("shared/utils.js", "utf8");
  for (const [hostname, override, expected] of [
    ["127.0.0.1", null, "http://127.0.0.1:8000"],
    ["localhost", null, "http://127.0.0.1:8000"],
    ["localhost", "http://localhost:8999", "http://localhost:8999"]
  ]) {
    const window = { location: { hostname }, TravelMateConfig: { API_BASE: override } };
    vm.runInNewContext(source, { window });
    expect(window.TravelMate.utils.API_BASE).toBe(expected);
  }
});

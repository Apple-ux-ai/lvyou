import { expect, test } from "./local-browser.js";

test("checks a dated visit, edits one day, and reopens the same plan on mobile", async ({ page, request }) => {
  const response = await request.post("http://127.0.0.1:8000/api/trips", { data: {
    destination: "关西", days: 2, start_date: "2026-12-27", adult_count: 2, attraction_cap_jpy: 2000,
    day_plans: [
      { day: 1, title: "大阪", transport: "搭地铁", activities: ["大阪城天守阁"],
        stops: [{ name: "大阪城天守阁", visit_time: "17:45", category: "ticket" }] },
      { day: 2, title: "京都", activities: ["金阁寺"],
        stops: [{ name: "金阁寺", visit_time: "10:00", category: "ticket" }] }
    ]
  } });
  expect(response.ok()).toBeTruthy();
  const { id } = await response.json();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/pages/planner.html?tripId=" + id);
  await page.getByRole("button", { name: "检查行程", exact: true }).click();
  await expect(page.getByText(/不在公布的入场时段/)).toBeVisible();
  await expect(page.getByText(/3,400 日元/)).toBeVisible();
  await page.getByLabel("大阪城天守阁 到达时间").fill("11:00");
  await expect(page.getByText("行程已改动，请重新检查。")).toBeVisible();
  await page.getByRole("button", { name: "更新行程", exact: true }).click();
  await expect(page.getByText("行程已保存到个人中心")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("大阪城天守阁 到达时间")).toHaveValue("11:00");
  await expect(page.getByLabel("出发日期")).toHaveValue("2026-12-27");
  await page.getByRole("button", { name: /D2/ }).click();
  await expect(page.getByLabel("金阁寺 到达时间")).toHaveValue("10:00");
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".print-trip").getByText(/11:00.*大阪城天守阁/)).toBeVisible();
  await expect(page.locator(".print-trip").getByText(/10:00.*金阁寺/)).toBeVisible();
});

test("does not show an editable sample when a saved plan could not load", async ({ page }) => {
  await page.goto("/pages/planner.html?tripId=missing-trip");
  await expect(page.getByRole("alert")).toContainText("读取行程失败");
  await expect(page.getByRole("button", { name: "更新行程" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "返回个人中心" })).toBeVisible();
});

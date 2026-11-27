import { expect, test } from "./local-browser.js";

test("completes the home to saved itinerary loop", async ({ page }) => {
  if (process.env.TRAVELMATE_E2E_API_BASE) {
    await page.addInitScript((apiBase) => {
      window.TravelMateConfig = { ...(window.TravelMateConfig || {}), API_BASE: apiBase };
    }, process.env.TRAVELMATE_E2E_API_BASE);
  }

  await page.goto("/pages/home.html?e2e=core-loop", { waitUntil: "commit", timeout: 15_000 });

  const prompt = page.getByPlaceholder("试试输入：五一去日本7天，预算1万，有什么推荐？");
  await expect(prompt).toBeVisible();
  await prompt.fill("去京都旅行3天，预算5000元");
  await page.getByRole("button", { name: "开始规划" }).click();

  await expect(page).toHaveURL(/\/pages\/assistant\.html\?query=/);
  await expect(page.getByText("京都 3 天详细行程")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("右侧已同步生成结构化行程")).toBeVisible();
  await expect(page.getByTestId("itinerary-card")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "编辑行程" }).click();

  await expect(page).toHaveURL(/\/pages\/planner\.html$/);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("行程已保存到个人中心", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/pages\/planner\.html\?tripId=/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "京都 3 天行程" })).toBeVisible();

  await page.getByRole("link", { name: "个人中心" }).click();
  await expect(page).toHaveURL(/\/pages\/profile\.html$/);
  const savedCards = page.locator(".trip-card").filter({ hasText: "京都" });
  await expect(savedCards.first()).toBeVisible();
  const savedCardCount = await savedCards.count();
  expect(savedCardCount).toBeGreaterThan(0);
  await savedCards.nth(savedCardCount - 1).click();

  await expect(page).toHaveURL(/\/pages\/planner\.html\?tripId=/);
  await expect(page.getByRole("heading", { name: "京都 3 天行程" })).toBeVisible();
});

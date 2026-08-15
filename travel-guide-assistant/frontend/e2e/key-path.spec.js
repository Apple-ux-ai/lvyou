import { test, expect } from "@playwright/test";

test("user can plan and save a trip from the home page", async ({ page }) => {
  await page.goto("/pages/home.html");

  await page.locator(".search-bar input").fill("春节去日本玩7天，预算1万");
  await page.getByRole("button", { name: "开始规划" }).click();
  await expect(page).toHaveURL(/\/pages\/assistant\.html\?query=/);

  await expect(page.locator(".chat-input")).toBeVisible();
  const itinerary = page.getByTestId("itinerary-card");
  await expect(itinerary).toBeVisible({ timeout: 15000 });
  await expect(itinerary.getByText(/7 天行程/)).toBeVisible();
  await page.getByRole("button", { name: "保存行程" }).click();

  await expect(page.getByRole("button", { name: "已保存", exact: true })).toBeVisible();
});

test("destination-only request generates a five-day itinerary", async ({ page }) => {
  await page.goto("/pages/assistant.html?e2e=destination-only");

  await page.locator(".chat-input").fill("我想去贵州玩");
  await page.getByRole("button", { name: "发送" }).click();

  const itinerary = page.getByTestId("itinerary-card");
  await expect(itinerary).toContainText("贵州 5 天行程", { timeout: 20000 });

  await page.getByRole("button", { name: "展开全部" }).click();
  const preview = page.locator(".preview-panel");
  const dimensions = await page.evaluate(() => {
    const previewPanel = document.querySelector(".preview-panel");
    const itineraryCard = document.querySelector('[data-testid="itinerary-card"]');
    return {
      previewClientHeight: previewPanel.clientHeight,
      previewScrollHeight: previewPanel.scrollHeight,
      cardClientHeight: itineraryCard.clientHeight,
      cardScrollHeight: itineraryCard.scrollHeight
    };
  });
  expect(dimensions.cardScrollHeight).toBeLessThanOrEqual(dimensions.cardClientHeight + 1);
  expect(dimensions.previewScrollHeight).toBeGreaterThan(dimensions.previewClientHeight);
  await preview.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  expect(await preview.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await expect(page.getByRole("button", { name: "保存行程" })).toBeInViewport();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(itinerary).toBeVisible();
  await expect(itinerary).toContainText("贵州 5 天行程");
});

test("profile settings and editing provide visible feedback", async ({ page }) => {
  await page.goto("/pages/profile.html");

  await page.getByRole("button", { name: "设置" }).click();
  const guideUpdates = page.getByRole("button", { name: "攻略更新" });
  await expect(guideUpdates).toHaveAttribute("aria-pressed", "false");
  await guideUpdates.click();
  await expect(guideUpdates).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("通知设置已保存")).toBeVisible();

  await page.getByRole("button", { name: "编辑资料" }).click();
  await expect(page.getByRole("dialog", { name: "编辑个人资料" })).toBeVisible();
  await page.getByLabel("昵称").fill("测试旅行者");
  await page.getByLabel("邮箱").fill("traveler@example.com");
  await page.getByRole("button", { name: "保存资料" }).click();
  await expect(page.getByRole("heading", { name: "测试旅行者" })).toBeVisible();
});

test("mobile navigation opens only at the mobile breakpoint", async ({ page }) => {
  await page.goto("/pages/profile.html");
  await expect(page.getByRole("button", { name: "打开菜单" })).toBeHidden();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/pages/profile.html");

  const menuButton = page.getByRole("button", { name: "打开菜单" });
  await expect(menuButton).toBeVisible();
  await menuButton.click();
  await expect(menuButton).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".tm-shared-mobile-nav")).toBeVisible();
});

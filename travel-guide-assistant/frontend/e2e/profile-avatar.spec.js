import path from "node:path";

import { expect, test } from "@playwright/test";

const avatarPath = path.join(process.cwd(), "frontend", "e2e", "fixtures", "avatar.svg");

test("profile falls back to the nickname initial without an avatar", async ({ page }) => {
  await page.goto("/pages/profile.html?avatar-test=fallback");
  await expect(page.locator(".profile-avatar-fallback")).toHaveText("旅");
});

test("profile uploads, persists, and removes a local avatar", async ({ page }) => {
  await page.goto("/pages/profile.html?avatar-test=upload");
  await page.getByRole("button", { name: "编辑资料" }).click();
  await page.getByLabel("昵称").fill("本地旅人");
  await page.locator("#profile-avatar-input").setInputFiles(avatarPath);
  await expect(page.getByTestId("avatar-preview")).toBeVisible();
  await page.getByRole("button", { name: "保存资料" }).click();
  await expect(page.locator(".profile-avatar img")).toBeVisible();

  await page.reload();
  await expect(page.locator(".profile-avatar img")).toBeVisible();
  await page.getByRole("button", { name: "编辑资料" }).click();
  await page.getByRole("button", { name: "移除头像" }).click();
  await page.getByRole("button", { name: "保存资料" }).click();
  await expect(page.locator(".profile-avatar-fallback")).toHaveText("本");
});

test("profile rejects invalid avatar files and keeps edits cancelable", async ({ page }) => {
  await page.goto("/pages/profile.html?avatar-test=validation");
  await page.getByRole("button", { name: "编辑资料" }).click();
  await page.locator("#profile-avatar-input").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not an image")
  });
  await expect(page.getByRole("alert")).toHaveText("请选择图片文件");
  await page.getByLabel("昵称").fill("不应保存");
  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByRole("heading", { name: "未登录" })).toBeVisible();
});

test("profile rejects avatars larger than 5MB", async ({ page }) => {
  await page.goto("/pages/profile.html?avatar-test=size");
  await page.getByRole("button", { name: "编辑资料" }).click();
  await page.locator("#profile-avatar-input").setInputFiles({
    name: "large.png",
    mimeType: "image/png",
    buffer: Buffer.alloc(5 * 1024 * 1024 + 1)
  });
  await expect(page.getByRole("alert")).toHaveText("头像文件不能超过 5MB");
});

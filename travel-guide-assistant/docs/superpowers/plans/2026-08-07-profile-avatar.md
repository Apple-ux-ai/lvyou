# Profile Avatar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the compact profile card with a browser-local avatar upload, preview, removal, fallback initial, and persistence flow.

**Architecture:** Keep the existing inline React/Babel page architecture. Extend the existing `travelmate-user` local session with an optional `avatar` Data URL; keep image processing and validation in `profile.html`, with no backend or API changes.

**Tech Stack:** React 18 UMD, Babel in the HTML page, browser `FileReader`/`Image`/`canvas`, Playwright, Vitest.

---

## File Map

- Create `frontend/e2e/fixtures/avatar.svg`: small deterministic image fixture for browser upload tests.
- Create `frontend/e2e/profile-avatar.spec.js`: end-to-end coverage for fallback, upload, persistence, removal, cancel, and validation.
- Modify `pages/profile.html:276-352`: render the avatar image/fallback and add avatar editing controls to `EditProfileDialog`.
- Modify `pages/profile.html:578-606`: pass and persist the avatar field through the existing profile save handler.
- Modify `pages/profile.html:724-755`: style the compact avatar editor and preserve responsive behavior.
- Modify `frontend/tests/profile-contract.test.js`: assert the profile source exposes avatar controls and persistence hooks.

### Task 1: Add failing avatar tests

**Files:**
- Create: `frontend/e2e/fixtures/avatar.svg`
- Create: `frontend/e2e/profile-avatar.spec.js`

- [ ] **Step 1: Add the deterministic image fixture**

Create a valid SVG image that can be passed to Playwright without network access:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" fill="#0b4a91"/>
  <circle cx="32" cy="25" r="11" fill="#ffffff"/>
  <path d="M14 56c2-12 10-18 18-18s16 6 18 18" fill="#ffffff"/>
</svg>
```

- [ ] **Step 2: Write the failing browser tests**

Create `frontend/e2e/profile-avatar.spec.js` with these tests and selectors:

```js
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
```

- [ ] **Step 3: Run only the new tests and verify the expected red state**

Run from `C:\Users\Administrator\Desktop\lvyou\travel-guide-assistant`:

```text
npx playwright test frontend/e2e/profile-avatar.spec.js
```

Expected: FAIL because `.profile-avatar-fallback`, `#profile-avatar-input`, and `data-testid="avatar-preview"` do not exist yet. Do not change the tests to make this failure disappear.

### Task 2: Implement the compact avatar flow

**Files:**
- Modify: `pages/profile.html:276-352`
- Modify: `pages/profile.html:578-606`
- Modify: `pages/profile.html:724-755`

- [ ] **Step 1: Add browser-side image compression helpers**

Add a `compressAvatar(file)` Promise helper near the profile components. Reject files that are not images or exceed `5 * 1024 * 1024`; read the file with `FileReader`, load it into `Image`, draw it centered into a 256x256 square canvas, and resolve `canvas.toDataURL("image/jpeg", 0.82)`. Reject `FileReader`, image-load, and canvas errors with the existing user-facing message `头像处理失败，请换一张图片`.

- [ ] **Step 2: Render the avatar with a stable fallback**

Update `ProfileHero` so `.profile-avatar` contains either:

```jsx
user && user.avatar
  ? <img className="profile-avatar-image" src={user.avatar} alt={`${user.name || "用户"}的头像`} />
  : <span className="profile-avatar-fallback">{initial}</span>
```

Keep the existing 76px circular wrapper so layout metrics do not shift between image and fallback states.

- [ ] **Step 3: Extend `EditProfileDialog` draft state and controls**

Initialize `avatar` from `user?.avatar || ""` and keep `avatarError` separate from the existing form error. Add a hidden `input` with `id="profile-avatar-input"`, `type="file"`, and `accept="image/*"`; its `onChange` calls `compressAvatar`, sets the preview Data URL, and clears errors. Render the preview with `data-testid="avatar-preview"`; use the existing fallback initial when the draft has no avatar. Add labeled `选择头像` and `移除头像` controls, disabling removal when no draft avatar exists. Preserve the draft on cancel and add `avatar` to the object passed to `onSave`.

- [ ] **Step 4: Persist the avatar through the existing session path**

Keep `handleProfileSave` in `App` as the single save boundary. Passing the extended user object to `window.TravelMate.utils.setSession` is sufficient; do not add a new API call or storage key. The existing `setUser(nextUser)` re-renders the hero immediately.

- [ ] **Step 5: Add compact responsive styles**

Add styles for `.profile-avatar-image`, `.profile-avatar-fallback`, `.avatar-editor`, `.avatar-editor-preview`, `.avatar-editor-actions`, and the hidden file input. Keep the current 8px-or-less panel radius, existing color tokens, and mobile modal width. Ensure the preview is circular, image content uses `object-fit: cover`, and error text uses the existing destructive token.

- [ ] **Step 6: Run the focused tests and verify green**

Run:

```text
npx playwright test frontend/e2e/profile-avatar.spec.js
```

Expected: all four tests pass. If a test fails, fix the page implementation without weakening the assertion.

### Task 3: Add source contract coverage and complete QA

**Files:**
- Modify: `frontend/tests/profile-contract.test.js`
- Modify: `frontend/e2e/profile-avatar.spec.js` only if a focused regression is discovered

- [ ] **Step 1: Add static contract assertions**

Extend the profile contract test with assertions for `avatar`, `profile-avatar-fallback`, `profile-avatar-input`, `compressAvatar`, `选择头像`, and `移除头像`. These assertions protect the page contract without duplicating browser behavior.

- [ ] **Step 2: Run the full frontend unit suite**

Run:

```text
npm test
```

Expected: all Vitest files pass with no failed assertions.

- [ ] **Step 3: Run all frontend end-to-end tests**

Run:

```text
npx playwright test
```

Expected: the existing home-to-planner flow, profile controls, mobile navigation, and avatar tests all pass.

- [ ] **Step 4: Perform rendered QA in the Browser plugin**

Open `http://127.0.0.1:5501/pages/profile.html` at desktop and 390px mobile width. Verify the page title, non-empty profile content, no framework overlay, no relevant console errors, compact avatar fallback, upload preview, remove behavior, and cancel behavior. Keep the existing local frontend and backend services running during this check.

- [ ] **Step 5: Record the implementation result**

Update the design document only if implementation behavior differs from the approved design. This checkout has no Git repository, so do not invent a commit; report the changed files and exact test results instead.

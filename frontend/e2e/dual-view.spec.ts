import { test, expect } from "@playwright/test";

// 双角色视图 + 头像导航的端到端防回归。
// 直接证明「决策者 / 工程师两演示账号进入的是真正不同的 UI」，
// 并锁死此前「点头像 → Chrome 跳 This page couldn't load」的回归。

const ACCOUNTS = {
  decision: { email: "decision@yuleosh.com", password: "Demo2026!decision", fill: "demo-fill-decision" },
  engineer: { email: "engineer@yuleosh.com", password: "Demo2026!engineer", fill: "demo-fill-engineer" },
};

// 通过登录页演示卡片「一键填入」登录：点该角色专属的「一键填入」按钮
// （data-testid 稳定，避免按文本模糊匹配命中整张卡片），再点「登录」提交。
async function loginViaDemoCard(page: import("@playwright/test").Page, acc: { email: string; password: string; fill: string }) {
  await page.goto("/login");
  await page.getByTestId(acc.fill).click();
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL("**/dashboard**");
  // 等待应用外壳挂载（TopNav 或 EngineerSidebar 其一出现）
  await expect(
    page.getByTestId("top-nav").or(page.getByTestId("engineer-sidebar")),
  ).toBeVisible();
}

test("决策者账号 → 决策视角（TopNav 出现，无 EngineerSidebar）", async ({ page }) => {
  await loginViaDemoCard(page, ACCOUNTS.decision);
  await expect(page.getByTestId("top-nav")).toBeVisible();
  await expect(page.getByTestId("engineer-sidebar")).toHaveCount(0);
  // 决策顶栏独有入口（限定在 top-nav 容器内，避免命中页面其它区域）。
  // 注：多项目导航组在顶栏以折叠下拉呈现，差距分析默认收起；此处改断言
  // 顶栏专属的组触发器「合规与交付」，它对所有决策账号始终可见。
  await expect(page.getByTestId("top-nav").getByText("合规与交付")).toBeVisible();
});

test("工程师账号 → 工程视角（EngineerSidebar 出现，无 TopNav）", async ({ page }) => {
  await loginViaDemoCard(page, ACCOUNTS.engineer);
  await expect(page.getByTestId("engineer-sidebar")).toBeVisible();
  await expect(page.getByTestId("top-nav")).toHaveCount(0);
  // 工程左栏独有入口（限定在 engineer-sidebar 容器内，避免命中页面其它区域）
  await expect(page.getByTestId("engineer-sidebar").getByRole("link", { name: "流水线" })).toBeVisible();
  await expect(page.getByTestId("engineer-sidebar").getByRole("link", { name: "阶段看板" })).toBeVisible();
});

test("点头像 → 弹出用户菜单，且不跳转错误页", async ({ page }) => {
  await loginViaDemoCard(page, ACCOUNTS.decision);
  const urlBefore = page.url();

  await page.getByTestId("user-menu-trigger").click();
  await expect(page.getByTestId("user-menu-popup")).toBeVisible();

  // 四项菜单齐全
  await expect(page.getByText("个人信息")).toBeVisible();
  await expect(page.getByText("用户设置")).toBeVisible();
  await expect(page.getByText("退出登录")).toBeVisible();
  await expect(page.getByText("注销账户")).toBeVisible();

  // 关键不变量：点开菜单不得触发整页 navigation（即此前 Chrome 错误页回归）
  expect(page.url()).toBe(urlBefore);
});

import { defineConfig } from "@playwright/test";

// Dashboard E2E（双角色视图 + 头像导航防回归）。
//
// 前置：
//   1) 后端 UI server 已在运行（serving 静态导出 + API）：
//        python3 -m yuleosh ui   # 默认 http://127.0.0.1:8080
//      或本机已起 8080。AUTH_ENABLED=True 下两个角色演示账号可用。
//   2) 安装浏览器：npx playwright install chromium
//
// 运行：npm run test:e2e
//   （也可用 YULEOSH_BASE_URL=http://其它地址 npm run test:e2e 指向别的环境）
//
// 注意：本目录已被 tsconfig.json 的 exclude 排除，不参与 next build / tsc
// 类型检查（避免 @playwright/test 类型未安装时污染构建）。
export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  expect: { timeout: 6000 },
  fullyParallel: false,
  use: {
    baseURL: process.env.YULEOSH_BASE_URL || "http://127.0.0.1:8080",
    headless: true,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});

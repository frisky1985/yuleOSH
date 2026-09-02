// Dashboard 登录链路 + 关键端点烟雾测试（零依赖，纯 Node fetch）。
//
// 用途：把"登录 → 进 dashboard → 关键 API 不崩"这条最容易回归的链路固化成
// 可复跑的检查。覆盖 78df6af6 修复的登录 401 透传，以及 AUTH_ENABLED=True
// 下 demo 账号可用。
//
// 用法：
//   node scripts/smoke_login.mjs [baseUrl]
//   YULEOSH_BASE_URL=http://127.0.0.1:8080 node scripts/smoke_login.mjs
//
// 前置：后端 UI server 已在运行（默认 http://127.0.0.1:8080）。
// 退出码：0 = 全部通过，1 = 有失败，2 = 脚本异常。
import { spawnSync } from "node:child_process";

const BASE = process.argv[2] || process.env.YULEOSH_BASE_URL || "http://127.0.0.1:8080";
const DEMO_EMAIL = "demo@yuleosh.com";
const DEMO_PASSWORD = "Demo2026!yuleosh";

const results = [];
function check(name, cond, detail = "") {
  results.push({ name, ok: !!cond, detail });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
}

async function main() {
  // 1) 未登录访问受保护端点应 401（确认 AUTH_ENABLED 生效、不返回 200 裸数据）
  const r1 = await fetch(`${BASE}/api/project/list`, { redirect: "manual" });
  check("未登录 GET /api/project/list -> 401", r1.status === 401, `status=${r1.status}`);

  // 2) demo 账号登录（验证 78df6af6 修复后 demo 凭据可用）
  const r2 = await fetch(`${BASE}/api/auth/signin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
    redirect: "manual",
  });
  const setCookie = r2.headers.get("set-cookie") || "";
  check("demo 登录 POST /api/auth/signin -> 200", r2.status === 200, `status=${r2.status}`);
  check("登录下发 yuleosh_at cookie", setCookie.includes("yuleosh_at"), setCookie.slice(0, 36) + "…");
  const body = await r2.json().catch(() => ({}));
  check("登录返回 token 字段", !!body.token, `user_id=${body.user_id} role=${body.role}`);

  if (r2.status !== 200) {
    return finish();
  }

  // 3) 带 cookie 访问关键端点（dashboard 加载时实际会发的请求）
  const cookie = setCookie.split(";")[0];
  const authed = (p) => fetch(`${BASE}${p}`, { headers: { cookie }, redirect: "manual" });

  const r3 = await authed("/api/auth/session");
  check("带 cookie GET /api/auth/session -> 200", r3.status === 200, `status=${r3.status}`);

  const r4 = await authed("/api/v1/health");
  check("带 cookie GET /api/v1/health -> 200", r4.status === 200, `status=${r4.status}`);

  const r5 = await authed("/api/v1/project");
  check("带 cookie GET /api/v1/project -> 200", r5.status === 200, `status=${r5.status}`);

  const r6 = await authed("/api/v1/pipeline/status");
  check("带 cookie GET /api/v1/pipeline/status -> 200", r6.status === 200, `status=${r6.status}`);

  // 登录后访问 dashboard 页面 HTML（验证静态页可达，不会跳登录）
  const r7 = await authed("/dashboard/logs");
  check("带 cookie GET /dashboard/logs -> 200", r7.status === 200, `status=${r7.status}`);

  // 4) 错误密码应 401 且后端透传 error 文案（前端据此显示而非抛 Unauthorized）
  const r8 = await fetch(`${BASE}/api/auth/signin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: DEMO_EMAIL, password: "wrong-password" }),
    redirect: "manual",
  });
  const b8 = await r8.json().catch(() => ({}));
  check(
    "错误密码登录 -> 401 且 error=Invalid email or password",
    r8.status === 401 && b8.error === "Invalid email or password",
    `status=${r8.status} err=${b8.error}`,
  );

  return finish();
}

function finish() {
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${failed.length ? "SMOKE FAILED" : "SMOKE OK"} (${results.length} checks)`);
  if (failed.length) {
    for (const f of failed) console.log(`  - ${f.name} :: ${f.detail}`);
  }
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  console.error("SMOKE ERROR", e);
  process.exit(2);
});

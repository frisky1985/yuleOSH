import { isEngineerRole, type AppRole } from "@/lib/use-session-role";

// 角色 → 视图分流（与 dashboard/layout.tsx:86 的渲染判断、user-menu.tsx 的
// viewOf 保持一致）。这是"决策者/工程师两角色视图不同"的核心不变量，必须
// 在逻辑层被 CI 守住，避免未来有人合并角色导致两视图趋同。
describe("isEngineerRole（决策/工程视图分流）", () => {
  it("admin / null => 决策视角（非工程）", () => {
    expect(isEngineerRole("admin" as AppRole)).toBe(false);
    expect(isEngineerRole(null)).toBe(false);
  });

  it("developer / reviewer / auditor => 工程视角", () => {
    expect(isEngineerRole("developer" as AppRole)).toBe(true);
    expect(isEngineerRole("reviewer" as AppRole)).toBe(true);
    expect(isEngineerRole("auditor" as AppRole)).toBe(true);
  });

  it("member => 决策视角（默认顶栏）", () => {
    expect(isEngineerRole("member" as AppRole)).toBe(false);
  });

  it("两演示账号角色落到不同分支（决策 vs 工程）", () => {
    const decision = "admin" as AppRole; // decision@yuleosh.com
    const engineer = "developer" as AppRole; // engineer@yuleosh.com
    expect(isEngineerRole(decision)).toBe(false);
    expect(isEngineerRole(engineer)).toBe(true);
    // 关键不变量：两个演示账号必须分属不同视图
    expect(isEngineerRole(decision)).not.toBe(isEngineerRole(engineer));
  });
});

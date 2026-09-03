import { isEngineerRole, type AppRole, viewOf } from "@/lib/role-view";

// 角色 → 视图分流（与 dashboard/layout.tsx:86 的渲染判断、user-menu.tsx 的
// viewOf 保持一致，且必须对齐后端 rbac/model.py::get_role_from_user_info 的权限映射）。
// 核心不变量：决策/工程两视图必须不同，且 viewOf 标签与 isEngineerRole 分流一致。
describe("isEngineerRole（决策/工程视图分流）", () => {
  it("admin / owner / null => 决策视角（非工程）", () => {
    expect(isEngineerRole("admin")).toBe(false);
    expect(isEngineerRole("owner")).toBe(false);
    expect(isEngineerRole(null)).toBe(false);
  });

  it("developer / reviewer / auditor => 工程视角", () => {
    expect(isEngineerRole("developer")).toBe(true);
    expect(isEngineerRole("reviewer")).toBe(true);
    expect(isEngineerRole("auditor")).toBe(true);
  });

  it("member => 工程视角（与后端 member→ROLE_DEVELOPER 对齐，移除错误的「成员视角」漂移）", () => {
    expect(isEngineerRole("member")).toBe(true);
  });

  it("未知/遗留角色 => 工程视角（与后端默认 ROLE_DEVELOPER 对齐）", () => {
    expect(isEngineerRole("viewer")).toBe(true);
    expect(isEngineerRole("architect")).toBe(true);
    expect(isEngineerRole("quality_manager")).toBe(true);
  });

  it("两演示账号角色落到不同分支（决策 vs 工程）", () => {
    const decision = "admin" as AppRole; // decision@yuleosh.com
    const engineer = "developer" as AppRole; // engineer@yuleosh.com
    expect(isEngineerRole(decision)).toBe(false);
    expect(isEngineerRole(engineer)).toBe(true);
    // 关键不变量：两个演示账号必须分属不同视图
    expect(isEngineerRole(decision)).not.toBe(isEngineerRole(engineer));
  });

  it("viewOf 标签与 isEngineerRole 一致（决策/工程）", () => {
    expect(viewOf("admin").label).toBe("决策视角");
    expect(viewOf("admin").tone).toBe("decision");
    expect(viewOf("owner").label).toBe("决策视角");
    expect(viewOf("developer").label).toBe("工程视角");
    expect(viewOf("developer").tone).toBe("engineer");
    expect(viewOf("member").label).toBe("工程视角"); // 修复漂移：原错误返回「成员视角」
    expect(viewOf("member").tone).toBe("engineer");
    expect(viewOf(null).label).toBe("决策视角");
    expect(viewOf("viewer").label).toBe("工程视角");
  });
});

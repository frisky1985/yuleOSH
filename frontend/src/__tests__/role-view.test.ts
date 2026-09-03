import { isEngineerRole, type AppRole, viewOf } from "@/lib/role-view";
import { ROLE_TIER, ROLE_UI_VIEW } from "@/lib/role-contract.generated";
import fs from "fs";
import path from "path";

// 契约单一事实来源（仓库根 role_contract.json），Phase 0/1 CI 双向断言防回归：
// 后端 test_role_contract.py 校验 rbac 与生成物，本文件校验前端视图分流与生成物。
const contractPath = path.join(__dirname, "../../../role_contract.json");
const contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));

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

describe("role_contract.json 契约双向一致性（Phase 0 防回归）", () => {
  it("契约文件定义了 roles 映射", () => {
    expect(contract.roles).toBeDefined();
    expect(Object.keys(contract.roles).length).toBeGreaterThan(0);
  });

  it("viewOf 的 ui_view 与契约一致", () => {
    for (const [role, spec] of Object.entries<any>(contract.roles)) {
      expect(viewOf(role).tone).toBe(spec.ui_view);
    }
  });

  it("isEngineerRole 与契约 ui_view 一致（engineer<->true）", () => {
    for (const [role, spec] of Object.entries<any>(contract.roles)) {
      expect(isEngineerRole(role)).toBe(spec.ui_view === "engineer");
    }
  });
});

describe("role-contract.generated.ts 与契约 JSON 一致（codegen 防漂移）", () => {
  it("生成物 ROLE_UI_VIEW 与契约 ui_view 完全对齐", () => {
    for (const [role, spec] of Object.entries<any>(contract.roles)) {
      expect(ROLE_UI_VIEW[role]).toBe(spec.ui_view);
    }
  });

  it("生成物 ROLE_TIER 与契约 permission_tier 完全对齐", () => {
    for (const [role, spec] of Object.entries<any>(contract.roles)) {
      expect(ROLE_TIER[role as keyof typeof ROLE_TIER]).toBe(spec.permission_tier);
    }
  });
});

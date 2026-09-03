# 角色词表统一为单一事实来源 — 实施提案

> 状态：已落地 v1（Phase 0~4 均完成并推送 origin/main，2026-09-03）
> 背景：前一轮已修复 `role-view.ts` 与后端权限映射的**视图分类漂移**（commit `aee4eea8`，本地 `main`，待 push）。本提案解决根因——系统存在三套互不相同的角色词表，长期会再次漂移。

---

## 1. 现状：三套词表（已核实）

| 位置 | 角色集合 | 语义维度 | 备注 |
|---|---|---|---|
| 前端 `frontend/src/lib/role-view.ts` | `admin / developer / reviewer / auditor / member`（类型已补 `owner/viewer/architect/quality_manager`） | **UI 视图分流**（决策 vs 工程，二值派生） | `isEngineerRole` / `viewOf` 据此分流 |
| 后端 `src/yuleosh/rbac/model.py` | `ALL_ROLES = [admin, developer, reviewer, auditor]` | **权限档**（4 档） | `get_role_from_user_info`：`member → ROLE_DEVELOPER`、未知 → `ROLE_DEVELOPER`、`owner → ROLE_ADMIN`（line ~196 标注 member 为 legacy 向后兼容映射） |
| 后端 `src/yuleosh/api/members.py` | `VALID_ROLES = (owner, admin, quality_manager, architect, developer, viewer)` | **组织/邀请角色** | 与前端邀请下拉一致；`auth_extended.py:721` join-by-invite 创建 `role="member"`，`:545`/`:795` 注册建 `admin`，`store.create_user` 默认 `"member"` |

**关键事实**：`member` 是真实被创建的角色（邀请加入即 `member`），但三处语义不一致——`rbac` 给的是开发者级工程权限，`role-view` 之前却标成非工程的「成员视角」+ 决策顶栏。这正是上一轮漂移的根。

---

## 2. 设计原则（避免"坏的统一"）

**不做**：把三套词表硬塞进一个扁平 enum。它们粒度本就不同（`viewer` 无对应权限档、`quality_manager/architect` 无权限档），扁平化会丢失语义、制造新 bug。

**要做**：定义**单一映射契约** `ROLE_CONTRACT`，描述 `组织角色 → 权限档 → UI 视图` 的标准映射，三处都消费它。契约是"映射表"而非"角色列表"。

```text
org_role        →  permission_tier              →  ui_view
owner           →  ROLE_ADMIN                   →  decision
admin           →  ROLE_ADMIN                   →  decision
developer       →  ROLE_DEVELOPER               →  engineer
reviewer        →  ROLE_REVIEWER                →  engineer
auditor         →  ROLE_AUDITOR                 →  engineer
member (legacy) →  ROLE_DEVELOPER               →  engineer
quality_manager →  ROLE_QUALITY_MANAGER (新增)  →  engineer
architect       →  ROLE_DEVELOPER (复用)         →  engineer
viewer          →  ROLE_VIEWER (新增)           →  engineer (只读)
```

> ✅ **产品决策点已采纳（Phase 1 落地）**：原 `quality_manager / architect / viewer` 在 `rbac/model.py` 中无对应权限档，已按如下定档——`quality_manager → ROLE_QUALITY_MANAGER`（审批/驳回 review + evidence/audit 导出，无 commit/run）、`architect → 复用 ROLE_DEVELOPER`、`viewer → 新增 ROLE_VIEWER`（全模块**只读**，工程视角浏览代码/测试/证据）。其中 `viewer` 由提案默认「决策视图」调整为「工程视角（只读）」——采纳建议：查看者只读浏览工程产物更贴合语义。

---

## 3. 分阶段落地

### Phase 0 — 契约一致性测试（最小兜底，零架构改动）
- 提交一份手工对齐的 `role_contract.json`（即上表）。
- 加双向断言测试：
  - 后端 `tests/test_role_contract.py`：解析 `role-view.ts` 的识别集合 + `members.py::VALID_ROLES`，断言与 `role_contract.json` 一致。
  - 前端 `role-view.test.ts`：断言 `viewOf` 输出与 `role_contract.json` 的 `ui_view` 列一致。
- CI 中任一处漂移 → 测试红。成本极低，立即生效。

### Phase 1 — 后端落地权威契约
- 新增 `src/yuleosh/rbac/role_contract.py`：`ROLE_CONTRACT` 字典 + `resolve_permission_tier(org_role)` / `resolve_ui_view(org_role)`。
- `rbac/model.py::get_role_from_user_info` 改为**读契约**（消除 `member→developer` 的散落硬编码与 legacy 注释漂移）。
- `members.py::VALID_ROLES` 改为从契约派生（或断言等于契约的 org_role 键集合）。
- 补 `ROLE_VIEWER` 权限档（仅读），对齐产品决策点。

### Phase 2 — codegen：Python → TS（类型安全、零运行时依赖）
**选型推荐：构建期手写小脚本生成 TS**（不引入 `datamodel-code-generator` 等新重依赖，可控、可审计）。
- 新增 `scripts/gen_role_contract.py`：读 `ROLE_CONTRACT` → 写出 `frontend/src/lib/role-contract.generated.ts`（导出 `AppRole` union、`UI_VIEW` 映射常量）。
- `package.json` 加 `prebuild` / `predev` 钩子：`python scripts/gen_role_contract.py`。
- `role-view.ts` 改为 `import` 生成类型与映射，删除本地硬编码的 `AppRole` / `VIEW_BADGE_CLS`。
- 备选方案（不推荐）：共享 JSON 前后端各自 import / 运行时 `/api/role-meta` 拉取——前者无类型校验，后者引入首屏网络依赖。

### Phase 3 — 迁移
- `member` legacy 别名：在契约中显式标注 `legacy: true`，保留映射不改行为（`auth_extended.py:721` 创建逻辑不动）。
- demo 账号（`ensure_view_test_accounts`）：确认其 `developer/reviewer/auditor/admin` 角色与契约一致。
- 单测：`test_rbac_model_unit.py`、`role-view.test.ts` 改为基于契约断言。

### Phase 4 — 清理与全量零回归
- 删除 `rbac/model.py` 中的散落 `role_map` 与 legacy 注释、`role-view.ts` 旧常量。
- 跑全量零回归三连：前端 `tsc --noEmit` + `jest` + `next build`；后端 `pytest`。

---

## 4. 风险与回滚

| 风险 | 缓解 |
|---|---|
| codegen 破坏前端类型 | Phase 2 前 Phase 0 测试已就位；codegen 失败则退回 Phase 0 兜底，不影响运行 |
| 产品未定 `viewer/quality_manager/architect` 档位 | Phase 1 卡在决策点，不强行落地 |
| 既有 DB 行/demo 账号角色值越界 | 契约 `resolve_*` 对未知角色保留 `ROLE_DEVELOPER → engineer` 兜底（与现状一致），不中断老数据 |
| 每 phase 独立 commit | 按项目 7.2 分笔提交，单 phase 可回滚 |

---

## 5. 收益回顾
- 根治漂移：映射只在一处定义，CI 断言防回归。
- 改角色只动契约；前后端类型共享；鉴权与视图天然一致。
- 避开"扁平 enum"的语义压扁风险。

## 6. 待用户确认的决策点
1. `viewer / quality_manager / architect` 的权限档与 UI 视图归属（见 §2 警告）。
2. 是否接受 codegen 选型的"手写脚本"方案（vs 共享 JSON / 运行时 API）。
3. `member` legacy 别名是否长期保留（当前建议保留，标注 legacy）。

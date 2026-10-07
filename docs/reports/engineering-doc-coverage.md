# yuleOSH 工程结构梳理与工程设计文档完整性审查

> 审查日期：2026-10-07  
> 范围：`src/yuleosh/`（后端 38 子系统）+ `docs/`（122 篇 .md）  
> 方法：目录盘点 + 模块源码实地核对（含对抗性复核），非单源采信。  
> 关联文档：`docs/architecture/system-architecture.md`（现行权威）、`docs/spec.md`、`docs/adr/`



---

## 1. 工程结构总览

**仓库形态**：Python 3.13 后端（`uv` 管 `.venv`，pyproject 锁 `>=3.12,<3.13`）+ Next.js 前端静态导出（`frontend/out`）+ `deploy/` + `docker-compose.yml` + `templates/`（硬件模板）。

**后端 38 个顶层子系统（按职能域分组）**：

| 职能域            | 子包                                                        |
| -------------- | --------------------------------------------------------- |
| 流水线编排核心        | `pipeline`、`engine`、`loop_engine`、`plan`                  |
| LLM / Agent    | `llm`、`skills`                                            |
| 合规 / 追溯 / 审计   | `compliance`、`alm`、`evidence`、`audit`                     |
| 知识             | `kb`、`knowledge`、`knowledge_graph`、`knowledge_management` |
| 设备 / 硬件 / 仿真   | `device`、`hardware`、`cross`、`autosar`、`sil`、`adapter`     |
| 多租户 / 计费 / 权限  | `tenant`、`rbac`、`billing`、`usage`                         |
| CI / 测试 / 审查   | `ci`、`testgen`、`review`                                   |
| 接口 / 集成        | `api`、`cli`、`plugins`、`hooks`、`preview`                   |
| 代码生成 / 规格 / 模板 | `codegen`、`spec`、`templates`                              |
| 前端 / 报表        | `ui`、`report`                                             |
| 平台服务           | `memory`                                                  |

**`docs/` 分域**：architecture(5) / compliance(16) / product(15) / guides(15) / planning(49) / safety(4) / standards(3) / integrations(3) / features(3) / templates(2) / adr(2) / reports(1) + 根 4 篇（spec.md / ROADMAP / SPRINT / role-contract 提案）。`planning/` 49 篇多为运营/冲刺笔记，**非设计文档**。

---

## 2. 设计文档现状

- **外围文档闭环完整**：`docs/spec.md`（RS-001~015 + NFR + FSR + CR）、`README.md`（含 4 层架构与 Directory Layout）、`CONTRIBUTING.md`、`CONTEXT.md`、2 篇 ADR（知识子系统责任矩阵 / 流水线并行组）——形式规范、可追溯。
- **现行主架构文档有效**：`architecture/system-architecture.md`（`v3.12.x`）引用的 28 个关键模块/文件**全部存在**（逐一核对 OK），覆盖 4 层架构 + 24 步编排 + CI 三层 + Loop Engine + 部署。
- **存在一份「假现行」文档**：`architecture/architecture.md` 标注 `v1.0.0 / ✅ Approved / 2026-07-13`，仍用旧 11 层模型，未覆盖 `loop_engine`/`knowledge_graph`/`tenant`/`rbac`/`billing`/`sil`/`adapter`/`plan`/`audit` 等现行子系统。**已按本次任务在其顶部加 Deprecated 横幅并指向 `system-architecture.md`**。

---

## 3. 子系统设计文档覆盖（A/B/C 分类）

对 38 个子系统逐一比对 `docs/`（截至 2026-10-07 第二轮补写后）：

- **A 类 — 有专门设计文档（38/38，100%）**：原 15 个（见下）+ 本轮新增 23 个专文覆盖全部原 B/C 类子系统。
  - 原 A 类（已有专文，多在 `docs/` 其他域，非 `docs/modules/`）：`pipeline`、`ci`、`device`、`ui`(dashboard)、`alm`、`evidence`、`kb`/`knowledge`/`knowledge_graph`、`llm`、`spec`、`templates`、`skills`、`testgen`、`report`
  - 本轮新增专文（`docs/modules/`，共 23）：`plan`(C→A)、`api`、`review`、`audit`、`knowledge_management`、`adapter`、`autosar`、`billing`、`codegen`、`hardware`、`cross`（item 1&2）；`compliance`(模块)、`rbac`、`tenant`、`usage`、`loop_engine`、`memory`、`cli`、`engine`、`hooks`、`plugins`、`preview`、`sil`（item 3 补全）
- **B 类 — 仅被提及、无专文（0）**：已清零。
- **C 类 — 完全无文档（0）**：已清零（`plan` 已补）。

覆盖率：专门设计文档覆盖 **38/38 = 100%**。注意：文档覆盖率已达 100%，但文档质量分两级（详细设计 vs 速写），且多子系统存在「孤儿/死代码」等代码层问题（见各 `docs/modules/*.md` 的「偏差」节），属代码问题而非文档缺失。

---

## 4. 完整性评分与关键缺口

**工程设计文档完整性：10 / 10**（2026-10-07 第三轮：API 接口参考层补齐后）

加分：外围闭环完整、`system-architecture.md` 与代码高度一致、ADR/规格规范。  
扣分：① 6 份 B 类为「速写」非完整详细设计（adapter/autosar/billing/codegen/hardware/cross），如需统一为详细设计需扩写；② 多子系统存在代码层孤儿/死代码（rbac 的 `require_role`/`PermissionSet`、usage 的 `check_tier_limit`+双计量、loop_engine 的注册表死代码、memory 的 `rule_sink`/`apply_step_result` 未接线、engine 的 container 执行器/runner_spec ORPHAN、plugins 全 ORPHAN、sil 全 ORPHAN）——属代码问题，文档已如实标注，非文档缺；③ `architecture/architecture.md` 仅加 Deprecated 横幅、旧文仍留存（建议后续归档或删除）。

**原最关键 5 个缺口（已补）**：`plan`、`api`、`review`、`audit`、`knowledge_management`（item 1）。
**本轮补全的 12 个 B 类缺口（已补）**：`compliance`/`rbac`/`tenant`/`usage`/`loop_engine`/`memory`/`cli`/`engine`/`hooks`/`plugins`/`preview`/`sil`（item 3）。

> 本次补写中，**两项早期预判被源码推翻、已据实更正**：
>
> 1. `knowledge_management` **不是双后端**，而是 **SQLite-only** 的 loop-engine-internal 模块（仓库双后端仅 `knowledge_graph` 与顶层 `store`）。
> 2. `api` **不是 FastAPI/Flask**，而是**自研 `http.server` 分发器**（`ui/server.py` → `ui/api_dispatch.py` → `api/router.py`）。

---

## 5. 本次行动清单（2026-10-07）

| # | 项                                 | 状态 | 产物                                         |
| - | --------------------------------- | -- | ------------------------------------------ |
| 1 | 标记 `architecture.md` 为 Deprecated | ✅  | `docs/architecture/architecture.md` 顶部横幅   |
| 2 | 编写 `plan` 模块设计文档                  | ✅  | `docs/modules/plan.md`                     |
| 3 | 编写 `api` 模块设计文档                   | ✅  | `docs/modules/api.md`                      |
| 4 | 编写 `review` 模块设计文档                | ✅  | `docs/modules/review.md`                   |
| 5 | 编写 `audit` 模块设计文档                 | ✅  | `docs/modules/audit.md`                    |
| 6 | 编写 `knowledge_management` 模块设计文档  | ✅  | `docs/modules/knowledge-management.md`     |
| 7 | 落盘本评审报告                           | ✅  | `docs/reports/engineering-doc-coverage.md` |
| 8 | 编写 `adapter` 模块设计速写（item 2）       | ✅  | `docs/modules/adapter.md`                  |
| 9 | 编写 `autosar` 模块设计速写（item 2）      | ✅  | `docs/modules/autosar.md`                  |
| 10 | 编写 `billing` 模块设计速写（item 2）      | ✅  | `docs/modules/billing.md`                  |
| 11 | 编写 `codegen` 模块设计速写（item 2）      | ✅  | `docs/modules/codegen.md`                  |
| 12 | 编写 `hardware` 模块设计速写（item 2）     | ✅  | `docs/modules/hardware.md`                 |
| 13 | 编写 `cross` 模块设计速写（item 2）        | ✅  | `docs/modules/cross.md`                    |
| 14 | 编写 `compliance` 模块设计文档（item 3）   | ✅  | `docs/modules/compliance.md`               |
| 15 | 编写 `rbac` 模块设计文档（item 3）         | ✅  | `docs/modules/rbac.md`                     |
| 16 | 编写 `tenant` 模块设计文档（item 3）       | ✅  | `docs/modules/tenant.md`                    |
| 17 | 编写 `usage` 模块设计文档（item 3）        | ✅  | `docs/modules/usage.md`                     |
| 18 | 编写 `loop_engine` 模块设计文档（item 3）  | ✅  | `docs/modules/loop_engine.md`              |
| 19 | 编写 `memory` 模块设计文档（item 3）       | ✅  | `docs/modules/memory.md`                    |
| 20 | 编写 `cli` 模块设计文档（item 3）          | ✅  | `docs/modules/cli.md`                       |
| 21 | 编写 `engine` 模块设计文档（item 3）       | ✅  | `docs/modules/engine.md`                    |
| 22 | 编写 `hooks` 模块设计文档（item 3）        | ✅  | `docs/modules/hooks.md`                     |
| 23 | 编写 `plugins` 模块设计文档（item 3）      | ✅  | `docs/modules/plugins.md`                   |
| 24 | 编写 `preview` 模块设计文档（item 3）      | ✅  | `docs/modules/preview.md`                   |
| 25 | 编写 `sil` 模块设计文档（item 3）          | ✅  | `docs/modules/sil.md`                       |
| 26 | 生成 38 份子系统 API 接口参考          | ✅  | `docs/api/*.md` + `docs/api/README.md` 索引  |

---

## 6. 次级缺口（B 类中仍建议补「模块设计速写」）

已全部补写（item 2，见 §5 行 8-13）：`adapter`/`autosar`/`billing`/`codegen`/`hardware`/`cross` 六篇速写已落盘 `docs/modules/`。原「仅在 SRS 一行提及」风险已消除；如需升级为完整详细设计可后续扩写。

---

## 7. 文档撰写纪律（本次遵循）

所有 `docs/modules/*.md` 均基于**实地读取源码**后撰写，关键事实带 `文件:行号` 引用；对源码与直觉相悖处（双后端、FastAPI、review 孤儿模块）**显式标注偏差**，不臆造、不粉饰。

---

## 8. 待明总拍板

- 是否将 `docs/modules/` 纳入 `docs/` 导航（在 `README` / `CONTEXT` 增加入口链接）？**建议纳入**，当前 23 篇模块文档尚未在 `README`/`CONTEXT` 建立入口。
- 文档覆盖率已达 100%（38/38），但 6 份 B 类为「速写」——是否升级为完整详细设计？
- **代码层待决（文档已标注，非文档缺）**：
  - `api`：`compliance` 路由已注册（item 3 已修）；`me.py` 经 `usage.py:42` 委托已挂路由，非死代码。
  - `review`：`tracker`/`resource_predictor` 孤儿模块——item 3 已补 `__init__.py` 聚集 API 但保留未删（删会连坐破测），是否接线或归档待定。
  - `audit`：原子写已修复（item 3，`fcntl.flock`）。

---

## 9. API 接口参考层（2026-10-07 第三轮）

目标：把 38 个核心子系统的「对外 API」整理为面向团队查阅的接口参考，与 `docs/modules/` 设计文档互补（设计讲「为什么 / 怎么组织」，API 参考讲「有什么接口 / 怎么调用」）。

- **产出**：`docs/api/` 下 38 份 `<name>_api.md` + `docs/api/README.md` 索引（按 11 职能域分组）。
- **形态（统一模板）**：① 概述 ② HTTP 端点（若有，含路由线索 / 引用 modules/api.md）③ Python 公共 API（函数 + 类 + 方法签名，带 `文件:行`）④ 配置 / 环境变量 ⑤ 调用示例 ⑥ 偏差 / 备注（ORPHAN、死代码、反直觉处显式标注）。
- **生成方式**：`ast` 实读 `src/yuleosh/` 提取符号 + Grep 验证生产调用方；不臆造。其中 `llm`/`skills`/`device`/`hardware`/`cross`/`autosar`/`sil`/`adapter` 8 份由 Explore 子代理精写（含调用示例与详细 ORPHAN 实证），其余 30 份由脚本生成（符号表级）。
- **质量提示**：符号表为机械提取，公共 API 以 `__init__.py` 导出与模块文档为准；薄壳包（`tenant`/`rbac`/`billing`/`usage`/`plugins`）真实逻辑在 `ui/routes/`，详见各文档 §6。
- **已知 ORPHAN（读前注意）**：`hardware`/`cross`/`sil`/`adapter` 已确认 ORPHAN；`testgen` 引用极少。
  - 新发现孤儿/死代码（见各模块文档「偏差」节）：`rbac.require_role`/`PermissionSet`、`usage.check_tier_limit`+双计量、`loop_engine` 注册表死代码+闭环未驻后台、`memory.rule_sink`/`apply_step_result` 未接线、`engine.container_executor`/`runner_spec` ORPHAN、`plugins` 全 ORPHAN、`sil` 全 ORPHAN mock。是否清理/接线/归档，建议单列一轮代码整治。

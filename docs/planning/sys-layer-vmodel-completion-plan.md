# 补全流程落地方案：让 yuleOSH 完全支撑 ASPICE V 模型

> 关联评估：`docs/planning/product-vmodel-gap-assessment.md`
> 日期：2026-10-08
> 目标：补齐 V 模型左半（SYS.1–5）+ 系统/软件验证确认 + 真实目标/HIL 合格性，使"从需求→开发→测试"端到端可审计。
> 非目标：不改产品内核（SWE.1–6 已可用）；不涉商业化特性（私有 LLM / 插件市场 / 非 C 等）。

---

## 0. 总体架构：V 模型 × yuleOSH 阶段

| V 活动 | ASPICE | 新增阶段 | 对应步骤（key） |
|---|---|---|---|
| 涉众/系统需求 | REQ / SYS.1–2 | S0 系统需求 | `sys-requirements` → `sys-architecture` → `sys-req-review` |
| 系统验证/确认 | SYS.3–5 | S0b 系统验证 | `sys-integration` → `sys-validation` |
| 软件需求 | SWE.1 | G1（已有） | spec-check / super-analysis / prd / prd-review |
| 软件架构 | SWE.2 | G2（已有） | architecture / arch-review |
| 详细设计&编码 | SWE.3 | G3（已有） | development / ... |
| 单元/集成测试 | SWE.4–5 | G6–G7（已有） | verify-loop / c-unit-test / code-review / integration-test / qemu-verify |
| 合格性测试 | SWE.6 | G10 扩展 | `test-qualification` + **`hil-verify`（新增）** |

阶段顺序保持现有 `PIPELINE_STEPS` 的 G1–G10 不变，仅在**头部插入 S0/S0b 组**、在 **G10 增补 `hil-verify`**。

---

## 1. Phase A：需求前移 + SYS 层（P0）

### A1. 系统级合规 profile（SYS.1–5）

- **新建** `src/yuleosh/compliance/profiles/aspice_sys_v3.1.yaml`，与 `aspice_v3.1.yaml` **同结构**（顶层 `meta` + `sys.1`~`sys.5` 区域键）。
- **零代码改动接入**：`compliance/profile.py` 是通用 loader，新增标准"只需提供同样结构的 yaml，无需改动 dataclass"（`profile.py:9,84,169-175`）。`ProcessArea`/`BasePractice`/`EvidenceSpec` 已支持任意 area 键。
- 区域与证据建议：
  - `sys.1` 系统需求分析 → `docs/system-requirements.md`
  - `sys.2` 系统架构设计 → `docs/system-architecture.md`
  - `sys.3` 系统验证（含集成测试计划）→ `docs/system-verification.md`
  - `sys.4` 系统集成 → `docs/system-integration.md`
  - `sys.5` 系统确认 → `docs/system-validation.md`

### A2. 需求前移步骤（REQ/SYS.1–2）

- 在 `step_handlers/__init__.py:176` 的 `PIPELINE_STEPS` **头部**插入 S0 组（与现有条目同构，四元组 `(key, agent, name, handler)`）：
  - `("sys-requirements", "小明", "系统需求获取", step_sys_requirements)`
  - `("sys-architecture", "Claude", "系统架构设计", step_sys_architecture)`
  - `("sys-req-review", "小克", "系统需求/架构评审", step_review_sys)`
- 新增 handler 文件 `step_handlers/sys_requirements.py` 等，签名沿用 `def step_x(session: PipelineSession) -> str`（`spec.py:45`、`analysis.py:152` 同模式）。
- 将现有 `spec-check` 重定义为"系统需求→软件需求分解（SWE.1）"，在 `alm/traceability.py` 建立 **`SYS.x → SWE.1`** 追溯链路（复用现有追溯引擎）。

### A3. 系统验证/确认步骤（SYS.4/SYS.5）

- `sys-integration`：系统集成测试计划/证据；仿真层可复用 QEMU 多目标能力。
- `sys-validation`：系统确认（用户场景验收），复用 `test-qualification` 框架扩展，产出 `docs/system-validation.md`。

**A 阶段验收**：`yuleosh compliance check --profile aspice_sys_v3.1` 能产出 SYS.1–5 证据清单；跑一个含 S0 组的 demo，`gate-summary.json` 含 SYS 区且非 `not-run`。

---

## 2. Phase B：SWE.6 做实（真实目标/HIL）（P1）

### B1. HIL 适配器接入流水线

- **现状**：`src/yuleosh/device/{registry,allocator,pool,watchdog}.py` 已实现设备管理层，但**未接入流水线**——`PIPELINE_STEPS` 仅 `fault-injection` 接入（`__init__.py:233`），无 `HilTestRunner` 步骤。
- **新增** `step_handlers/hil_verify.py`：`step_hil_verify(session) -> str`
  1. 经 `device.allocator` 分配目标板（registry/allocator 已存在）；
  2. 调 Flash 抽象层（`FlashTool`/`FlashRunner`，spec RS-009.1）刷写 `.elf`；
  3. 经 `HilTestRunner`（RS-009.2 指令 `expect/assert/wait/read_until`）跑系统级测试；
  4. 结果写入 `evidence/`，关联 SWE.6。
- 在 `PIPELINE_STEPS` 的 G10 区、`test-qualification` 后插入 `("hil-verify", "小克", "HIL 真实目标验证", step_hil_verify)`（:241 后）。

### B2. SWE.6 合格性双轨

- `test-qualification`（:241）扩展为"仿真 + 真实目标"双轨：**无 HIL 环境时降级仿真**（保留当前行为，避免破坏现有 SWE 链路），**有设备时跑真实目标**。
- 在 `gates.py:58` 的 `GATES` 增加 SWE.6 区，关联 `test-qualification` + `hil-verify`（GATES 是门禁↔步骤的稳定契约，:23-24）。

**B 阶段验收**：设备在线时 `hil-verify` 真实刷写并产出 HIL 证据；离线时降级仿真且不阻塞；GATES 含 SWE.6 门禁且 `classify_run_outcome` 正确聚合。

---

## 3. Phase C：文档与信号治理（消除"一直在修"）（P0/P1）

### C1. 蓝图对齐

- `blueprint.md:103-114,128-129` 的 "36 步 / 34/34 全绿" → 修正为实际步数（含 SYS 步骤后更新）；补 SYS/HIL 能力说明，删除"设计已定"中已落地的项。

### C2. 权威追溯矩阵

- 以 `yuleosh traceability check` 输出为**唯一权威源**，自动生成矩阵并落库；`requirement-traceability-matrix.md` 的 v1 快照降为历史参考（其头部已自注不可作对外证据，:1-6,119）。

### C3. 测试信号治理

- 固化"文档即代码"快照：CI 中生成证据指纹；内部易变处（如 context-only 提示词改版）走**契约测试**而非逐用例改写。
- 门禁契约测试 `test_step_handlers_init_deep.py` 的 `GATES` 断言（gates.py:23-24）**扩展覆盖新增 SYS/HIL 步骤**，防步骤/门禁漂移。

**C 阶段验收**：蓝图/矩阵与实际代码一致；CI 复验"全绿"可信（失败数=真实产品问题，非过期/沙箱假错）。

---

## 4. 实施路线与里程碑

| 里程碑 | 周期 | 内容 | 依赖 |
|---|---|---|---|
| M1 | 2 周 | SYS profile + S0/S0b 三步 + 追溯链（A1/A2/A3） | 无 |
| M2 | 3 周 | HIL 接入 + SWE.6 双轨（B1/B2），设备管理层联调 | 设备硬件/模拟器 |
| M3 | 1 周 | 文档治理 + 权威矩阵 + 测试信号（C1–C3） | M1/M2 |

**端到端验收 demo**：以 `projects/gpio-led-chaser`（含系统级 spec）跑通 SYS+SWE 全链路，`gate-summary.json` 含 SYS.1–5 + SWE.1–6 全 `passed`，证据包含 SYS+SWE 双链路 + HIL（在线时）。

---

## 5. 风险与回退

- **风险：SYS 步骤若纯 LLM 生成证据，易假绿** → 复用 `review-critical-safety` 的**确定性门禁模式**（cppcheck 风格，`__init__.py:230`）对 SYS 产物做结构/必需章节校验，非 LLM 判绿。
- **回退**：新增步骤可经 `OSH_NA_GATES`（gates.py:659）豁免，不阻塞现有 SWE 链路；HIL 离线自动降级仿真。

---

## 6. 验收准则（DoD）

1. 合规 checker 能加载 SYS profile 并产出 SYS.1–5 证据清单（零 dataclass 改动）。
2. `PIPELINE_STEPS` 含 S0/S0b 组与 `hil-verify`，`GATES` 含对应门禁。
3. 一个 dogfood 项目从系统需求→软件→测试→合格性全绿，证据包含 SYS+SWE 双链路（在线含 HIL）。
4. 文档（蓝图/矩阵）与实际代码一致，CI 中可复验；失败信号可信。

# SYS 层孤岛模块消除方案（M1.5 专项）

> 生成日期：2026-10-08 · 关联里程碑：M1（SYS 层已落地但未接入下游）
> 诊断方法：代码库静态审计 + 全仓 Grep 实证（所有结论带 `文件:行` 证据，无臆测）
> 目标：把 M1 新增的 SYS.1–5 模块真正并入 V 模型闭环，使其「可追溯、被消费、可可视化」

---

## 0. 背景与诊断范围

M1 已落地 SYS 层（profile + 6 个确定性 handler + G0 门禁 + 追溯 sidecar），产物均在本地未提交。
但审计发现：**SYS 层在架构里是"孤岛"**——它生成了 `docs/system-*.md` 与 `sys-to-swe-trace.json`，
却没有下游消费、没有并入追溯矩阵、没有在报告/仪表盘/前端展示、SWE.1 也不读它的需求。

**本次审计排除的伪孤岛**（经实证非孤岛，不纳入本方案）：
- `step_review_embedded_*` / `step_review_bsp` / `step_review_timing` / `step_review_memory` /
  `step_review_selftest` 等虽未直接进 `PIPELINE_STEPS`，但被聚合 handler 调用：
  - `code_review_unified.py:50,62` → `embedded-runtime`（内含 `memory` 子项 `review_embedded_runtime.py:33,46`）
  - `verify_loop.py:48,68` → `self-test-review`（`step_review_selftest`）
  - `review_embedded_peripheral.py:32` / `review_embedded_realtime.py:35,46` → `bsp` / `timing`
  - 属子步骤，由 `code-review` / `verify-loop` 等顶级步骤聚合执行，链路完整。

---

## 1. 四重孤岛定位（证据）

### 孤岛①：追溯断层（sys-to-swe-trace 孤写不读）
| 项 | 证据 |
|---|---|
| 写入 | `pipeline/step_handlers/sys_layer.py:115-129` `_record_sys_swe_trace` 写 `.osh/evidence/sys-to-swe-trace.json`（SYS-REQ → SWE.1） |
| 读取器 | `alm/traceability.py:1567` `load_sys_swe_trace(project_dir)` 已提供 |
| 调用方 | **零**。全仓 Grep `load_sys_swe_trace` 仅命中定义处（traceability.py:1567/1601）与写入侧（sys_layer.py:115）。**无任何模块消费该映射** |
| 后果 | V 模型「系统需求 ↔ 软件需求」双向追溯断裂；ALM 主矩阵不含 SYS-REQ 条目 |

### 孤岛②：上游断链（SWE.1 不读 SYS 需求）
| 项 | 证据 |
|---|---|
| SWE.1 实现 | `pipeline/step_handlers/spec.py:45` `step_spec_check`（OpenSpec 合规 + 契约机器校验，line 47-100） |
| 是否读 SYS | **否**。该函数不引用 `docs/system-requirements.md`、不读 `SYS-REQ-*`、不调用 `load_sys_swe_trace` |
| 后果 | SYS.1 产出的系统需求未作为 SWE.1 的上游输入；V 模型左半「系统→软件」链路断开（仅 M1 建了正向映射文件，SWE 侧无感知） |

### 孤岛③：可视化盲区（报告/dashboard 不展示 SYS 区 + G0）
| 项 | 证据 |
|---|---|
| `api/dashboard.py` | 仅 SWE.1~6（`dashboard.py:83` / `:568` / `:592`）。Grep `G0\|sys\.\|SYS` **零命中** → 不展示 G0 门禁、不展示 SYS 区状态 |
| `evidence/evidence_check.py:347` | 仅 SWE.1~6 状态字典 |
| `ci/dashboard_writer.py:52` | 仅 SWE.1~6 列表 |
| `report/audit_report.py:10` | docstring 提 SYS.1–5，但实现只 SWE.1（`audit_report.py:119/246/549/567`）→ SYS 区被 ComplianceChecker 产出（`swe_sections` 含 `sys.1~5`，M1 已验证）但下游报告不渲染 |
| G0 门禁本身 | **不是孤岛**：`gates.py:176/566/578/789` 均 `for g in GATES` 遍历，G0 在表头 → 门禁引擎已正确纳入 run 级门禁计算；但**可视化层看不到** G0 状态 |

### 孤岛④：前端盲区
| 项 | 证据 |
|---|---|
| `frontend/` | Grep `G0\|sys-requirements\|sys\.1\|SYS\.1` **零命中**（仅 `package-lock.json` 无关 sha 命中）→ 流水线步骤图、gate 状态面板、合规面板均不展示 SYS 步骤 + G0 门禁 |
| 后果 | 用户在前端完全看不到 M1 新增的 6 步 + G0，M1 价值不可见 |

---

## 2. 方案：四条打通链路

### 链路 A — 消除孤岛①：SYS 映射并入 ALM 主追溯矩阵
- **改动**：在 ALM 主追溯聚合点（候选 `ci/agent_traceability.py` 或 `ci/stages/traceability.py` 的矩阵构建函数）读取 `load_sys_swe_trace(project_dir)`，将 `sys_to_swe` 并入主矩阵，使 SYS-REQ 条目与 SWE.1 互链。
- **新增 API 使用**：`traceability.py:1567` 已有读取器，零新增依赖。
- **测试**：断言主矩阵含 `SYS-REQ-xxx → SWE.1` 双向条目。

### 链路 B — 消除孤岛②：SWE.1 消费 SYS 上游需求
- **改动**：`spec.py:step_spec_check` 在契约校验后（line ~100 之后）追加确定性校验：
  - 若 `docs/system-requirements.md` 存在，读取其 `SYS-REQ-NNN` 清单，校验 spec 中是否显式引用（建立 SWE.1 → SYS 反向链接）；缺失则记 WARNING 并回写 `sys-to-swe-trace.json` 的反向索引，**不阻断主流程**（避免破坏既有绿色）。
- **边界**：仅做「引用存在性」机器校验，不做语义评审（语义评审属 LLM 范畴，超出确定性门禁）。

### 链路 C — 消除孤岛③：报告 / 仪表盘展示 SYS 区 + G0
- `api/dashboard.py`：swe-status 扩展为读取 `compliance_checker` 的 `swe_sections`（已含 `sys.1~5`），或新增 `sys_status` 字段；gate 状态面板遍历 GATES（已含 G0）。
- `evidence/evidence_check.py:347`：补充 SYS.1~5 区状态定义。
- `report/audit_report.py`：实现 SYS 分支（当前仅 docstring 占位）。
- `ci/dashboard_writer.py:52`：补充 SYS 区。
- **测试**：dashboard 单测覆盖 SYS 区 + G0 展示。

### 链路 D — 消除孤岛④：前端展示 SYS 步骤 + G0
- 后端 `api/pipeline_steps.py` / `dashboard.py` 已暴露 30 步 + G0（编排层数据完整），前端步骤图按阶段分组渲染「系统层 (SYS.1–5) + G0」区块与门禁徽标。
- **复核**：需本机终端起服务 + 浏览器截图（sandbox 命名空间隔离，AI 起的服务浏览器连不上）。

---

## 3. 验证与提交纪律

- **零回归**：pytest 影响闭包 A/B（sys_layer / traceability / spec / dashboard 改动）+ 契约测试
  `test_step_handlers_init_deep.py` / `test_pipeline_extended.py` + 新增 SYS 可视化/追溯测试。
  固定参数：`-o addopts= --no-cov -p no:cacheprovider -p no:randomly --basetemp=/tmp/xxx`。
- **分笔提交**（后端，不推送待明总指示）：
  1. 链路 A：traceability 主矩阵消费
  2. 链路 B：spec-check 上游校验
  3. 链路 C：dashboard + report + evidence_check + dashboard_writer
  4. 链路 D：前端（独立 commit，不与后端混合）
- **前端复核**：D 链路完成后需明总本机起服务截图确认渲染，再提交。

---

## 4. 与 M 里程碑关系 & 边界

- 本方案 = **M1.5（孤岛消除专项）**，是 M1 的「下游接入」补全。M1 已落地但不可见/不可追溯，
  不消除则 M1 交付价值存疑；建议独立快速闭环，不阻塞 M2/M3。
- **不在本方案范围（边界）**：
  - M3 的 `ComplianceChecker` SYS 启发式补全（让 SYS 区 BP 判 ✅ 而非仅识别证据）——属 checker 信号治理。
  - 更广模块碎片化审计（`autosar/`、`billing/`、`kb/`、`kg/` 等是否接入主流水线编排）——若明总指的为该类孤岛，需另开专项审计。

---

## 5. 待明总拍板

1. 是否按 M1.5 四链路推进（A/B/C/D）？还是仅做可见性最低的 A+B（追溯+上游），C+D 延后？
2. 孤岛④（前端）是否本轮一并做，还是留待前端统一化阶段？
3. 若「孤岛模块」另有所指（如功能模块碎片化），请指明范围，我另开审计。

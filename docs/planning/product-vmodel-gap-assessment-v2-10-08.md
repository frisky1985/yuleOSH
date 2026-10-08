# yuleOSH 是否支持 ASPICE V 模型开发流程 —— 复评（v2，M1/M1.5 之后）

> 复评日期：2026-10-08（M1 SYS 层 + M1.5 孤岛打通已落地后）
> 复评对象：`main @ 6075aa90`（已推送远程）
> 方法：**直接取证**（读代码 + 实跑合规引擎），非记忆复述；含对抗性核验（专门找"假绿"）
> 与 v1 的关系：v1（同目录 `product-vmodel-gap-assessment.md`）为 M1 之前结论；本文为复评，含实测数据

---

## 1. 结论（先给答案）

**分级回答，不能简单说"支持"或"不支持"：**

| 问题 | 答案 |
|---|---|
| 能否产出完整 V 模型两侧的**过程与证据骨架**？ | ✅ **能** —— 现已覆盖左半 SYS.1–5 + 右半 SWE.1–6，共 11 个过程域、30 步流水线、11 道 Gate |
| 能否作为**真实可用的 V 模型开发流程**（需求驱动开发）？ | ⚠️ **还不能完全算** —— 左半是"由 spec 反推"而非"由涉众需求驱动"，且 SYS→SWE 链接**不强制** |
| 产出的合规证据能否**直接对外/审计**？ | ❌ **暂不能** —— 实测存在 2 类会经不起审计的问题：**假绿**（借用无关信号判过）与**追溯不实质** |

一句话：**从"只覆盖 V 的右半"进化到了"两侧骨架齐全"，但从"骨架齐全"到"流程真实可用、证据可审计"还剩三个硬缺口（M2 HIL 假绿、M3 判绿启发式、左半语义倒置）。**

---

## 2. M1/M1.5 带来的真实变化（相对 v1）

| v1 判定 | v1 证据 | 复评现状（本次实测） |
|---|---|---|
| ❌ 无 SYS 过程 | 唯一 profile 仅 SWE.1–6 | ✅ 已闭环：`compliance/profiles/aspice_sys_v3.1.yaml`（SYS.1–5，13 个 BP）已存在并被 loader 正常装载 |
| ❌ 流水线无系统级步骤 | `PIPELINE_STEPS=24` 全 SWE | ✅ 已闭环：头部新增 6 步 SYS（`__init__.py:195-203`），`PIPELINE_STEPS=30` |
| ❌ G0 无门禁 / 不可见 | dashboard 仅 SWE | ✅ 已闭环：GATES 含 G0（11 道），M1.5 让 dashboard 暴露 `sys_status`+`gates` | 
| ❌ SYS 追溯孤写不读 | `sys-to-swe-trace.json` 零调用方 | ✅ 已闭环：M1.5 并入 `generate_lrt`/`report_builder`/`api/matrix`（`sys_trace` 段） |
| ❌ SWE.1 不消费 SYS 上游 | `spec.py` 只读 OpenSpec | ✅ 已闭环（**但见 §4.2**：仅告警，不阻断） |
| ⚠️ SWE.6 仿真级无 HIL | 无 HIL 步骤 | ❌ **仍未闭环**：见 §4.4，且新增了"假绿"风险 |
| ❌ 追溯 v1 快照不可信 | 自注"不可作对外证据" | ⚠️ **部分闭环**：权威 CLI 存在（见 §4.5），但默认未落盘为"实质矩阵" |
| ❌ 文档漂移 36 vs 24 | blueprint 写 36 | ❌ **仍未闭环**：blueprint 仍写 36（`blueprint.md:103,111,128`），实际已 30 |

---

## 3. 合规引擎实测（本次跑出来的真实数据）

方法：对同一工程目录实跑两个 profile，打印逐 BP 判定。
探针：`/tmp/sys_compliance_probe.py`（临时产物，未入库）。

| 过程域 | BP 全绿数 | 实测判定摘要 |
|---|---|---|
| SYS.1 | 0/3 | 证据识别 ✅，但"追溯至涉众需求"❌ |
| SYS.2 | 0/3 | ❌ 架构文档"no substantive content"（仅 595B） |
| SYS.3 | 0/2 | ❌ **"unknown check type — not recognized"**（判不了） |
| SYS.4 | 2/3 | ✅ 部分绿（**但借用了集成测试结果**，见 §4.4） |
| SYS.5 | 0/2 | ❌ 同上 unrecognized；无目标环境证据 |
| SWE.1–6 | 6/18 | 详见下方重要说明 |

> ⚠️ **读数前提（避免误读，重要）**：本探针跑的是 **yuleOSH 自身仓库**（一个 Python 工程）作为"被测项目"。因此 SWE 侧大量 `❌ Missing evidence: SRS / architecture doc / qualification strategy` 是**因为该仓库本就没有这些 C/嵌入式交付物**，不代表工具能力不足。**请只看结构结论与具体缺陷，不要把上表的分数当作产品能力评分。**

---

## 4. 仍然存在的硬缺口（按审计风险排序）

### 4.1 ❌【最高危】左半语义倒置：SYS 由 spec 反推，而非驱动 spec
- 证据：`sys_layer.py:82-104` `_extract_functional_areas()` **从 spec 的 Markdown 标题派生**功能域；`:126` sidecar 自述 *"SYS 系统需求向上追溯至 SWE.1 软件需求（spec 派生）"*。
- 含义：真实 ASPICE 流向是 **涉众需求 → SYS.1 → SWE.1**；本系统是 **spec(SWE.1 输入) → 反推 SYS.1**。左半是**事后重建**，不是真正的先后驱动。
- 影响：能产出"看起来完整"的左半文档链，但**不满足"需求驱动开发"的本意**，也拿不出涉众需求（REQ./Stakeholder）证据。
- 建议：若要真做 V 左半，需引入**涉众需求输入源**（而非 spec 派生），并让 spec 改由 SYS 需求派生。属新增 P0，工作量大于 M1。

### 4.2 ⚠️【高危】SYS→SWE 链接是"告警"，不参与门禁
- 证据：M1.5 的 `_check_sys_requirements_aligned`（`spec.py`）**缺失仅 WARNING 不 raise**，写 `sys-spec-alignment.json` 但不断流。
- 影响：SYS 与 SWE.1 脱节时**流水线照样全绿通过**，V 模型连续性只是"被记录"而非"被强制"。
- 建议：至少在与 aspice 严格 profile 联动时升级为阻断（保留向后兼容开关）。

### 4.3 ⚠️【高危】判绿启发式不认识 SYS 内容（M3 未做）
- 证据：实测 `SYS.3.BP1/BP2`、`SYS.5.BP1/BP2` 直接返回 **"unknown check type — not recognized"**；`SYS.2` 判 `no substantive architecture doc found`（595B 未达实质阈值）。
- 现状：所有 13 个 SYS BP 的**证据路径都被识别**（✅ Evidence found，说明 M1 路径对齐有效），但**内容级判定基本拿不到绿**。
- 影响：SYS 区域现在呈"有证据、判不过"的中间态，既非假绿也非真绿。

### 4.4 ❌【审计高危】SWE.6/HIL 的**假绿**——本次复评最应警惕项
- 证据（`aspice_v3.1` 实测输出）：
  ```
  SWE.6.BP2  ✅
      ✅ Evidence found: Qualification test results
      ❌ Missing evidence: SIL/HIL test results          ← 同一 BP 内部自相矛盾
      ✅ Check: Tests are executed in target or equivalent environment
                 (567 test files, suite passed)          ← 用" pytest 用例数"充当"目标环境执行"证据
  ```
- 根因：`compliance_checker.py:1098-1106` 的 "test" 分支以 `_count_unit_tests()` + `_test_suite_passes()` 判过；任何含 "test" 字样的检查项都会被这条路通用地判绿。
- 佐证：`src/yuleosh/device/{registry,allocator,pool,watchdog,cli,models}.py` 已实现，但 `PIPELINE_STEPS` 中 **HIL/device 零引用**（grep 无命中）→ 根本没有真机步骤，却能判"目标环境已执行"。
- 影响：**这是唯一会在客户/审计面前直接崩盘的项**——它声称在目标环境验证过，实际跑的是宿主 pytest。
- 建议（新增 P0，优先级等同或高于 M2）：① 给 "target/equivalent environment" 类检查项改用**专用证据类型**（如 `sil`/`hil` 产物校验），禁止由通用 unit-test 分支兜底；② 无 HIL 产物时强制判 ❌ 或 `n-a`，不得 ✅。

### 4.5 ⚠️ 追溯矩阵：权威 CLI 已存在，但默认未生成"实质矩阵"
- 证据：`cli/commands/traceability.py:503` 明载 `yuleosh traceability check` 可作 CI gate（由 `generate_lrt` 支撑）→ v1 的 P0"生成权威追溯矩阵"**能力已具备**。
- 但：实测 6 个 BP 报 `no substantive traceability matrix`（判定路径见 `compliance_checker.py:1085-1097`，要求 `_traceability_metrics_met()` ≥60% 或 `_has_traced_requirements()`）。
- 另有一处内部不一致：`SWE.4.BP2` 同时出现 `✅ Evidence found: Traceability matrix` 与 `❌ Check ... (no substantive traceability matrix)` —— **证据层给绿、内容层给红**，易误导。
- 建议：流水线默认落盘权威矩阵；并将"证据层绿但内容层红"的 BP 显式标记为 ⚠️ 而非静默。

### 4.6 ❌ 文档漂移未修
- `blueprint.md:103,111,128` 仍宣称 **36 步**；实际 `PIPELINE_STEPS=30`（`__init__.py:18`）。v1 已列为 P0，仍未闭环。

### 4.7 ⚠️ 测试信号仍不可直接当真
- 基线仍约 125 failed（仅 A 类死 mock 部分整改）；本轮复评另发现 gated E2E `test_e2e.py::test_e2e_pipeline_full_flow` 因 M1 新增 SYS 步而在真实仓库下 `session.status!="completed"`（已单独记录待 triage）。

---

## 5. 最终判定表

| 维度 | 判定 | 依据 |
|---|---|---|
| V 左半（SYS.1–5）**结构** | ✅ 已具备 | profile + 6 步 + G0 + 证据路径对齐 |
| V 左半 **语义正确性** | ❌ 倒置 | SYS 由 spec 派生（§4.1） |
| V 右半（SWE.1–6）**结构** | ✅ 完整 | 沿用既有 24 步 + profile |
| SWE.4/5 单元测试/集成 | ✅ 真实可用 | 确定性 cppcheck P0 门禁、Unity、QEMU SIL、MISRA |
| SWE.6 合格性 | ❌ 仿真级 + **假绿** | §4.4，无 HIL，却判"目标环境"绿 |
| 双向追溯 | ⚠️ 能力有、默认不实质 | §4.5 |
| 门禁强制性 | ⚠️ SYS 段偏软 | §4.2 告警不阻断；P0 cppcheck 是真硬门禁 |
| 对外审计可用性 | ❌ 暂不可直接交付 | §4.4 假绿 + §4.5 追溯 + §4.6 漂移 |

---

## 6. 建议优先级（相对 v1 的变更）

- **P0-新①（最高）**：消除 SWE.6/HIL 假绿 —— 专用证据类型替代通用 unit-test 兜底，无 HIL 产物强制 ❌/n-a。（新增，v1 未识别，本次选出）
- **P0-新②**：左半语义正位 —— 引入涉众需求输入源，让 spec 由 SYS 需求派生。（v1 未展开）
- **P0**：SYS→SWE 链接升级为可配置阻断（默认放行、严格 profile 阻断）。
- **P1（原 M2）**：HIL 接入 —— 把已实现的 `device/` 层接进流水线，让"目标环境执行"有真实来源（`cerebro` 层已有雏形）。
- **P1（原 M3）**：checker 启发式扩展支持 SYS 交付物内容判绿，消除 "unknown check type"。
- **P1**：修 `blueprint.md` 36→30 步漂移 + 流水线默认落盘权威追溯矩阵。
- **P2**：`.gitignore` / 测试信号治理（沿用 v1）。

---

## 7. 附：本次复评取证清单

| 结论 | 证据位置 |
|---|---|
| SYS profile 存在 | `compliance/profiles/aspice_sys_v3.1.yaml`（SYS.1–5 / 13 BP） |
| PIPELINE_STEPS=30 | `pipeline/step_handlers/__init__.py:18,195-271` |
| GATES=11（含 G0） | `pipeline/gates.py`（G0 在表头） |
| SYS 由 spec 派生 | `pipeline/step_handlers/sys_layer.py:82-104,126` |
| 假绿判定逻辑 | `compliance/compliance_checker.py:1098-1106` |
| 追溯判定逻辑 | `compliance/compliance_checker.py:1085-1097` |
| device/HIL 未接入 | `src/yuleosh/device/*` 存在；`step_handlers/__init__.py` grep `hil/HIL/device.` 零命中 |
| 权威追溯 CLI 存在 | `cli/commands/traceability.py:134,503` |
| blueprint 漂移 | `docs/product/yuleOSH-product-blueprint.md:103,111,128`（写 36） |
| 实测逐 BP 输出 | 探针 `/tmp/sys_compliance_probe.py`（临时，未入库） |

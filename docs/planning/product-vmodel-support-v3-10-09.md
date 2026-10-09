# yuleOSH 对 ASPICE V 模型开发工作流的支持度评估（v3，2026-10-09）

> 评估方法：实证三轮交叉核查。①直接取证（读源码 + 实跑合规引擎）；
> ②对抗性复核（假设"已全支持"错误，专扫残留假绿向量）；
> ③对高影响结论自行复验后标注「成立/修正/存疑」。
> 基线：v2 评估 `product-vmodel-gap-assessment-v2-10-08.md`；本轮在 v2 之后已落地
> SYS.4 + SWE.6 反假绿修复（提交 `f673688d`/`8939b595`，已推送）。

## 0. 结论摘要（直接回答明总）

**不能声称"完全支持"V 模型开发工作流。** 准确表述为：

> yuleOSH 已具备支撑 ASPICE V 模型**工程过程**（SYS.1–5 系统层 + SWE.1–6 软件层）
> 的**骨架与合规判定能力**，覆盖 30 步流水线 + 11 个 Gate 视图，且关键假绿
> （SYS.4 / SWE.6 被单测顶替）已清除。但在以下三处仍**不能完全支撑真实汽车项目的
> V 模型交付**，需补强后才算闭环：
> 1. **SWE.6 端到端"目标或等效环境执行"证据链断开**（P0）；
> 2. **SYS→SWE 左→右追溯链不强制**（默认仅 WARNING，P1）；
> 3. **SUP/MAN 支持与管理过程无独立评估域**（P2，范围待定）。

读盘纪律提醒：拿 yuleOSH 自身仓库跑合规引擎，SWE 侧大量 `missing evidence` 仅因
该仓库非汽车交付物（无 C/嵌入式目标环境产物），**禁止当作产品能力缺陷评分**；
本评估仅以"结构/能力支持度"为口径。

---

## 1. V 模型工程过程覆盖度（成立）

| 过程域 | 流水线步骤（文件:行） | Profile 域 | Checker 识别 |
|---|---|---|---|
| SYS.1 系统需求分析 | `sys-requirements`（step_handlers/__init__.py:198） | aspice_sys_v3.1.yaml | ✅ |
| SYS.2 系统架构设计 | `sys-architecture`（:199） | 同上 | ✅ |
| SYS.3 系统验证规划 | `sys-verification`（:200） | 同上 | ✅ |
| SYS.4 系统集成与集成测试 | `sys-integration`（:201） | 同上 | ✅（反假绿已修） |
| SYS.5 系统确认 | `sys-validation`（:202） | 同上 | ✅ |
| SYS 确定性门禁 | `sys-req-review`（:203） | — | — |
| SWE.1 软件需求 | `spec-check`/`prd`/`prd-review`（:206–212） | aspice_v3.1.yaml | ✅ |
| SWE.2 软件架构 | `architecture`/`arch-review`（:215–217） | 同上 | ✅ |
| SWE.3 详细设计与编码 | `development`/`codegen-deploy`/`internal-code-review`（:220–225） | 同上 | ✅ |
| SWE.4 单元验证 | `verify-loop`/`c-unit-test`（:240–241） | 同上 | ✅ |
| SWE.5 软件集成与集成测试 | `code-review`/`integration-test`/`qemu-verify`/`coverage-review`（:245–255） | 同上 | ✅ |
| SWE.6 合格性测试 | `test-qualification`（:269） | 同上 | ✅（判定已修，但**证据链断**，见 §3） |

- `PIPELINE_STEPS = 30` 步（step_handlers/__init__.py:194），左半 G0 含 SYS.1–5 共 6 步。
- `gates.py` 含 **11 个 Gate 视图 G0–G10**（gates.py:8 注释 "11 Gate 视图"；G0 定义 :63，G10 :126），与 ASPICE 过程域对齐。
- **实跑合规引擎**：`aspice_sys_v3.1` 与 `aspice_v3.1` 两 profile 的 `unknown check type` 计数均为 **0**（11 个过程域全部 check_item 均有判定分支）。
  - 对比 v2：v2 评估时 SYS 侧曾有 **4 个 `unknown check type`**（13 BP 全绿仅 2），本轮 T3 左半修复后已归零 —— **成立，且为实质性改善**。

---

## 2. 反假绿状态（成立）

| 假绿向量 | 状态 | 证据 |
|---|---|---|
| SYS.4 系统集成被单测顶替 | ✅ 已修 | compliance_checker.py:1303–1358（`_is_sys_area` 执行类走 `_sys_execution_record`，禁用 `_test_suite_passes`）；提交 `7a402c9c` |
| SWE.6 合格性测试被单测顶替 | ✅ 已修 | compliance_checker.py:1210–1217（`swe_id.upper()=="SWE.6"` 专用分支走 `_has_sil_results`）；提交 `f673688d` |
| 跨域误判（SYS 区查 SWE 的 integration-strategy.md） | ✅ 已修 | SYS 区 `stub/driver` 改查 `docs/system-integration.md`（:1311） |

**对抗性复核（假设"已全支持"错误，专找反例）**：
- 全仓扫描 `_test_suite_passes()` 调用点，仅余：
  - `:1228` SWE.4 单元测试分支（合法，ASPICE SWE.4 单元测试本就是单测）；
  - `:1327` SWE.5 集成测试分支（**弱证据，非明确假绿**，见 §3 灰色地带）；
  - `:1360` 通用 SWE.1–3 设计/验证类 check（合法）。
- `_has_sil_results()` 已覆盖 SYS 执行分支 + SWE.6；`_ci_results_exist()` 仅作"有 CI 但无通过证据→RED"的诚实降级（:1333/:1363）。
- **结论：明确假绿向量已清零**，残留为可接受/待加强项。

---

## 3. 残余硬缺口（按优先级）

### P0 — SWE.6 端到端"目标或等效环境执行"证据链断开（存疑→确认）

- **现象**：`step_test_qualification`（SWE.6 handler，test_qualification.py:669）做的是
  spec 场景的**主机仿真 / host-sim** 执行（注释明写 "host-sim compilation"，:356–414），
  且**不产生** checker 所需的 `.osh/ci/sil-*.json`（`all_passed=True`）真 SIL/HIL 结果。
- **后果**：即便 SWE.6 handler 跑通，checker 的 `SWE.6.BP2 "Tests are executed in target
  or equivalent environment"` 仍判 **RED**（无真 SIL/HIL 结果文件）。即 yuleOSH 当前
  **无法自动产出 SWE.6 的 GREEN 证据**——要 GREEN 必须由用户手动放置 SIL/HIL 结果文件，
  或接入 HIL 台架自动产出。
- **根因**：`device/` HIL 层（allocator/registry/pool/watchdog/cli，功能完整）**未被任何
  step_handler 调用**（全仓 grep `from yuleosh.device` 仅出现在 `cli/main.py` 与
  `api/device_ui.py` 的 CLI/UI 入口，无任何 pipeline step 接入）。
- **判定**：这是"完全支持 V 模型"的**最大功能缺口**，真实汽车项目 SWE.6 必须在目标/等效
  环境执行，host-sim 不能替代。需将 device/HIL 层接入 `test-qualification`（或新增 HIL step），
  使其自动产出 checker 认可的 SIL/HIL 结果。

### P1 — SYS→SWE 左→右追溯链不强制（成立）

- `_check_sys_requirements_aligned`（spec.py:186）默认 `status=partial`（有 missing）时
  **仅 WARNING，不阻断**；严格阻断需 `OSH_SYS_ALIGN_STRICT=1`（spec.py:160–167，默认关）。
- 即：SYS 需求未被 SWE.1 spec 引用时，流水线仍全绿。左半到右半的追溯链弱。
- 建议：默认开启 `OSH_SYS_ALIGN_STRICT`，或至少在 G0 门禁体现对齐状态。

### P2 — SWE.5 集成测试弱证据（灰色地带，非假绿）

- compliance_checker.py:1327 SWE.5 集成类 check 仍用 `_test_suite_passes()` 代理"集成测试通过"。
- 严格 ASPICE 解读：SWE.5 集成测试应证明"软件单元集成为软件项并在集成环境验证"，层级高于单测。
- 当前 yuleOSH 有真实 `integration-test` handler（step_integration_test），但 checker 未消费其产物，
  而是用单测通过代理。**建议**：接 `integration-test` handler 真实产物（如 `.osh/evidence/integration-*.json`）。
- 本轮**未擅自动**（动会翻红，且与 SWE.6 同源需 HIL 基础设施），标注为待加强。

### P2 — SUP/MAN 支持与管理过程无独立评估域（成立，范围待定）

- profile 仅含 SYS/SWE 工程过程域；无 SUP.1/SUP.8/SUP.9/MAN.1 等独立检查项。
- 部分覆盖：
  - SUP.1 双向追溯性 → `traceability-matrix.{md,json}` 由 orchestrator **默认落盘**
    （orchestrator.py:365 `_emit_traceability_artifacts`，:754–755 默认调用；提交 T5 `4db475cc`）；
    profile SWE.3 BP 引用 `.osh/evidence/traceability-matrix.md`（aspice_v3.1.yaml:144）。
  - 一致性 → G9 `merge-gate` 做 KG 图一致性检查。
  - 配置管理(SUP.8)/问题解决(SUP.9)/管理(MAN.1) → 无独立评估，由 gate 体系 + session 管理部分覆盖。
- 是否纳入"V 模型支持"范围待明总界定（工程过程双 V 通常不含管理过程）。

---

## 4. 支持度总评

| 维度 | 状态 | 关键证据 |
|---|---|---|
| V 模型工程过程骨架（SYS.1–5 + SWE.1–6） | ✅ 完整 | 30 步 + 11 域 profile + unknown=0 |
| 11 Gate 视图 | ✅ 完整 | gates.py G0–G10 |
| 反假绿（SYS.4/SWE.6 不被单测顶替） | ✅ 已修 | 提交 `7a402c9c`/`f673688d` |
| 双向追溯 SUP.1 | ⚠️ 部分 | traceability-matrix 默认落盘；SYS→SWE 对齐仅 WARNING |
| 一致性 | ⚠️ 部分 | G9 merge-gate KG 一致性 |
| 目标/等效环境执行证据（SWE.6） | ❌ 断链 | test_qualification host-sim；device/ 未接入 SWE.6 |
| SUP/MAN 支持管理过程 | ⚠️ 弱 | 无独立 profile 域 |

**一句话**：工程过程双 V 的"工具链 + 合规判定"已就绪且诚实，但
**SWE.6 目标环境执行证据链未打通**是通向"完全支持"的最后一块硬骨头；
加之 SYS→SWE 对齐与 SUP/MAN 覆盖偏弱，故**当前为"强骨架、弱闭环"，距完全支持差 P0 一项 + P1/P2 补强**。

---

## 5. 建议下一步（待明总拍板）

1. **P0**：在 `test-qualification` 接入 `device/` HIL 层（或新增 `hil-qualification` step），
   使其自动产出 checker 认可的 `.osh/ci/sil-*.json`，打通 SWE.6 端到端 GREEN。
2. **P1**：默认开启 `OSH_SYS_ALIGN_STRICT`，让左→右脱节在 G0 门禁显式阻断。
3. **P2**：SWE.5 接 `integration-test` handler 真实产物；界定 SUP/MAN 是否纳入评估范围。

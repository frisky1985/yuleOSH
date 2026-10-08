# yuleOSH 产品功能完整评估（ASPICE V 模型覆盖度）

> 评估日期：2026-10-08
> 评估方法：基于代码与文档**直接取证**（非记忆复述）+ 交叉核验（含对抗性核验：SYS 覆盖、HIL/设备管理、模板数、多租户、测试真实状态）
> 证据来源：
> - `docs/product/yuleOSH-product-blueprint.md`（v1.2, 2026-08-15）
> - `docs/spec.md`（627 行，RS-001~015 + NFR/FSR/CR）
> - `src/yuleosh/compliance/profiles/aspice_v3.1.yaml`
> - `src/yuleosh/pipeline/step_handlers/__init__.py`（实际 `PIPELINE_STEPS`）
> - `docs/compliance/requirement-traceability-matrix.md`

---

## 1. 一句话结论

yuleOSH 当前真实覆盖的是 ASPICE **软件工程层（SWE.1–6）右半 V** + 一套相当完整的**分层测试/验证**（单元/集成/SIL/MISRA/故障注入/覆盖率）。但它：

- ❌ **不覆盖系统级（SYS.1–5）**——合规引擎唯一 profile 只有 `aspice_v3.1.yaml`（SWE.1–6），全仓无 SYS 过程；
- ❌ **SWE.6 合格性 = 仿真级，没有真实目标/HIL 验证**；
- ❌ **需求侧只到"写好的 spec 文档"（SWE.1），不到涉众/系统需求（REQ./SYS.1–2）**。

结论：现在是 **"AI 辅助软件工程流水线 + 合规证据自动生成"**，**还不是覆盖完整 V 模型的全部工程活动**。

---

## 2. ASPICE V 模型覆盖矩阵（实测）

| V 模型活动 | ASPICE 过程 | 覆盖 | 证据 |
|---|---|---|---|
| 客户/涉众需求 | REQ.1–4 / SYS.1–2 | ❌ 缺 | 流水线起点是 `spec-check`（SWE.1），无 REQ/SYS 过程；合规 profile 仅 SWE |
| 系统需求分析 | SYS.3 | ❌ 缺 | `aspice_v3.1.yaml` 仅 `swe.1`~`swe.6`（`profiles/aspice_v3.1.yaml:9-227`） |
| 系统架构设计 | SYS.4 | ❌ 缺 | 同上 |
| 系统集成/验证/确认 | SYS.4/SYS.5 | ❌ 缺 | 同上 |
| 软件需求分析 | SWE.1 | ✅ | `spec-check`/`super-analysis`/`prd`/`prd-review`（`step_handlers/__init__.py:178-184`） |
| 软件架构设计 | SWE.2 | ✅ | `architecture`/`arch-review`（:187-189） |
| 详细设计 & 编码 | SWE.3 | ✅ | `development`/`development-review`/`codegen-deploy`/`internal-code-review`（:192-197） |
| 单元测试 | SWE.4 | ✅ | `verify-loop`/`c-unit-test`（:212-213） |
| 集成测试 | SWE.5 | ✅ | `code-review`/`misra-review`/`integration-test`/`qemu-verify`/`coverage-review`（:217-227） |
| 安全/CM 门禁 | SWE.5/6 支撑 | ✅ | `review-critical-safety`(P0 非LLM cppcheck)/`fault-injection`/`merge-gate`（:231-238） |
| 合格性测试 | SWE.6 | ⚠️ 弱 | `test-qualification` 存在（:241），但只跑仿真+文档，无真实目标刷写 |

---

## 3. 真实已落地的强项（带证据）

- **24 步 AI Agent 流水线**对应 SWE.1–6，结构清晰（`step_handlers/__init__.py:176-243`）。
- **确定性安全门禁**：`review-critical-safety` 是 cppcheck 非 LLM 的 P0 阻断（注释 :230），非"AI 说过了"式假绿。
- **分层测试闭环实打实**：C 单元（Unity）、集成、SIL(QEMU)、MISRA、覆盖率门禁、故障注入均有 handler。
- **合规副产物真实**：`evidence/` 证据包、`alm/traceability.py` 追溯、`audit_report.py` 审计均存在。
- **多租户安全基座在**：`engine/tenant_security.py`（8 个 def，已迁移加密保险库）。
- **模板市场达标**：`templates/` 下 9 个目录（RS-011 要求 ≥5）。
- **设备管理层已实现未接入**：`src/yuleosh/device/{registry,allocator,pool,watchdog}.py` 存在，但流水线无 HIL 步骤。

---

## 4. 关键缺口（诚实列出）

1. **系统级（SYS）完全缺失**——与"满足完整 V 模型"目标的最大差距。V 模型左半（系统需求→系统架构→系统集成/验证/确认）无过程、profile 或流水线步骤。
2. **SWE.6 合格性是仿真级**——无 HIL/真实目标刷写。`PIPELINE_STEPS` 仅接 `fault_injection`（:233），无 `HilTestRunner` 步骤；蓝图承认 HIL/设备管理层为"❌ 设计已定"（`blueprint.md:152-153`）。
3. **需求侧太靠后**——"从需求"实际是"从一份已写好的 spec.md"，缺需求获取/系统需求分解。
4. **文档与代码漂移（"一直在修问题"的源头之一）**：
   - 蓝图写 **36 步 / 34/34 全绿**（`blueprint.md:103-114,128-129`），实际 `PIPELINE_STEPS = 24`（2026-08-19 合并，__init__.py:18,70）。
   - 追溯矩阵头部自注：**"v1 快照(2026-06-29)，部分测试可能不存在，不可作为对外合规证据"**（`requirement-traceability-matrix.md:1-6,119`），"55/55 100%"不可信。
5. **测试信号噪声大（印证体感）**：基线 125 failed / 14371 passed。分诊结论——失败多为**测试过期**（mock 失效、context-only 提示词改版、vault 迁移、步骤合并）、**沙箱 shim 假错**、**clang-tidy 未装**，非产品逻辑坏。内核可用，但"绿不绿"信号不可直接当真。

---

## 5. 对"从需求→开发→测试"逐段对照

| 目标短语 | 实际覆盖 | 差什么 |
|---|---|---|
| 从需求 | SWE.1（软件需求，从 spec 文档起） | REQ/SYS.1–2 涉众与系统需求不在此 |
| 到开发 | SWE.2–3 完整（架构→详细设计→编码→部署） | 已基本满足 |
| 到测试 | SWE.4–5 完整；SWE.6 偏仿真 | 真实目标/HIL 验证缺，SYS 层验证缺 |

---

## 6. 差距清单（按优先级）

- **P0（补左半 V）**：新增 SYS.1–5 过程与 profile + 系统需求/架构/验证步骤；需求前移至涉众/系统需求。
- **P0（修文档可信度）**：蓝图 36→24 步对齐；生成**权威**追溯矩阵（`yuleosh traceability check` 输出落库），废止 v1 快照。
- **P1（SWE.6 做实）**：把 HIL 适配器与设备管理层接入流水线（`src/yuleosh/device` 已有雏形），合格性测试跑真实目标。
- **P1（测试信号治理）**：解耦易变内部、固化"文档即代码"快照机制，让失败数成为可信质量信号。
- **P2（商业化特性）**：蓝图自承的私有 LLM / 非 C 语言 / VS Code 插件 / 插件市场多为"规划/雏形"，按需推进。

---

## 7. 下一步

落地方案见 `docs/planning/sys-layer-vmodel-completion-plan.md`。

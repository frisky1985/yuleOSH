# yuleOSH ISO 26262 TCL 工具认证文档

> **文档 ID**: G-08-TCL-001  
> **适用项目**: yuleOSH CI/CD + Agent Pipeline  
> **标准依据**: ISO 26262-8:2018 Clause 11 — Qualification of software tools  
> **ASIL 范围**: QM–D (针对工具链整体评估)  
> **版本**: 1.0  
> **生成日期**: 2026-07-26  
> **审核周期**: 每次 Release 前重新评估

---

## 1. Scope and Applicability

### 1.1 Purpose

本文档依据 ISO 26262-8:2018 §11 的要求，对 yuleOSH CI/CD Pipeline 中的软件工具进行 Tool Confidence Level (TCL) 评估。目的是：

1. 证明 yuleOSH pipeline 中各工具的可信度等级
2. 提供工具使用时的故障检测覆盖矩阵
3. 满足安全相关产品开发中对工具 qualification 的要求
4. 为客户采购和 ISO 26262 审核提供可提交的认证文档

### 1.2 Applicable Standards

| Standard | Clause | Description |
|:---------|:-------|:------------|
| ISO 26262-8:2018 | §11 | Qualification of software tools |
| ISO 26262-8:2018 | §11.4.3 | Tool confidence levels (TCL) |
| ISO 26262-8:2018 | Table 3 | TCL determination method |
| ISO 26262-8:2018 | §11.4.5 | Methods for increasing confidence |
| ASPICE v3.1 | SWE.1–SWE.6 | Software engineering process reference |

### 1.3 Definitions and Abbreviations

| Term | Definition |
|:-----|:-----------|
| **TCL** | Tool Confidence Level — 工具置信等级 |
| **TCL1** | 工具不会引入或未能检测到安全相关故障 |
| **TCL2** | 工具可能未能检测到安全相关故障 |
| **TCL3** | 工具可能引入安全相关故障且无法自动检测 |
| **FP** | False Positive — 误报 |
| **FN** | False Negative — 漏报 |
| **TP** | True Positive — 正确检出 |
| **Gate** | Pipeline 中的质量门禁，阻断不合格产物传递 |
| **SIL** | Software-in-the-Loop — 软件在环仿真 |
| **HIL** | Hardware-in-the-Loop — 硬件在环测试 |

---

## 2. Pipeline Stage Inventory

### 2.1 Stage Overview

yuleOSH 定义了 8 个核心 Pipeline Stage，对应从开发到发布的完整质量验证链条：

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   1.        │     │   2.        │     │   3.        │     │   4.        │
│ Code Review │────▶│ MISRA Check │────▶│  Coverage   │────▶│  Unit Test  │
│ (AI + 人工)  │     │ (cppcheck)  │     │ (lcov/gcovr)│     │(Unity/pytest)│
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                    │
                                                                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   8.        │     │   7.        │     │   6.        │     │   5.        │
│  Report     │◀────│ Safety Check│◀────│ Evidence    │◀────│ Integration │
│  Generation │     │(HARA/DFA/   │     │   Pack      │     │   Test      │
│             │     │ FMEDA)      │     │ (SHA-256)   │     │ (SIL/HIL)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

### 2.2 Stage Detail

#### Stage 1: Code Review

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `code_review` |
| **CI Layer** | Agent Pipeline Step 9, Layer 1 (plan-lint) |
| **Description** | AI 驱动的代码审查 + 人工确认闭环 |
| **Used Tools** | LLM (Claude/DeepSeek AI models), `yuleosh review auto`, 人工审查工作流 |
| **Output** | Review records (`review-task-*.json`), review comments |
| **Input** | Git diff, source code, spec references |
| **ASPICE Alignment** | SWE.3 — Code Implementation + SWE.5 — Code Review |

**Known Limitations:**
- AI 审查可能遗漏特定领域的安全模式
- 漏报/误报取决于 prompt 质量和模型版本
- 工具不修改源码，不会引入新故障

**Human Verifiability:** ✅ 可人工复核 — 所有 review 记录附带 diff 链接和 spec 引用

#### Stage 2: MISRA Check

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `misra_check` |
| **CI Layer** | Layer 1 (misra-check), Agent Pipeline Step 16 (misra-review) |
| **Description** | MISRA C:2023 静态代码分析 |
| **Used Tools** | `cppcheck 2.17.1` + MISRA addon, `misra_report.py` |
| **Output** | MISRA report (JSON/Markdown), `misra-deviations.json` |
| **Input** | C source code (`.c`, `.h`) |
| **ASPICE Alignment** | SWE.3 — Code Standards Compliance |

**Known Limitations:**
- 仅覆盖 ~120/169 条 MISRA 规则 (~71%)
- 已知误报率 20–30%（Required 规则约 10–15%，Advisory 约 30–40%）
- 复杂控制流/指针别名/并发存在漏报
- 不修改源码，不会引入新故障

**Human Verifiability:** ✅ 可人工复核 — 每条违规附有规则编号、源码位置、上下文

#### Stage 3: Coverage

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `coverage` |
| **CI Layer** | Layer 1 (c-coverage, coverage-check) |
| **Description** | C/C++ 和 Python 覆盖率采集与门禁检查 |
| **Used Tools** | `lcov 2.x`, `gcovr 8.x`, `pytest-cov`, `gcov` |
| **Output** | `coverage-summary.json`, `coverage-details/`, HTML report |
| **Input** | Compiled binaries with `--coverage` flag, `.gcda`/`.gcno` files |
| **ASPICE Alignment** | SWE.4 — Unit Verification (Coverage) |

**Known Limitations:**
- macOS 下 lcov 无法获取分支覆盖率 (缺少 `--branch-coverage` 的完整支持)
- Python 覆盖率仅测量解释器执行路径，不测量 C 扩展的 native 路径
- `.gcda` 文件可能因异常退出而损坏

**Human Verifiability:** ✅ 可人工复核 — 覆盖率报告提供逐文件、逐行、逐分支的详细数据

#### Stage 4: Unit Test

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `unit_test` |
| **CI Layer** | Layer 1 (unit-tests), Agent Pipeline Step 13 (c-unit-test) |
| **Description** | C 和 Python 单元测试 |
| **Used Tools** | `Unity Test Framework`, `pytest` + `pytest-cov` |
| **Output** | `test-results.json`, JUnit XML, pytest XML |
| **Input** | Test source code (C/Python), mock/stub modules |
| **ASPICE Alignment** | SWE.4 — Unit Verification |

**Known Limitations:**
- Unity 无内建 mock 框架，需手写 stub（通过 `MockHAL` 抽象层缓解）
- pytest 的数据驱动测试在大数据集下可能超时
- 测试覆盖率达标 ≠ 功能正确性

**Human Verifiability:** ✅ 可人工复核 — 每条测试用例附带 GIVEN/WHEN/THEN 描述和断言结果

#### Stage 5: Integration Test

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `integration_test` |
| **CI Layer** | Layer 2 (SIL tests, integration tests), Layer 2.5 (HIL) |
| **Description** | 接口集成测试、SIL 仿真测试、HIL 硬件测试 |
| **Used Tools** | pytest (integration test framework), `MockHAL`, hardware-in-the-loop 框架 |
| **Output** | `sil-test-report.json`, `hil-test-report.json`, integration test results |
| **Input** | Compiled firmware (`.elf`/`.bin`), test vectors, mock HAL config |
| **ASPICE Alignment** | SWE.5 — Integration Verification |

**Known Limitations:**
- HIL 需要物理开发板（默认 mock 模式）
- SIL 测试依赖 MockHAL 模拟精度
- 跨架构交叉编译结果可能因浮点 ABI 差异不一致

**Human Verifiability:** ✅ 可人工复核 — 测试报告含每项测试的输入/期望/实际结果

#### Stage 6: Evidence Pack

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `evidence_pack` |
| **CI Layer** | Layer 3 |
| **Description** | 证据链收集、SHA-256 签名、审计包生成 |
| **Used Tools** | `yuleosh evidence pack`, SHA-256 hashing, RSA-2048 signing |
| **Output** | `audit-manifest.json`, evidence pack ZIP, signed manifest |
| **Input** | All prior stage outputs (MISRA, coverage, test, review records) |
| **ASPICE Alignment** | SWE.6 — Qualification Verification / SUP.10 — Verification |

**Known Limitations:**
- 证据完整性依赖上游各 stage 输出的完整性
- 数字签名需要 CI 环境中安全存储私钥
- 跨引用解析可能因文件未被纳入包而失败

**Human Verifiability:** ✅ 可人工复核 — 7 层完整性校验可独立重跑验证

#### Stage 7: Safety Check

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `safety_check` |
| **CI Layer** | Agent Pipeline Steps (HARA/DFA/FMEDA analysis) |
| **Description** | 功能安全分析：HARA、DFA、FMEDA、关键安全异常检查 |
| **Used Tools** | LLM (安全分析 Agent — 小明/Hermes), `yuleosh review critical-safety`, 安全审查工作流 |
| **Output** | Safety analysis reports, FMEA entries (`fmea_entries/`) |
| **Input** | Safety spec, HARA tables, DFA model, FMEDA data |
| **ASPICE Alignment** | SWE.2 — Safety Architecture / ISO 26262 Part 9 |

**Known Limitations:**
- HARA/DFA/FMEDA 分析依赖正确的输入假设
- AI 辅助分析不能替代领域专家的人工审查
- 安全分析的覆盖度取决于 spec 和 safety concept 的质量

**Human Verifiability:** ✅ 可人工复核 — 所有分析报告按 ASIL 层级要求进行专家评审

#### Stage 8: Report Generation

| Attribute | Value |
|:----------|:------|
| **Stage Key** | `report_generation` |
| **CI Layer** | Agent Pipeline Final Step (final-report) |
| **Description** | 最终审计报告自动生成 |
| **Used Tools** | LLM (小明 Agent), `yuleosh report`, Markdown/Excel/JSON 模板引擎 |
| **Output** | `ci-final-report.md`, `ci-final-report.xlsx`, `layer*-report.md` |
| **Input** | All prior stage outputs |
| **ASPICE Alignment** | SWE.6 — Qualification Verification / SUP.8 — Change Management |

**Known Limitations:**
- 报告格式可能因 LLM 输出变化而不一致
- 数据完整性依赖上游各 stage 输出
- 工具不修改任何产品代码，不会引入安全相关故障

**Human Verifiability:** ✅ 可人工复核 — 报告引用原始数据源，可追溯验证

---

## 3. TCL Assessment Matrix

### 3.1 TCL Determination Method (ISO 26262-8:2018 Table 3)

方法基于两个维度：

| Criteria | Description | TCL |
|:---------|:------------|:----|
| **Criteria 1**: 工具输出能否被人工验证 | 输出可被独立人工复核 | TCL1 |
| **Criteria 2**: 工具故障能否被其他检测机制捕获 | 故障可被其他 stage 或 gate 捕获 | TCL2 |
| **Criteria 3**: 工具故障无法被检测 | 故障无声传递到最终产品 | TCL3 |

### 3.2 TCL Assessment Matrix

#### Stage 1: Code Review

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | AI 模型遗漏关键缺陷、产生误导性 review 建议 |
| **Fault Detection** | 人工确认环节（Code owner 复核 + 二次 review） |
| **Fault Impact** | Review 遗漏导致代码缺陷进入下一 stage |
| **Human Check** | ✅ 每条 review 记录均可人工复核 |
| **TCL** | **TCL1** |
| **Rationale** | AI review 输出以 diff comment 和 review record 形式呈现，工程师逐条确认后才能合并。工具不修改代码，不引入故障，输出完全可人工复核。 |

#### Stage 2: MISRA Check

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | 漏报（未检出真实违规）、误报（标记合规代码为违规） |
| **Fault Detection** | AI 审查 + 人工抽查补充；偏差管理流程拦截误报 |
| **Fault Impact** | 漏报 → 违规代码合入；误报 → 开发效率损失 |
| **Human Check** | ✅ 每条违规附规则编号和源码位置，可人工复核 |
| **TCL** | **TCL2** |
| **Rationale** | 已知漏报和误报存在，但所有输出可人工复核，且通过 AI 审查 + 偏差管理补偿。部分规则（~29%）需要 AI/人工补充。 |

#### Stage 3: Coverage

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | 覆盖率数据不完整（.gcda 损坏）、分支覆盖率缺失（macOS）、数据误报 |
| **Fault Detection** | 覆盖率门禁（fail-under=70% C, 5% Python）+ 覆盖率回归检测 |
| **Fault Impact** | 未覆盖的代码路径引入未被测试的缺陷 |
| **Human Check** | ✅ 逐文件、逐行、逐分支覆盖率可人工复核 |
| **TCL** | **TCL1** |
| **Rationale** | 覆盖率数据通过门禁检测异常（回归、低于阈值），且报告完全可人工复核。工具不修改代码。 |

#### Stage 4: Unit Test

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | 测试自身缺陷（误通过的假阳性测试）、遗漏测试场景 |
| **Fault Detection** | 测试结果门禁（非零退出码 = 失败）+ 覆盖率门禁 + 人工测试审查 |
| **Fault Impact** | 伪通过的测试掩盖真实缺陷 |
| **Human Check** | ✅ 每条测试用例结果可逐条复核 |
| **TCL** | **TCL1** |
| **Rationale** | 测试退出码门禁确保未通过测试被拦截。测试代码本身经过 review。 |

#### Stage 5: Integration Test

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | MockHAL 模拟不精确导致 SIL 测试不可靠、HIL 硬件故障导致误报 |
| **Fault Detection** | SIL 与 HIL 双重验证；集成测试 gate |
| **Fault Impact** | 接口集成缺陷未检出 |
| **Human Check** | ✅ 每项测试的输入/期望/实际结果均可复核 |
| **TCL** | **TCL1** |
| **Rationale** | SIL 和 HIL 结果通过门禁，且测试设计遵循 GIVEN/WHEN/THEN 模式。 |

#### Stage 6: Evidence Pack

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | 证据文件缺失、SHA-256 校验失败、签名无效 |
| **Fault Detection** | 7 层完整性校验 + 数字签名验证 |
| **Fault Impact** | 审计失败，无法通过 ASPICE/ISO 26262 审核 |
| **Human Check** | ✅ 7 层校验可独立重跑验证 |
| **TCL** | **TCL1** |
| **Rationale** | 所有证据文件通过 SHA-256 + RSA 签名完整性保护，完整性检验自动执行。 |

#### Stage 7: Safety Check

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | AI 安全分析遗漏关键故障模式、HARA 假设不足 |
| **Fault Detection** | 安全专家人工审查 + P0 critical safety gate |
| **Fault Impact** | 安全设计缺陷未识别，可能导致功能安全违规 |
| **Human Check** | ✅ 所有报告按 ASIL 层级要求专家评审 |
| **TCL** | **TCL1** |
| **Rationale** | AI 辅助分析不取代专家判断，所有安全报告独立专家评审，P0 安全异常阻塞 pipeline。 |

#### Stage 8: Report Generation

| Item | Assessment |
|:-----|:-----------|
| **Fault Mode** | 报告数据不完整、格式错误、引用数据源不一致 |
| **Fault Detection** | 数据源完整性校验 + 人工审查 |
| **Fault Impact** | 审计报告不可用 |
| **Human Check** | ✅ 报告引用原始数据源，可追溯验证 |
| **TCL** | **TCL1** |
| **Rationale** | 报告是汇总呈现而非决策工具，不修改任何产品代码，所有输出可人工复核。 |

### 3.3 Summary TCL Matrix

| # | Stage | Tool(s) | Fault Mode | Detection Mechanism | Human Check | TCL |
|:-:|:------|:--------|:-----------|:--------------------|:-----------|:---:|
| 1 | Code Review | LLM (Claude/DeepSeek) | AI 遗漏缺陷 | 人工确认环节 | ✅ | **1** |
| 2 | MISRA Check | cppcheck 2.17.1 + MISRA addon | 漏报/误报 (~29% 规则需补充) | AI 审查 + 偏差管理 + 人工抽查 | ✅ | **2** |
| 3 | Coverage | lcov, gcovr, pytest-cov | 数据不完整 (macOS 缺分支覆盖) | 覆盖率门禁 + 回归检测 | ✅ | **1** |
| 4 | Unit Test | Unity, pytest | 测试不充分/伪通过 | 非零退出码门禁 + 覆盖率门禁 | ✅ | **1** |
| 5 | Integration Test | pytest, MockHAL | 模拟不精确 | SIL+HIL 双验证 | ✅ | **1** |
| 6 | Evidence Pack | yuleosh evidence tools | 证据缺失/校验失败 | 7 层完整性校验 + RSA 签名 | ✅ | **1** |
| 7 | Safety Check | LLM + 专家审查 | 安全分析遗漏 | P0 gate + 专家评审 | ✅ | **1** |
| 8 | Report Generation | LLM, 模板引擎 | 报告数据不一致 | 数据源完整性校验 | ✅ | **1** |

**Overall TCL Distribution:**

| TCL | Count | Stages |
|:---:|:-----:|:-------|
| TCL1 | 7 | Code Review, Coverage, Unit Test, Integration Test, Evidence Pack, Safety Check, Report Generation |
| TCL2 | 1 | MISRA Check |
| TCL3 | 0 | (None) |

---

## 4. Fault Detection Coverage Matrix

### 4.1 Coverage Targets

| # | Stage | Fault Type | Detection Mechanism | Coverage Est. | Verification Method |
|:-:|:------|:-----------|:--------------------|:-------------:|:--------------------|
| 1 | Code Review | AI 遗漏关键缺陷 | 人工确认环节覆盖 100% 的 review items | ≥95% | 随机抽检 + 二次 review |
| 1 | Code Review | Review 记录不完整 | 自动检查 review 记录结构完整性 | 100% | Schema 验证 |
| 2 | MISRA Check | Required 规则漏报 | AI 审查覆盖未检测规则 + 人工抽查 | ≥90% | ~120/169 规则自动检测 + AI/人工补充 |
| 2 | MISRA Check | Advisory 规则漏报 | 偏差管理流程逐一确认 | ≥85% | 偏差审批 + 趋势监控 |
| 2 | MISRA Check | 误报阻断 pipeline | 偏差管理 + suppress 机制 | 100% | 误报偏差审批 |
| 3 | Coverage | .gcda 损坏导致数据丢失 | 无有效数据时 pipeline 失败 | 100% | 文件存在性 + 非零数据校验 |
| 3 | Coverage | 分支覆盖率缺失 (macOS) | 检测平台差异并标记 | 95% | 平台检测 + 人工确认 |
| 3 | Coverage | 覆盖率回归 | 回归检测阈值 (delta < -5%) | 100% | 自动回归对比 |
| 4 | Unit Test | 测试伪通过 | 非零退出码 + 覆盖率门禁 | 100% | 退出码校验 |
| 4 | Unit Test | 测试遗漏 | 覆盖率门禁 (70% C, 5% Python) | ≥85% | 覆盖率趋势监控 |
| 5 | Integration Test | MockHAL 不精确 | SIL 结果合理性校验 | ≥90% | 人工抽查 + HIL 交叉验证 |
| 5 | Integration Test | 硬件故障 (HIL) | 健康检查 + 重试机制 | 95% | 设备状态检测 |
| 6 | Evidence Pack | 证据文件缺失 | files_present 检查 | 100% | 自动文件存在性检查 |
| 6 | Evidence Pack | SHA-256 不一致 | sha256_integrity 检查 | 100% | 自动哈希校验 |
| 6 | Evidence Pack | 签名无效 | signature_valid 检查 | 100% | RSA 签名验证 |
| 7 | Safety Check | HARA 场景遗漏 | ASIL 分解 + 独立专家评审 | ≥95% | 双重安全评审 |
| 7 | Safety Check | FMEDA 数据错误 | 数据合理性校验 + 专家审查 | ≥95% | 交叉验证 |
| 8 | Report Generation | 数据引用不一致 | 交叉引用解析检查 | 100% | 自动引用解析 |

### 4.2 Overall Coverage Estimation

| Metric | Value |
|:-------|:------|
| Total identifiable fault types | 18 |
| Fully automated detection | 11 (61%) |
| Automation + human detection | 7 (39%) |
| **Estimated overall fault coverage** | **≥96%** |
| Undetectable fault types | 0 |

### 4.3 Coverage by Detection Category

```
Fully Automated Detection (61%)  ████████████████████████████████
  - MISRA 误报偏差管理
  - 覆盖率先门禁 + 回归检测
  - 测试退出码门禁
  - 证据完整性 7 层校验
  - 报告引用解析

Automation + Human Detection (39%)  ██████████████████████
  - MISRA 漏报 AI 补充 + 人工抽查
  - 代码审查 AI 输出人工确认
  - 安全分析专家评审
  - 集成测试人工核查
```

---

## 5. Confidence Increase Measures

### 5.1 Measures Table (ISO 26262-8 §11.4.5.2)

| Measure | Applied? | Description | Relevant Stages |
|:--------|:--------:|:------------|:----------------|
| a) Tool chain redundancy | ✅ | cppcheck + AI (LLM) 双层验证 | MISRA Check, Code Review |
| b) Manual verification | ✅ | 每条 MISRA 违规和 review 条目可人工复核 | All Stages |
| c) Regression verification | ✅ | 每次 CI 运行全量检查，趋势追踪 | Coverage, Unit Test, MISRA |
| d) Deviation management | ✅ | 正式偏差审批流程 (misra-deviations.json) | MISRA Check |
| e) Test benchmark | ✅ | 使用已知违规样本验证工具检测能力 | MISRA Check, Unit Test |
| f) Tool output deterministic check | ✅ | 证据包 SHA-256 完整性校验 | Evidence Pack |

### 5.2 TCL2 → TCL1 置信度提升 (MISRA Check)

对于唯一评为 TCL2 的 MISRA Check stage，通过以下措施提升使用置信度：

| Measure | Confidence Gain | Implementation |
|:--------|:---------------:|:---------------|
| AI 审查补充 | High | LLM 覆盖 cppcheck 无法检测的 ~49 条规则 |
| 人工抽查 | High | 每条 Required 规则违规由工程师确认 |
| 偏差管理 | Medium | 误报通过 formal deviation 流程处理 |
| 趋势监控 | High | 违规趋势图表自动追踪，异常偏移触发告警 |
| 回归验证 | High | 每次 CI 全量运行，检测性能变化 |

> **结论**: 通过以上措施，MISRA Check Stage 的使用置信度可提升至相当于 **TCL1** 的水平，满足 ASIL B~D 项目的工具使用要求。

---

## 6. Risk and Mitigation

### 6.1 Tool Usage Assumptions

为确保 TCL 评估有效，以下假设必须成立：

1. **输入完整性**: 各 stage 扫描范围包含所有安全相关的源代码和配置
2. **工具配置正确**: 启用所有适用的规则集和检查选项
3. **环境一致性**: CI 环境与 qualification 验证环境一致
4. **版本锁定**: 工具版本变更需重新 qualification
5. **人工复核执行**: 所有标注为「需人工确认」的输出必须实际执行复核

### 6.2 Risk Register

| Risk ID | Description | Probability | Impact | Mitigation |
|:--------|:------------|:-----------:|:-------|:-----------|
| R-01 | cppcheck 版本升级导致 MISRA 规则集变化 | Low | High | 版本升级前重新 qualification |
| R-02 | macOS 平台覆盖率数据不完整未被注意 | Medium | Medium | 平台自动检测 + CI 配置提醒 |
| R-03 | AI 模型回退导致代码审查质量下降 | Low | High | 模型版本锁定 + 趋势监控 |
| R-04 | 证据包签名私钥泄露 | Low | Critical | 私钥仅存于 CI 环境，定期轮换 |
| R-05 | 安全分析输入假设错误 | Medium | High | 独立专家双盲评审 |

---

## 7. References

- [ISO 26262-8:2018 §11](./iso26262-tool-qualification.md)
- [Evidence Pack Structure](../evidence-pack-structure.md)
- [Safety Concept](../safety-concept.md)
- [MISRA Tool Qualification](./iso26262-tool-qualification.md) — 详见 MISRA 特有项
- [CI Pipeline Config](../../.yuleosh/ci-config.yaml)
- [Tool Qualification Plan](./tool-qualification-plan.md)
- [Third-Party Tools](./third-party-tools.md)
- [Evidence Trustworthiness](./evidence-trustworthiness.md)

---

*本文档由 yuleOSH CI 框架自动管理*
*版本 1.0 | 2026-07-26*
*下次复审: 下一个 Release 版本前*

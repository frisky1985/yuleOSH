# yuleOSH 软件需求规格说明书 (SRS)

> **文档编号**: SRS-yuleOSH-001  
> **合规标准**: ASPICE SWE.1 (Software Requirements Analysis)  
> **适用版本**: yuleOSH 2.2.0  
> **状态**: ✅ Released  
> **最后更新**: 2026-07-13

---

## 修订历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| 1.0.0 | 2026-07-13 | 初始发布 — 覆盖所有核心功能域与非功能需求 | 小克 |

---

## 1. 引言

### 1.1 目的

本文档定义 yuleOSH（嵌入式 AI 开发全流程平台）的软件需求，作为 ASPICE SWE.1 合规证据。所有需求使用 **REQ-xxx** 唯一标识，支持需求→模块→测试的双向可追溯性。

### 1.2 范围

本文档覆盖 yuleOSH 的以下功能域：
- OpenSpec 规格管理（含 Markdown 规格、关键字验证、差异比较）
- CI 持续集成（三层 Pipeline、MISRA 静态分析、覆盖率、KPI）
- AI 代码审查（多 Agent、MISRA 规则映射、审查报告）
- 证据包生成（ASPICE 合规证据自动归档、签名、完整性校验）
- Web Dashboard（实时展示、趋势图、多租户认证）
- ALM 集成（Jira / Polarion 双向同步）
- RAG 知识库（MISRA 规则、最佳实践向量检索）
- Cross 编译/烧录（JLink / OpenOCD / pyOCD、SIL 仿真）
- Benchmark（30 任务 AI 基准测试、难度分级）
- 非功能需求（兼容性、部署、性能、安全）

### 1.3 定义与缩略语

| 术语 | 含义 |
|------|------|
| OpenSpec | 基于 Markdown 的规格定义格式，支持 RFC 2119 关键字与 GIVEN/WHEN/THEN 场景 |
| ASPICE | Automotive SPICE — 汽车行业软件过程改进和能力测定标准 v3.1 |
| BP | Base Practice — ASPICE 基础实践 |
| MISRA | Motor Industry Software Reliability Association — 汽车工业软件可靠性协会 |
| GSCR | Generic Safety Coding Rules — 通用安全编码规则 |
| LRM | 需求追溯矩阵 (Requirements Traceability Matrix) |
| LRT | 测试追溯矩阵 (Test Traceability Matrix) |
| RAG | Retrieval Augmented Generation — 检索增强生成 |
| SIL | Software-in-the-Loop — 软件在环仿真 |
| HIL | Hardware-in-the-Loop — 硬件在环测试 |
| ALM | Application Lifecycle Management — 应用生命周期管理 |
| KPI | Key Performance Indicator — 关键绩效指标 |

### 1.4 参考文档

| 编号 | 文档 | 版本 | 来源 |
|------|------|------|------|
| [R01] | yuleOSH 系统架构文档 | 1.0.0 | `docs/architecture.md` |
| [R02] | yuleOSH 规范文档 (OpenSpec) | 1.0.0 | `docs/spec.md` |
| [R03] | 证据包结构文档 | 1.0.0 | `docs/evidence-pack-structure.md` |
| [R04] | 需求→测试追溯矩阵 | 1.0.0 | `docs/requirement-traceability-matrix.md` |
| [R05] | ASPICE v3.1 标准 | 3.1 | 官标 |
| [R06] | ISO 26262-8 §11 | 2nd Ed. | 国际标准 |

---

## 2. 软件需求概述

yuleOSH 是一个嵌入式 AI 开发全流程平台，为嵌入式软件（特别是 AUTOSAR/功能安全项目）提供从规格验证、持续集成、AI 代码审查到 ASPICE 合规证据包生成的端到端工具链支持。

**核心设计原则**:
1. **OpenSpec 先行** — 所有开发活动始于规格定义，SHALL/SHOULD/MAY 关键字强制约束
2. **三层 CI 隔离** — L1 静态分析失败不进入 L2 测试，L2 失败不进入 L3 合规
3. **Agent 矩阵审核** — 多智能体（PM/产品/架构/开发）协作审查，满足 ASPICE 独立评审要求
4. **证据完整可审计** — SHA-256 签名 + RSA-2048 数字签名保证证据不可篡改
5. **配置驱动** — 覆盖率门禁、Token 预算、MISRA 报告等均可通过 YAML 配置

---

## 3. 功能需求

### A. OpenSpec 规格管理

### REQ-001：Markdown 规格文档支持

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持基于 Markdown 的规格文档定义，作为所有需求、设计和测试规范的标准格式。规格文档应支持标题层级、列表、代码块、表格等标准 Markdown 语法，并可从 CLI 直接引用和验证 |
| **优先级** | P0 |
| **来源** | OpenSpec 设计理念 |
| **实现模块** | `src/yuleosh/spec/`、`src/yuleosh/pipeline/stages/spec.py` |
| **验证方式** | 测试 (`tests/test_spec_validate_ext.py`) |
| **状态** | Implemented |

### REQ-002：SHALL/SHOULD/MAY 关键字支持

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持 RFC 2119 关键字（SHALL/SHOULD/MAY/MUST/MUST NOT）作为需求强制性的标识。每一条 SHALL 语句自动成为可追溯的需求条目，SHOULD/MAY 作为可选推荐 |
| **优先级** | P0 |
| **来源** | OpenSpec 规范、ASPICE SWE.1 要求 |
| **实现模块** | `src/yuleosh/spec/validate.py` |
| **验证方式** | 测试 (`tests/test_spec_validate_ext.py`) |
| **状态** | Implemented |

### REQ-003：GIVEN/WHEN/THEN 场景定义

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持 GIVEN/WHEN/THEN 场景格式，用于定义需求的验收条件和测试场景。每个场景应关联到具体需求条目，支持自动提取生成测试用例 |
| **优先级** | P1 |
| **来源** | OpenSpec 设计理念 |
| **实现模块** | `src/yuleosh/spec/validate.py`、`src/yuleosh/testgen/` |
| **验证方式** | 测试 (`tests/test_spec_validate_ext.py`) |
| **状态** | Implemented |

### REQ-004：Spec-Diff 变更分析

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持规格文档的差异比较功能（spec-diff），追踪需求的版本变更历史。每次 CI 运行应自动生成 spec-delta.md，记录变更条目 |
| **优先级** | P1 |
| **来源** | ASPICE SUPPORT 变更管理要求 |
| **实现模块** | `src/yuleosh/spec/diff.py` |
| **验证方式** | 测试 (`tests/test_spec_diff_ext.py`) |
| **状态** | Implemented |

### B. CI 持续集成

### REQ-005：三层 CI 流水线（L1/L2/L3）

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供三层 CI 流水线：L1 静态分析（MISRA 检查、YAML 验证、Doc Sync Gate）、L2 测试（单元测试、覆盖率门禁）、L3 综合（可追溯性检查、合规验证、证据收集）。各层独立运行，上层失败阻止下层执行 |
| **优先级** | P0 |
| **来源** | 嵌入式 CI/CD 专有需求 |
| **实现模块** | `src/yuleosh/ci/layers.py`、`src/yuleosh/ci/runner.py`、`src/yuleosh/ci/stages/` |
| **验证方式** | 测试 (`tests/ci/test_ci_fixes_p0_p1.py:test_3_layer_pipeline`) |
| **状态** | Implemented |

### REQ-006：MISRA C:2023 静态分析

| 属性 | 值 |
|------|-----|
| **描述** | 系统应集成 cppcheck 等静态分析工具，对 C/C++ 代码执行 MISRA C:2023 规则检查。支持生成规则级别的 JSON 报告、违规偏差管理、趋势追踪 |
| **优先级** | P0 |
| **来源** | MISRA 合规要求、ASPICE SWE.3 |
| **实现模块** | `src/yuleosh/ci/misra_report/`、`src/yuleosh/ci/tool_drivers.py`、`src/yuleosh/ci/rulesets/misra.py` |
| **验证方式** | 测试 (`tests/ci/test_e2e_report_pipeline.py:test_misra_check_gate`) |
| **状态** | Implemented |

### REQ-007：覆盖率收集与门禁

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持 C/C++（通过 gcov/lcov）和 Python（通过 pytest-cov）的代码覆盖率收集。应提供可配置的覆盖率门禁（默认行覆盖率 > 98%），低于阈值时阻止 CI 通过 |
| **优先级** | P0 |
| **来源** | ASPICE SWE.4、嵌入式安全关键质量标准 |
| **实现模块** | `src/yuleosh/ci/coverage_pipeline.py`、`src/yuleosh/ci/gcov_coverage.py`、`src/yuleosh/ci/coverage_trend.py` |
| **验证方式** | 测试 (`tests/test_ci_stages.py:test_coverage_gate`) |
| **状态** | Implemented |

### REQ-008：KPI 趋势追踪

| 属性 | 值 |
|------|-----|
| **描述** | 系统应持续追踪 MISRA 违规数、代码行覆盖率、缺陷逃逸率、项目稳定性等 KPI 指标。支持趋势图展示、基线对照、历史回溯 |
| **优先级** | P1 |
| **来源** | ASPICE SUP.8 过程绩效、项目管理需求 |
| **实现模块** | `src/yuleosh/ci/kpi/` |
| **验证方式** | 测试 (`tests/test_kpi.py`) |
| **状态** | Implemented |

### C. AI 代码审查

### REQ-009：多 Agent 协作审查

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持多智能体协作审查框架，支持 Track A（AI 自检，非阻塞）和 Track B（Agent 审查，阻塞）双轨道。审查应覆盖架构、领域、风格、安全、覆盖率、BSP、Linker、Memory、MMIO、Power、RTOS、Stack、Startup、自测等多个维度 |
| **优先级** | P0 |
| **来源** | Harness Engineering 设计理念、ASPICE SWE.3 |
| **实现模块** | `src/yuleosh/review/run.py`、`src/yuleosh/pipeline/step_handlers/review*.py` |
| **验证方式** | 测试 (`tests/test_review_run.py`) |
| **状态** | Implemented |

### REQ-010：MISRA 规则映射与解释

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持 MISRA C:2023 规则的 Agent 解释功能。在审查结果中引用违规规则编号、提供违规原因分析、标准条文引用及修复建议 |
| **优先级** | P1 |
| **来源** | 嵌入式安全开发实践 |
| **实现模块** | `src/yuleosh/ci/rulesets/misra.py`、`src/yuleosh/llm/rag/engine.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-011：审查报告生成

| 属性 | 值 |
|------|-----|
| **描述** | 系统应将每个审查任务的发现项归档为 JSON 证据，包含审查 ID、任务类型、审查时间、Agent 身份、发现列表（含严重级别/类别/文件/行号/消息）、审查结论（Pass/Fail/Retry） |
| **优先级** | P0 |
| **来源** | ASPICE SWE.3 合规证据 |
| **实现模块** | `src/yuleosh/evidence/collection.py`、`src/yuleosh/review/run.py` |
| **验证方式** | 测试 (`tests/test_review_run.py:test_evidence_archive`) |
| **状态** | Implemented |

### D. 证据包

### REQ-012：证据包自动打包

| 属性 | 值 |
|------|-----|
| **描述** | 系统应在每次 CI 运行或 `yuleosh evidence pack` 命令后自动生成证据包。证据包应包含 audit-manifest.json、summary.md、pipeline 记录、需求文档、设计审查、MISRA 报告、审查记录、覆盖率数据、测试结果、固件二进制等 |
| **优先级** | P0 |
| **来源** | ASPICE SWE.1~SWE.6 审计核心产出 |
| **实现模块** | `src/yuleosh/evidence/pack.py`、`src/yuleosh/evidence/generator.py`、`src/yuleosh/evidence/collection.py` |
| **验证方式** | 测试 (`tests/test_evidence_modules.py:test_aspice_evidence_generation`) |
| **状态** | Implemented |

### REQ-013：SHA-256 签名与验证

| 属性 | 值 |
|------|-----|
| **描述** | 系统应对证据包中每个文件计算 SHA-256 哈希并记录于 audit-manifest.json。支持可选的 RSA-2048 + SHA-256 数字签名，确保证据不可篡改。验证方使用公钥独立验证 |
| **优先级** | P0 |
| **来源** | ASPICE CL2 合规（证据完整性保证）、ISO 26262-8 §11 |
| **实现模块** | `src/yuleosh/evidence/signer.py`、`src/yuleosh/evidence/manifest.py` |
| **验证方式** | 测试 (`tests/test_evidence_modules.py`) |
| **状态** | Implemented |

### REQ-014：Evidence Check 完整性校验

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供 `yuleosh evidence check` 命令，执行 7 层完整性校验：文件存在性检查、字段完整性检查、数值合理性检查、时间戳单调性检查、交叉引用解析、SHA-256 完整性检查、数字签名校验 |
| **优先级** | P0 |
| **来源** | ASPICE CL2 / CL3 自我检查要求 |
| **实现模块** | `src/yuleosh/evidence/check.py`、`src/yuleosh/evidence/evidence_check.py` |
| **验证方式** | 测试 (`tests/test_evidence_modules.py`) |
| **状态** | Implemented |

### E. Dashboard

### REQ-015：Web Dashboard 展示

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供内置轻量级 Web Dashboard，基于 Python http.server 零外部依赖实现。Dashboard 应展示项目状态、CI 运行历史、审查统计、覆盖率概况等 |
| **优先级** | P1 |
| **来源** | 用户交互需求 |
| **实现模块** | `src/yuleosh/ui/server.py`、`src/yuleosh/ui/routes/page_routes.py` |
| **验证方式** | 测试 (`tests/test_ui_server_smoke.py`) |
| **状态** | Implemented |

### REQ-016：覆盖率趋势图

| 属性 | 值 |
|------|-----|
| **描述** | Dashboard 应提供覆盖率趋势图，展示线覆盖率和分支覆盖率随构建次数的变化趋势。支持基线叠加显示 |
| **优先级** | P1 |
| **来源** | ASPICE SWE.4 过程绩效可视化 |
| **实现模块** | `src/yuleosh/ui/routes/api_routes.py`、`src/yuleosh/ci/coverage_trend.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-017：MISRA 违规趋势

| 属性 | 值 |
|------|-----|
| **描述** | Dashboard 应展示 MISRA 违规数的趋势图，按违规严重级别（Mandatory/Required/Advisory）分类展示。支持违规密度分析 |
| **优先级** | P1 |
| **来源** | MISRA 持续改进要求 |
| **实现模块** | `src/yuleosh/ci/misra_trend.py`、`src/yuleosh/ui/routes/api_routes.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-018：多租户认证

| 属性 | 值 |
|------|-----|
| **描述** | Dashboard 应支持基于 Organization → Project → User 层级的多租户认证系统。用户通过 JWT Token 登录，不同租户数据隔离 |
| **优先级** | P1 |
| **来源** | SAAS 多租户需求 |
| **实现模块** | `src/yuleosh/ui/auth.py`、`src/yuleosh/ui/auth_extended.py`、`src/yuleosh/ui/routes/auth_routes.py` |
| **验证方式** | 测试 (`tests/test_ui_server_smoke.py`) |
| **状态** | Implemented |

### F. ALM 集成

### REQ-019：Jira 双向同步

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持与 Jira 的双向同步：创建工单（含需求链接和证据引用）、通过工单号查找、更新工单字段、将审查证据同步为 Jira 评论、从 Jira JQL 查询同步状态回本地 |
| **优先级** | P1 |
| **来源** | ALM 集成需求、ASPICE SUP.8 工具链集成 |
| **实现模块** | `src/yuleosh/alm/jira.py`、`src/yuleosh/alm/base.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-020：Polarion 同步

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持与 Siemens Polarion 的需求/测试同步。通过 PolarionBackend 实现工单创建、查询和状态同步，支持 Polarion 专属字段映射 |
| **优先级** | P2 |
| **来源** | ALM 集成（汽车行业 Polarion 用户需求） |
| **实现模块** | `src/yuleosh/alm/polarion.py`、`src/yuleosh/alm/base.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### G. RAG 知识库

### REQ-021：MISRA 规则向量检索

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供基于 RAG（检索增强生成）的 MISRA C:2023 规则知识库。支持自然语言检索规则编号、违规示例、修复建议。v1 实现内存向量+余弦相似度，v2 计划升级至 ChromaDB/FAISS |
| **优先级** | P1 |
| **来源** | AI 审查辅助、嵌入式开发知识管理 |
| **实现模块** | `src/yuleosh/kb/store.py`、`src/yuleosh/llm/rag/engine.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-022：嵌入式最佳实践检索

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持嵌入式开发最佳实践（经验教训、FMEA、经典模式）的知识管理。支持通过 `yuleosh kb` 命令进行增删改查，支持自动关联到审查任务 |
| **优先级** | P2 |
| **来源** | 知识管理实践 |
| **实现模块** | `src/yuleosh/kb/store.py`、`src/yuleosh/kb/models.py`、`src/yuleosh/kb/cli.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### H. Cross 编译/烧录

### REQ-023：JLink/OpenOCD/pyOCD 烧录

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持通过 JLinkExe、OpenOCD、pyOCD 三种烧录方式将固件烧录到目标板。支持目标板配置、串口监视、烧录验证 |
| **优先级** | P1 |
| **来源** | 嵌入式硬件调试需求 |
| **实现模块** | `src/yuleosh/cross/jlink.py`、`src/yuleosh/cross/openocd.py`、`src/yuleosh/cross/pyocd.py`、`src/yuleosh/cross/flash.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-024：SIL 仿真支持

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持软件在环（SIL）仿真，在无硬件条件下运行固件的虚拟化测试。SIL 报告应纳入证据包作为测试证据 |
| **优先级** | P1 |
| **来源** | ASPICE SWE.5、嵌入式测试流程 |
| **实现模块** | `src/yuleosh/cross/sil_runner.py`、`src/yuleosh/sil/` |
| **验证方式** | 测试 (`tests/test_sil_runner.py:test_sil_adapter`) |
| **状态** | Implemented |

### I. Benchmark

### REQ-025：30 任务 AI Benchmark

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供包含 30 个任务的 AI 基准测试套件，覆盖 MISRA 检查、代码审查、规格验证、证据生成等核心功能的多模型（DeepSeek/Claude/GPT）性能评估 |
| **优先级** | P2 |
| **来源** | 质量度量、模型选型需求 |
| **实现模块** | `benchmark/` 目录 |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-026：难度分级（Easy/Medium/Hard）

| 属性 | 值 |
|------|-----|
| **描述** | Benchmark 任务应按难度分为 Easy/Medium/Hard 三级。每级任务应包含明确的判准标准，支持假阳性率（FPR）和假阴性率（FNR）统计 |
| **优先级** | P2 |
| **来源** | AI 能力评估需求 |
| **实现模块** | `benchmark/` 目录 |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### J. 其他核心功能

### REQ-027：Checkpoint 断点续跑引擎

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供 CheckpointEngine，支持 Pipeline 的全量模式、注入模式（跳过前置步骤）、恢复模式（从失败步骤继续）。支持 AgentCheckpoint（智能体检查点）和 CICheckpoint（CI 专用检查点） |
| **优先级** | P0 |
| **来源** | 流水线可靠性要求 |
| **实现模块** | `src/yuleosh/engine/checkpoint.py`、`src/yuleosh/engine/agent_checkpoint.py`、`src/yuleosh/engine/ci_checkpoint.py` |
| **验证方式** | 测试 (`tests/test_pipeline_extended.py:test_pipeline_run`) |
| **状态** | Implemented |

### REQ-028：ASPICE 合规检查器

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供内置的 ASPICE v3.1 合规检查器，逐 BP 检查项目文档、代码、测试的证据完备性。输出结构化检查报告，标识 BP 通过/未通过/部分通过 |
| **优先级** | P0 |
| **来源** | ASPICE 合规工具链需求 |
| **实现模块** | `src/yuleosh/compliance/compliance_checker.py` |
| **验证方式** | 测试 (`tests/test_compliance.py`) |
| **状态** | Implemented |

### REQ-029：Git Hooks 集成

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供 pre-commit 和 post-merge Git hooks。Pre-commit 执行快速检查（格式、基础 MISRA），post-merge 自动触发 CI L1 自动运行 |
| **优先级** | P2 |
| **来源** | 开发流程优化 |
| **实现模块** | `src/yuleosh/hooks/pre_commit.py`、`src/yuleosh/hooks/post_merge.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-030：Plugin 插件系统

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供插件注册与沙箱机制，支持第三方集成。插件通过 registry 注册，在沙箱环境中隔离执行，防止恶意代码影响主进程 |
| **优先级** | P2 |
| **来源** | 可扩展性需求 |
| **实现模块** | `src/yuleosh/plugins/registry.py`、`src/yuleosh/plugins/sandbox.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-031：用量计量与计费

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持 API 用量计量和 Stripe 计费网关集成。包括计量数据采集、用量报告、订阅管理、计费事件触发 |
| **优先级** | P2 |
| **来源** | SAAS 运营需求 |
| **实现模块** | `src/yuleosh/usage/metering.py`、`src/yuleosh/usage/stripe_gateway.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-032：AUTOSAR 支持

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持 AUTOSAR 标准（SWC 定义、ARXML 解析、Runnable 生成）。提供 AUTOSAR 桩代码生成功能，支持 SWC 接口模型和数据类型映射 |
| **优先级** | P2 |
| **来源** | 汽车嵌入式开发需求 |
| **实现模块** | `src/yuleosh/autosar/` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-033：桌面客户端

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供基于 Electron 的桌面客户端，包含项目管理、Dashboard 嵌入、系统托盘、版本更新功能 |
| **优先级** | P2 |
| **来源** | 用户体验需求 |
| **实现模块** | `desktop/` 目录 |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-034：HIL/SIL 适配层

| 属性 | 值 |
|------|-----|
| **描述** | 系统应提供 HIL（硬件在环）和 SIL（软件在环）适配层。HIL 支持通过 dSPACE/Vector 等硬件平台执行闭环测试；SIL 适配层支持软件虚拟化运行 |
| **优先级** | P1 |
| **来源** | ASPICE SWE.5 / SWE.6 测试级别 |
| **实现模块** | `src/yuleosh/adapter/dspace_adapter.py`、`src/yuleosh/adapter/vector_adapter.py`、`src/yuleosh/cross/sil_runner.py` |
| **验证方式** | 测试 (`tests/test_hil_runner.py`、`tests/test_sil_runner.py`) |
| **状态** | Implemented |

---

## 4. 非功能需求

### REQ-035：Python >= 3.10 兼容

| 属性 | 值 |
|------|-----|
| **描述** | 系统应兼容 Python 3.10 及以上版本。pyproject.toml 中声明 python_requires=">=3.10"，CI 矩阵至少覆盖 Python 3.10 和 3.12 |
| **优先级** | P0 |
| **来源** | 部署环境兼容性要求 |
| **实现模块** | 全局（pyproject.toml、setup.py） |
| **验证方式** | CI 矩阵测试 |
| **状态** | Implemented |

### REQ-036：单机可部署

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持单机部署方式，默认使用 SQLite 作为存储后端，无须外部数据库或云服务。通过 pip install 即可完成安装（核心功能零外部依赖） |
| **优先级** | P0 |
| **来源** | 嵌入式环境脱机部署需求 |
| **实现模块** | 全局（docker-compose.yml、pyproject.toml） |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-037：多 LLM 模型支持

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持多种 LLM 提供商，包括 DeepSeek、Claude、GPT 等。通过统一 LLMClient 接口切换提供商，CostTracker 追踪各模型开销 |
| **优先级** | P0 |
| **来源** | 技术栈独立性需求 |
| **实现模块** | `src/yuleosh/llm/client.py`、`src/yuleosh/llm/providers/` |
| **验证方式** | 测试 / 审查 |
| **状态** | Implemented |

### REQ-038：覆盖率门禁可配置

| 属性 | 值 |
|------|-----|
| **描述** | 覆盖率门禁阈值应支持通过项目 YAML 配置文件设定（默认行覆盖率 > 98%），支持按项目粒度定制。门禁结果应纳入 CI 报告和证据包 |
| **优先级** | P1 |
| **来源** | 项目级质量标准定制 |
| **实现模块** | `src/yuleosh/ci/config.py`、`src/yuleosh/ci/coverage_pipeline.py` |
| **验证方式** | 测试 |
| **状态** | Implemented |

### REQ-039：Token 预算限流

| 属性 | 值 |
|------|-----|
| **描述** | 系统应为 LLM 调用提供 Token 预算管理（TokenBudget），支持为不同 Agent 角色配置不同的预算上限。超限时自动降级或拒绝请求 |
| **优先级** | P1 |
| **来源** | LLM 成本控制需求 |
| **实现模块** | `src/yuleosh/llm/token_budget.py` |
| **验证方式** | 测试 |
| **状态** | Implemented |

### REQ-040：SQLite/PostgreSQL 双存储

| 属性 | 值 |
|------|-----|
| **描述** | 系统应支持 SQLite（默认）和 PostgreSQL（可选）两种存储后端。通过统一 AbstractStore 接口实现透明切换，设置 `YULEOSH_DB_URL=postgresql://...` 自动切换 |
| **优先级** | P1 |
| **来源** | 开发便捷性 + 生产性能需求 |
| **实现模块** | `src/yuleosh/store_interface.py`、`src/yuleosh/store.py`、`src/yuleosh/store_pg.py` |
| **验证方式** | 测试 |
| **状态** | Implemented |

### REQ-041：API 速率限制

| 属性 | 值 |
|------|-----|
| **描述** | 系统应为 REST API 端点提供可配置的速率限制（rate limiting），支持按 API Key 或用户身份限流，防止滥用 |
| **优先级** | P2 |
| **来源** | API 安全与稳定性需求 |
| **实现模块** | `src/yuleosh/api/ratelimit.py` |
| **验证方式** | 审查 / 演示 |
| **状态** | Implemented |

### REQ-042：密码安全认证

| 属性 | 值 |
|------|-----|
| **描述** | 系统应使用 bcrypt 进行密码哈希存储，JWT Token 进行会话认证。API 密钥支持轮换和吊销 |
| **优先级** | P0 |
| **来源** | 基本安全要求 |
| **实现模块** | `src/yuleosh/api/auth.py`、`src/yuleosh/api/apikeys.py` |
| **验证方式** | 测试 |
| **状态** | Implemented |

---

## 5. 需求追溯矩阵

| REQ-ID | 需求名称 | 功能域 | 实现模块 | 验证方式 | 测试文件 | 状态 |
|--------|----------|--------|----------|----------|----------|------|
| REQ-001 | Markdown 规格文档 | OpenSpec | `src/yuleosh/spec/` | 测试 | `test_spec_validate_ext.py` | Implemented |
| REQ-002 | SHALL/SHOULD/MAY 关键字 | OpenSpec | `src/yuleosh/spec/validate.py` | 测试 | `test_spec_validate_ext.py` | Implemented |
| REQ-003 | GIVEN/WHEN/THEN 场景 | OpenSpec | `src/yuleosh/spec/validate.py` | 测试 | `test_spec_validate_ext.py` | Implemented |
| REQ-004 | Spec-Diff 变更分析 | OpenSpec | `src/yuleosh/spec/diff.py` | 测试 | `test_spec_diff_ext.py` | Implemented |
| REQ-005 | 三层 CI 流水线 | CI | `src/yuleosh/ci/layers.py` | 测试 | `ci/test_ci_fixes_p0_p1.py` | Implemented |
| REQ-006 | MISRA C:2023 静态分析 | CI | `src/yuleosh/ci/misra_report/` | 测试 | `ci/test_e2e_report_pipeline.py` | Implemented |
| REQ-007 | 覆盖率收集与门禁 | CI | `src/yuleosh/ci/coverage_pipeline.py` | 测试 | `test_ci_stages.py` | Implemented |
| REQ-008 | KPI 趋势追踪 | CI | `src/yuleosh/ci/kpi/` | 测试 | `test_kpi.py` | Implemented |
| REQ-009 | 多 Agent 协作审查 | AI Review | `src/yuleosh/review/run.py` | 测试 | `test_review_run.py` | Implemented |
| REQ-010 | MISRA 规则映射解释 | AI Review | `src/yuleosh/llm/rag/engine.py` | 审查 | — | Implemented |
| REQ-011 | 审查报告生成 | AI Review | `src/yuleosh/evidence/collection.py` | 测试 | `test_review_run.py` | Implemented |
| REQ-012 | 证据包自动打包 | Evidence | `src/yuleosh/evidence/pack.py` | 测试 | `test_evidence_modules.py` | Implemented |
| REQ-013 | SHA-256 签名验证 | Evidence | `src/yuleosh/evidence/signer.py` | 测试 | `test_evidence_modules.py` | Implemented |
| REQ-014 | Evidence Check 校验 | Evidence | `src/yuleosh/evidence/check.py` | 测试 | `test_evidence_modules.py` | Implemented |
| REQ-015 | Web Dashboard 展示 | Dashboard | `src/yuleosh/ui/server.py` | 测试 | `test_ui_server_smoke.py` | Implemented |
| REQ-016 | 覆盖率趋势图 | Dashboard | `src/yuleosh/ci/coverage_trend.py` | 审查 | — | Implemented |
| REQ-017 | MISRA 违规趋势 | Dashboard | `src/yuleosh/ci/misra_trend.py` | 审查 | — | Implemented |
| REQ-018 | 多租户认证 | Dashboard | `src/yuleosh/ui/auth.py` | 测试 | `test_ui_server_smoke.py` | Implemented |
| REQ-019 | Jira 双向同步 | ALM | `src/yuleosh/alm/jira.py` | 审查 | — | Implemented |
| REQ-020 | Polarion 同步 | ALM | `src/yuleosh/alm/polarion.py` | 审查 | — | Implemented |
| REQ-021 | MISRA 规则向量检索 | RAG | `src/yuleosh/kb/store.py` | 审查 | — | Implemented |
| REQ-022 | 嵌入式最佳实践检索 | RAG | `src/yuleosh/kb/cli.py` | 审查 | — | Implemented |
| REQ-023 | 多后端烧录 | Cross | `src/yuleosh/cross/flash.py` | 审查 | — | Implemented |
| REQ-024 | SIL 仿真支持 | Cross | `src/yuleosh/cross/sil_runner.py` | 测试 | `test_sil_runner.py` | Implemented |
| REQ-025 | 30 任务 AI Benchmark | Benchmark | `benchmark/` | 审查 | — | Implemented |
| REQ-026 | 难度分级 | Benchmark | `benchmark/` | 审查 | — | Implemented |
| REQ-027 | Checkpoint 断点续跑 | Engine | `src/yuleosh/engine/checkpoint.py` | 测试 | `test_pipeline_extended.py` | Implemented |
| REQ-028 | ASPICE 合规检查器 | Compliance | `src/yuleosh/compliance/compliance_checker.py` | 测试 | `test_compliance.py` | Implemented |
| REQ-029 | Git Hooks 集成 | Hooks | `src/yuleosh/hooks/pre_commit.py` | 审查 | — | Implemented |
| REQ-030 | Plugin 插件系统 | Plugins | `src/yuleosh/plugins/registry.py` | 审查 | — | Implemented |
| REQ-031 | 用量计量与计费 | Usage | `src/yuleosh/usage/metering.py` | 审查 | — | Implemented |
| REQ-032 | AUTOSAR 支持 | AUTOSAR | `src/yuleosh/autosar/` | 审查 | — | Implemented |
| REQ-033 | 桌面客户端 | Desktop | `desktop/` | 审查 | — | Implemented |
| REQ-034 | HIL/SIL 适配层 | Adapter | `src/yuleosh/cross/sil_runner.py` | 测试 | `test_hil_runner.py` | Implemented |
| REQ-035 | Python >= 3.10 兼容 | Non-func | 全局 | CI 矩阵 | — | Implemented |
| REQ-036 | 单机可部署 | Non-func | 全局 | 审查 | — | Implemented |
| REQ-037 | 多 LLM 模型支持 | Non-func | `src/yuleosh/llm/client.py` | 测试 | — | Implemented |
| REQ-038 | 覆盖率门禁可配置 | Non-func | `src/yuleosh/ci/config.py` | 测试 | — | Implemented |
| REQ-039 | Token 预算限流 | Non-func | `src/yuleosh/llm/token_budget.py` | 测试 | — | Implemented |
| REQ-040 | SQLite/PostgreSQL 双存储 | Non-func | `src/yuleosh/store.py` | 测试 | — | Implemented |
| REQ-041 | API 速率限制 | Non-func | `src/yuleosh/api/ratelimit.py` | 审查 | — | Implemented |
| REQ-042 | 密码安全认证 | Non-func | `src/yuleosh/api/auth.py` | 测试 | — | Implemented |

### 5.1 追溯覆盖统计

| 指标 | 值 |
|------|-----|
| 需求总数 (REQ-xxx) | 42 |
| 已实现 (Implemented) | 42 |
| 测试覆盖 (有测试文件) | 26 (62%) |
| 审查覆盖 (人工/演示) | 16 (38%) |
| 计划中 (Planned) | 0 |

---

## 6. 需求变更历史

| 日期 | 变更 | 影响 REQ-ID | 原因 | 审批人 |
|------|------|-------------|------|--------|
| 2026-07-13 | 初始版本发布 | 全部 REQ-001~REQ-042 | SRS 初始编制 | 小克 |

---

## 附录 A：需求与 ASPICE SWE.1 BP 映射

| ASPICE SWE.1 BP | 描述 | 对应需求 |
|-----------------|------|----------|
| SWE.1.BP1 | 定义软件需求 | 本文档全部 REQ-xxx 条目 |
| SWE.1.BP2 | 结构化需求内容 | REQ-001 (Markdown 结构化)、REQ-002 (关键字语义) |
| SWE.1.BP3 | 评估需求影响 | REQ-004 (Spec-Diff 变更分析) |
| SWE.1.BP4 | 定义验证准则 | 各 REQ-xxx 的"验证方式"属性 |
| SWE.1.BP5 | 建立双向可追溯性 | §5 需求追溯矩阵 |
| SWE.1.BP6 | 确保一致性 | REQ-028 (ASPICE 合规检查器) |
| SWE.1.BP7 | 沟通已批准的软件需求 | 本文档通过 Git 版本控制分发 + Dashboard 实时展示；需求变更触发飞书/邮件通知，post-merge hook 自动同步变更至关联的 Jira/Polarion 条目；影响分析与回归测试范围通过三层 CI Pipeline 自动验证 |

## 附录 B：关键术语

| 术语 | 含义 |
|------|------|
| REQ-xxx | yuleOSH 软件需求唯一标识符，用于追溯矩阵的左端标识 |
| OpenSpec | 基于 Markdown 的规格定义格式，支持 RFC 2119 关键字 |
| ASPICE | Automotive SPICE — 汽车行业软件过程改进和能力测定标准 |
| Checkpoint | yuleOSH 的断点续跑引擎，支持 Pipeline 全量/注入/恢复三种模式 |
| Evidence Pack | 包含所有审计证据的自包含 ZIP 包，含 SHA-256 签名 |
| Track A/B | 双轨道审查：A 为 AI 自检（非阻塞），B 为 Agent 审查（阻塞） |

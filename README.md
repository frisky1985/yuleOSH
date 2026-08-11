<div align="center">
  <h1>yuleOSH</h1>
  <p><strong>嵌入式软件合规开发自动化平台<br>
  Embedded Software Compliance Automation Platform<br>
  AI 辅助 · SWE 全流程 · 证据包一键生成</strong></p>

  <!-- Badges -->
  <p>
    <a href="https://github.com/frisky1985/yuleOSH/actions">
      <img src="https://img.shields.io/badge/CI-Passing-brightgreen?style=flat-square" alt="CI">
    </a>
    <img src="https://img.shields.io/badge/version-3.13.0-blue?style=flat-square" alt="Version">
    <img src="https://img.shields.io/badge/license-Elastic%202.0-green?style=flat-square" alt="License">
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-ff69b4?style=flat-square" alt="Python">
    <img src="https://img.shields.io/badge/tests-10000%2B%20passing-brightgreen?style=flat-square" alt="Tests">
    <img src="https://img.shields.io/badge/coverage-85%25-success?style=flat-square" alt="Coverage">
    <img src="https://img.shields.io/badge/ASPICE%20SWE.1-6-traceable-success?style=flat-square" alt="ASPICE">
  </p>

  <p>
    <code>pip install yuleosh</code> → running in 2 minutes.<br>
    No NDA. No Sales Call. No License Negotiation.
  </p>

  <p>
    <a href="#quick-start">Quick Start</a> ·
    <a href="#features">Features</a> ·
    <a href="#architecture">Architecture</a> ·
    <a href="#supported-platforms">Platforms</a> ·
    <a href="#pricing">Pricing</a> ·
    <a href="#roadmap">Roadmap</a>
  </p>
</div>

---

> **🇬🇧 English** · [🇨🇳 中文](#yuleosh-嵌入式软件合规开发自动化平台)

---

## 📋 Table of Contents

- [What is yuleOSH?](#what-is-yuleosh)
- [Quick Start](#quick-start)
- [Features](#features)
- [Architecture](#architecture)
- [Supported Platforms](#supported-platforms)
- [Directory Layout](#directory-layout)
- [Production Deployment](#production-deployment)
- [Pricing & Editions](#pricing--editions)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

---

## What is yuleOSH?

**yuleOSH** is an ASPICE assistance tool for embedded development powered by AI. It converts natural language requirements into complete, CI/CD-ready firmware projects with Automotive SPICE traceability assistance.

**In one sentence:** yuleOSH takes a spec or user story and outputs reviewed, tested, CI-instrumented firmware with ASPICE traceability assistance — all in under 2 minutes.

> 📖 **完整使用说明**: [docs/USER-GUIDE.md](docs/USER-GUIDE.md) — 从安装、初始化、
> 写 spec、配置 LLM、跑全流程 pipeline 到出合规证据包的完整操作指南。

---

## ⚡ Quick Start — 3 Commands

```bash
# Step 1: Install (15 seconds)
pip install yuleosh

# Step 2: Initialize a project (15 seconds)
yuleosh init my-project

# Step 3: Run the full pipeline (90 seconds)
cd my-project && yuleosh pipeline run docs/spec.md
```

**3 commands. 2 minutes. From zero to firmware.**  
No MCU board, no compiler setup, no document reading required.

---

## 🎬 Demo — Try the UART Demo

```bash
pip install yuleosh
yuleosh demo uart
cd uart-demo && yuleosh pipeline run --mock docs/spec.md
```

Output you'll see:
```
Hello from yuleOSH Demo UART
demo UART ready — send characters to echo
[yuleOSH] alive — 5s
[yuleOSH] alive — 10s
```

---

## Features

### 🧠 OpenSpec Engine
Structured requirements using RFC 2119 keywords (`SHALL`/`SHOULD`/`MAY`) with `GIVEN`/`WHEN`/`THEN` scenarios. Auto-validates, diffs, and traces every requirement through design → code → test.

### 🔍 AI Code Review
Parallel 4-agent review matrix covering architecture, domain correctness, coding style, and test coverage. Includes 8 embedded-C static analysis checks plus resource usage prediction (stack, heap, flash, RAM).

### 🔧 Hardware-in-the-Loop
Built-in adapters for **OpenOCD** (STM32), **JLink** (ARM Cortex-M), and **esptool** (ESP32). Auto-flash, serial monitor, and GDB debugging — one command away.

### ☁️ SaaS Dashboard
Next.js web dashboard with PostgreSQL multi-tenant storage, JWT authentication, org/project isolation, and real-time pipeline monitoring.

### 📋 Compliance
One-click generation of traceability matrices, acceptance matrices, and compliance evidence ZIP archives — assists in preparing ASPICE SWE.1~SWE.6 audit evidence.

### 🛡️ Security & Auditability (安全可审计, v3.13+)
Every state-changing operation is recorded in an **append-only, tamper-evident audit log**. Each event carries a SHA-256 hash chained to the previous event — any edit, deletion, or reordering is detected by `yuleosh audit verify`. Built for teams whose compliance story depends on being able to say: *"our toolchain's own audit trail is intact."*

### ⚙️ D3 Code Generation Loop (v3.4+)
Generate code directly from spec/architecture in `generate-code` mode. Every generated file is automatically compile-verified (Python/C), with an auto-repair loop (up to 3 rounds) that feeds compiler errors back into the LLM until it passes.

### 🧩 Skills Library (v3.4+)
Built-in skills (`autosar-coding`, `misra-fix`, `python-testing`) that are injected into LLM prompts for domain-consistent code generation. Extensible registry + CLI (`yuleosh skills list/show`).

### 🧭 Methodology Platform (v3.10+)
Three-layer enforcement gates blending engineering methodology into agent behavior: L1 behavior constraints → L2 methodology contract gates (executable) → L3-B standalone gate engine (zero-dependency, one-click mount to any project with a standalone gate CLI). Piloted on yuleASR.

### 🌐 Mixed-Language CI (v3.12+)
Embedded C MISRA gates extended to **Go/Python projects** (`project_language: mixed`), Go monorepo multi-module build/vet/test; cppcheck relative-path/exclude/scan_dirs fixes. yuleDKCS measured **690 → 0 MISRA C:2023 violations** (57 files).

### 🔄 Loop Engineering (v3.0+)
Four closed-loop feedback systems: defect→spec traceability, field defect→FMEA safety analysis, KPI→RCA→improvement tickets, and self-evolving knowledge graph with confidence scoring.

### 🧠 Knowledge Graph
Knowledge graph store (SQLite BFS / PostgreSQL recursive CTE) for traceability, impact analysis, and incremental CI hooks.

### Full Automation Pipeline
```
User Story → OpenSpec → SDD → DDD → Code Gen → Internal Review →
Test Planning → Code Review → CI Run → Evidence Pack → Deployment
```

---

## Architecture

### 4-Layer Architecture

```
[User Story / Spec] ──▶ [OpenSpec Engine] ──▶ [Agent Pipeline] ──▶ [Code Gen]
                              │                       │                    │
                              ▼                       ▼                    ▼
                      SHALL/SHOULD/MAY         10-Step Agent        C + Python
                      + GIVEN/WHEN/THEN        Orchestration        Firmware
                                                                         │
                              ┌──────────────────────────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │    Review        │
                    │  (4-Agent Matrix) │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
                    │   CI Layer 1    │▶──▶ │   CI Layer 2     │▶──▶ │   CI Layer 3     │
                    │  Unit + Coverage │     │  Cross-Compile    │     │  System Verify    │
                    │  + Plan-Lint     │     │  + Static Analysis│     │  + Evidence       │
                    └─────────────────┘     └──────────────────┘     └──────────────────┘
                                                                              │
                                                                              ▼
                                                                     ┌──────────────────┐
                                                                     │  Deploy Hardware │
                                                                     │  OpenOCD / JLink  │
                                                                     │  / esptool        │
                                                                     └──────────────────┘
```

### Layer Details

<details>
<summary><strong>1. OpenSpec Engine</strong> — Spec parsing, validation, version diff, state machine</summary>

- **Parser**: SHALL/SHOULD/MAY + GIVEN/WHEN/THEN
- **Validator**: Hierarchical requirement IDs (SYS/SW/FEATURE)
- **Differ**: Version-to-version delta with impact analysis
- **State machine**: PROPOSED → APPROVED → IMPLEMENTED → VERIFIED
- **Location**: `src/yuleosh/spec/`
</details>

<details>
<summary><strong>2. Agent Pipeline</strong> — 10-step LLM orchestration</summary>

- 10-step orchestration: spec → SDD → DDD → code → test → review
- LLM-agnostic client (OpenAI-compatible API)
- Blocking review gates before each stage transition
- S.U.P.E.R. startup analysis for new requirements
- **Location**: `src/yuleosh/pipeline/`, `src/yuleosh/llm/`
</details>

<details>
<summary><strong>3. CI/CD Engine</strong> — 3-layer automated verification</summary>

- **Layer 1 — Dev Verify**: Unit tests + coverage gate + plan-lint on every commit
- **Layer 2 — Integration**: Cross-compilation + MISRA static analysis on MR
- **Layer 2.5 — AI Review**: 4-agent parallel code review
- **Layer 3 — System Verify**: System tests + evidence pack on release tag
- **Location**: `src/yuleosh/ci/`
</details>

<details>
<summary><strong>4. Hardware & Cross-Compilation</strong> — MCU flashing, monitoring, debugging</summary>

- Target configuration for MCU families
- Flash, monitor, and debug orchestration
- SIL (Software-in-the-Loop) runner with assertion checking
- Extensible adapter architecture
- **Location**: `src/yuleosh/cross/`, `src/yuleosh/hardware/`
</details>

### Supporting Modules

| Module | Path | Purpose |
|:-------|:-----|:--------|
| Evidence Engine | `src/yuleosh/evidence/` | Traceability matrix + acceptance matrix + compliance ZIP |
| Review Engine | `src/yuleosh/review/` | 4-agent parallel review + resource predictor |
| CodeGen Engine | `src/yuleosh/codegen/` | D3 code generation + compile verification + auto-repair loop |
| Skills Library | `src/yuleosh/skills/` | Skill registry (`autosar-coding`/`misra-fix`/`python-testing`) + prompt injection |
| Loop Engine | `src/yuleosh/loop_engine/` | 4 closed-loop feedback (defect/FMEA/KPI/KG) |
| Knowledge Graph | `src/yuleosh/knowledge_graph/` | KG store (SQLite BFS / PostgreSQL CTE) + incremental CI |
| Knowledge Base | `src/yuleosh/kb/` | Persistent KB store (env-isolatable via `YULEOSH_KB_DB`) |
| Memory | `src/yuleosh/memory/` | Cross-session fact store + FTS5 session search (`yuleosh memory` / `yuleosh session`) |
| Test Generation | `src/yuleosh/testgen/` | Auto-generate test harness from spec scenarios |
| Plugins | `src/yuleosh/plugins/` | Plugin registry + sandboxed execution |
| Usage/Billing | `src/yuleosh/usage/` `src/yuleosh/billing/` | Metering + Stripe gateway (for SaaS) |
| Auth/RBAC/Audit | `src/yuleosh/api/` `src/yuleosh/rbac/` `src/yuleosh/audit/` | JWT auth + role-based access + audit log |
| ALM | `src/yuleosh/alm/` | ALM tool integration (Jira/linear etc.) |
| CLI | `src/yuleosh/cli/` | 25 subcommands (`pipeline`/`skills`/`kg`/`kpi`/`coverage`/…) |
| API | `src/yuleosh/api/` | Modular REST API v1 (14+ resource handlers, HMAC webhooks) |
| Dashboard UI | `frontend/` | Next.js web dashboard |
| Preview | `src/yuleosh/preview/` | Pre-pipeline analysis & scoring |

---

## Supported Platforms

| Platform | Flash Tool | Debugger |
|:---------|:-----------|:---------|
| ESP32 / ESP32-S3 | esptool | idf-monitor + GDB |
| STM32 (F4/H7/G0) | OpenOCD | OpenOCD + GDB |
| Any ARM Cortex-M | JLinkExe | JLinkGDBServer |
| Custom | Plugin API | Plugin API |

---

## Directory Layout

```
yuleOSH/
├── src/yuleosh/
│   ├── spec/          OpenSpec parser, validator, differ
│   ├── pipeline/      Agent pipeline orchestrator (10 steps)
│   ├── ci/            3-layer CI/CD with dependency chaining
│   ├── review/        4-agent parallel review + resource predictor
│   ├── codegen/       D3 code generation + compile verify + auto-repair
│   ├── skills/        Skills registry + prompt injection
│   ├── evidence/      Traceability + acceptance + compliance ZIP
│   ├── hardware/      Flash, monitor, debug orchestration
│   ├── cross/         Cross-compilation + HIL/SIL runners
│   ├── testgen/       Auto test harness generation
│   ├── llm/           LLM-agnostic agent client
│   ├── plugins/       Plugin registry + sandbox
│   ├── api/           Modular REST API v1 (JWT + HMAC webhooks)
│   ├── ui/            Dashboard server (auth, routes)
│   ├── cli/           CLI subcommands (25)
│   ├── loop_engine/   Loop Engineering 4 closed loops
│   ├── knowledge_graph/  KG store (SQLite/PostgreSQL)
│   ├── kb/            Knowledge base store
│   ├── alm/           ALM tool integration
│   ├── audit/ rbac/ billing/ tenant/   Enterprise features
│   ├── usage/         Metering + billing integration
│   ├── preview/       Pre-pipeline analysis & scoring
│   └── store.py       Multi-tenant SQLite/PostgreSQL backend
├── frontend/          Next.js SaaS dashboard
├── tests/             10000+ tests (392 files, all passing)
├── docs/              Specifications, guides, reports
├── deploy/            Production deployment configs
├── Dockerfile         Multi-stage production Dockerfile
├── docker-compose.yml Production Docker Compose
├── install.sh         One-line production install
└── pyproject.toml     Python packaging
```

---

## Production Deployment

### Docker Compose (Recommended)

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
cp deploy/.env.production.example deploy/.env.production
# Edit deploy/.env.production with your secrets
docker compose -f deploy/docker-compose.yml up -d
```

### pip Install (Standalone CLI)

```bash
pip install yuleosh
yuleosh init my-project
yuleosh pipeline run docs/spec.md
```

### One-Line Install (Full Suite)

```bash
curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash
```

### From Source

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
pip install -e .
yuleosh init .
yuleosh help
```

---

## Pricing & Editions

yuleOSH offers multiple editions tailored to different needs. The open source edition is free under the Elastic License 2.0; commercial editions are priced by team size and deployment model — [contact sales](mailto:sales@yuleosh.com) for a quote.

| Edition | Price | Best For |
|:--------|:------|:---------|
| **Open Source** (Elastic License 2.0) | Free | Individual developers, open-source projects |
| **Team / Pro** | Contact sales | Embedded teams needing ASPICE compliance + full pipeline |
| **Enterprise** | Contact sales | Large organizations needing private deployment + RMB contract support |

---

## Roadmap

| Version | Focus | Status |
|:--------|:------|:-------|
| v0.1.0 | Foundation — OpenSpec, agent pipeline, CI/CD, evidence | ✅ |
| v0.2.0 | ASPICE compliance — strict mode, bidirectional tracing | ✅ |
| v0.3.0 | Ground reinforcement — test planning, hierarchy, cross-compile | ✅ |
| v1.0.0 | Production — HIL adapter, plugin marketplace, scaling | ✅ |
| v2.x | SaaS multi-tenant, knowledge graph, enterprise modules | ✅ |
| v3.0.0 | Loop Engineering — 4 closed-loop feedback (defect/FMEA/KPI/KG) | ✅ |
| v3.3.0 | Production sprint — quality gates, ASPICE evidence, coverage 76% | ✅ |
| v3.4.x | D3 codegen loop + Skills library + coverage 83% + ultra-review P0 security | ✅ |
| v3.5.0 | Coverage 85-90% + P1/P2 backlog from ultra-review + SaaS GA | 🚧 |
| v4.0.0 | Cloud — multi-region, data residency, managed hosting | 📋 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code conventions, and PR workflow.

## Security

See [SECURITY.md](SECURITY.md) for our vulnerability disclosure process.

### Auditability (安全可审计)

yuleOSH is built to be **secure and auditable** — the toolchain's own audit trail is tamper-evident:

- **Append-only audit log**: every state-changing operation (project/pipeline/review/auth/billing/evidence) is recorded to `data/audit/YYYY-MM-DD.jsonl` — no edits, no deletes.
- **SHA-256 hash chain**: each event's hash covers its payload plus the previous event's hash. Editing, deleting, or reordering any recorded event breaks the chain.
- **`yuleosh audit verify`**: replay the chain to prove integrity. Exit code 0 = intact, 1 = tampering detected (with the exact broken position).
- **Evidence packs embed the proof**: `yuleosh audit evidence` automatically runs the verification and ships `audit-log-verification.json` inside the bundle — your ASPICE evidence pack carries its own audit-trail integrity statement.
- **Legacy compatible**: logs written before the hash-chain feature remain readable and are seamlessly anchored into the chain.

```bash
# Prove your audit trail is intact — any tampering fails the check
yuleosh audit verify
# ✅ 审计日志哈希链完整（安全可审计）

# Machine-readable output for CI / evidence packs
yuleosh audit verify --json
```

## License

Elastic License 2.0 — see [LICENSE](LICENSE) for details. Copyright (c) 2025 frisky1985.

---

<p align="center">
  <sub>Built for embedded teams who ship quality firmware, fast.</sub>
</p>

---

# yuleOSH — 嵌入式软件合规开发自动化平台

## 📋 目录

- [项目简介](#项目简介)
- [快速开始](#快速开始)
- [核心特性](#核心特性)
- [架构](#架构)
- [支持平台](#支持平台)
- [目录结构](#目录结构)
- [生产部署](#生产部署)
- [定价与版本](#定价与版本)
- [路线图](#路线图)
- [参与贡献](#参与贡献)
- [安全](#安全)
- [许可证](#许可证)

---

## 项目简介

**yuleOSH** 是嵌入式软件合规开发自动化平台（ASPICE SWE 辅助工具），由 AI 驱动，将自然语言需求自动转化为完整、CI/CD就绪的固件工程，辅助 Automotive SPICE SWE.1~SWE.6 合规证据准备。它用 AI 辅助流水线替代了需求工程、代码生成、审查、测试规划和合规证据收集中繁琐的人工环节。

**一句话：** yuleOSH 接收需求描述，输出经过审查、测试、CI集成的固件，并附带 ASPICE 合规辅助证据——AI 辅助完成。

---

## 快速开始

```bash
# 第一步：安装（15秒）
pip install yuleosh

# 第二步：初始化项目（15秒）
yuleosh init my-project

# 第三步：运行完整流水线（90秒）
cd my-project && yuleosh pipeline run docs/spec.md
```

**三行命令，两分钟，从零到固件。**

---

## 核心特性

### 🧠 OpenSpec 规范引擎
结构化需求，使用 RFC 2119 关键字（`SHALL`/`SHOULD`/`MAY`）配合 `GIVEN`/`WHEN`/`THEN` 场景。自动验证、差异对比、全链路追溯。

### 🔍 AI 代码审查
四代理并行审查矩阵覆盖架构、领域正确性、代码风格和测试覆盖率。8项嵌入式C静态分析 + 资源使用预测。

### 🔧 硬件在环
内置 **OpenOCD**（STM32）、**JLink**（ARM Cortex-M）、**esptool**（ESP32）适配器。一条命令即可自动刷写、监视串口、启动GDB调试。

### ☁️ SaaS 管理面板
Next.js 管理面板 + PostgreSQL 多租户存储 + JWT 认证 + 组织/项目隔离 + 流水线实时监控。

### 📋 合规审计
一键生成追溯矩阵、验收矩阵和合规证据 ZIP 包——辅助 ASPICE SWE.1~SWE.6 证据准备。

### ⚙️ D3 编码生成闭环（v3.4+）
`generate-code` 模式直接从 spec/架构生成代码，自动编译验证（Python/C），失败自动修复循环（最多 3 轮，编译错误回喂 LLM）。

### 🧩 技能库（v3.4+）
内置技能（`autosar-coding`/`misra-fix`/`python-testing`）注入 LLM prompt，保证生成代码的领域一致性。可扩展注册表 + CLI（`yuleosh skills list/show`）。

### 🧭 方法论平台化（v3.10+）
融合工程方法论的**三层门禁体系**：L1 行为约束层 → L2 方法论契约门禁（可执行化）→ L3-B 独立门禁引擎（standalone 零依赖，一键挂载到任意项目，含独立门禁 CLI）。已在 yuleASR 试点成功。

### 🌐 混合语言 CI（v3.12+）
嵌入式 C MISRA 门禁扩展支持 **Go/Python 项目**（`project_language: mixed`），Go monorepo 多模块 build/vet/test；cppcheck 相对路径/exclude/scan_dirs 修复。yuleDKCS 实测 MISRA C:2023 **690 → 0 违规**（57 文件）。

### 🔄 Loop Engineering（v3.0+）
四大闭环：缺陷→需求回溯、现场→FMEA 安全分析、KPI→RCA→改进工单、知识图谱自进化（置信度评分）。

### 🧠 知识图谱
知识图谱存储（SQLite BFS / PostgreSQL 递归 CTE），支撑追溯、影响分析、增量 CI 钩子。

### AI 辅助流水线
```
用户需求 → OpenSpec → 系统设计 → 详细设计 → 代码生成 → 内审 →
测试规划 → 代码审查 → CI运行 → 证据打包 → 部署
```

---

## 架构

```
[用户需求] ──▶ [OpenSpec 引擎] ──▶ [代理流水线] ──▶ [代码生成]
                                                    │
                                                    ▼
                                          验证 → CI → 硬件部署
```

四层架构细节参见英文版上方说明。

---

## 支持平台

| 平台 | 刷写工具 | 调试器 |
|:-----|:---------|:-------|
| ESP32 / ESP32-S3 | esptool | idf-monitor + GDB |
| STM32 (F4/H7/G0) | OpenOCD | OpenOCD + GDB |
| ARM Cortex-M 系列 | JLinkExe | JLinkGDBServer |
| 自定义平台 | 插件 API | 插件 API |

---

## 目录结构

```
yuleOSH/
├── src/yuleosh/    核心源码模块（spec/pipeline/ci/codegen/skills/kg/loop_engine/api/cli…）
├── frontend/       Next.js SaaS 管理面板
├── tests/          10000+ 测试（392 文件，全部通过）
├── docs/           需求文档、指南、报告
├── deploy/         生产部署配置
├── Dockerfile      多阶段 Docker 构建
├── docker-compose.yml  生产 Docker Compose
├── install.sh      一键安装脚本
└── pyproject.toml  Python 包配置
```

---

## 生产部署

### Docker Compose（推荐）

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
cp deploy/.env.production.example deploy/.env.production
# 编辑 deploy/.env.production 填入密钥
docker compose -f deploy/docker-compose.yml up -d
```

### pip 安装（CLI 模式）

```bash
pip install yuleosh
yuleosh init my-project
yuleosh pipeline run docs/spec.md
```

### 一键安装（完整套件）

```bash
curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash
```

### 源码安装

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
pip install -e .
yuleosh init .
yuleosh help
```

---

## 定价与版本

yuleOSH 提供多个版本。开源版基于 Elastic License 2.0 免费使用；商业版按团队规模与部署方式定价，请 [联系销售](mailto:sales@yuleosh.com) 获取报价。

| 版本 | 定价 | 适用场景 |
|:-----|:-----|:---------|
| **开源版** (Elastic License 2.0) | 免费 | 个人开发者、开源项目 |
| **团队版 / Pro** | 联系销售 | 嵌入式合规团队，全功能流水线 |
| **企业版** | 联系销售 | 大型企业，私有化部署 + 人民币合同支持 |

---

## 路线图

| 版本 | 重点 | 状态 |
|:-----|:-----|:-----|
| v0.1.0 | 基础—OpenSpec、代理流水线、CI/CD、证据 | ✅ |
| v0.2.0 | ASPICE合规—严格模式、双向追溯 | ✅ |
| v0.3.0 | 地基加固—测试规划、层级、交叉编译 | ✅ |
| v1.0.0 | 生产就绪—HIL适配器、插件市场、扩展 | ✅ |
| v2.x | SaaS 多租户、知识图谱、企业模块 | ✅ |
| v3.0.0 | Loop Engineering—四大闭环（缺陷/FMEA/KPI/KG） | ✅ |
| v3.3.0 | 量产冲刺—质量门禁、ASPICE 证据、覆盖率 76% | ✅ |
| v3.4.x | D3 编码生成闭环 + 技能库 + 覆盖率 83% + ultra-review P0 安全 | ✅ |
| v3.5.x | 覆盖率 84% + ultra-review P1/P2 backlog + SaaS 加固 | ✅ |
| v3.6.x | 架构/质量冲刺 + yuleDKCS 试点 | ✅ |
| v3.7.x | 工具链 + 交叉编译加固 | ✅ |
| v3.8.x | 量产冲刺 + 门禁体系 | ✅ |
| v3.9.x | 全量测试 10017 passed / 0 failed，覆盖率 84.17% | ✅ |
| v3.10.x | 方法论约束层（L1）+ 真实 LLM 集成 + CI 门禁复活 | ✅ |
| v3.11.0 | 方法论契约门禁（L2）可执行化 | ✅ |
| v3.12.x | 方法论平台化（L3-B 门禁引擎）+ 混合语言 CI（Go/Python/C MISRA）+ yuleDKCS 690→0 违规 | ✅ |
| v4.0.0 | 云端—多区域、数据驻留、托管服务 | 📋 |

---

## 参与贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发环境配置、代码规范和 PR 流程。

## 安全

参见 [SECURITY.md](SECURITY.md) 了解漏洞披露流程。

---

## MISRA 基准测试（Benchmark）已知限制

> **诚实声明（2026-08-07 修订）：** `tests/test_misra_benchmark.py` 中的 MISRA
> 误报/漏报基准当前有 **11 个场景**（5 个 known-positive 漏检 + 6 个 clean-code
> 已知误报）受 cppcheck misra addon 工具链限制影响，无法通过验证。这些场景在测试中
> 以**显式 skip + 注释**标记，**不冒充全绿**；实测快照见
> `benchmark/results/misra-benchmark-report.json`（cppcheck 2.17.1 记录）。

已知限制明细：

- **漏检（FN，5 个）**：`case001`/`case009`/`case010`/`case011`/`case012` 的预期规则
  （10.1 / 18.2 / 8.2 / 10.1 / 14.3）未被 cppcheck misra addon 检出。记录快照的
  `actual_count` 已显示同一现象（检出了其他规则但非预期规则），属工具链固有行为而非回归。
- **已知误报（FP，6 个）**：`case002`~`case007` 为记录在案的误报场景（基准报告
  `validation: false_positive`），工具在"干净代码"上仍报告违规。

因此：**本基准的通过数不代表 MISRA 合规全绿**。工具链升级（cppcheck / misra addon
版本变化）后，应重新生成基准快照并复核这些场景，再移除对应的 skip。

---

## 合规评级说明（话术修正）

审计报告（`yuleosh audit-report`）中的 **E1–E3 等级是"证据覆盖度"分级**：由通过状态
证据占该过程维度证据总数的比例计算得出（E3 ≥90% 且零失败 / E2 ≥70% 且失败 <20% /
E1 ≥30% / NI 无证据或 <30%）。

**E1–E3 不是 Automotive SPICE 能力等级（Capability Level），也不代表任何正式评估
结论**（如 CL1 等），仅用于内部量化"证据链是否完整"。如需正式 ASPICE 评估，请咨询
经认可的评估机构。详见下方法律免责声明。

---

## 法律免责声明

yuleOSH 是一款 ASPICE 合规辅助工具，不替代正式的 ASPICE 认证评估。合规状态取决于组织级项目管理流程，工具生成的结果仅供参考。

---

## 许可证

Elastic License 2.0 — 详见 [LICENSE](LICENSE)。Copyright (c) 2025 frisky1985。

---

<p align="center">
  <sub>为认真交付优质固件的嵌入式团队而构建。</sub>
</p>

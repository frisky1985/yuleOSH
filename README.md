<div align="center">
  <h1>yuleOSH</h1>
  <p><strong>AI-Powered Embedded Development Pipeline<br>
  From spec to hardware, fully automated.</strong></p>

  <!-- Badges -->
  <p>
    <a href="https://github.com/frisky1985/yuleOSH/actions">
      <img src="https://img.shields.io/badge/CI-L1%20L2%20L3%20Passing-brightgreen?style=flat-square" alt="CI">
    </a>
    <img src="https://img.shields.io/badge/version-1.0.0-blue?style=flat-square" alt="Version">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-ff69b4?style=flat-square" alt="Python">
    <img src="https://img.shields.io/badge/coverage-86%25-yellow?style=flat-square" alt="Coverage">
    <img src="https://img.shields.io/badge/ASPICE-compliant-8A2BE2?style=flat-square" alt="ASPICE">
  </p>
</div>

---

<p align="center">
  <strong>Pricing</strong><br>
  ▶ <strong>Free:</strong> ¥0 — 3 projects, AI Code Review, ESP32 templates &nbsp;·&nbsp;
  ▶ <strong>Pro:</strong> ¥199/mo (¥1,999/yr) — unlimited projects, full pipeline, HIL, Vector adapters &nbsp;·&nbsp;
  ▶ <strong>Enterprise:</strong> ¥98,000/yr — on-prem, SAML, SLA, SOC 2
</p>

<p align="center">
  <code>pip install yuleosh</code> → you're running in 5 minutes.<br>
  No NDA. No Sales Call. No License Negotiation.
</p>

---

> **🇬🇧 English** · [🇨🇳 中文](#yuleosh-ai驱动的嵌入式开发流水线)

<p align="center">
  <img src="https://img.shields.io/badge/status-production%20ready-success?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/architecture-4%20layer-blue?style=for-the-badge" alt="Architecture">
  <img src="https://img.shields.io/badge/tests-988%20passing-success?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/platforms-STM32%20%7C%20ESP32%20%7C%20ARM-success?style=for-the-badge" alt="Platforms">
</p>

---

# yuleOSH — AI-Powered Embedded Development Pipeline

## What is yuleOSH?

**yuleOSH** is an AI-powered embedded development pipeline that converts natural language requirements into complete, CI/CD-ready firmware projects. It replaces the manual, error-prone steps of requirements engineering, code generation, review, test planning, and compliance evidence collection with an automated agent pipeline.

**One sentence:** yuleOSH takes a spec or user story and outputs reviewed, tested, CI-instrumented firmware with full ASPICE-compliant traceability — automatically.

### Pipeline Architecture

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

## Key Features

### OpenSpec规范驱动
Requirements are written in a structured format using RFC 2119 keywords (`SHALL`/`SHOULD`/`MAY`) with `GIVEN`/`WHEN`/`THEN` scenarios. The spec engine validates, diffs, and traces every requirement through design → code → test.

### AI Code Review — 8 Embedded C Checks
Parallel 4-agent review matrix covering architecture, domain correctness, coding style, and test coverage. Includes 8 embedded-C specific static analysis checks plus resource usage prediction (stack, heap, flash, RAM).

### Hardware-in-the-Loop
Built-in adapters for **OpenOCD** (STM32), **JLink** (ARM Cortex-M), and **esptool** (ESP32). Auto-flash, serial monitor, and GDB debugging are one command away.

### SaaS-Ready Dashboard
Next.js web dashboard with PostgreSQL multi-tenant storage, JWT authentication, org/project isolation, and real-time pipeline monitoring.

### Full Automation Pipeline
```
User Story → OpenSpec → SDD → DDD → Code Gen → Internal Review → 
Test Planning → Code Review → CI Run → Evidence Pack → Deployment
```

### ASPICE / ISO 26262 Compliance
One-click generation of traceability matrices, acceptance matrices, and compliance evidence ZIP archives — ready for audit.

## Quick Start

```bash
# Install
pip install yuleosh

# Initialize a project
yuleosh init my-project

# Run the full pipeline (spec → code → test → CI → evidence)
yuleosh pipeline run

# Or in Docker
docker compose up -d
```

## Supported MCU / Platforms

| Platform | Flash Tool | Debugger |
|:---------|:-----------|:---------|
| ESP32 / ESP32-S3 | esptool | idf-monitor + GDB |
| STM32 (F4/H7/G0) | OpenOCD | OpenOCD + GDB |
| Any ARM Cortex-M | JLinkExe | JLinkGDBServer |
| Custom | Plugin API | Plugin API |

## Architecture Overview

yuleOSH is built on 4 core layers:

### 1. OpenSpec Engine (`src/spec/`)
- Parser: SHALL/SHOULD/MAY + GIVEN/WHEN/THEN
- Validator: hierarchical requirement IDs (SYS/SW/FEATURE)
- Differ: version-to-version delta with impact analysis
- State machine: PROPOSED → APPROVED → IMPLEMENTED → VERIFIED

### 2. Agent Pipeline (`src/pipeline/`, `src/llm/`)
- 10-step orchestration: spec → SDD → DDD → code → test → review
- LLM-agnostic client (OpenAI-compatible API)
- Blocking review gates before each stage transition
- S.U.P.E.R. startup analysis for new requirements

### 3. CI/CD Engine (`src/ci/`)
- **Layer 1 — Dev Verify:** unit tests + coverage gate + plan-lint on every commit
- **Layer 2 — Integration:** cross-compilation + MISRA static analysis on MR
- **Layer 2.5 — AI Review:** 4-agent parallel code review
- **Layer 3 — System Verify:** system tests + evidence pack on release tag

### 4. Hardware & Cross-Compilation (`src/cross/`, `src/hardware/`)
- Target configuration for MCU families
- Flash, monitor, and debug orchestration
- SIL (Software-in-the-Loop) runner with assertion checking
- Extensible adapter architecture

### Supporting Modules

| Module | Path | Purpose |
|:-------|:-----|:--------|
| Evidence Engine | `src/evidence/` | Traceability matrix + acceptance matrix + compliance ZIP |
| Review Engine | `src/review/` | 4-agent parallel review + resource predictor |
| Test Generation | `src/testgen/` | Auto-generate test harness from spec scenarios |
| Plugins | `src/plugins/` | Plugin registry + sandboxed execution |
| Usage/Billing | `src/usage/` | Metering + Stripe gateway (for SaaS deployments) |
| CLI | `src/cli/` | 12+ subcommands |
| API | `src/api/` | REST API v1 with 14 resource handlers |
| Dashboard UI | `frontend/` | Next.js web dashboard |

## Directory Layout

```
yuleOSH/
├── src/
│   ├── spec/          OpenSpec parser, validator, differ
│   ├── pipeline/      Agent pipeline orchestrator (10 steps)
│   ├── ci/            3-layer CI/CD with dependency chaining
│   ├── review/        4-agent parallel review + resource predictor
│   ├── evidence/      Traceability + acceptance + compliance ZIP
│   ├── hardware/      Flash, monitor, debug orchestration
│   ├── cross/         Cross-compilation + HIL/SIL runners
│   ├── testgen/       Auto test harness generation
│   ├── llm/           LLM-agnostic agent client
│   ├── plugins/       Plugin registry + sandbox
│   ├── api/           REST API v1 (14 handlers)
│   ├── ui/            Dashboard server (auth, routes)
│   ├── cli/           CLI subcommands
│   ├── usage/         Metering + billing integration
│   └── store.py       Multi-tenant SQLite/PostgreSQL backend
├── frontend/          Next.js SaaS dashboard
├── tests/             257+ tests (all passing)
├── docs/              Specifications, guides, reports
├── deploy/            Production deployment configs
├── Dockerfile         Multi-stage production Dockerfile
├── Dockerfile.cross   ARM/RISC-V cross-compilation image
├── docker-compose.yml Production Docker Compose
├── install.sh         One-line production install
└── pyproject.toml     Python packaging
```

## Production Deployment

### Docker Compose (Recommended)

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
mkdir -p projects .yuleosh
export YULEOSH_API_KEY="your-secure-random-key"
docker compose up -d
```

### One-Line Install

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

## Roadmap

| Version | Focus | Status |
|:--------|:------|:-------|
| v0.1.0 | Foundation — OpenSpec, agent pipeline, CI/CD, evidence | ✅ |
| v0.2.0 | ASPICE compliance — strict mode, bidirectional tracing | ✅ |
| v0.3.0 | Ground reinforcement — test planning, hierarchy, cross-compile | ✅ |
| v1.0.0 | Production — HIL adapter, plugin marketplace, scaling | 🚧 |
| v1.1.0 | Enterprise — RBAC, audit logging, SAML SSO | 📋 |
| v1.2.0 | Cloud — multi-region, data residency, managed hosting | 📋 |

## Related Projects



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code conventions, and PR workflow.

## Security

See [SECURITY.md](SECURITY.md) for our vulnerability disclosure process.

## License

MIT License — see [LICENSE](LICENSE) for details. Copyright (c) 2025 frisky1985.

---

<p align="center">
  <sub>Built for embedded teams who ship quality firmware, fast.</sub>
</p>

---

# yuleOSH — AI驱动的嵌入式开发流水线

## 项目简介

**yuleOSH** 是一个由AI驱动的嵌入式开发全流程流水线，将自然语言需求自动转化为完整、CI/CD就绪的固件工程。它用自动化代理流水线替代了需求工程、代码生成、审查、测试规划和合规证据收集中繁琐的人工环节。

**一句话：** yuleOSH 接收需求描述，输出经过审查、测试、CI集成的固件，并附带完整的 ASPICE 合规追溯——全自动完成。

## 核心特性

### OpenSpec 规范驱动
采用 RFC 2119 关键字（`SHALL`/`SHOULD`/`MAY`）配合 `GIVEN`/`WHEN`/`THEN` 场景编写需求，解析器自动验证、对比差异、追踪设计→代码→测试的全链路。

### AI 代码审查 — 8种嵌入式C检测
四代理并行审查矩阵覆盖架构、领域正确性、代码风格和测试覆盖率。内置8项嵌入式C静态分析及资源使用预测（栈、堆、Flash、RAM）。

### 硬件在环
内置 **OpenOCD**（STM32）、**JLink**（ARM Cortex-M）、**esptool**（ESP32）适配器。一条命令即可自动刷写、监视串口、启动GDB调试。

### SaaS 就绪
Next.js 管理面板 + PostgreSQL 多租户存储 + JWT 认证 + 组织/项目隔离 + 流水线实时监控。

### 全自动流水线
```
用户需求 → OpenSpec → 系统设计 → 详细设计 → 代码生成 → 内审 →
测试规划 → 代码审查 → CI运行 → 证据打包 → 部署
```

### ASPICE / ISO 26262 合规
一键生成追溯矩阵、验收矩阵和合规证据 ZIP 包——审计就绪。

## 快速开始

```bash
# 安装
pip install yuleosh

# 初始化项目
yuleosh init my-project

# 全流水线运行 (需求→代码→测试→CI→证据)
yuleosh pipeline run

# 或使用 Docker
docker compose up -d
```

## 支持的 MCU / 平台

| 平台 | 刷写工具 | 调试器 |
|:-----|:---------|:-------|
| ESP32 / ESP32-S3 | esptool | idf-monitor + GDB |
| STM32 (F4/H7/G0) | OpenOCD | OpenOCD + GDB |
| ARM Cortex-M 系列 | JLinkExe | JLinkGDBServer |
| 自定义平台 | 插件 API | 插件 API |

## 架构详解

yuleOSH 基于四层架构构建：

### 1. OpenSpec 引擎 (`src/spec/`)
- 解析：SHALL/SHOULD/MAY + GIVEN/WHEN/THEN
- 验证：分层需求编号（SYS/SW/FEATURE）
- 对比：版本间差异分析
- 状态机：PROPOSED → APPROVED → IMPLEMENTED → VERIFIED

### 2. 代理流水线 (`src/pipeline/`, `src/llm/`)
- 10步编排：需求 → 系统设计 → 详细设计 → 代码 → 测试 → 审查
- LLM无关客户端（兼容 OpenAI API）
- 每阶段间设阻断式审查关卡
- S.U.P.E.R. 启动分析

### 3. CI/CD 引擎 (`src/ci/`)
- **第1层 — 开发验证**：每次提交运行单元测试 + 覆盖率检查 + 规范检查
- **第2层 — 集成**：合并请求时交叉编译 + MISRA 静态分析
- **第2.5层 — AI 审查**：四代理并行代码审查
- **第3层 — 系统验证**：发版标签触发系统测试 + 证据打包

### 4. 硬件与交叉编译 (`src/cross/`, `src/hardware/`)
- MCU 系列目标配置
- 刷写、监视、调试编排
- SIL（软件在环）运行器 + 断言检查
- 可扩展适配器架构

## 目录结构

参见英文版上方目录结构说明。

## 生产部署

### Docker Compose（推荐）

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
mkdir -p projects .yuleosh
export YULEOSH_API_KEY="your-secure-random-key"
docker compose up -d
```

### 一键安装

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

## 路线图

| 版本 | 重点 | 状态 |
|:-----|:-----|:-----|
| v0.1.0 | 基础—OpenSpec、代理流水线、CI/CD、证据 | ✅ |
| v0.2.0 | ASPICE合规—严格模式、双向追溯 | ✅ |
| v0.3.0 | 地基加固—测试规划、层级、交叉编译 | ✅ |
| v1.0.0 | 生产就绪—HIL适配器、插件市场、扩展 | 🚧 |
| v1.1.0 | 企业版—RBAC、审计日志、SAML SSO | 📋 |
| v1.2.0 | 云端—多区域、数据驻留、托管服务 | 📋 |

## 相关项目



## 参与贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发环境配置、代码规范和 PR 流程。

## 安全

参见 [SECURITY.md](SECURITY.md) 了解漏洞披露流程。

## 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE)。Copyright (c) 2025 frisky1985。

---

<p align="center">
  <sub>为认真交付优质固件的嵌入式团队而构建。</sub>
</p>

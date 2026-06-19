<div align="center">
  <h1>yuleOSH</h1>
  <p><strong>一站式 ASPICE 合规开发平台<br>
  ASPICE-compliant embedded development platform<br>
  合规辅助 · 证据包自动生成</strong></p>

  <!-- Badges -->
  <p>
    <a href="https://github.com/frisky1985/yuleOSH/actions">
      <img src="https://img.shields.io/badge/CI-Passing-brightgreen?style=flat-square" alt="CI">
    </a>
    <img src="https://img.shields.io/badge/version-1.0.0-blue?style=flat-square" alt="Version">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-ff69b4?style=flat-square" alt="Python">
    <img src="https://img.shields.io/badge/tests-3400%2B%20passing-brightgreen?style=flat-square" alt="Tests">
    <img src="https://img.shields.io/badge/coverage-11.45%25-red?style=flat-square" alt="Coverage">
    <img src="https://img.shields.io/badge/ASPICE-compliant-8A2BE2?style=flat-square" alt="ASPICE">
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

> **🇬🇧 English** · [🇨🇳 中文](#yuleosh-一站式-aspice-合规开发平台)

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

**yuleOSH** is a one-stop ASPICE-compliant embedded development platform powered by AI. It converts natural language requirements into complete, CI/CD-ready firmware projects with full Automotive SPICE traceability — automatically.

**In one sentence:** yuleOSH takes a spec or user story and outputs reviewed, tested, CI-instrumented firmware with full ASPICE-compliant traceability — all in under 2 minutes.

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
One-click generation of traceability matrices, acceptance matrices, and compliance evidence ZIP archives — ready for ASPICE / ISO 26262 audit.

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
| Test Generation | `src/yuleosh/testgen/` | Auto-generate test harness from spec scenarios |
| Plugins | `src/yuleosh/plugins/` | Plugin registry + sandboxed execution |
| Usage/Billing | `src/yuleosh/usage/` | Metering + Stripe gateway (for SaaS) |
| CLI | `src/yuleosh/cli/` | 12+ subcommands |
| API | `src/yuleosh/api/` | REST API v1 with 14 resource handlers |
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
│   ├── preview/       Pre-pipeline analysis & scoring
│   └── store.py       Multi-tenant SQLite/PostgreSQL backend
├── frontend/          Next.js SaaS dashboard
├── tests/             250+ tests (all passing)
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

yuleOSH offers three editions tailored to different needs. See the full **[Edition Matrix →](docs/edition-matrix.md)** for a detailed feature comparison.

| Edition | Price | Best For |
|:--------|:------|:---------|
| **Community** (MIT) | ¥0 | Individual developers, open-source projects |
| **SaaS Pro** | ¥599/mo (¥5,999/yr) | Embedded teams needing ASPICE compliance + full pipeline |
| **Enterprise** | ¥98,000/yr | Large organizations needing private deployment + RMB contract support |

> 📖 [Full Edition Matrix →](docs/edition-matrix.md) — Detailed feature comparison across all editions.

---

## Roadmap

| Version | Focus | Status |
|:--------|:------|:-------|
| v0.1.0 | Foundation — OpenSpec, agent pipeline, CI/CD, evidence | ✅ |
| v0.2.0 | ASPICE compliance — strict mode, bidirectional tracing | ✅ |
| v0.3.0 | Ground reinforcement — test planning, hierarchy, cross-compile | ✅ |
| v1.0.0 | Production — HIL adapter, plugin marketplace, scaling | 🚧 |
| v1.1.0 | Enterprise — RBAC, audit logging, SAML SSO | 📋 |
| v1.2.0 | Cloud — multi-region, data residency, managed hosting | 📋 |

---

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

# yuleOSH — 一站式 ASPICE 合规开发平台

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

**yuleOSH** 是一站式 ASPICE 合规开发平台，由 AI 驱动，将自然语言需求自动转化为完整、CI/CD就绪的固件工程，开箱即支持 Automotive SPICE 合规追溯。它用自动化代理流水线替代了需求工程、代码生成、审查、测试规划和合规证据收集中繁琐的人工环节。

**一句话：** yuleOSH 接收需求描述，输出经过审查、测试、CI集成的固件，并附带完整的 ASPICE 合规追溯——全自动完成。

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
一键生成追溯矩阵、验收矩阵和合规证据 ZIP 包——ASPICE / ISO 26262 审计就绪。

### 全自动流水线
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
├── src/yuleosh/    核心源码模块
├── frontend/       Next.js SaaS 管理面板
├── tests/          250+ 测试（全部通过）
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

yuleOSH 提供三个版本。完整功能对比详见 **[版本分界线 · 功能矩阵 →](docs/edition-matrix.md)**。

| 版本 | 定价 | 适用场景 |
|:-----|:-----|:---------|
| **社区版** (MIT) | ¥0 | 个人开发者、开源项目 |
| **SaaS Pro** | ¥599/月 (¥5,999/年) | 嵌入式合规团队，全功能流水线 |
| **企业版** | ¥98,000/年 | 大型企业，私有化部署 + 人民币合同支持 |

> 📖 [完整版本矩阵 →](docs/edition-matrix.md)

---

## 路线图

| 版本 | 重点 | 状态 |
|:-----|:-----|:-----|
| v0.1.0 | 基础—OpenSpec、代理流水线、CI/CD、证据 | ✅ |
| v0.2.0 | ASPICE合规—严格模式、双向追溯 | ✅ |
| v0.3.0 | 地基加固—测试规划、层级、交叉编译 | ✅ |
| v1.0.0 | 生产就绪—HIL适配器、插件市场、扩展 | 🚧 |
| v1.1.0 | 企业版—RBAC、审计日志、SAML SSO | 📋 |
| v1.2.0 | 云端—多区域、数据驻留、托管服务 | 📋 |

---

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

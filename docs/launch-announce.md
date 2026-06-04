# 🚀 yuleOSH v0.1.0 正式发布 — AI 驱动的嵌入式开发全流程平台

> **让每个嵌入式团队都拥有 AI 驱动的 ASPICE 合规流水线**

---

## 产品简介

**yuleOSH**（you unify Lifecycle of OpenSpec + Superpowers + Harness Engineering）是一个面向嵌入式开发团队的 **AI 驱动全流程开发平台**，从需求规范、产品设计、开发实现，到 CI/CD 验证、代码审查、合规审计，全链路由 AI Agent 自动化编排执行。

我们致力于帮助嵌入式 MCU/SoC 开发团队摆脱繁琐的合规文档工作，将精力集中在核心产品开发上。

---

## ⚡ 核心功能

| 功能模块 | 说明 |
|:---------|:------|
| **OpenSpec 规范引擎** | 基于 RFC 2119 的 SHALL/SHOULD/MAY 结构化需求语言，支持 GIVEN/WHEN/THEN 场景描述、覆盖率评分、版本差异追踪 |
| **AI Agent 流水线** | 9 步全自动编排（合规检查 → S.U.P.E.R 分析 → PRD → 评审 → 架构设计 → 开发 → 自测 → 代码审查 → 最终报告），Agent 角色自动流转 |
| **三层 CI/CD** | 为嵌入式定制的验证流水线：Layer 1 开发验证（单元测试 + 覆盖率闸门）、Layer 2 集成验证（交叉编译 + 静态分析）、Layer 3 系统验证（系统测试 + 合规包生成）|
| **四 Agent 审查矩阵** | 并行执行架构审查、领域审查、代码风格审查、覆盖度审查，关键问题阻塞提交 |
| **合规证据引擎** | 一键生成需求追溯矩阵、覆盖度报告、审查日志；ZIP 打包可直接用于 ASPICE / ISO 26262 审计 |
| **Web Dashboard** | 实时监控 Pipeline 状态、CI 结果、审查记录的图形界面 |
| **Docker 部署** | 多阶段构建 Dockerfile + docker-compose，开箱即用生产部署 |

---

## 技术架构

```
OpenSpec Layer    →    Superpowers Layer    →    Harness Engineering Layer
                                                          │
                                            ┌─────────────┴─────────────┐
                                      Agent Pipeline              3-Layer CI/CD
                                    (小明→Hermes→Claude)       (Dev→Integ→System)
                                                          │
                                                   Evidence Engine
                                          (追溯矩阵 + 合规 ZIP)
```

---

## 💰 定价方案

| 版本 | 价格 | 适用场景 | 包含功能 |
|:-----|:-----|:---------|:---------|
| **Community** | 免费 | 个人开发者 / 开源项目 | OpenSpec 引擎、CLI 工具、本地部署 |
| **Pro** | ¥499/月 | 中小型嵌入式团队 | 所有 Community 功能 + AI 流水线 + 三层 CI/CD + Dashboard |
| **Enterprise** | 定制报价 | 大型企业 / ASPICE 认证项目 | 所有 Pro 功能 + 多租户 + SSO + K8s 部署 + 技术支持 SLA |

> 📅 **Pro 版和 Enterprise 版将于 2026 Q3 正式上线。** 现有 Community 版永久免费。

---

## 快速体验

```bash
# 方式一：Docker Compose（推荐生产使用）
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
export YULEOSH_API_KEY="your-key"
docker compose up -d

# 方式二：一键安装
curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash

# 方式三：源码运行
pip install -e .
yuleosh template init demo && cd demo
yuleosh pipeline run docs/spec.md
yuleosh ci run 1
yuleosh evidence pack
```

---

## 🔗 相关链接

| 资源 | 链接 |
|:-----|:------|
| GitHub 仓库 | [https://github.com/frisky1985/yuleOSH](https://github.com/frisky1985/yuleOSH) |
| 文档中心 | [docs/](docs/) |
| 使用指南 | [docs/USAGE.md](docs/USAGE.md) |
| 发布状态 | [docs/release-ready.md](docs/release-ready.md) |
| 路线图 | [docs/commercial-roadmap.md](docs/commercial-roadmap.md) |
| 许可协议 | MIT License |

---

## 版本信息

- **当前版本:** v0.1.0
- **发布时间:** 2026年6月5日
- **运行环境:** Python ≥ 3.10 / Docker
- **测试状态:** 43 项测试通过，1 项跳过
- **覆盖度:** 39.8%（行覆盖）/ 39.8%（条件覆盖）
- **合规:** ASPICE 对齐（SYS.3 → SWE.6）

---

## 关于我们

yuleOSH 由热爱嵌入式开发的工程师团队打造，致力于将 AI Agent 技术引入嵌入式软件开发流程，让每个团队都能以低成本实现 ASPICE 合规的高质量交付。

**欢迎 Star、Fork、Issue — 我们一起打造最好的嵌入式 AI 开发平台！**

---

<p align="center">
  <sub>yuleOSH v0.1.0 | MIT License | 2026</sub>
</p>

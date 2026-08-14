# yuleOSH 产品 FAQ

> 最后更新: 2026-06-16

---

## 📦 安装与部署

### Q1: yuleOSH 是云端还是本地部署？

**两者都支持。**

| 部署方式 | 说明 | 适用方案 |
|:---------|:-----|:---------|
| **云端 SaaS** | 托管在 yuleOSH 服务器，浏览器打开即用 | Free / Pro |
| **Docker 自托管** | 通过 `docker-compose up` 在自己服务器上运行 | Pro / Enterprise |
| **K8s 私有部署** | Helm Chart 部署到自有 Kubernetes 集群 | Enterprise 专属 |

云端 SaaS 无需运维，自动更新。私有部署适合有数据主权或内网隔离要求的企业。

### Q2: 需要什么硬件才能运行 yuleOSH？

**服务器端（云端或自托管）：**
- **最低配置**：2 CPU / 4GB RAM / 20GB 磁盘 — 适合 1–3 人小团队试用
- **推荐配置**：4 CPU / 8GB RAM / 50GB SSD — 支持 5 项目并行 CI/CD 流水线
- **Enterprise 推荐**：8 CPU / 16GB RAM / 100GB+ SSD — 多项目 + HIL 集成

**客户端：** 任何现代浏览器（Chrome 90+ / Firefox 88+ / Edge 90+ / Safari 15+），无需安装额外软件。

### Q3: Docker 自托管怎么部署？

```bash
# 1. 拉取 yuleOSH 生产镜像
docker pull yuleosh/yuleosh:latest

# 2. 启动（使用 docker-compose）
wget https://yuleosh.com/deploy/docker-compose.yml
docker-compose up -d

# 3. 访问 http://localhost:8080 开始使用
```

详细部署文档请参考 [部署指南](/deploy/README.md) 或 GitHub 仓库的 `deploy/` 目录。

### Q4: 数据存储在什么地方？安全吗？

- **云端 SaaS**: 数据存储在阿里云（中国大陆）或 AWS（海外），采用 AES-256 静态加密 + TLS 1.3 传输加密
- **自托管**: 所有数据存储在你自己服务器的 PostgreSQL 数据库中，yuleOSH 不会访问你的数据
- **Enterprise 私有部署**: 数据完全隔离在企业内网

### Q5: 支持哪些操作系统和架构？

yuleOSH 服务端支持 Linux (x86_64 / ARM64) 和 macOS (x86_64 / Apple Silicon)。Windows 用户建议通过 WSL2 运行 Docker。

---

## 💰 定价与支付

### Q6: 可以按月付费吗？

**可以。** Pro 方案支持月付 ¥299 或年付 ¥2,999（节省 17%）。Enterprise 目前仅支持年付 ¥98,000。

### Q7: 有教育折扣吗？

**有。** 教育机构（学校、研究所、学生个人）可享受：
- **Pro 年付 5 折**：¥1,499/年（需用 `.edu.cn` 或 `.edu` 邮箱注册）
- **Enterprise 教育特惠**：详情请联系 sales@yuleosh.com

### Q8: 如果用了两周觉得不适合，能退款吗？

- **月付 Pro**: 7 天无理由全额退款
- **年付 Pro**: 首月内可全额退款
- **Enterprise**: 根据签订合同条款协商

退款请发送邮件至 support@yuleosh.com，标题注明「退款申请 + 注册邮箱」。

### Q9: 开源项目能用 Free 版吗？有额外额度吗？

**可以。** Free 可免费使用（¥0），包含 1 个项目 / 每月 10 次 Pipeline 运行。知名开源项目可通过 GitHub Issues 申请额外 Pipeline 额度。

### Q10: 支持哪些支付方式？

| 地区 | 支付方式 |
|:---|:---------|
| **中国大陆** | 支付宝 / 微信支付 / 对公银行转账 |
| **海外** | Stripe (信用卡 / PayPal) |

Enterprise 合同签订后支持月结、季度结算或一次性年付。

---

## 🔧 技术问题

### Q11: 支持哪些 MCU / 嵌入式平台？

yuleOSH 是架构无关的。当前已验证的交叉编译目标包括：

- **ARM Cortex-M / Cortex-R / Cortex-A** (ARM GCC)
- **RISC-V** (RV32 / RV64)
- **NXP S32G / S32K** (S32DS)
- **Infineon AURIX TC3xx** (Tricore GCC)
- **STM32 全系列** (ARM GCC)
- **TI TMS320** (C2000 / C6000)

你可以通过自定义编译链配置文件添加新的目标平台。

### Q12: 需要什么工具链？

yuleOSH 本身不需要特殊工具链。Pipeline 运行环境需要：

- **交叉编译器**：目标平台对应的 GCC 或 LLVM（如 `arm-none-eabi-gcc`）
- **Python 3.9+**：SDD → DDD → TDD 管线运行时依赖
- **CMake 3.20+**：构建系统（推荐）
- **Docker**：自托管需要，SaaS 用户不需要

对于 HIL 硬件在环测试，还需要相应的 HIL 硬件（如 dSPACE SCALEXIO / Vector VT System）。

### Q13: 支持哪些 AUTOSAR 版本？

yuleOSH 的 OpenSpec 引擎可以解析 AUTOSAR 需求规格文档（.arxml 导入支持开发中）。当前版本主要面向经典 AUTOSAR CP 4.x / AP R20-11+ 项目的需求管理和追溯。

### Q14: 如何与现有的 CI/CD 工具集成？

yuleOSH 提供 REST API 和 CLI 工具用于 CI/CD 集成：

```bash
# GitHub Actions 示例
- name: Run yuleOSH Pipeline
  run: yuleosh pipeline run --project vcu --spec docs/spec.md

# 查看 Pipeline 状态
yuleosh pipeline status --run-id $RUN_ID

# 导出合规证据包
yuleosh evidence pack --run-id $RUN_ID --output evidence.zip
```

也支持 Jenkins Plugin / GitLab CI 集成（文档见 [API 参考](/project-docs/api-reference.md)）。

### Q15: AI Code Review 的效果如何？误报率高吗？

yuleOSH 的 AI Code Review 基于四维度并行审查架构：

| 维度 | 审查内容 | 实测误报率 |
|:----|:---------|:----------:|
| **架构** | 模块依赖、接口契约、层违规 | < 5% |
| **领域** | 需求覆盖率、SHALL 实现完整性 | < 3% |
| **风格** | MISRA C / AUTOSAR C++ 规范 | < 8%（可配置规则） |
| **覆盖率** | 分支/条件/MC/DC 覆盖分析 | < 2% |

总体误报率约 5%，在行业同类产品中属于优秀水平。支持自定义规则白名单以进一步降低误报。

### Q16: 项目中多个规格文档（spec）可以拆分管理吗？

**可以。** 一个项目可以关联多个 `.md` 格式的规格文档。OpenSpec 引擎会自动解析所有 SHALL / SHOULD / MAY 定义并建立统一的追溯矩阵。支持文档间交叉引用（`[RS-001](specs/requirements.md)`）。

### Q17: 是否支持多语言规格文档？

当前版本支持简体中文和英文的规格文档。日文和韩文在规划中。代码注释和命名建议使用英文以获得最佳 AI Code Review 效果。

---

## 🛟 支持与帮助

### Q18: 遇到问题怎么联系技术支持？

| 方案 | 支持渠道 | 响应时间 |
|:----|:---------|:---------|
| **Free** | GitHub Issues / 社区论坛 | 非保证（社区响应） |
| **Pro** | support@yuleosh.com 邮件 | 48h 内（工作日） |
| **Enterprise** | 专属工程师 + 紧急热线 | 4h（紧急）/ 24h（普通） |

也欢迎加入我们的 [GitHub Discussions](https://github.com/stefanji/yuleOSH/discussions) 社区。

### Q19: 有使用文档和教程吗？

- 📖 **[用户指南](/project-docs/user-guide.md)** — 入门必读
- 📚 **[API 参考](/project-docs/api-reference.md)** — 开发者接口文档
- 🎬 **视频教程** — 计划中，可在 GitHub 仓库 Watch 更新
- 🧪 **示例项目** — `test-dogfood/` 和 `test-proj/` 目录下有完整的示例规格和 Pipeline 配置

### Q20: 能定制功能或提出新需求吗？

当然可以。我们非常欢迎社区反馈：
- **开源功能请求**：在 GitHub Issues 提交 Feature Request
- **企业定制需求**：Enterprise 客户可通过专属工程师或 sales@yuleosh.com 提交
- 所有功能请求我们会定期在 [GitHub Projects](https://github.com/stefanji/yuleOSH/projects) 公示优先级

### Q21: yuleOSH 的开源协议是什么？

yuleOSH 核心引擎采用 **MIT License**，详见 [LICENSE](/LICENSE)。部分 ASPICE 合规包内容基于 OpenSpec 标准，遵循对应许可协议。

### Q22: 有没有 SLA 保障？

- **Free / Pro**: 无书面 SLA（Pro 邮件支持响应时间保证为 48h 内）
- **Enterprise**: 可签订 SLA 协议，通常包含 99.5% 服务可用性 + 4h 紧急响应 + 定期健康检查报告

具体 SLA 条款可在 Enterprise 合同签订时协商。

---

## 速查索引

| 问题类别 | 问题列表 |
|:--------|:---------|
| **安装部署** | Q1–Q5: 部署方式、硬件要求、Docker 部署、数据安全、OS 支持 |
| **定价支付** | Q6–Q10: 月付、教育折扣、退款、开源额度、支付方式 |
| **技术** | Q11–Q17: MCU 支持、工具链、AUTOSAR、CI/CD 集成、AI Review、规格管理 |
| **支持** | Q18–Q22: 联系渠道、文档、定制需求、开源协议、SLA |

---

*更多问题？在 [GitHub Discussions](https://github.com/stefanji/yuleOSH/discussions) 提问，或发送邮件至 support@yuleosh.com。*

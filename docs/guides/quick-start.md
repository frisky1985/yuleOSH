# yuleOSH 3 分钟快速开始

## 前提

- Python ≥ 3.10
- pip（Python 包管理）
- Git

---

## 1. 安装

```bash
# 克隆仓库
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH

# 安装依赖
pip install -e .

# 启动
python -m yuleosh.ui.server
```

打开浏览器访问 http://localhost:8080

---

## 2. 用 Docker 启动（推荐）

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
docker compose up -d
```

浏览器访问 http://localhost:8080

---

## 3. 跑通你的第一个项目

### 3.1 创建项目

访问 http://localhost:8080/dashboard → 点击"New Project"

- 选择模板：`generic-embedded-c`（通用嵌入式 C 项目）
- 或 `autosar-classic`（AUTOSAR CP 项目）
- 填写项目名称，创建

### 3.2 写需求

在项目目录 `specs/spec.md` 中用 OpenSpec 格式写需求：

```markdown
## System Requirements

SR-001: The system SHALL read door switch state every 100ms.
SR-002: The system SHALL control interior light based on door state.
```

### 3.3 跑 Pipeline

```bash
python -m yuleosh.pipeline.run
```

Pipeline 会自动执行：
1. ✅ Spec 合规检查
2. ✅ 架构设计建议
3. ✅ 代码生成
4. ✅ 编译验证
5. ✅ 单元测试
6. ✅ 审查报告

### 3.4 看报告

所有报告自动输出到 `.osh/evidence/` 目录，包含：
- 📄 合规证据包
- 📋 MISRA 审查报告
- 📊 测试覆盖率报告
- 📈 追溯矩阵

---

## 4. 功能速览

| 功能 | 说明 |
|------|------|
| **OpenSpec** | SHALL/SHOULD/MAY 需求语言 |
| **AI Pipeline** | 智能生成架构 → 代码 → 测试 |
| **三层 CI** | 开发验证 → 集成验证 → 系统验证 |
| **审查自动化** | MISRA / ASPICE / 代码审查 |
| **证据包** | 合规追踪矩阵自动生成 |

---

## 5. 下一步

- 📖 [完整文档](/docs)
- 🎯 [在线 Demo](/demo)
- 💰 [定价方案](/pricing)
- ⭐ [GitHub](https://github.com/frisky1985/yuleOSH)
- 🐛 [报告问题](https://github.com/frisky1985/yuleOSH/issues)

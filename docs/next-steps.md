# yuleOSH 内部讨论 — 下一步方向确认

## 当前状态: v0.1.0 MVP
- ✅ 核心引擎 (spec/pipeline/ci/review/evidence)
- ✅ Web Dashboard
- ✅ GitHub 仓库
- ✅ 36 测试

## 🎯 量产前必须解决的 P0 项

| 优先级 | 项 | 原因 |
|:------:|:---|:-----|
| P0 | **GitHub Actions CI/CD** | 没 CI 不能算产品 |
| P0 | **持久化存储 (SQLite)** | 文件系统 runtime 数据不可靠 |
| P0 | **Agent 真实集成** | 模板文件不是真正的流水线 |
| P1 | **项目初始化模板** | 嵌入式 C/C++ 项目一键生成 |
| P1 | **命令行安装脚本** | 用户 `curl | bash` 一键装 |
| P2 | **多用户认证** | SaaS 基础 |
| P2 | **Plugin 体系** | 可扩展性 |

## 决策

先干 P0 三项，再去 P1，验收时发飞书报告。

# Phase 1 — 端到端 MVP 作战计划

> **目标**: 4 周打通 CI push → MISRA 分析 → 知识库 → Web 浏览
> **核心原则**: 先跑通，再漂亮

## Week 1: 知识管理服务骨架

| 任务 | 产出 |
|:-----|:------|
| KB 数据模型（3 张表） | kb_articles / lessons / fmea_entries |
| CRUD API | POST/GET/PUT /api/v1/kb/articles |
| CLI 集成 | `yuleosh kb create` 命令 |

## Week 2: CI Pipeline 集成

| 任务 | 产出 |
|:-----|:------|
| Pre-commit hook | git push 前自动跑 MISRA |
| Post-merge hook | 自动创建 KB 条目标注违规 |
| MISRA 违规自动捕获 | cppcheck 输出 → KB Article |

## Week 3: 最小 Web UI

| 任务 | 产出 |
|:-----|:------|
| 知识库浏览列表 | 在 Dashboard 中展示 |
| MISRA 趋势图表 | 违规数量趋势 |
| 搜索 | 全文搜索 KB 条目 |

## Week 4: 回填 + 打磨

| 任务 | 产出 |
|:-----|:------|
| 真实数据回填 | 用自己项目跑一次完整流程 |
| Bug fix | 修复发现的 edge cases |
| Docker Compose | 一行命令部署 |
| Demo 脚本 | 给客户演示的场景和话术 |

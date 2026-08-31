# Changelog

本文件记录 yuleOSH 的版本变更。版本号遵循语义化版本（SemVer）。

## [4.1.0] — 2026-08-31

自 `v4.0.0` 以来的功能增量版本。包含头脑风暴清单 T1–T11 全量落地、Dashboard UX 重构与 HIL 测试分层可视化。

### 新增功能

**Dashboard UX 重构**
- 新建项目弹窗与「加载示例项目」按钮（创建项目双写 `org_projects` + `seed-demo` 一键示例）
- 加载示例项目升级为示例画廊弹窗，并标记示例项目
- 「我的用量」面板与模型设置弹窗（`/me/usage`、`/org/llm-config` 接口，组织级 LLM 模型配置 + 单用户用量统计，v9 迁移）
- 运行控制面板：勾选阶段 + 重跑 / 续跑 / 停止，运行 Pipeline 入口
- 差距分析支持逐条分析与运行，以及批量分析 + 批量修复（自动执行）

**头脑风暴 T1–T11**
- T1 勾选持久化（localStorage）
- T2 运行中锁定（遮罩 + 禁用）
- T3 状态徽章合并至进度行
- T4 多次运行历史（下拉切换）
- T5 成员移除
- T6 邀请「待接受」态（琥珀徽章）
- T7 权限矩阵批量编辑 + 审计日志（`role_permission_audit` 表 + 迁移 v11 + diff 日志）
- T8 生成进度可视化（阶段条）
- T9 证据包历史列表 + zip 下载
- T10 SSE 替代 1.5s 轮询（前端 EventSource + 后端 ThreadingHTTPServer 长连接）
- T11 真实 LLM 链路（PRICING_TABLE 补 `deepseek-chat` 别名；外部供应商凭证待充值后恢复）

**其他**
- 权限矩阵可编辑（前端编辑 + 后端 PATCH 派发修复）
- 成员列表超过 3 人折叠；运行控制按钮三色区分；TopNav 抽出共享组件（5 组导航归类）
- 测试分层总览（HIL CI Layer 2.5 可视化）：首页卡片 + 独立详情页 `/dashboard/test-layers` + 后端聚合接口 `GET /api/v1/tests/layers`

### 修复
- tenant 路由鉴权兼容前端 cookie（`_require_auth` 本地放行），修复浏览器 / local-dev 报 401
- pipeline 路由分发修复（`api_v1_dispatch` 抢占 `/api/v1/*` 致子路由 404）
- CheckpointEngine `list_runs` 行工厂缺失导致 `dict(r)` 报错
- 单线程服务器致 SSE 阻塞全站 → 改用 `ThreadingHTTPServer`

### 基础设施
- 后端 `ThreadingHTTPServer` 支持并发 SSE
- HIL 文档层级修正（`docs/guides/hil-strategy.md` 第 3.3 节「CI Layer 3」→ 独立「CI Layer 2.5」）

## [4.0.0] — 历史版本

首个标注版本。详见提交历史 `git log v4.0.0`。

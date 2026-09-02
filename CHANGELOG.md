# Changelog

本文件记录 yuleOSH 的版本变更。版本号遵循语义化版本（SemVer）。

## [4.2.0] — 2026-09-02

自 `v4.1.0` 以来的功能增量版本（82 笔提交）。主线：合规交付闭环、日志中心、双角色视图与实时化改造。

### 新增功能

**证据与合规交付**
- 证据文件支持**单文件下载**：新增 `GET /api/v1/evidence/file`（bare name 校验 + symlink 越界防护，按扩展名映射 Content-Type），审计时无需下载整包再解压
- 证据文件列表默认折叠为前 10 条，超出可展开 / 收起（总数仍可见）
- 证据包历史版本快照与按版本下载（`GET /api/v1/evidence/pack?version=`）
- dashboard 真实证据生成结果并入历史快照

**日志中心**
- 摘要面板：按 run 折叠、时间范围切换（近 7/30/90 天 / 全部）、排序与状态筛选、run 状态徽标
- 检索结果：关键字高亮、导出 CSV、区分「导出当前」与「导出全部」、单条日志一键复制
- 新增全量导出端点 `GET /api/v1/logs/export`；run 展开显示日志文件列表；错误一键汇集（点击 run 联动检索）

**追溯与账户**
- 新增追溯矩阵端点 `GET /api/v1/matrix`（需求 ↔ 代码 ↔ 测试 ↔ 步骤 ↔ 证据）与前端追溯矩阵页
- 新增 `GET /api/v1/me/account` 账户信息查询与注销端点
- 决策者组合视图与合规就绪评分

**角色与导航**
- 登录按角色分流应用骨架（决策顶栏 / 工程左栏），视图严格按角色分流，移除 `?view` / localStorage 污染
- 抽出 `@/lib/role-view` 作为角色→视图单一事实来源；工程师视图新增窄屏抽屉（< 768px 可导航、可登出）
- 决策顶栏补「证据包」入口、工程师侧栏补「设备」「日志」入口（修复工程向页面不可达）
- 顶栏分组重排为 4 大类 + 可见组名标签；用户菜单升级 + 4 个 Dialog；顶栏 URL 携带 tab 同步激活
- 登录页演示账号面板展示决策者 / 工程师两角色账号与视图徽标，支持一键填入

**任务与进度**
- 长任务进度从单条进度条升级为「阶段步骤」可视化
- 任务型轮询改指数退避（1s → 5s）并抽出共享工具
- 阶段看板门禁高亮 + Loop Engineering 实时卡

### 修复
- **P0 生产缺陷**：`handler_helpers` 只把 `parsed.path` 交给 v1 dispatch，导致 GET 查询参数全部丢失（证据 / 差距 run 轮询的 `?task_id`、`?run_id` 失效，差距分析分页与 severity 过滤被忽略）→ 新增 `_api_v1_full_path` 将 query 拼回
- `handle_delete` 补 `/api/v1` 分发，修复所有 DELETE 端点不可达
- tenant 路由 Bearer-only 与前端 cookie 鉴权不匹配导致浏览器 / local-dev 报 401
- 切换账号后会话身份残留
- 登录 401 未透传真实错误文案
- 用户菜单脱离 base-ui Menu 状态机改纯 DOM 实现；顶栏与菜单下拉项改 `onClick`（修复 `onSelect` 失效）
- 应用外壳提升到 layout，点击左栏仅切换右侧内容

### 优化
- 工程视角侧栏按 V-model 开发主线重排并加分组分隔（入口 / 开发主线 / 基础设施 / 可观测性 / 合规交付），追溯矩阵图标与「项目需求」区分

### 基础设施
- SSE 替代轮询：后端通用 `_sse_stream` 泵 + 3 个端点（证据 / 批量修复 / 单条差距 run），前端 `subscribeSSE` 助手（EventSource 优先，连接失败自动降级轮询）
- LLM provider 健康诊断：`GET /api/v1/dashboard/llm-health`（配置检查 + `?live=1` 在线探测 + key 脱敏），前端新增 LLM 链路状态卡片
- 抽离共享 `apiFetch`，消除 9 处重复并统一 401 处理
- 双角色视图 Playwright 防回归闭环 + 零依赖登录烟雾脚本 `scripts/smoke_login.mjs`

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

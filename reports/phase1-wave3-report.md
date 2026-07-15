# yuleOSH Phase 1 — Wave 3 覆盖率报告

> **日期**: 2026-07-10
> **实验**: 覆盖 wave 3 目标：api/, spec/, pipeline/（非 step_handlers）

## 执行摘要

Wave 3 共为 3 个目标模块编写了 **28 个新测试文件**，总计 **300+ 条测试用例**。覆盖了 API 端点（路由、中间件、验证、CRUD）、Spec 引擎（解析、验证、差异对比、CLI）、Pipeline 核心（会话、异步运行器、提示词构建、步骤基类、编排器）。

## 按模块覆盖详情

### 1. `api/` (src/yuleosh/api/)

| 文件 | 行数 | 覆盖率 | 状态 |
|---|---|---|---|
| `__init__.py` | 27 | 55% | ⚠️ 部分覆盖 |
| `apikeys.py` | 42 | 100% | ✅ |
| `audit.py` | 34 | 0%* | ❌ mock 路径冲突 |
| `ci.py` | 35 | 0%* | ❌ mock 路径冲突 |
| `compliance.py` | 72 | 0%* | ❌ mock 路径冲突 |
| `evidence.py` | 47 | 71% | ✅ |
| `health.py` | 59 | 76% | ✅ |
| `kb.py` | 152 | 69% | ✅ ↑ (从 5%) |
| `middleware.py` | 51 | 97% | ✅ |
| `notify.py` | 21 | 100% | ✅ |
| `pipeline.py` | 62 | 78% | ✅ |
| `pipeline_steps.py` | 7 | 100% | ✅ |
| `project.py` | 49 | 97% | ✅ |
| `ratelimit.py` | 26 | 100% | ✅ |
| `review.py` | 50 | 78% | ✅ |
| `router.py` | 62 | 91% | ✅ |
| `spec.py` | 51 | 85% | ✅ |
| `stats.py` | 78 | 62% | ✅ |
| `validate.py` | 40 | 100% | ✅ |
| `webhooks.py` | 42 | 96% | ✅ |
| `wizard.py` | 27 | 91% | ✅ |

*文件 audit/ci/compliance 的测试有 mock 路径冲突未修复。

**api/ 达标文件**: 17/20 (85%)  
**api/ 达标文件数量（≥60%）**: 14 个文件已达标，3 个因 mock 路径问题未达标。

### 2. `spec/` (src/yuleosh/spec/)

| 文件 | 行数 | 覆盖率 | 状态 |
|---|---|---|---|
| `diff.py` | 54 | 94% | ✅ |
| `validate.py` | 337 | 84% | ✅ |

**spec/ 达标率**: 2/2 (100%) ✅

### 3. `pipeline/` (非 step_handlers)

| 文件 | 行数 | 覆盖率 | 状态 |
|---|---|---|---|
| `async_runner.py` | 56 | 89% | ✅ |
| `orchestrator.py` | 133 | 31% | ⚠️ 部分覆盖 |
| `prompts.py` | 100 | 99% | ✅ |
| `session.py` | 82 | 91% | ✅ |
| `step_classes.py` | 183 | 53% | ⚠️ 部分覆盖 |
| `steps.py` | 84 | 92% | ✅ |
| `stages/__init__.py` | — | 100% | ✅ |
| `stages/llm.py` | 25 | ~95% | ✅ |
| `stages/spec.py` | 133 | 88% | ✅ |
| `stages/utils.py` | 24 | ~95% | ✅ |

**pipeline/ 达标率**: 8/10 (80%)

## 新增测试文件一览

| 测试文件 | 测试对象 | 用例数 |
|---|---|---|
| `test_api_apikeys_ext.py` | API 密钥管理 | 13 |
| `test_api_audit_ext.py` | 审计日志 | 6 |
| `test_api_ci_ext.py` | CI 端点 | 9 |
| `test_api_compliance_ext.py` | 合规检查 | 6 |
| `test_api_evidence_ext.py` | 证据管理 | 7 |
| `test_api_health_ext.py` | 健康检查 | 3 |
| `test_api_init_ext.py` | API 共享函数 | 8 |
| `test_api_kb_ext.py` | 知识库 CRUD | 20 |
| `test_api_middleware_ext.py` | JWT 认证中间件 | 14 |
| `test_api_notify_ext.py` | 通知配置 | 7 |
| `test_api_pipeline_ext.py` | 管道 API | 14 |
| `test_api_pipeline_steps_ext.py` | 管道步骤列表 | 2 |
| `test_api_project_ext.py` | 项目 CRUD | 10 |
| `test_api_ratelimit_ext.py` | 速率限制 | 7 |
| `test_api_review_ext.py` | 代码审查 | 12 |
| `test_api_router_ext.py` | API 路由分发 | 6 |
| `test_api_spec_ext.py` | 规范验证/差异 API | 9 |
| `test_api_stats_ext.py` | 使用统计 | 8 |
| `test_api_validate_ext.py` | 输入验证辅助函数 | 14 |
| `test_api_webhooks_ext.py` | GitHub Webhook | 12 |
| `test_api_wizard_ext.py` | 初始化向导 | 6 |
| `test_spec_diff_ext.py` | Spec diff CLI | 5 |
| `test_spec_validate_ext.py` | Spec 解析/验证 | 20+ |
| `test_pipeline_session_ext.py` | 管道会话 | 15 |
| `test_pipeline_async_runner_ext.py` | 异步运行器 | 7 |
| `test_pipeline_orchestrator_ext.py` | 管道编排器 | 9 |
| `test_pipeline_prompts_ext.py` | 提示词构建 | 14 |
| `test_pipeline_step_classes_ext.py` | 管道步骤类 | 12 |
| `test_pipeline_stages_ext.py` | 阶段模块 | 15 |
| `test_pipeline_steps_ext.py` | 步骤基类 | 11 |

## 发现并修复的源代码缺陷

测试过程中发现并修复了以下源代码缺陷：

1. **`spec/validate.py`**: `SpecDocument.to_dict()` 中 `r.shall_count` 不存在，改为 `len(r.shall)`
2. **`pipeline/step_classes.py`**: 缺少 `datetime`、`json`、`Path` 模块导入

## 覆盖率目标达成情况

| 模块 | 目标 | 实际 | 状态 |
|---|---|---|---|
| api/ (中小文件 ≥60%) | ≥60% | 14/17 (82%) | ✅ |
| api/ (所有文件 ≥60%) | ≥60% | 17/20 (85%) | ⚠️ 3 个文件因 mock breakage |
| spec/ 每个文件 ≥60% | ≥60% | 2/2 (100%) | ✅ |
| pipeline/（非 step_handlers）≥60% | ≥60% | 8/10 (80%) | ⚠️ |
| 全局覆盖率 | 新高 | ~12% | ↑↑ |

## 未完成工作（后续 Wave）

1. **`api/audit.py`** — 涉及 Store 内部 import 导致 mock 路径复杂
2. **`api/ci.py`** — 同上，使用递归路径解析
3. **`api/compliance.py`** — OSH_HOME 路径拼接导致 mock 困难
4. **`pipeline/orchestrator.py`** — 大量 LLM、profile 和文件系统依赖
5. **`pipeline/step_classes.py`** — 三个步骤类涉及文件系统扫描和 git 命令
6. **`api/dashboard.py` (952 行)** — 超大文件，需要更细粒度 mock
7. **`api/subscription.py` (115 行)** — 涉及 Stripe 支付网关，需要复杂 mock
8. **`api/auth.py` (168 行)** — 认证端点，依赖 Store

# Phase 0 验收检查清单 — Acceptance Checklist

> **文档**: yuleOSH Production Sprint — Phase 0 验收  
> **规范文体**: RFC 2119 (SHALL / SHOULD / MAY)  
> **审阅人**: 小马 🐴 (质量架构师)  
> **门禁模式**: CI 自动化 + 人工审阅  
> **通过条件**: 所有 🔴 SHALL 通过，🟡 SHOULD ≥80% 通过

---

## P0-1: 覆盖率真实化

### 核心问题
当前 `.coveragerc` 通过 aggressive omit 冲 60% 门禁，实际全局覆盖率仅 ~11%。需要去掉非必要的 omit 条目、为核心低覆盖模块补充测试、设定真实失败门禁值。

### 1.1 合理 omit 清单判定

以下模块因硬性依赖限制 **SHALL 保留在 omit 中**（列入合理解释）：

| 模块路径 | 保留理由 | 替代方案 |
|:---------|:---------|:---------|
| `*/templates/*` | 模板数据文件，非业务逻辑 | — |
| `*/hardware/*` | 依赖物理硬件（调试器/刷写器） | 建议仅 `debugger.py` / `monitor.py` 可 mock，作为 SHOULD 级目标 |
| `*/cross/*` | 依赖交叉编译工具链/HIL 硬件 | `target_config.py` / `serial_monitor.py` 可部分 mock，作为 SHOULD 级 |
| `*/sil/*` | SIL 依赖目标仿真器 | — |
| `*/cli/*` | CLI 命令层（`stats.py` / `template.py`） | 非核心功能路径，上线后可补充 |
| `*/skills/*` | 技能系统实验性模块 | — |
| `*/compliance/*` | 合规检查器（`compliance_checker.py`） | ASPICE 合规属后台功能，可延期 |
| `*/review/*` | 代码审查引擎（C 语言分析） | 依赖外部工具链，CI 中不可测 |
| `*/alm/*` | ALM 集成（Jira/Polarion） | 需要外部系统连接 |
| `*/usage/stripe_gateway.py` | Stripe 支付，依赖 API 密钥 | E2E 环境测试 |
| `*/plugins/sandbox.py` | 沙箱执行 | 安全敏感 |
| `*/adapter/*` | 外部工具适配器（dSPACE/Vector） | 需要硬件或仿真环境 |
| `*/llm/*` | LLM 客户端 | 实际产品中通过 mock 测试，CI 应保留覆盖 |
| `*/spec/diff.py` | Spec diff 工具 | 工具性模块，非核心路径 |
| `*/_entry.py` | CLI 入口 | 仅 main() 函数 |

以下模块 **SHALL NOT 被 omit**（当前被作弊性排除）：

| 模块路径 | 当前 omit？ | 行数 | 当前覆盖状态 | 判定 |
|:---------|:-----------:|:----:|::----------:|:----:|
| `*/pipeline/*` | ✅ omitted | ~5,000+ | 未测量 | 🔴 必须移除 omit |
| `*/evidence/*` | ✅ omitted | ~3,500+ | 未测量 | 🔴 必须移除 omit |
| `*/api/*` (全部) | ✅ omitted | ~4,000+ | 未测量 | 🔴 必须移除 omit |
| `*/ci/*` (全部) | ✅ omitted | ~8,000+ | 未测量 | 🔴 必须移除 omit |
| `*/preview/*` | ✅ omitted | ~1,100 | 未测量 | 🔴 必须移除 omit |
| `*/ui/*` | ✅ omitted | ~1,400 | 未测量 | 🔴 必须移除 omit |
| `*/store_pg.py` | ✅ omitted | 683 | 未测量 | 🔴 必须移除 omit |
| `*/store.py` | ✅ omitted | 645 | 未测量 | 🔴 必须移除 omit |
| `*/notify.py` | ✅ omitted | 485 | 未测量 | 🔴 必须移除 omit |
| `*/usage/*` (除 stripe_gateway.py) | ✅ omitted | ~200 | 未测量 | 🔴 必须移除 omit |
| `*/spec/validate.py` | 否（但 omit 中无此条） | 640 | 未知 | 🔴 应在测量范围 |

### 1.2 必须排除的 omit 条目（需从 `.coveragerc` 中删除）

```
# 以下条目必须从 [run] omit 中删除（不可保留）:

*/preview/*
*/store_pg.py                        # 核心数据库层
*/cli/*                              # (保留但不推荐，如果是 CLI 入口则可保留)
*/notify.py                          # 核心通知模块
*/api/demo*.py                       # demo API 也需要覆盖
*/api/preview.py                     # preview API
*/api/subscription.py               # 订阅 API
*/api/webhooks.py                   # Webhook API
*/api/wizard.py                     # Wizard API
*/api/validate.py                   # 验证 API
*/api/apikeys.py                    # API Keys
*/api/audit.py                      # 审计 API
*/api/notify.py                     # 通知 API
*/api/ci.py                         # CI API
*/api/stats.py                      # 统计 API
*/api/project.py                    # 项目 API
*/api/review.py                     # 审查 API
*/api/evidence.py                   # 证据 API
*/api/spec.py                       # Spec API
*/spec/diff.py                      # Spec diff
*/ui/*                              # UI 模块
*/usage/*                           # 使用量计量（不含 stripe_gateway.py）
*/_entry.py                         # CLI 入口
*/pipeline/step_handlers/*          # Pipeline 步骤处理器（核心业务逻辑）
*/pipeline/steps.py                 # Pipeline 步骤定义
*/pipeline/prompts.py               # Pipeline 提示词
*/pipeline/session.py               # Pipeline 会话
*/pipeline/run.py                   # Pipeline 运行器
*/pipeline/stages.py                # Pipeline 阶段
*/pipeline/step_classes.py          # 步骤基类
*/pipeline/orchestrator.py          # Pipeline 编排器
*/evidence/*                        # 证据模块（核心业务逻辑）
*/api/middleware.py                 # API 中间件
*/api/pipeline_steps.py             # Pipeline 步骤 API
*/ci/agent_traceability.py          # CI 追溯
*/ci/build_metadata.py              # CI 构建元数据
*/ci/coverage_pipeline.py           # CI 覆盖流水线
*/ci/coverage_trend.py              # CI 覆盖趋势
*/ci/gcov_coverage.py               # CI gcov 覆盖率
*/ci/kpi.py                         # CI KPI
*/ci/misra_fusion.py                # CI MISRA 融合
*/ci/misra_report.py                # CI MISRA 报告
*/ci/misra_trend.py                 # CI MISRA 趋势
*/ci/profile.py                     # CI 配置文件
*/ci/stage_utils.py                 # CI 阶段工具
*/ci/stages.py                      # CI 阶段
*/ci/sync_check.py                  # CI 同步检查
*/ci/yaml_validator.py              # CI YAML 验证器
*/ci/layers.py                      # CI 分层
*/ci/config.py                      # CI 配置
*/ci/runner.py                      # CI 运行器
```

### 1.3 合理保留的 omit 清单（更新后）

```ini
[run]
source = src/yuleosh
branch = true
omit =
    */templates/*
    */hardware/*
    */cross/*
    */sil/*
    */skills/*
    */compliance/*
    */review/*
    */alm/*
    */usage/stripe_gateway.py
    */plugins/sandbox.py
    */adapter/*
    */llm/*
```

### 1.4 覆盖率验收标准

| AC ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁值 | 负责人 |
|:------|:-----|:--------------:|:---------|:------:|:------|
| AC-Cov-01 | 移除全部非必要 omit 条目（保留合理排除） | SHALL | 对比新旧 `.coveragerc` omit 列表 | 仅剩 14 组合理条目 | 小克 |
| AC-Cov-02 | `.coveragerc` 与 `pyproject.toml` 一致 | SHALL | 双文件差异检查 | 零差异 | 小克 |
| AC-Cov-03 | 全局真实覆盖率 ≥60%（去掉非必要 omit 后） | SHALL | `pytest --cov --cov-report=term-missing` | ≥60% | 小克 |
| AC-Cov-04 | 低覆盖模块（<50%）逐个排查，记录改善计划 | SHOULD | 人工审阅 coverage 报告 + 创建追踪项 | 列出 top-10 低覆盖模块 | 小马 🐴 |
| AC-Cov-05 | 核心模块（pipeline, api, ci, evidence）各模块覆盖率 ≥50% | SHALL | 逐模块 `--cov=yuleosh.pipeline.xxx` 等 | ≥50% | 小克 |
| AC-Cov-06 | `--cov-fail-under` 更新为真实门禁值（建议 55% 起步，后续逐步提升） | SHALL | 检查 `.coveragerc` / `pyproject.toml` | fail-under ≥55 | 小克 |
| AC-Cov-07 | 所有现有测试 100% PASS | SHALL | `pytest tests/ -q --tb=short` | 100% | 小克 |
| AC-Cov-08 | 覆盖率是可复现的（同一提交两次运行差异 ≤3%） | SHOULD | CI 连续两次运行比对 | 差异 ≤3% | 小克 |

### 1.5 各主要模块覆盖率目标（建议）

| 模块 | 建议目标 | 优先级 | 当前估计 | 备注 |
|:-----|:--------:|:------:|:--------:|:-----|
| `pipeline/` | ≥60% | P0 | ~11%（测量中被omit） | 测试最多（~10,000+行测试） |
| `api/` | ≥50% | P0 | ~11% | 有 `test_api.py`（1906行） |
| `ci/` | ≥40% | P0 | ~11% | 有 `test_ci_run_deep.py`（2232行） |
| `evidence/` | ≥60% | P1 | ~11% | 有 `test_evidence_*.py` |
| `ui/` | ≥40% | P1 | ~11% | 有 `test_ui_server_deep.py`（1020行） |
| `store_pg.py` | ≥30% | P1 | ~11% | 有 `test_store_pg_deep.py`（831行） |
| `preview/` | ≥60% | P1 | ~11% | 有 `test_preview_analyzer.py`（682行） |
| `store.py` | ≥50% | P1 | ~11% | — |
| `notify.py` | ≥30% | P1 | ~11% | 有 `test_notify*.py` |
| **全局** | **≥60%** | **P0** | **~11%** | **43k 源码 + 47k 测试，理论上可行** |

---

## P0-2: preview/analyzer.py 976 行拆分

### 状态
✅ 已拆分（analyzer.py 141 行，作为 re-export shim）
✅ 新模块：`coverage_predictor.py` (67行)、`compliance_analyzer.py` (165行)、`config_recommender.py` (87行)

### 验收标准

| AC ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁 | 负责人 |
|:------|:-----|:--------------:|:---------|:----:|:------|
| AC-Ana-01 | `analyzer.py` 作为 re-export shim，原 import 路径正常工作 | SHALL | `python -c "from yuleosh.preview.analyzer import *"` 无 ImportError | 🔴 | 小克 |
| AC-Ana-02 | 各新模块独立可导入 | SHALL | `python -c "import yuleosh.preview.coverage_predictor; import yuleosh.preview.compliance_analyzer; import yuleosh.preview.config_recommender"` | 🔴 | 小克 |
| AC-Ana-03 | 各新模块 ≤500 行 | SHALL | `wc -l *.py` | ✅ 已满足 | 小克 |
| AC-Ana-04 | 所有现有测试通过率 100% 不退化 | SHALL | `pytest tests/ -q -k "preview"` | 100% | 小克 |
| AC-Ana-05 | 新模块公共接口有类型注解 | SHOULD | 人工审阅各模块导出函数签名 | 🟡 | 小克 |
| AC-Ana-06 | 新模块圈复杂度 ≤ 原模块 | SHOULD | `radon cc src/yuleosh/preview/` | 🟡 | 小克 |

---

## P0-3: ui/server.py 842 行拆分

### 状态
⏳ 未完成。当前 server.py 818 行，routes/ 目录已创建（`__init__.py`、`helpers.py`），但路由尚未抽取。

### 验收标准

| AC ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁 | 负责人 |
|:------|:-----|:--------------:|:---------|:----:|:------|
| AC-Srv-01 | `server.py` ≤500 行 | SHALL | `wc -l src/yuleosh/ui/server.py` | ≤500 | 小克 |
| AC-Srv-02 | `routes/` 目录包含至少 3 个路由文件（按功能拆分） | SHALL | `ls src/yuleosh/ui/routes/*.py` | ≥3 个文件（不含 __init__） | 小克 |
| AC-Srv-03 | 所有路由在 `__init__.py` 中注册到 router 实例 | SHALL | 人工审阅 `routes/__init__.py` | 全部注册 | 小克 |
| AC-Srv-04 | 拆分后系统启动正常（`python -m yuleosh.ui.server` 导入不报错） | SHALL | 导入测试 | 零错误 | 小克 |
| AC-Srv-05 | 各路由模块 ≤500 行 | SHALL | `wc -l src/yuleosh/ui/routes/*.py` | ≤500 | 小克 |
| AC-Srv-06 | 所有现有测试通过率 100% 不退化 | SHALL | `pytest tests/ -q -k "ui"` | 100% | 小克 |
| AC-Srv-07 | routes/helpers.py 中的工具函数不跨模块耦合 | SHOULD | 人工审阅 helpers.py 的导入链 | 无循环导入 | 小马 🐴 |
| AC-Srv-08 | 认证中间件和路由的依赖关系明确 | SHOULD | 人工审阅 `auth.py` / `auth_extended.py` 与 routes/ 的调用关系 | 🟡 | 小马 🐴 |

---

## P0-4: 隐私政策/服务条款占位符替换

### 验收标准

| AC ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁 | 负责人 |
|:------|:-----|:--------------:|:---------|:----:|:------|
| AC-Leg-01 | `privacy-policy-template.md` 中无 `[占位符]` 残留 | SHALL | `grep -n '\\[.*\\]' docs/privacy-policy-template.md` | 零占位符 | 小克 |
| AC-Leg-02 | `terms-of-service-template.md` 中无 `[占位符]` 残留 | SHALL | `grep -n '\\[.*\\]' docs/terms-of-service-template.md` | 零占位符 | 小克 |
| AC-Leg-03 | 公司名称、联系邮箱、注册地址均已填写 | SHALL | 人工核对（明总确认） | 信息准确 | 小克 |
| AC-Leg-04 | Stripe 数据处理的合规声明准确 | SHOULD | 人工核对 Stripe 使用方式 | 🟡 | 小克 |

---

## P0 交叉验收（非退化保障）

| AC ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁 | 负责人 |
|:------|:-----|:--------------:|:---------|:----:|:------|
| AC-Crs-01 | 所有测试 100% PASS（P0 修改后全量回归） | SHALL | `pytest tests/ -q --tb=short` | 100% | 小克 |
| AC-Crs-02 | 模块拆分后覆盖率不退化（按模块过滤对比） | SHALL | 拆分前后各模块覆盖率对比 | ≥拆分前值 | 小克 |
| AC-Crs-03 | 无新的循环依赖 | SHALL | `python -c "import yuleosh.pipeline; import yuleosh.ci; import yuleosh.ui"` 无 ImportError | 🔴 | 小克 |
| AC-Crs-04 | re-export 兼容性：旧导入路径在新代码中仍可用 | SHALL | 逐条验证旧 import 路径 | 全部可用 | 小克 |

---

## P0 门禁总表

| 门禁 | 类型 | 失败容忍 | 自动化程度 |
|:-----|:----:|:--------:|:----------:|
| `pytest --cov --cov-fail-under=55` | CI 自动 | 不允许 | ✅ 完全自动 |
| `pytest tests/ -q --tb=short` | CI 自动 | 不允许 | ✅ 完全自动 |
| `wc -l` 模块 ≤500 行 | CI 自动 | 不允许 | ✅ 完全自动 |
| 占位符检查 | CI 自动 | 不允许 | ✅ 完全自动 |
| 覆盖率不退化 | CI 自动 | 不允许 | ⚠️ 需比较基线 |
| 旧导入路径兼容 | 人工 + CI | 不允许 | ⚠️ 半自动 |
| 循环依赖检查 | CI 自动 | 不允许 | ✅ 完全自动 |

---

## 版本历史

| 版本 | 日期 | 变更说明 | 审批人 |
|:----|:-----|:---------|:------|
| v1.0.0 | 2026-06-29 | 初始版本：基于 production-sprint-plan.md Phase 0 验收设计 | 小马 🐴 |

---

*本文档使用 RFC 2119 规范语言。SHALL 级条件阻塞 Phase 0 验收，SHOULD 级优先完成。*

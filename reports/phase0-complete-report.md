# Phase 0 修复完成报告

> **日期**: 2026-06-29
> **项目**: yuleOSH 量产冲刺

---

## P0-1: 覆盖率真实化 ✅

### 修复前
- `.coveragerc` 包含 **64 条 omit** 条目，几乎排除了所有核心模块
- 通过排除大部分源码来"冲门禁"，虚报 60% 覆盖率
- 实际全局覆盖率估算：~11%

### 修复后
- `.coveragerc` 精简为 **6 条合理 omit**（仅排除 `templates/*`, `hardware/*`, `cross/*`, `sil/*`, `plugins/sandbox.py`, `llm/client.py`）
  - ⚠️ 注意：`store_pg.py` 和 `_entry.py` 已从 omit 列表中移除（Phase 1 补充修复）
- `pyproject.toml` 保持一致
- 编写 **100 个新测试**（`test_phase0_coverage_boost.py`），覆盖之前 omitted 的模块
  - `preview/*`（analyzer, coverage_predictor, compliance_analyzer, config_recommender, score_engine, code_parser）
  - `engine/checkpoint.py`（CheckpointEngine 核心逻辑）
  - `report/*`（card_generator, exporter, feishu_notifier, trend_exporter）
  - `review/*`（ReviewSession, ReviewFinding, ReviewResult, resource_predictor）
  - `ci/*`（config, layers, tool_drivers, coverage_pipeline, stages, stage_utils, misra 模块等）
  - `evidence/*`（analysis, report, check, compliance, generator, pack 等）
  - `api/*`（ratelimit, middleware, compliance, pipeline_steps）
  - `spec/*`（validate, diff）
  - `usage/*`（metering, stripe_gateway）
  - `alm/*`（base, jira, polarion, traceability）
  - `skills/*`（SkillManifest, Workflow）
  - `notify.py`
  - `testgen/*`
  - `adapter/*`
  - `cli/*`
  - `compliance/*`
- 真实覆盖率（基于 `pytest --cov` 实测，627 个测试用例）：**~20.79%**（有进一步增长空间）
  - `server.py` 覆盖率：**96%**（高效 refactor，handler_helpers.py 70%, response_helpers.py 77%）
  - `store_pg.py` 覆盖率：**28%**（不需要 PostgreSQL 的模块级方法已验证，11 个 store_pg 测试全通过）
  - `_entry.py` 覆盖率：**100%**
  - `store.py` 覆盖率：**84%**
- 设置 `fail_under = 60` 保持目标，同时明确标记真实覆盖率水平

### 未覆盖模块及后续工作
| 模块 | 预估行数 | 难度 | 建议 | 状态 |
|------|---------|------|------|------|
| `pipeline/*` | ~1500 | 中 | 需要 mock Store 和大模型依赖 | ⏳ Phase 2 |
| `ci/*` | ~2000 | 中 | 部分模块已覆盖，需要 mock 工具链 | ⏳ Phase 2 |
| `api/*` (完整) | ~1000 | 低 | 路由/验证逻辑可以直接测试 | ⏳ Phase 2 |
| `llm/client.py` | ~200 | 中 | 需要 mock HTTP 调用 | ⏳ Phase 2 |
| `store_pg.py` | ~300 | 低 | mock 数据库（已移除 omit，有基础测试） | ✅ Phase 1 |

---

## P0-2: preview/analyzer.py 拆分 ✅

### 修复前
- `analyzer.py` 曾经是 976 行单文件
- 覆盖率被 omit 隐藏

### 修复后
- analyzer.py: **141 行**（仅保留 `analyze_directory()` 协调函数 + re-export）
- 已拆分为：
  - `coverage_predictor.py` — 67 行（`_predict_coverage()`）
  - `compliance_analyzer.py` — 165 行（`_scan_risks()`）
  - `config_recommender.py` — 87 行（`_recommend_template()`）
  - `code_parser.py` — 298 行（文件发现、框架检测、复杂度分析）
  - `score_engine.py` — 243 行（评分、语言检测、工作量估算）
  - `reporter.py` — 99 行（报告生成）
- `__init__.py` 统一 re-export，保持向后兼容
- 已编写 `test_preview_analyzer.py` 和 `test_phase0_coverage_boost.py` 中的预览模块测试

---

## P0-3: ui/server.py 拆分 ✅

### 修复前
- `server.py`: **818 行**，所有路由逻辑在 OSHHandler 类中
- `ui/routes/` 仅有 `__init__.py` 和 `helpers.py`

### 修复后
- `server.py`: **384 行**（Phase 1 进一步抽离到 `routes/handler_helpers.py`，从 749 行降至 ≤500 行门禁）
- 新增路由模块：
  - `routes/auth_routes.py` — 174 行（认证检查、登录处理、租户 API）
  - `routes/page_routes.py` — 131 行（页面服务、文件服务）
  - `routes/api_routes.py` — 134 行（状态/健康/证据/审查/CI 端点）
  - `routes/handler_helpers.py` — 137 行（do_GET/do_POST/do_DELETE 路由调度）
  - `routes/response_helpers.py` — 104 行（JSON/页面/文件响应实现，线程安全引用 server 模块变量以支持测试 patch）
- server.py 保持为入口集成文件，所有 delegate 方法向后兼容
- **所有 82 个 ui_server 测试全部通过**（含 do_GET/do_POST/do_DELETE/do_OPTIONS 路由、未授权 API 阻拦、登录处理、JSON/页面/文件响应、审计日志、端点数据）

---

## P0-4: 隐私政策/服务条款占位符替换 ✅

### 修复前
- `docs/privacy-policy-template.md` 包含 `[privacy@yuleosh.com]`, `[公司注册地址]`, `[DPO 联系方式]`, `[指定区域/云服务商]` 等占位符
- `docs/terms-of-service-template.md` 包含 `[support@yuleosh.com]`, `[sales@yuleosh.com]`, `[legal@yuleosh.com]`, `[公司注册地址]` 等占位符

### 修复后
- 所有联系邮箱 → `admin@yuleosh.com`
- 公司名 → `[公司名称]` + `<!-- TODO: 确认公司全称后替换 -->`
- 注册地址 → `[公司注册地址 — TODO: 确认后填写]`
- DPO → `admin@yuleosh.com` + `<!-- TODO: 替换为实际 DPO 联系信息 -->`
- 云服务商 → `[指定区域/云服务商 — TODO: 确认基础设施部署区域]`

---

## 测试结果

- `test_phase0_coverage_boost.py`: **100/100 通过** ✅
- `test_ui_server_smoke.py + test_ui_server_deep.py`: **82/82 通过** ✅
- 覆盖率配置净化后所有主要测试通过

---

## 开放问题

1. **公司全称**: 明总确认后替换 `[公司名称]`
2. **注册地址**: 确认后填写到两个文档
3. **覆盖率达到 60%**: 当前真实覆盖率 ~20.79%（实测 `pytest --cov` 结果，627 测试），需要持续编写测试。
   - `fail_under = 60` 保持目标值
   - 每轮迭代逐步提升
4. **B3 (小马审查阻塞项)**: 需要明总确认，未修复

---

## 交付物清单

| 交付物 | 状态 |
|:-------|:-----|
| 覆盖率真实基线报告 | ✅ 本报告 |
| `.coveragerc` 净化 | ✅ 64→6 omit（已移除 store_pg.py 和 _entry.py） |
| `pyproject.toml` 一致更新 | ✅ |
| 100 个覆盖率测试 | ✅ |
| `store_pg.py` 测试（`test_store_pg.py`，11 个测试，全部通过） | ✅ |
| `_entry.py` 测试（`test_entry_smoke.py`，6 个测试，全部通过） | ✅ |
| `analyzer.py` 拆分 | ✅ 976→141 行 |
| `server.py` 拆分 | ✅ 602→384 行（≤500 行门禁已达标）；handler_helpers.py 137 行，response_helpers.py 104 行 |
| 法律文书更新 | ✅ 占位符替换 |
| B3 确认 | ⏳ 需要明总确认 |

---

*报告自动生成 — yuleOSH Phase 0 完成检查点*

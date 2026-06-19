# yuleOSH 技术债务追踪

> 来源: `reports/v1.0.0-quality-assessment.md` | 更新: 2026-06-19

---

## 🔴 阻塞级 (Blocking)

### TD-001: `.coveragerc` 路径配置导致覆盖率测量失效
- **描述**: `[run] source = yuleosh` 期望 `yuleosh` 作为已安装包存在，但本地开发时 `src/yuleosh/` 未被识别。`pytest.ini` 使用 `--cov=src/yuleosh` 路径模式，但 `.coveragerc` 的 `source` 配置不匹配，导致覆盖率报告显示虚假低值（~11% 而非 ~70-80%）。`pyproject.toml` 也有冗余 coverage 配置（门禁 70% vs pytest.ini 的 80%）。
- **严重度**: 🔴 **阻塞**
- **预计修复时间**: 1h（已修复：统一为 `source = src/yuleosh`）
- **追踪状态**: ✅ **已修复**

### TD-002: `evidence/pack.py` 模块过大（1,084 行）
- **描述**: 证据打包、追溯矩阵、验收矩阵、合规包生成全部塞在一个文件，严重违反模块单一职责原则（500 行阈值）。
- **建议拆分**: 拆为 `generator.py`（追溯矩阵）、`compliance.py`（合规包）、`report.py`（报告）
- **严重度**: 🔴 **阻塞**
- **预计修复时间**: 4h
- **追踪状态**: 📋 待排期

### TD-003: `preview/analyzer.py` 模块过大（976 行）
- **描述**: AI Preview 分析器将静态分析、覆盖率预测、合规风险评估合并在一个模块。
- **建议拆分**: 拆为 `coverage_predictor.py`、`compliance_analyzer.py`、`config_recommender.py`
- **严重度**: 🔴 **阻塞**
- **预计修复时间**: 4h
- **追踪状态**: 📋 待排期

### TD-004: `ui/server.py` 模块过大（842 行）
- **描述**: 完整的 FastAPI/Starlette server 单文件，含路由、认证、中间件。建议拆分为 `routers/` 目录。
- **预计修复时间**: 3h
- **追踪状态**: 📋 待排期

### TD-005: `ci/stages.py` 模块过长（1,008 行→1,200+ 行）
- **描述**: 超过 1,000 行的单文件，建议拆分为 `stages/` 目录结构
- **预计修复时间**: 3h
- **追踪状态**: 📋 待排期

---

## 🟡 高优先级

### TD-010: `evidence_check.py` 是新增模块，需与 `pack.py` 边界清晰
- **描述**: Wave 3 新增 `evidence_check.py`（G-50 证据包完整性校验），与现有 `pack.py` 部分重叠
- **建议方向**: 未来将 `pack.py` 重新导出，`evidence_check.py` 独立承担 pack+check
- **追踪状态**: ⚠️ 已交付，待重构合并

### TD-011: `kpi.py` 持续增长（含 G-49 过程稳定性 KPI）
- **描述**: kpi.py 已扩展到 800+ 行，建议拆为 `kpi/status.py`, `kpi/baseline.py`, `kpi/process.py`
- **预计修复时间**: 2h
- **追踪状态**: 📋 待排期

---

## ✅ Wave 3 完成项 (2026-06-19)

| ID | 任务 | 状态 | 文件 |
|:---|:-----|:----:|:-----|
| DEF-011 | G-49 过程稳定性KPI采集 | ✅ | `kpi.py`（build success rate, regression trigger, fix timeliness）|
| DEF-012 | G-50 证据包CLI + 完整性校验 | ✅ | `evidence_check.py`（pack/check, SHA256, 6子目录）|
| G-04 | MISRA Dir 规则补齐 | ✅ | `misra-rules.yaml`（Dir 4.1~4.14 已在）|
| G-02 | 偏差管理流程升级 | ✅ | `docs/misra-deviations.md` |
| SWE.5 | V-Model 左侧集成规范 | ✅ | `stages.py`（spec-validation, architecture-review, requirements-trace）|
| G-05 | MISRA 验证计划文档 | ✅ | `docs/misra-verification-plan.md`（已存在）|
| G-08 | Rule 22.x Resource management | ✅ | `misra-rules.yaml`（22.1~22.11 已在）|
| G-07 | Tool qualification 文档 | ✅ | `docs/misra-tool-qualification.md`（已存在）|
| G-11 | 趋势存储（90天历史数据） | ✅ | `coverage_trend.py`（已有 JSONL 持久化）|
| H-07 | 代码-文档同步自动化门禁增强 | ✅ | `stages.py` run_docsync_gate + `layers.py` L1 集成 |
| G-12 | Dashboard 基础（CLI 趋势折线图） | ✅ | `coverage_trend.py`（已有趋势显示）|

---

## Sprint C — Critical CL2 缺陷修复 (2026-06-19)

| ID | 修复项 | 状态 | Commit 前缀 |
|:---|:-------|:----:|:------------|
| C1 | TM-02: 追溯矩阵 missing_test_count 修复（244→148） | ✅ | fix(cl2-critical): c1-tm-02-traceability-shall-extraction |
| C2 | TM-14: 偏差记录从1条扩展至8条（不同状态） | ✅ | fix(cl2-critical): c2-tm-14-deviation-records |
| C3 | MP-03/MP-04: timezone bug 修复（naive-aware 比较） | ✅ | fix(cl2-critical): c3-mp-timezone-naive-aware-fix |
| C4 | MP-04/MP-08: build-metadata.jsonl 路径修正 | ✅ | fix(cl2-critical): c4-mp-build-metadata-path |
| C5 | RI-03: 生成 tools-version.yaml | ✅ | fix(cl2-critical): c5-ri-tools-version-yaml |
| C6 | TM-05: 实现 misra deviate create CLI | ✅ | fix(cl2-critical): c6-tm-misra-deviate-create |

### 修复详情

- **C1**: `traceability.py` → 改进 SHALL 提取（使用章节 header req_id）、添加 pytest 文件扫描、修复 req_id 传递
- **C2**: `.yuleosh/ci-config.yaml` → 从 1 条默认偏差扩展到 8 条（approved/open/rejected/closed 4种状态）
- **C3**: `kpi.py` + `coverage_trend.py` → `_parse_ts`/`_parse_timestamp` 自动 strip tzinfo
- **C4**: `build_metadata.py` → `BUILD_META_FILE` 路径从 `reports/` 改为 `metrics/`
- **C5**: `.yuleosh/config/tools-version.yaml` → 记录 python/node/gcc/cppcheck/gcov/lcov/cmake/git 各版本
- **C6**: `yuleosh_cli.py` → 新增 `create` 子命令及 `_cli_add_deviation()` 非交互式添加函数

# yuleOSH 技术债务追踪

> 来源: `reports/v1.0.0-quality-assessment.md` | 更新: 2026-06-17

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
- **描述**: 完整的 FastAPI/Starlette server 单文件，含路由、认证、中间件。
- **建议拆分**: 拆为 `routes/` 子包
- **严重度**: 🔴 **阻塞**
- **预计修复时间**: 3h
- **追踪状态**: 📋 待排期

### TD-005: `cross/flash.py` 模块过大（800 行）
- **描述**: FAL 全功能（3 个 runner + 1 个 facade + 工具函数）
- **建议拆分**: 拆为 `openocd.py`、`jlink.py`、`pyocd.py`、`facade.py`
- **严重度**: 🔴 **阻塞**
- **预计修复时间**: 3h
- **追踪状态**: 📋 待排期

---

## 🟡 严重级 (Major)

### TD-006: `store_pg.py` 分支覆盖率仅 53%
- **描述**: PostgreSQL 存储层是数据持久化和审计追踪的关键路径，但分支覆盖率远低于 70% 门禁。关键路径如事务回滚、连接重试未覆盖。
- **严重度**: 🟡 **严重**
- **预计修复时间**: 3h
- **追踪状态**: 📋 待排期

### TD-007: `ci/` 模块覆盖提升未完成
- **描述**: Sprint 1 T-02 遗留，`ci/` 模块（如 stages.py 384 行）覆盖率未达门禁标准。
- **严重度**: 🟡 **严重**
- **预计修复时间**: 2h
- **追踪状态**: 📋 待排期

### TD-008: `pyproject.toml` vs `pytest.ini` 配置分裂
- **描述**: 两份 coverage 配置，门禁冲突（`pyproject.toml` 要求 70% 分支覆盖，`pytest.ini` 要求 80% 行覆盖）。`.coveragerc` 与 `pyproject.toml` 的 source 配置也有冗余。
- **严重度**: 🟡 **严重**
- **预计修复时间**: 1h
- **追踪状态**: 📋 待排期

### TD-009: API 模块（SaaS/API deep）覆盖率偏低
- **描述**: 新 SaaS 模块的 API deep 测试覆盖率接近 0%，认证、计费、预览评估等核心路径需要补充测试。
- **严重度**: 🟡 **严重**
- **预计修复时间**: 4h
- **追踪状态**: 📋 待排期

### TD-010: `ci/stages.py` 拆分 incomplete（384 行）
- **描述**: Sprint 2 T-09 遗留，stages.py 仍有 384 行，未完全拆分。
- **严重度**: 🟡 **中等**
- **预计修复时间**: 2h
- **追踪状态**: 📋 待排期

---

## 🟢 低级 (Minor)

### TD-011: 6 个未覆盖 SHOULD 需求
- **描述**: 6 个 SHOULD 层级需求在 RTM 中无对应测试用例。
- **严重度**: 🟢 **低**
- **预计修复时间**: 2h
- **追踪状态**: 📋 待排期

### TD-012: SWE.6 确认测试等级仅 3/5
- **描述**: 软件合格性测试（SWE.6）的 ASPICE 等级评估仅 3/5，发布验证需要加强 E2E 测试和验收标准。
- **严重度**: 🟢 **低**
- **预计修复时间**: 3h
- **追踪状态**: 📋 待排期

### TD-013: 偶有中英混杂注释
- **描述**: `monitor.py`、`flasher.py` 等文件中偶有 XXXX 占位符和中文注释，应统一为英文。
- **严重度**: 🟢 **低**
- **预计修复时间**: 1h
- **追踪状态**: 📋 待排期

### TD-014: `.coveragerc` vs `pyproject.toml` source 双写
- **描述**: 两处配置了相同的 `source` 路径，建议统一到单一配置文件。
- **严重度**: 🟢 **低**
- **预计修复时间**: 0.5h
- **追踪状态**: 📋 待排期

---

## 2026-06-19 修复记录（v2.1 缺陷修复）

### 🔧 DF-001: alloca/VLA 运行时检测缺失
- **描述**: `review_bsp.py` 缺少 alloca()/VLA/dynamic-allocation 运行时检测。老陈 Pipeline 终审报告指出应在 BSP 审查中实现运行时检测增强。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `_check_alloca_usage()` — 检测 alloca() 及 strdupa/strndupa 使用
  - 新增 `_check_vla_usage()` — 检测 VLA（变长数组）使用
  - 新增 `_check_dynamic_allocation()` — 检测 malloc/calloc/realloc/free 及 NULL-check
  - 新增 `_check_runtime_allocation_integrity()` — 跨文件运行所有运行时分配检查
  - 集成到 `_static_bsp_review()` 主流程
- **文件**: `src/yuleosh/pipeline/step_handlers/review_bsp.py`
- **提交**: 待

### 🔧 DF-002: test_c_unit.py `$$` PID 展开 bug
- **描述**: `$$` 在 subprocess.run(list) 中不会被 shell 展开，导致输出文件始终名为 `/tmp/c_test_runner_$$`。重复运行会覆盖或文件锁定。
- **状态**: ✅ **已修复**
- **修复内容**: 替换为 `tempfile.gettempdir() + os.getpid() + session.id` 生成唯一临时路径
- **文件**: `src/yuleosh/pipeline/step_handlers/test_c_unit.py`
- **提交**: 待

### 🔧 DF-003: gcov_coverage.py 缺少 fail_under 门禁 (CL2-E03)
- **描述**: gcov_coverage.py 只采集覆盖率不检查阈值。虽然 stages.py 有门禁逻辑，但 gcov_coverage.py 自身没有 fail_under 支持，无法独立运行门禁。
- **状态**: ✅ **已修复**
- **修复内容**:
  - `generate_c_coverage_report()` 新增 `fail_under` 和 `fail_under_branch` 参数
  - 新增 JSON 输出 `gate_passed` 和 `gate_details` 字段
  - CLI 新增 `--fail-under` 和 `--fail-under-branch` 参数
  - CLI 退出码反映门禁结果（失败时 exit 1）
- **文件**: `src/yuleosh/ci/gcov_coverage.py`
- **提交**: 待

### 🔧 DF-004: coverage_trend.py 缺少回归告警 (CL2-E04)
- **描述**: CL2-E04 step 4 要求单次下降 > 5% 触发 warning，coverage_trend.py 未实现。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `check_coverage_regression()` 函数
  - 比较最新条目与滑动窗口平均值（默认窗口=3）
  - 支持 C/Python 行覆盖率 + 分支覆盖率回归检测
  - 默认阈值：行 5pp，分支 5pp
  - 返回结构化告警结果
- **文件**: `src/yuleosh/ci/coverage_trend.py`
- **提交**: 待

### 🔧 DF-005: sync_check.py 缺少 YAML Schema 验证 (CL2-E05) 和增强门禁 (CL2-E06)
- **描述**: sync_check.py 有基础 tracking 功能，但缺少 CL2-E05 YAML Schema 验证和关键模块差异化门禁。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `DOC_YAML_SCHEMAS` 定义文档 Schema 规范
  - 新增 `validate_doc_yaml_schema()` 验证文档必需字段
  - 新增 `run_sync_check_gate()` 组合 E05+E06 的增强门禁
  - 新增 `--enhanced` CLI 参数启用 Schema 验证
  - 更新 `print_sync_result()` 同时显示 tracking 和 schema 结果
- **文件**: `src/yuleosh/ci/sync_check.py`
- **提交**: 待

## 汇总

| 等级 | 数量 | 预计总修复时间 |
|:-----|:----:|:--------------:|
| 🔴 阻塞 | 5 | 15h |
| 🟡 严重 | 5 | 12h |
| 🟢 低 | 4 | 6.5h |
| 🔧 新增(已修复) | 5 | 3h |
| **合计** | **19** | **36.5h** |

> 注：TD-001（.coveragerc 路径）已在 Phase 0 Bug 修复中处理完毕。TD-008（配置分裂）在统一 source 过程中部分解决。

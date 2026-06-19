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

### 🔧 DF-006: Pipeline Profile 切换机制 (DEF-004 / G-33)
- **描述**: Pipeline Profile 切换机制实现。ci-config.yaml 配置、≥2 个 profile、启动校验、step 过滤。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `src/yuleosh/ci/profile.py` — profile 定义、验证、step 过滤
  - 内置 4 个 profile（safety, ci, performance, testing），≥2 个
  - 启动时校验 active_profile，无效时回退 safety
  - `filter_steps_for_profile()` 根据 profile 排除/包含 step
  - `run_pipeline()` 支持 `--profile <name>` CLI 参数
  - 更新 `.yuleosh/ci-config.yaml` 添加 profiles 定义
- **测试文件**: `tests/test_profile.py`（16 个测试用例）
- **提交**: 待

### 🔧 DF-007: MISRA Delta 模式 (DEF-006 / §14.20~§14.22)
- **描述**: MISRA 双重 delta 模式实现：L1 增量 + L2 全量+零增量阻断。
- **状态**: ✅ **已修复**
- **修复内容**:
  - `stages.py:run_misra_check()` 新增 `mode` 参数（auto/delta/full）
  - L1（`mode="delta"`）：仅扫描 `git diff HEAD~1` 修改文件
  - L2（`mode="full"`）：全量扫描 + 基线对比 + 阻断新增 Required
  - 新增 `_load_misra_baseline()` 加载最近全量扫描基线
  - 新增 `_is_new_required_violation()` 检测新增 Required 违规
  - L2 零增量阻断优先于所有其他阻断规则
  - 更新 `layers.py` L1 调用传递 mode="delta"
- **文件**: `src/yuleosh/ci/stages.py`, `src/yuleosh/ci/layers.py`
- **提交**: 待

### 🔧 DF-008: 堆栈使用分析 Step Handler (DEF-007 / §14.14~§14.15)
- **描述**: 堆栈使用分析 step handler 实现，≥95% 使用率阻断。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `src/yuleosh/pipeline/step_handlers/review_stack.py`（516 行）
  - 静态堆栈分析（linker script + 大数组检测）
  - 函数调用深度分析（内联启发式）
  - 中断嵌套堆栈预算检查
  - RAM vs 堆栈利用率估算
  - ≥95% 使用率触发 PipelineStepError 阻断
  - 已注册至 PIPELINE_STEPS（review-stack step）
- **测试文件**: `tests/test_stack_review.py`（10 个测试用例）
- **提交**: 待

### 🔧 DF-009: MMIO 配置审查 Step Handler (DEF-008 / §14.18~§14.19)
- **描述**: MMIO 配置审查自动化：时钟/GPIO/NVIC/DMA 审查。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `src/yuleosh/pipeline/step_handlers/review_mmio.py`（741 行）
  - 时钟系统审查（HSE/LSE/PLL/RCC 配置完整性）
  - GPIO 配置审查（初始化、引脚分配、上下拉）
  - NVIC 配置审查（优先级分组、IRQ 启用、优先级合理性）
  - DMA 配置审查（通道/模式/优先级/中断）
  - 跨系统一致性检查（外设→DMA、MSP Init）
  - 已注册至 PIPELINE_STEPS（review-mmio step）
- **测试文件**: `tests/test_mmio_review.py`（10 个测试用例）
- **提交**: 待

### 🔧 DF-010: 构建元数据持久化 (DEF-009 / G-48 §20.1~§20.6)
- **描述**: 构建元数据 JSONL 持久化，字段完整性、变更审计、可关联性、工具版本锁定。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `src/yuleosh/ci/build_metadata.py`（CLI + API）
  - JSONL 文件格式（`.yuleosh/reports/build-metadata.jsonl`）
  - 9 个必填字段（build_id, timestamp, commit, status, layer, tool_versions, files_changed 等）
  - 字段完整性校验（`_validate_fields()`）
  - 变更审计：files_changed 计数
  - 可关联性：`get_build_chain()` 按 commit 关联所有 build
  - 工具版本锁定：`_get_tool_versions()` 捕获 6 个工具版本
  - 完整性验证：`validate_metadata_integrity()` 检查重复/时间序/必填字段
- **测试文件**: `tests/test_build_metadata.py`（9 个测试用例）
- **提交**: 待

### 🔧 DF-011: Agent 审查↔代码版本双向追溯 (DEF-010 / G-47 §19.1~§19.4)
- **描述**: Agent 审查与代码版本双向追溯：commit SHA、file:line、build_id 关联。
- **状态**: ✅ **已修复**
- **修复内容**:
  - 新增 `src/yuleosh/ci/agent_traceability.py`（CLI + API）
  - JSONL 文件格式（`.yuleosh/reports/agent-traceability.jsonl`）
  - `record_review()` — 记录审查会话含 commit SHA、file:line、build_id
  - `get_reviews_for_commit()` — commit → 审查正向追溯
  - `get_commits_for_review()` — review_id → commit 反向追溯
  - `get_findings_for_file()` — file:line 定位查询
  - `get_reviews_by_build()` — build_id → 审查关联
  - 标准化 file:line 格式的 location 字段
- **测试文件**: `tests/test_agent_traceability.py`（11 个测试用例）
- **提交**: 待

## 汇总

| 等级 | 数量 | 预计总修复时间 |
|:-----|:----:|:--------------:|
| 🔴 阻塞 | 5 | 15h |
| 🟡 严重 | 5 | 12h |
| 🟢 低 | 4 | 6.5h |
| 🔧 新增(已修复) | 11 | 6h |
| **合计** | **25** | **39.5h** |

> 注：TD-001（.coveragerc 路径）已在 Phase 0 Bug 修复中处理完毕。TD-008（配置分裂）在统一 source 过程中部分解决。
> Sprint B Wave 1 已修复 6 个 P0 缺陷（DEF-004~DEF-010），对应 11 个 DF 修复记录。

# yuleOSH 技术债务追踪

> 来源: `reports/v1.0.0-quality-assessment.md` | 更新: 2026-06-19

---

## 🔴 阻塞级 (Blocking)

### TD-001: `.coveragerc` 路径配置导致覆盖率测量失效
- **描述**: `[run] source = yuleosh` 期望 `yuleosh` 作为已安装包存在，但本地开发时 `src/yuleosh/` 未被识别。`pytest.ini` 使用 `--cov=src/yuleosh` 路径模式，但 `.coveragerc` 的 `source` 配置不匹配，导致覆盖率报告显示虚假低值（~11% 而非 ~70-80%）。`pyproject.toml` 也有冗余 coverage 配置（门禁 70% vs pytest.ini 的 80%）。
- **严重度**: 🔴 **阻塞**
- **预计修复时间**: 1h（已修复：统一为 `source = src/yuleosh`）
- **追踪状态**: ✅ **已修复**

### TD-002: `evidence/pack.py` 模块过大（1,084 行 → 已拆分）
- **描述**: 证据打包、追溯矩阵、验收矩阵、合规包生成全部塞在一个文件。已拆分为 `generator.py`、`compliance.py`、`report.py`。
- **Sprint E 修复**: `pack.py` 作为 re-export 模块，核心逻辑移至 `compliance.py`（含 manifest.json 生成）
- **严重度**: 🔴 **阻塞**
- **预计修复时间**: 4h
- **追踪状态**: ✅ **Sprint E 已修复**

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

## Sprint E — CL2 审查问题全量修复 (2026-06-19)

| ID | 修复项 | 状态 | Commit 前缀 |
|:---|:-------|:----:|:------------|
| E1 | P0-C覆盖率 1.4%→≥60% (实际99.2%) | ✅ | feat(sprint-e): e0-p0-c-coverage-99pct |
| E2 | P1-缺陷逃逸率采集 | ✅ | feat(sprint-e): e1-defect-escape-rate |
| E3 | P1-Profile变更审计 | ✅ | feat(sprint-e): e2-profile-audit |
| E4 | P2-工具版本变更审批 | ✅ | feat(sprint-e): e3-tool-version-approval |
| E5 | P2-证据包manifest修复 | ✅ | feat(sprint-e): e4-evidence-manifest |
| E6 | P2-基线文档完善 | ✅ | feat(sprint-e): e5-baseline-doc-update |

### 修复详情

- **E1**: 新增Unity C测试（16个HAL mock + 2个hello测试），使用gcovr提升C覆盖率至99.2%
- **E2**: `kpi.py` 新增 `record_defect_escape()` / `get_defect_escape_summary()`，CLI: `yuleosh kpi defect-escape record|status`
- **E3**: `profile.py` 新增 `record_profile_change()` / `get_profile_audit_log()`，CLI: `yuleosh config profile audit`
- **E4**: 新增 `docs/tool-version-change-process.md`，`tools-version.yaml` 添加 `approval` 字段
- **E5**: `compliance.py` 中 `pack_compliance_zip()` 添加 manifest.json 生成
- **E6**: `docs/process-performance-baseline.md` 补充缺陷逃逸率、C覆盖率、Profile审计等数据

### 新文件

| 文件 | 描述 |
|:-----|:------|
| `scripts/run_c_coverage.py` | C 覆盖率运行器 (gcovr) |
| `tests/unity/test_hal_mock_unity.c` | HAL mock Unity 测试 (16 case) |
| `tests/unity/test_hello_unity.c` | hello.c Unity 测试 (2 case) |
| `docs/tool-version-change-process.md` | 工具版本变更流程文档 |

### 改动文件

| 文件 | 改动 |
|:-----|:------|
| `tests/unity/src/unity.c` | 修复 Unity 类型定义、添加测试名输出 |
| `tests/unity/src/unity_internals.h` | 添加 UNITY_LINE_TYPE 宏定义 |
| `tests/unity/Makefile` | 重构支持 coverage 编译 |
| `Makefile` | 添加 c-coverage / c-coverage-gate 目标 |
| `src/yuleosh/ci/kpi.py` | 添加缺陷逃逸率采集 |
| `src/yuleosh/ci/profile.py` | 添加 Profile 变更审计 |
| `src/yuleosh/evidence/compliance.py` | 添加 manifest.json 生成 |
| `yuleosh_cli.py` | 添加 config/profile/audit、kpi/defect-escape 命令 |
| `.yuleosh/config/tools-version.yaml` | 添加 approval 字段 |
| `docs/process-performance-baseline.md` | 补充 Sprint E 数据 |
| `.yuleosh/reports/c-coverage.json` | C 覆盖率报告（自动生成） |



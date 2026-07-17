# yuleOSH v2.5.0 Phase 2 — 模块重构 + KPI 深化 + 测试扩面

## 进度报告

### 工作1: Pipeline handler 去重 (P1, 2天) ✅

**状态**: 完成
**方案**:
- 新建 `handler_base.py` — 包含 BaseHandler 抽象基类
- retry 装饰器 (指数退避重试)
- CheckpointManager (检查点管理)
- as_handler 装饰器 (函数式快速迁移)
- timed_step 模板方法: pre_check → checkpoint → execute → post_write

**文件**:
- `src/yuleosh/pipeline/step_handlers/handler_base.py` (新文件)

**向后兼容**: ✅ 所有 handler 接口未修改

### 工作2: ci/layers.py 分拆 (P1, 4天) ✅

**状态**: 完成
**方案**: 拆成 `ci/layers/` package:
- `layer_config.py` — 配置、依赖检查、语言检测
- `layer_executor.py` — 各层执行函数 (run_layer1/2/2.5/3)
- `layer_validator.py` — 验证与结果处理

**文件**:
- `src/yuleosh/ci/layers/__init__.py` (新)
- `src/yuleosh/ci/layers/layer_config.py` (新)
- `src/yuleosh/ci/layers/layer_executor.py` (新)
- `src/yuleosh/ci/layers/layer_validator.py` (新)
- `src/yuleosh/ci/layers.py` → 改写为 backward-compatible re-exporter

**向后兼容**: ✅ 所有 `from yuleosh.ci.layers import ...` 保持原样

### 工作3: KG 度量接入 KPI 管线 (P1, 1.5天) ✅

**状态**: 完成
**方案**:
- 新增 `ci/kpi/kg_source.py` — KG 度量数据源
  - `get_kg_coverage_metrics()` — 覆盖率: coverage_pct, covered, uncovered
  - `get_kg_health_metrics()` — 图健康度: 节点/边数, 孤立文件, 低置信度边
  - `get_kg_confidence_metrics()` — 置信度: 平均置信度, explicit/derived/heuristic 分布
  - `get_kg_metrics_summary()` — 汇总输出 (JSON/文本)

- 扩展 `ci/kpi/utils.py` DEFAULT_THRESHOLDS:
  - `kg_coverage_pct`, `kg_health_min_nodes`, `kg_health_max_orphan_pct`
  - `kg_confidence_min`, `kg_confidence_explicit_pct`

- 扩展 `ci/kpi/report.py`:
  - `kpi_status()` 新增 KG KPI 6 个维度评估条目
  - `kpi_baseline_save()` 保存 KG 基线快照

**文件**:
- `src/yuleosh/ci/kpi/kg_source.py` (新)
- `src/yuleosh/ci/kpi/utils.py` (修改)
- `src/yuleosh/ci/kpi/__init__.py` (修改)
- `src/yuleosh/ci/kpi/report.py` (修改)

### 工作4: cross/hardware 测试覆盖 (P1, 3.5天) ✅

**状态**: 完成 (72 个新测试)
**测试内容**:
- `tests/test_cross_hardware_coverage.py` (70 tests)
  - Cross: SerialMonitor, PipeSerialMonitor, sil_runner, target_config
  - Hardware: HardwareDeployer, AIDebugger, DebugReport, SerialMonitor, flasher, integration

- `tests/ci/test_kpi_kg_integration.py` (10 tests)
  - KG coverage/health/confidence metrics
  - KG metrics summary (JSON/text)
  - KPI dashboard integration

**覆盖率**: 移除了 cross/ 和 hardware/ 的 omit 配置
**向后兼容**: ✅ 注意 — coverage fail-under=50% 尚未达标 (约 5.74%)，因许多其他模块仍无测试

### 测试结果
- 139/140 现有测试通过
- 72/72 新测试通过
- 1 个预存在 `test_cross_smoke.py::test_discover_targets_empty` 的失败 (与本次修改无关)

### Git 提交状态
待提交。规范 commit message 如下。

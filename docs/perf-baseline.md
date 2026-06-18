# yuleOSH 性能基线文档

> **ASPICE 关联**: SWE.4-BP4 — 验证软件单元的资源消耗  
> **文档版本**: v1.0.0 | **状态**: 初版  
> **测试文件**: `tests/test_perf_baseline.py`  
> **维护人**: 小克 👨‍💻 (后端组)

---

## 1. 测试环境

### 1.1 硬件环境

| 项目 | 值 |
|:----|:----|
| 主机 | Mac mini (Apple M4) |
| CPU | Apple M4 (10 核) |
| RAM | 24 GB |
| 操作系统 | macOS 15.x |

### 1.2 软件环境

| 项目 | 值 |
|:----|:----|
| Python | 3.13.13 |
| pytest | 9.0.3 |
| pytest-cov | 7.1.0 |
| bcrypt | 4.x |
| PyJWT | 2.x |
| PyYAML | 6.x |
| 运行模式 | `--tb=short --no-cov` (减少覆盖检测延迟) |

### 1.3 测试分类

| 分组 | Mark 标签 | 测试数 | 覆盖模块 |
|:----|:---------|:------:|:--------|
| Spec 解析 | `perf` | 5 | `yuleosh.spec.validate` |
| 证据包生成 | `perf` | 5 | `yuleosh.evidence.generator` |
| CI 配置加载 | `perf` | 4 | `yuleosh.ci.config` |
| API 响应时间 | `perf` | 7 | `yuleosh.api.{auth,subscription,wizard}` |
| 内存基线 | `perf` | 6 | 各关键模块完整导入 |
| 集成场景 | `perf` | 2 | 多模块组合 |
| 元测试 | `perf` | 1 | 基线框架完整性验证 |
| **合计** | | **30** | |

---

## 2. 基线结果

> 所有时间单位为 **秒 (s)**，内存单位为 **MiB**。  
> 测试时间：首次运行基准。

### 2.1 Spec 解析性能

| 测试 | 操作 | 输入规模 | 实测值 | 阈值 | 状态 |
|:----|:----|:--------:|:------:|:----:|:----:|
| `test_spec_parse_10_reqs` | parse_spec | 10 需求, 5 场景 | < 0.1s | < 2.0s | ✅ |
| `test_spec_parse_100_reqs` | parse_spec | 100 需求, 30 场景 | < 0.2s | < 3.0s | ✅ |
| `test_spec_parse_500_reqs` | parse_spec | 500 需求, 100 场景 | < 0.5s | < 5.0s | ✅ |
| `test_spec_validate_100_reqs` | validate_spec | 100 需求 | < 0.1s | < 3.0s | ✅ |
| `test_spec_diff_perf` | diff_specs | 100→105 需求 | < 0.2s | < 3.0s | ✅ |

**分析**: Spec 解析器在 **O(n)** 时间内线性伸缩。500 需求 + 100 场景在 0.5s 内完成，性能充裕。

### 2.2 证据包生成性能

| 测试 | 操作 | 实测值 | 阈值 | 状态 |
|:----|:----|:------:|:----:|:----:|
| `test_evidence_collector_init` | EvidenceCollector() | < 0.1s | < 0.5s | ✅ |
| `test_evidence_collect_requirements_via_spec` | parse_spec → dict | < 0.1s | < 2.0s | ✅ |
| `test_evidence_full_chain_empty` | 全链 (无 CI/SIL) | < 0.1s | < 5.0s | ✅ |
| `test_evidence_traceability_matrix` | traceability matrix | < 0.1s | < 2.0s | ✅ |
| `test_evidence_coverage_summary` | coverage summary | < 0.1s | < 1.0s | ✅ |

**分析**: 证据生成模块初始化快、数据结构操作轻量。矩阵生成和覆盖率汇总均在毫秒级完成。  
**注意**: `collect_requirements()` 方法存在内部 `from validate import parse_spec` 的脆弱导入路径；基线测试绕过此问题，直接调用 `yuleosh.spec.validate.parse_spec`。建议在后续 Sprint 修复 `collection.py` 的导入逻辑。

### 2.3 CI 配置加载性能

| 测试 | 操作 | 实测值 | 阈值 | 状态 |
|:----|:----|:------:|:----:|:----:|
| `test_ci_config_load_default` | load_ci_config (无文件) | < 0.1s | < 0.5s | ✅ |
| `test_ci_config_load_from_yaml` | load_ci_config (YAML) | < 0.1s | < 0.5s | ✅ |
| `test_ci_config_parse_heavy` | _parse_ci_config (20 模块阈值) | < 0.1s | < 1.0s | ✅ |
| `test_ci_strict_and_misra_checks` | is_strict + is_misra_fail_fast | < 0.1s | < 0.1s | ✅ |

**分析**: CI 配置模块性能良好。大配置加载也远低于阈值。

### 2.4 API 核心函数响应时间

| 测试 | 操作 | 调用次数 | 实测值 | 阈值 | 状态 |
|:----|:----|:-------:|:------:|:----:|:----:|
| `test_auth_slugify_1000` | _slugify | 1050 次 | < 0.01s | < 0.5s | ✅ |
| `test_auth_bcrypt_hash_verify` | bcrypt hash+verify | 10 轮 | < 0.05s | < 2.0s | ✅ |
| `test_auth_jwt_encode_decode` | JWT encode+decode | 500 轮 | < 0.05s | < 1.0s | ✅ |
| `test_subscription_tier_lookup_10000` | TIERS 字典查找 | 10000 次 | < 0.01s | < 0.2s | ✅ |
| `test_subscription_extract_token_5000` | _extract_token | ~5100 次 | < 0.01s | < 0.2s | ✅ |
| `test_wizard_jwt_parse_500` | JWT 解析 | 500 次 | < 0.02s | < 0.5s | ✅ |
| `test_core_json_helpers` | json_ok + json_error | 1000 次 | < 0.01s | < 0.1s | ✅ |

**分析**: 各 API 核心函数性能充裕。bcrypt 哈希因计算成本较高但阈值设置合理。

### 2.5 内存基线

| 测试 | 模块 | 实测值 | 阈值 (MiB) | 状态 |
|:----|:----|:------:|:----------:|:----:|
| `test_memory_spec_module` | yuleosh.spec.validate | < 1 MiB | < 200 | ✅ |
| `test_memory_evidence_module` | yuleosh.evidence.generator | < 1 MiB | < 200 | ✅ |
| `test_memory_ci_config_module` | yuleosh.ci.config | < 1 MiB | < 200 | ✅ |
| `test_memory_api_auth_module` | yuleosh.api.auth | < 1 MiB | < 200 | ✅ |
| `test_memory_api_subscription_module` | yuleosh.api.subscription | < 1 MiB | < 200 | ✅ |
| `test_memory_full_yuleosh` | yuleosh (完整) | < 1 MiB | < 500 | ✅ |

**分析**: 各模块导入内存开销极小（均 < 1 MiB）。tracemalloc 增量测量在 macOS 开发环境下表现稳定。

### 2.6 集成场景

| 测试 | 操作链 | 实测值 | 阈值 | 状态 |
|:----|:-------|:------:|:----:|:----:|
| `test_spec_to_evidence_chain` | parse_spec → requirements → matrix | < 0.1s | < 10.0s | ✅ |
| `test_ci_config_and_coverage_threshold` | load_ci_config + threshold check | < 0.1s | < 1.0s | ✅ |

---

## 3. 预警阈值

### 3.1 当前阈值（v1.0.0 基线）

| 模块 | 指标 | 警告线 | 故障线 | 触发动作 |
|:----|:----|:------:|:------:|:--------|
| Spec 解析 | 500 需求解析时间 | 3.0s | 5.0s | 审查 parse_spec 复杂度 |
| 证据生成 | 空链全流程 | 2.0s | 5.0s | 审查 EvidenceCollector 各方法 |
| CI 配置 | 大配置解析 | 0.5s | 1.0s | 审查 _parse_ci_config |
| API 函数 | 单函数响应 | 0.1s | 0.5s | 审查具体函数实现 |
| 内存 | 单模块导入 | 100 MiB | 200 MiB | 审查模块依赖树 |

### 3.2 阈值调整规则

- **宽松化需求**: 当 CI 环境性能显著低于 Dev 环境时，调整阈值上浮最多 5 倍
- **收紧需求**: 当 3 次以上 Sprint 内实测值持续低于阈值的 10%，可将阈值下调 50%
- **变更触发**: 任何对被测模块的重构/升级需同步更新阈值

---

## 4. 长期趋势追踪建议

### 4.1 CI 集成

建议在 CI 中加入性能基线追踪：

```yaml
# .github/workflows/perf-baseline.yml (建议)
name: Performance Baseline
on:
  schedule:
    - cron: "0 6 * * 1"  # 每周一 06:00 UTC
  workflow_dispatch:

jobs:
  perf:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e ".[dev]"
      - run: python -m pytest tests/test_perf_baseline.py -v --tb=short --no-cov
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: perf-baseline-results
          path: reports/perf-baseline-*.md
```

### 4.2 趋势数据记录

每次性能测试运行结束后，建议将结果追加到 `reports/perf-baseline-history.jsonl`：

```json
{"timestamp": "2026-06-16T09:21:00Z", "run_id": "v1.0.0-baseline", "test_count": 30, "pass_count": 30, "fail_count": 0}
```

### 4.3 回归检测

- 任何被测功能重构后，需先运行基线套件，确认不恶化超过警告线
- 若恶化超过故障线，提交必须附加性能修复或调整阈值说明

### 4.4 工具推荐

- **pytest-benchmark**: 可替代手动 `time.perf_counter()`，提供统计直方图
- **pytest-timeout**: 为性能测试添加超时保护
- **py-spy / memory_profiler**: 用于更细致的内存/CPU profiling

---

## 5. 开发注意事项

1. **collection.py 的脆弱导入**: `collect_requirements()` 方法内 `from validate import parse_spec` 依赖于 `src/spec/validate.py` 存在。若重新组织目录结构需同步修复此路径。
2. **环境敏感性**: bcrypt 性能依赖 CPU 指令集（ARM M4 vs x86_64）。CI 环境若使用不同架构，需调整相关阈值。
3. **内存测量**: 当前使用 `tracemalloc` + subprocess 单次采样。更精确的测量推荐 `memory_profiler` 的迭代采样模式。

---

## 附录 A: 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|:----|:----|:---------|:----|
| v1.0.0 | 2026-06-16 | 初版基线：5 个模块 30 测试项，全部 PASS | 小克 👨‍💻 |

## 附录 B: 覆盖的 SWE.4-BP4 评估项

| 评估项 | 覆盖情况 |
|:-------|:---------|
| Spec 解析时间 | ✅ 3 个规模等级 |
| 证据生成时间 | ✅ 含初始化、矩阵、汇总 |
| CI 配置加载时间 | ✅ 含默认与 YAML |
| API 函数延迟 | ✅ auth / subscription / wizard |
| 模块内存占用 | ✅ 6 个关键模块 |
| 集成链延迟 | ✅ 2 个跨模场景 |

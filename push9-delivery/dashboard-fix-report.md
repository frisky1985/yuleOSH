# Dashboard Fix Report (A1~A4)

## A1: swe_status 写入 evidence pack manifest

**问题**: `pack_evidence_bundle()` 生成 audit-manifest.json 但未写入 `swe_status` 字段，导致 Dashboard 的 `GET /api/v1/dashboard/swe-status` 总是找不到数据而回落 mock。

**修复**: 在 `src/yuleosh/evidence/evidence_check.py` 的 `pack_evidence_bundle()` 函数末尾、写入 manifest 之前添加了 SWE 状态聚合逻辑。新的逻辑：
1. 根据 evidence bundle 中实际找到的组件（ci-results, misra-reports, coverage, reviews, traceability）推导 SWE.1~SWE.6 的完成状态
2. 按标准分配状态：`completed`/`partial`/`not_started`
3. 状态定义包括名称、颜色、标签和更新时间
4. 写入 manifest 的 `swe_status` 字段

**Dashboard 读取路径**: `_dashboard_swe_status()` → `manifest.get("swe_status", {})` → 现在能找到真实数据。

**验证**: 调用 `pack_evidence_bundle()` 后检查 manifest 的 swe_status 字段存在且包含 6 条记录。

## A2: coverage-trend.jsonl CI 写入

**问题**: `_dashboard_coverage()` 从 `.yuleosh/reports/coverage-trend.jsonl` 读取趋势但文件可能为空，因为 CI 没有自动追加密度记录。

**修复**: 在 `src/yuleosh/ci/coverage_pipeline.py` 的 `generate_branch_coverage_report()` 函数中，Step 4（构建报告）之后、Step 5（发布制品）之前插入 `record_coverage()` 调用：
```python
from yuleosh.ci.coverage_trend import record_coverage
record_coverage(project_dir)
```
这样每次 CI 运行都会在 coverage-trend.jsonl 中追加一条记录。已有 `record_coverage()` 实现保持不变（位于 `coverage_trend.py`，读取 C 覆盖率和 Python 覆盖率 JSON 文件）。

**验证**: 运行 CI 覆盖率管道后检查 `.yuleosh/reports/coverage-trend.jsonl` 是否存在且有新条目。

## A3: KB 文章去重 (MISRA 违规)

**问题**: KbStore 中 MISRA 违规文章大量重复（同一 rule_id + 同一 file + 同一 line 的多次扫描记录），Dashboard 的 `_dashboard_misra_trend()` 读取质量差。

**修复**: 在 `src/yuleosh/kb/store.py` 的 KbStore 类中添加了三个新方法：

1. **`deduplicate_misra_articles()`** — 对 `source='misra_analysis'` 的 KB 文章进行去重：
   - 从标题提取 rule_id（格式 `MISRA-10.1: ...`）
   - 从 `source_ref` 提取 file 和 line（格式 `path/to/file.c:142`）
   - 以 (rule_id, file, line) 为去重键
   - 每组只保留最新一条（id 最大），删除其余

2. **`list_deduped_misra_articles()`** — 返回去重后的 MISRA 文章列表（用于 Dashboard）

3. **`count_misra_violations_by_rule()`** — 按 rule_id 统计唯一违规数量（文件+行去重）

**验证**: 创建 3 条文章（2 条重复），去重后删除 1 条保留 2 条，count 返回 `{'10.1': 1, '11.3': 1}`。

## A4: _estimate_swe_completed() 硬编码修复

**问题**: `dashboard.py` 中 `_estimate_swe_completed()` 根据项目名关键字硬编码 heuristic。

**修复**: 改为优先从 evidence pack 的 audit-manifest.json 读取 `swe_status` 数据：
1. 调用 `_find_latest_manifest()` 定位最新的 manifest 文件
2. 从 manifest 的 `swe_status` 中统计 completed 状态的数量
3. 如果找到有效数据则返回，否则回落为原 hardcoded heuristic
4. 新增了 `project_id` 参数传递

**验证**: 当不存在 manifest 时回落为原 behavior；当存在含 swe_status 的 manifest 时使用真实数据。

# KG → Dashboard 接入报告

## 概述

将 `dashboard_writer.py` 的 `write_swe_status()` 中基于文件探测的 SWE 阶段判定改造为使用知识图谱（KG）中的真实追溯数据。KG 数据优先级高于文件探测，KG 不可用时优雅降级。

## 改造内容

### 1. 新增 `_swe_status_from_kg()` 函数

在 `src/yuleosh/ci/dashboard_writer.py` 中新增：

```python
def _swe_status_from_kg(project_dir: str | Path) -> dict[str, str]:
```

- 查询项目 `.yuleosh/knowledge_graph.db` 中的 KG 数据
- 使用 `get_aspice_coverage()` → SWE.4（unit 层 covers > 0）
- 使用 `get_confirmation_trace()` → SWE.5（validates 边 > 0）
- 使用 `list_snapshots()` → SWE.8（≥3 个 snapshot=validated，>0=completed）
- 使用 `get_graph_stats()` → SWE.10（covers 边数 ≥ 需求数）
- KG DB 不存在 / 异常 / 空图 → 返回 `{}`（触发文件探测降级）

### 2. 修改 `write_swe_status()` 合并逻辑

KG 数据在 `write_swe_status()` 末尾合并，KG 返回的 phase 覆盖文件探测结果：

```python
kg_status = _swe_status_from_kg(project_dir)
for phase, kg_value in kg_status.items():
    status[phase] = kg_value
    evidence[phase].append(f"kg: {kg_value}")
```

### 3. 新增测试文件

`tests/ci/test_dashboard_kg_integration.py` — 16 个测试，覆盖：

| 测试类别 | 测试数 | 覆盖点 |
|:---------|:-------|:-------|
| 优雅降级 | 2 | KG DB 不存在、KG 模块不可用、KG 异常 |
| SWE.4 | 1 | `get_aspice_coverage` unit 层 covers > 0 → completed |
| SWE.5 | 2 | validates 边 > 0 → completed；无 validates → 跳过 |
| SWE.8 | 1 | ≥3 snapshot → validated；>0 → completed |
| SWE.10 | 3 | covers ≥ reqs → validated；covers>0 → completed；无 covers → 跳过 |
| write_swe_status 集成 | 5 | KG 覆盖文件探测、降级回文件探测、输出格式、幂等性、向后兼容 |
| coverage_trend | 1 | 输出为 dict 结构 |

### 4. 向后兼容

- `_check_kg_available()` 延迟检查 KG 模块是否可导入（全局缓存）
- 所有异常捕获（`os.path.exists` 返回 False、store 初始化异常、查询异常）→ 返回 `{}`
- 原有文件探测逻辑完全保留
- CLI 入口不变
- `write_swe_status()` 签名不变

## 测试结果

```
tests/ci/test_dashboard_kg_integration.py ........ 16 passed
tests/ci/ (existing) ........................ 296 passed, 3 failed (pre-existing)
```

3 个失败为 MISRA 规则格式相关预存问题，与本任务无关。

## 文件变更

| 文件 | 操作 | 说明 |
|:-----|:-----|:-----|
| `src/yuleosh/ci/dashboard_writer.py` | 修改 | 新增 `_swe_status_from_kg()` + 合并逻辑 |
| `tests/ci/test_dashboard_kg_integration.py` | 新增 | 16 个集成/单元测试 |
| `reports/kg-dashboard-integration-report.md` | 新增 | 本报告 |

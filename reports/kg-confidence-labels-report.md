# KG 置信度标签 — 实现报告

## 背景

当前 Agent 自动生成的 implements/verifies/covers 边都没有置信度标记。
审计师需要透明度：必须能区分「确定的映射」和「启发式推导的映射」。

## 数据模型

**设计决策**：置信度作为 `properties` 字典中的 `confidence` 子字段存储。

```
Edge.properties["confidence"] = float  # 0.0 ~ 1.0
```

现有 API 签名无变化，向后兼容。不提供 confidence 的旧边默认视为 `1.0`。

## 各边类型的置信度

| 边类型 | 生成位置 | 置信度 | 推导方式 |
|:-------|:---------|:------:|:---------|
| covers (RTM) | `import_from_rtm_md()` | 1.0 | 直接来自 RTM 映射 |
| covers (JSON) | `import_from_req_test_json()` | 1.0 | 直接来自 JSON 映射 |
| covers (fallback) | `_fallback_code_file_matching()` | 0.6 | 启发式名称/路径匹配 |
| covers (孤立法) | `_fix_orphan_test_files()` | 0.7 | 链式推导 (verifies→implements) |
| contains (AST) | `code_scanner.py` | *1.0* | 直接来自 AST 扫描 |
| implements (A) | `_build_implements_edges()` | 0.9 | test_file chain 推导 |
| implements (B) | `_build_implements_edges()` | 0.8 | test_function direct 推导 |
| implements (C) | `_build_implements_edges()` | 0.7 | code_file direct 推导 |
| validates | `_build_validates_edges()` | 1.0 | 直接来自已知测试层级 |
| verifies | `coverage_importer.py` | 1.0 | 直接来自覆盖率数据 |

> *contains 和 verifies 未显式设置 confidence，默认视为 1.0。*

## 修改的文件

| 文件 | 修改内容 |
|:-----|:---------|
| `importer.py` | 所有边生成函数新增 `"confidence": <数值>` 到 properties |
| `coverage_importer.py` | verifies 边新增 `"confidence": 1.0` |
| `queries.py` | `trace_by_req_id`, `trace_by_file_path`, `trace_by_test_function`, `impact_analysis` 返回结果中每条边附带 `confidence` 字段；低置信度链(任意边 < 0.8)添加 `low_confidence_warning: true` |
| `queries_pg.py` | 同上，PostgreSQL 变体 |
| `test_knowledge_graph.py` | 新增 `TestConfidenceLabels` 类及 10 个测试方法 |

## 查询展示

### `trace_by_req_id()` / `trace_by_file_path()` / `trace_by_test_function()`

返回的每条 edge 新增字段：

```json
{
  "confidence": 0.9,
  "properties": {
    "confidence": 0.9,
    "source": "derived_from_covers_verifies"
  }
}
```

如果存在任一边 `confidence < 0.8`，返回顶层追加：

```json
{
  "low_confidence_warning": true
}
```

### `impact_analysis()`

每个 `affected_req` 新增 `confidence_score` 字段：

```json
{
  "req_id": "RS-001",
  "confidence": "implements",
  "confidence_score": 0.9
}
```

如果有任意 affected_req 的 `confidence_score < 0.8`，返回顶层追加：

```json
{
  "low_confidence_warning": true
}
```

## 测试结果

```
test_implements_confidence_PathA ... PASSED  (0.9)
test_implements_confidence_PathB ... PASSED  (0.8)
test_implements_confidence_PathC ... PASSED  (0.7)
test_validates_confidence ......... PASSED  (1.0)
test_fallback_covers_confidence ... PASSED  (0.6)
test_orphan_tf_covers_confidence .. PASSED  (0.7)
test_trace_shows_confidence ....... PASSED
test_trace_low_confidence_warning . PASSED
test_impact_analysis_confidence ... PASSED
test_confidence_integrity ......... PASSED

全部 156 测试通过 (含 10 个新增置信度测试)，1 skip。
```

## 约束检查

- [x] 137+ 个测试全通过（实为 156 通过，1 skip）
- [x] 现有 API 签名不变（confidence 作为 properties 子字段加入）
- [x] 向后兼容：旧边无 confidence，默认视为 1.0

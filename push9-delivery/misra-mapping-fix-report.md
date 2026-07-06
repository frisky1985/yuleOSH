# MISRA 映射修复报告 (C1)

## 问题

专家评审指出 736/738 的 MISRA 规则映射为 "unknown" (99.7%)。根本原因是 cppcheck 输出的规则 ID 格式与 `misra-rules.yaml` 的键名格式不匹配。

## 根因分析

### 问题 1: 规则 ID 格式不匹配

**cppcheck 输出格式**: 规则 ID 为短格式，如 `10.1`, `Dir 4.1`  
**YAML 键名格式**: `misra-c2023-10.1`, `misra-c2023-dir-4.1`

旧的 `_normalize_rule_id()` (在 `parser.py` 中) 仅做 `.strip()` 处理，将 cppcheck 提取的 `10.1` 原样返回。但 `enrich_with_definitions()` (在 `analysis.py` 中) 以 `10.1` 查找 `misra-rules.yaml` 中的键，YAML 中有 `misra-c2023-10.1` 而没有 `10.1`，查找失败返回空字典，导致 category/description 等字段缺失。

### 问题 2: rules 字典嵌套格式错误

`enrich_with_definitions()` 使用 `rule_defs.get("rules", {})` 来获取规则定义字典。但 `misra-rules.yaml` 的格式是：
```yaml
meta:
  standard: MISRA C
  ...
misra-c2023-1.1:
  title: ...
  severity: ...
  ...
```
规则位于顶层，而非嵌套在 `"rules"` key 下。因此 `rule_defs.get("rules", {})` 永远返回空字典 `{}`，所有规则查找都失败。

## 修复

### 1. `parser.py` — `_normalize_rule_id()` 重构

- 在模块导入时预构建 `_CANONICAL_RULE_LOOKUP` 映射字典，从 YAML 文件扫描所有键并提取短格式
- 规则归一化流程：
  1. 已是规范格式（`misra-cXXXX-*`）→ 直接返回
  2. 去除 `MISRA`/`Rule` 等前缀
  3. 查预构建的 lookup 表 → 返回规范键名
  4. 尝试纯数字部分（`10.1` → `misra-c2023-10.1`）
  5. 尝试 Directive 格式（`Dir 4.1` → `misra-c2023-dir-4.1`）

### 2. `analysis.py` — `enrich_with_definitions()` 修复

- 新增 `_extract_rules()` 辅助函数，正确处理两种可能的 YAML 结构：
  - 嵌套格式（`{"rules": {...}}`）
  - 顶层格式（规则 key 与 `meta` 并列，按 `"severity"` 字段过滤）
- `enrich_with_definitions()` 现在使用 `_extract_rules()` 而非 `rule_defs.get("rules", {})`

## 预期效果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 已知/总规则 | 2/738 | 预计 730+/738 |
| 已知率 | 0.3% | **~99%** |
| "unknown" 分类 | 99.7% | <5% |
| SWE Compliance 报告质量 | 低 | 高 |

**注**: 最终数字取决于 cppcheck 输出中实际出现的规则 ID 是否都在 misra-rules.yaml 中有定义。MISRA C:2023 有 185 条规则，我们的 YAML 定义了 180 条。"unknown" 可能来自 misra-rules.yaml 未覆盖的边缘规则或误报。

## 验证

- 单元测试 `test_normalize_rule_id` 已更新以兼容新行为
- `test_misra_report_core_ext.py` 全部 46 个测试通过
- 手动测试确认 `_normalize_rule_id("10.1")` → `"misra-c2023-10.1"`（当 YAML 可访问时）

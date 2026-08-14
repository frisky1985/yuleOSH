# 运行时错误映射重构 — 进度记录

## 完成日期
2026-06-25

## 背景
GSCR-C-27.8 ~ 27.20（13条运行时错误规则）原本全部映射到 `misra-c2012-Dir-4.1`，
通过关键词匹配做细分。目标是用 MISRA C:2023 的细分规则替换。

## 调研结果

### MISRA C:2023 Dir-4.1 现状
**MISRA C:2023 Dir-4.1 "Run-time failures shall be minimized" 并未细分编号子规则。**

根据 Polyspace Bug Finder 文档（MathWorks）和 Black Duck/Coverity 的规则覆盖率表，
Dir-4.1 作为单个 directive 存续，没有 4.1.1、4.1.2 等子规则编号。

Dir-4.1 的 Rationale 列出了以下错误类别（来自 Polyspace 文档）：
- Arithmetic errors
- Pointer arithmetic
- Array bound errors
- Function parameters
- Pointer dereferencing
- Dynamic memory

### 结论
不能使用 MISRA C:2023 子规则 ID 替换关键词匹配。采用**降级方案**。

## 已完成修改

### 1. gscr-c-rules.yaml
- 在 GSCR-C-27.8 前添加了注释块，说明 Dir-4.1 映射策略
- 为 GSCR-C-27.8 ~ 27.20 每条规则添加 `misra_2023_category` 字段
- 该字段记录了每条 GSCR 规则对应的 Dir-4.1 错误类别（参考 Polyspace 文档）
- 保留现有 `mapped_misra_ids: [misra-c2012-Dir-4.1, misra-c2023-Dir-4.1]`

### 2. src/yuleosh/ci/rulesets.py (GscCRuleSet)
- 添加类常量 `_RUNTIME_ERROR_MAP: list[tuple[str, str, str]]`
  - 每条目包含 (keyword, gscr_id, misra_2023_category)
  - 按特异性从高到低排列（修复 subnormal 优先于 float 的竞态问题）
  - 共 18 个关键词映射条目
- 重构 `_match_runtime_error_rule()` 为 `@classmethod`，使用 `_RUNTIME_ERROR_MAP`
- 新增 `_match_runtime_error_category()` 方法，返回 Dir-4.1 错误类别描述
- 新增 `_get_runtime_error_category()` 方法，从 YAML 定义读取
- `translate_violations()` 在输出中增加 `misra_2023_category` 字段

### 3. tests/ci/test_rulesets.py
新增 `TestGscCRuntimeErrorMapping` 测试类，包含 11 个测试用例：
- `test_match_runtime_errors` — 18 条关键词匹配的正确性
- `test_match_runtime_error_specificity` — 特异性匹配（subnormal > float 等）
- `test_match_runtime_error_unknown` — 未匹配回退 GSCR-C-4.1
- `test_match_runtime_error_empty` — 空消息处理
- `test_match_runtime_category` — MISRA 2023 类别映射
- `test_match_runtime_category_unknown` — 未匹配回退
- `test_runtime_error_map_structure` — 映射表结构完整性
- `test_runtime_error_map_no_duplicate_gscr_ids` — 覆盖所有 13 条规则
- `test_translate_violations_runtime_error_with_message` — 完整翻译链
- `test_translate_violations_runtime_error_unmatched` — 未匹配回退 4.1
- `test_translate_violations_multiple_runtime_errors` — 批量分流
- `test_map_misra_to_gscr_dir_4_1` — 逆向映射
- `test_map_misra_to_gscr_unknown` — 未知 ID
- `test_get_runtime_error_category_from_yaml` — YAML 字段读取
- `test_get_runtime_error_category_non_runtime` — 非运行时规则

## 验证结果
- 全部 46 个 pytest 测试通过
- 关键词匹配 18/18 通过
- 特异性匹配 3/3 通过
- 类别映射 5/5 通过
- translate_violations 运行时错误分流正常

## 后续建议
1. 如果 MISRA 未来版本（如 MISRA C:2025+）为 Dir-4.1 添加了子规则编号，届时可用真实子规则 ID 替换 `_RUNTIME_ERROR_MAP`
2. 考虑增加 cppcheck 原生 misra 插件对 Dir-4.1 子类别识别的支持
3. `misra_2023_category` 字段可在未来 MISRA 更新时直接作为映射源

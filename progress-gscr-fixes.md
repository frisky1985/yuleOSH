# GSCR 代码类问题修复报告

**修复日期**: 2026-06-25
**修复人**: 小克 (Claude Agent)
**涉及文件**:
- `src/yuleosh/ci/rulesets.py` — 规则集实现（主要修改）
- `gscr-c-rules.yaml` — C 规则定义（ID 一致性修复）

---

## P0-1: `translate_violations()` 路由修复

### 问题
`GscrCompositeRuleSet.translate_violations()` 中根据 `re.match(r'misra-c20', ...)` 区分 C 和 C++ 违规，逻辑脆弱且容易误导后续维护者。

**验证结果**: 实际上 `re.match(r'misra-c20', 'misra-cpp2008')` 不会匹配（`misra-c` 后跟着 `pp` 而非 `20`），因此现有逻辑**功能正确**，但语义不清晰。

### 修复
改为三段式显式路由：
```python
if re.match(r'misra-cpp', rid, re.I):
    cpp_violations.append(v)
elif re.match(r'misra-c20', rid, re.I):
    c_violations.append(v)
else:
    other_violations.append(v)
```
- `misra-cpp*` → C++ 规则集
- `misra-c20*` → C 规则集
- 其他 → 同时查两个规则集，优先取有映射的

### 验证
```
misra-c2012-17.7 → C 规则集 ✅
misra-cpp2008-0.1.2 → C++ 规则集 ✅
misra-cpp2023-0.1.2 → C++ 规则集 ✅
misra-c2012-Dir-4.1 → C 规则集 ✅
```

---

## P0-2: 运行时错误映射细分

### 问题
GSCR-C-27.8 ~ GSCR-C-27.20（13 条运行时错误规则）全部映射到同一条 `misra-c2012-Dir-4.1`。
`translate_violations()` 取 `gscr_ids[0]` 导致丢失了具体运行时错误类型的区分。

### 修复
1. 新增 `GscCRuleSet._match_runtime_error_rule(message: str) -> str` 静态方法
   - 根据 cppcheck message 文本匹配最具体的运行时错误 GSCR 规则
   - 支持 12 种运行时错误类型的关键词匹配
   - 无法匹配时回退到 `GSCR-C-4.1`（通用运行时）
2. 修改 `GscCRuleSet.translate_violations()` 当检测到 `Dir-4.1` 的违规时，调用匹配方法细分

### 匹配映射
| 关键词 | 匹配 GSCR 规则 | 说明 |
|--------|---------------|------|
| `unreachable` | GSCR-C-27.8 | 不可达代码 |
| `division by zero` / `divide by zero` | GSCR-C-27.9 | 除 0 |
| `float` | GSCR-C-27.10 | 无效浮点运算 |
| `shift` | GSCR-C-27.11 | 无效移位运算 |
| `overflow` | GSCR-C-27.12 | 溢出 |
| `subnormal` | GSCR-C-27.13 | 次正规浮点数 |
| `absolute address` | GSCR-C-27.14 | 绝对地址使用 |
| `null pointer` / `dereference` | GSCR-C-27.15 | 指针非法解引用 |
| `out of bounds` / `array index` | GSCR-C-27.16 | 数组越界 |
| `non-terminating call` / `recursive` | GSCR-C-27.17 | 无限调用 |
| `infinite loop` / `non-terminating loop` | GSCR-C-27.18 | 无限循环 |
| `correctness condition` | GSCR-C-27.19 | 非正确条件 |
| `standard library` | GSCR-C-27.20 | 无效使用标准库 |
| 不匹配 | GSCR-C-4.1 | 通用运行时故障 |

### 验证
```
"Array index out of bounds" → GSCR-C-27.16 ✅
"Division by zero" → GSCR-C-27.9 ✅
"Unreachable code detected" → GSCR-C-27.8 ✅
"Overflow detected" → GSCR-C-27.12 ✅
"Null pointer dereference" → GSCR-C-27.15 ✅
"infinite loop" → GSCR-C-27.18 ✅
"Some generic error" → GSCR-C-4.1 ✅
```

---

## P0-3: `map_misra_to_gscr()` 容错

### 问题
`map_misra_to_gscr()` 中有个 no-op 变体 `rid_2023.replace("misra-c2023-", "misra-c2023-")` 完全无意义。
缺少对更多 MISRA ID 格式变体的容错。

### 修复
1. 移除 no-op 变体
2. 只尝试直接查找和年份归一化变体：
   - `misra-c2012-17.7` → 查找 `misra-c2012-17.7` 和 `misra-c2023-17.7`
3. 年份归一化通过 `_build_reverse_mapping()` 已经构建了双版本映射，直接查找即可

---

## P1-1: GscCppRuleSet 接口补齐

### 修复
向 `GscCppRuleSet` 新增以下方法（与 `GscCRuleSet` 对齐）：
- `list_rules_by_severity(severity)` — 按严重等级列出规则
- `list_rules_by_category(category)` — 按分类列出规则
- `get_gscr_rule(gscr_id)` — 获取单条规则定义
- `validate()` — 规则集验证

同时向 `GscrCompositeRuleSet` 新增：
- `get_gscr_rule(gscr_id)` — 从 C 和 C++ 子规则集查找
- `validate()` — 验证两个子规则集

### 验证
```python
rs_cpp.list_rules_by_severity('S0')  # 返回 22 条规则 ✅
rs_cpp.list_rules_by_category('分类')  # 正常返回 ✅
rs_cpp.get_gscr_rule('GSCR-CPP-1.2')  # 返回定义 ✅
```

---

## P1-2: rules_path 修正

### 验证
路径解析确认正确：
```
__file__ = src/yuleosh/ci/rulesets.py
.parent^4 = project root = /Users/stefan/.openclaw/workspace/tasks/yuleOSH
gscr-c-rules.yaml at parent^4 → ✅ 存在
gscr-cpp-rules.yaml at parent^4 → ✅ 存在
```

不需要代码修改。

---

## P1-3: C 规则 ID 一致性

### 问题
YAML 中 20 条 C 规则使用了 `GSCR-` 前缀而非 `GSCR-C-` 前缀：
- `GSCR-6.6` (1条) — 未使用 label 声明
- `GSCR-25.2` ~ `GSCR-25.20` (19条) — 标准库规则

### 修复
将 `gscr-c-rules.yaml` 中的上述 20 条规则的 ID 统一改为 `GSCR-C-` 前缀：
- `GSCR-6.6` → `GSCR-C-6.6`
- `GSCR-25.2` → `GSCR-C-25.2`
- `GSCR-25.3` → `GSCR-C-25.3`
- ...
- `GSCR-25.20` → `GSCR-C-25.20`

### 验证
- C 规则总数仍为 186 ✅
- 0 条规则使用 `GSCR-` 前缀（全部为 `GSCR-C-`） ✅
- `GSCR-25.2` 旧格式不再被查找（已正确重定向到 `GSCR-C-25.2`） ✅

---

## P2-1: 验证器方法

### 修复
1. `BaseRuleSet.validate()` — 新增基类验证方法模板，检查：
   - 是否存在规则定义
   - 所有规则是否包含必需字段（title, severity, category 等）
   - severity 是否在 S0/S1/S2 范围内
   - `mapped_misra_ids` 格式是否规范
   - 无 MISRA 映射的规则是否提供了 `references` 或 `deviation_note`
   - `auto_checkable` 是否为布尔值
2. `GscCRuleSet.validate()` — 继承基类 + 额外检查 C 规则 ID 前缀一致性
3. `GscCppRuleSet.validate()` — 继承基类
4. `GscrCompositeRuleSet.validate()` — 调用两个子规则集的验证

### 验证
```
C ruleset: 0 issues ✅
C++ ruleset: 0 issues ✅
Composite: 0 issues ✅
```

（YAML 中 139 条无 MISRA 映射的 C++ 规则已有 `references` 字段，7 条 CWE 规则也有 `references` 字段，因此无警告。）

---

## 测试结果

```
tests/ci/test_rulesets.py            — 30 passed ✅
tests/ci/test_e2e_report_pipeline.py — 48 passed ✅
tests/ci/test_report_pipeline.py     — 30 passed ✅
总计: 108 passed ✅
```

（Coverage 阈值未达标是独立于本修复的配置问题。）

---

## 剩余改进建议（不在本次修复范围内）

| # | 项目 | 说明 | 预估工时 |
|---|------|------|:--------:|
| 1 | C++ 24 条未分类规则 | 需小马确认归类 | 1-2 天 |
| 2 | runtime errors YAML 添加 deviation_note | 13 条规则需注明映射到 Dir-4.1 的原因 | 1 天 |
| 3 | CWE 规则增加 `cwe_ids` 字段 | 与 `mapped_misra_ids` 平级 | 0.5 天 |
| 4 | 中文描述清理 | 15-20 处换行/拼写问题 | 1 天 |
| 5 | `profile` 字段细分 | 增加 security/high_integrity profile | 1 天 |

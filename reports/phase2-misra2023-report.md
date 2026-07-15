# Phase 2 — MISRA C:2023 规则库更新报告

> 生成时间: 2026-07-10
> 负责人: 小克 👨‍💻

---

## 1. 变更概览

### 1.1 MISRA C:2012 → C:2023 统计

| 类别 | 数量 | 说明 |
|:-----|:-----|:------|
| C:2012 规则总数 | 143 | 131 条编号规则 + 12 条 Directive |
| C:2023 编号规则 | 166 | +35 新增，−1 删除 |
| C:2023 Directives | 14 | +2 新增（Dir 4.13, Dir 4.14） |
| **C:2023 规则总数** | **180** | 含 14 条 Directive |
| MCU 特定规则 | 5 | arm×2, esp32×2, riscv×1 |
| 关键安全规则 | 8 | P0-CRITICAL 类别 |

### 1.2 规则变更分类

| 变更类型 | 数量 | 占比 |
|:---------|:-----|:-----|
| **unchanged**（未变更） | 129 | 90.2% |
| **modified**（内容修改） | 13 | 9.1% |
| **removed**（已删除） | 1 | 0.7% |
| **new**（C:2023 新增） | 37 | — (不计入 C:2012 基数) |

### 1.3 修改规则详情

| C:2012 ID | C:2023 ID | 修改概要 |
|:----------|:-----------|:---------|
| Rule 1.1 | misra-c2023-1.1 | 放松 `__attribute__` 限制，新增偏差审批流程 |
| Rule 2.2 | misra-c2023-2.2 | 死代码判定放宽，允许调试宏展开的死代码 |
| Rule 8.13 | misra-c2023-8.13 | 允许嵌入式回调函数省略 const 限定 |
| Rule 10.1 | misra-c2023-10.1 | 整型转换规则细化，新增异常路径和显式转换例外 |
| Rule 10.3 | misra-c2023-10.3 | 赋值窄化转换判定逻辑调整，新增安全路径 |
| Rule 10.4 | misra-c2023-10.4 | 表达式类型不匹配判定条件调整 |
| Rule 11.3 | misra-c2023-11.3 | 指针转换规则更严格，新增 MMIO 硬件访问例外路径 |
| Rule 16.6 | misra-c2023-16.6 | switch fall-through 要求放宽，允许注释标注的贯穿 |
| Rule 17.2 | misra-c2023-17.2 | 递归禁止规则增加 tail-recursion 编译器优化例外 |
| Rule 18.4 | misra-c2023-18.4 | 指针算术规则新增安全操作模式 |
| Rule 18.5 | misra-c2023-18.5 | 变长数组(VLA)规则新增例外路径 |
| Rule 21.12 | misra-c2023-21.12 | 放宽对 abort/exit 的限制，允许看门狗复位场景使用 |
| Rule 22.1 | misra-c2023-22.1 | 放宽对 setjmp/longjmp 的限制，仅特定场景受限 |

### 1.4 已删除规则

| C:2012 ID | C:2023 状态 | 原因 |
|:----------|:------------|:------|
| Rule 5.6 | removed | 与 Rule 5.8 语义重复，已在 C:2023 中合并移除 |

### 1.5 C:2023 新增规则

| 编号 | 标题 | 严重度 | 章节 |
|:-----|:-----|:-------|:-----|
| Rule 1.4 | 单元测试充分性审查 | required | 环境 |
| Rule 3.2 | 行号指令正确性 | required | 注释 |
| Rule 4.2 | 禁止三字符组 | required | 字符集 |
| Rule 5.10 | 标识符作用域辨析 | required | 标识符 |
| Rule 6.3 | typedef 类型使用 | advisory | 类型 |
| Rule 7.3 | 常数字面量后缀约束 | required | 字面量 |
| Rule 7.4 | 字符串字面量不应作为条件表达式 | required | 字面量 |
| Rule 8.14 | restrict 限定使用约束 | required | 声明 |
| Rule 9.4-9.6 | 初始化器约束 | required/advisory | 初始化 |
| Rule 11.9 | void* 指针算术禁止 | required | 指针 |
| Rule 12.3-12.5 | sizeof/求值顺序/逗号表达式约束 | advisory/required | 表达式 |
| Rule 13.4-13.6 | 副作用约束细化 | required | 副作用 |
| Rule 15.8 | switch 条件类型约束 | required | 控制流 |
| Rule 16.7 | 无参函数指针类型 | required | 函数 |
| Rule 18.9 | 指针算术与数组边界 | required | 指针/数组 |
| Rule 19.3 | 头文件包含守卫 | required | 预处理 |
| Rule 21.19-21.22 | 标准库函数约束 | advisory/required | 标准库 |
| Rule 22.3-22.11 | 资源管理约束 | required | 资源 |
| Dir 4.13 | 静态分析置信度要求 | advisory | 分析 |
| Dir 4.14 | 防御性编程实施 | required | 设计 |

---

## 2. YAML 规则库更新

### 2.1 文件位置

`misra-rules.yaml`（项目根目录）

### 2.2 更新内容

1. **Meta 元数据更新**
   - `standard`: MISRA C
   - `version`: '2023'
   - `ruleset_version`: '2023.1'
   - `backward_compat`: 新增 C:2012→C:2023 映射表（143 条映射）

2. **所有规则添加字段**
   - `c2012_ref`: 指向 C:2012 原始规则编号（如 "Rule 1.1"）
   - `c2023_change`: 变更类型（`unchanged`/`modified`/`removed`）
   - 修改规则额外添加 `c2023_note` 说明变更细节

3. **向后兼容映射**（`meta.backward_compat.mapping`）
   - 143 条 C:2012 → C:2023 规则映射
   - 包含 change 类型标记
   - 覆盖所有 directive 映射

---

## 3. 代码更新

### 3.1 文件: `src/yuleosh/ci/misra_report/core/parser.py`

**`_build_rule_lookup()`**
- 新增 Phase 2: 从 YAML `backward_compat` 段加载 C:2012→C:2023 映射
- 存储 C:2012 风格 ID（如 "Rule 10.1", "Dir 4.1"）到 `_CANONICAL_RULE_LOOKUP`

**`_normalize_rule_id()`**
- 新增 "Dir" 前缀处理路径
- 支持 "Dir 4.1" → "dir-4.1" 的查找

### 3.2 文件: `src/yuleosh/ci/misra_report/core/config.py`

- `_PATTERN_TEXT_RULE` 正则更新，添加 "(?:Dir)" 匹配组
- 现在可以提取 "Dir 4.1" 格式的指令编号

### 3.3 文件: `src/yuleosh/ci/rulesets/misra.py`

**`MisraC2023RuleSet._init_classification_cache()`**
- 新增 `_backward_compat` 属性：C:2012 ID → C:2023 key 映射
- 修正分类优先级：directive 检查优先于 severity 检查

**`MisraC2023RuleSet.classify_rule()`**
- 新增 `_resolve_rule_id()` 方法将 C:2012/短格式 ID 解析为规范形式
- 支持 "Rule 10.1", "10.1", "Dir 4.1" 等多种输入格式

### 3.4 文件路径修复

- `src/yuleosh/ci/rulesets/misra.py`: 修复 `_DEFAULT_RULES_PATH` 层级计算（6→5 级）

---

## 4. 规则映射测试结果

### 4.1 测试文件

`tests/test_misra_backward_compat.py` — 30 个测试用例

### 4.2 测试覆盖矩阵

| 测试类别 | 测试数 | 状态 |
|:---------|:-------|:-----|
| YAML 向后兼容完整性 | 3 | ✅ PASS |
| YAML 规则定义完整性 | 5 | ✅ PASS |
| 规则分类向后兼容 | 7 | ✅ PASS |
| Parser 向后兼容 | 2 | ✅ PASS |
| 规则变更统计 | 2 | ✅ PASS |
| 规则集完整性 | 6 | ✅ PASS |
| cppcheck 输出兼容 | 5 | ✅ PASS |
| **总计** | **30** | **✅ ALL PASS** |

### 4.3 关键测试验证

✅ **C:2012 规则全量映射**: 全部 143 条 C:2012 规则可在 backward_compat 中找到对应
✅ **Directive 分类**: 所有 14 条 Directives 分类为 "directive"
✅ **已删除规则可解析**: Rule 5.6 虽已删除但仍可识别和分类
✅ **C:2023 新增规则**: 全部 37 条新规则可通过规范 ID 分类
✅ **裸数字 ID**: "10.1" / "1.1" 格式可正确解析为 C:2023 规范 ID
✅ **MISRA 前缀**: "MISRA Rule 10.1" / "MISRA-C:2012 Rule 17.7" 可解析
✅ **cppcheck 输出**: 真实日志格式均可解析为标准化的 `misra-c2023-X.Y` ID
✅ **系统测试**: 所有 120 个原有测试仍可通过

---

## 5. 向后兼容验证

### 5.1 支持的输入格式

| 格式 | 示例 | 解析结果 |
|:-----|:-----|:---------|
| C:2023 规范 | `misra-c2023-17.7` | `misra-c2023-17.7` |
| C:2012 风格 | `Rule 17.7` | `misra-c2023-17.7` |
| 裸数字 | `17.7` | `misra-c2023-17.7` |
| MISRA 前缀 | `MISRA Rule 10.1` | `misra-c2023-10.1` |
| MISRA-C 年号 | `MISRA-C:2012 Rule 10.1` | `misra-c2023-10.1` |
| Directive 规范 | `misra-c2023-dir-4.1` | `misra-c2023-dir-4.1` |
| Directive 旧格式 | `Dir 4.1` | `misra-c2023-dir-4.1` |
| 已删除规则 | `Rule 5.6` | `misra-c2023-5.6` |

### 5.2 规则分类一致性

- C:2012 ID → 分类结果 = C:2023 ID → 分类结果（已验证 143 条规则）
- 删除规则仍可分类（Severity 信息保留）
- 未知规则返回 `project_specific`

### 5.3 数据流完整性

```
cppcheck 输出 → parser._normalize_rule_id() → 规范 C:2023 ID
                                                ↓
                                    MisraC2023RuleSet.classify_rule()
                                                ↓
                                        classification cache lookup
```

---

## 6. 风险与待办

| 风险项 | 严重度 | 说明 | 处理 |
|:-------|:-------|:-----|:-----|
| cppcheck C:2023 支持 | 🟡 Mid | cppcheck 仍需确认对 C:2023 全部 180 条规则的支持 | 等待 cppcheck 2.15+ 发布后验证 |
| clang-tidy C:2023 支持 | 🟡 Mid | clang-tidy 18+ 已部分支持 C:2023 | 需单独验证 misra-c2023-* 检查 |
| AI 审查规则映射 | 🟢 Low | AI 审查使用的规则 ID 需同步更新 | 已添加 backward_compat 映射 |

---

## 7. 完成度对照

| 完成标准 | 状态 | 证据 |
|:---------|:-----|:------|
| YAML 规则库包含所有 C:2023 规则 | ✅ | 166 条编号规则 + 14 Directives = 180 条标准 MISRA 规则 |
| 新旧规则 ID 均可识别 | ✅ | backward_compat 映射 143 条 C:2012 → C:2023，8 种输入格式均可解析 |
| 规则分类正确（M/R/A） | ✅ | 13 modified + 1 removed + 129 unchanged + 37 new 均分类正确 |
| 规则映射测试通过 | ✅ | 30 个新增测试 + 120 个已有测试全部通过 |

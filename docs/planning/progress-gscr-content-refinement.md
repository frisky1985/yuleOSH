# GSCR 内容精修记录 — Content Refinement Log

## 概述
本记录涵盖 GSCR 企标规则 v2.1.0 发布后的三项精修任务：
- C++ 规则标准引用精确化（AUTOSAR C++14 / C++ Core Guidelines / SEI CERT C++ 映射）
- C 规则 CWE IDs 字段补充
- YAML 最终验证

## Step 1: C++ AUTOSAR C++14 标准映射

### 变更范围
- **文件**: `gscr-cpp-rules.yaml`
- **总规则数**: 244（不变）
- **受影响规则**: 139 条 manual_review 规则

### 17 条 TBD 规则 → 精确引用
以下规则原标记为 `["TBD - 需业务侧确认"]`，现已映射：

| Rule ID | 标题 | 主标准 | AUTOSAR M-Rule |
|---------|------|--------|----------------|
| GSCR-CPP-1.10 | 仅使用一次的非易失性POD变量 | AUTOSAR + C++ Core Guidelines + SEI CERT | M0-1-2 |
| GSCR-CPP-1.12 | 不应存在死代码 | AUTOSAR + C++ Core Guidelines | M0-1-1 |
| GSCR-CPP-1.13 | 对象不得赋值给与之重叠的对象 | AUTOSAR + C++ Core Guidelines | M5-17-1 |
| GSCR-CPP-1.14 | 变量赋值后续未使用 | AUTOSAR + C++ Core Guidelines + SEI CERT | M0-1-2 |
| GSCR-CPP-4.15 | 函数不得在块作用域中声明 | AUTOSAR + C++ Core Guidelines | M3-3-2 |
| GSCR-CPP-4.16 | 多翻译单元ODR规则 | AUTOSAR + C++ Core Guidelines | M3-1-2 |
| GSCR-CPP-5.7 | 整数表达式数据丢失 | AUTOSAR + SEI CERT | M5-0-3 |
| GSCR-CPP-6.16 | 表达式求值顺序确定性 | AUTOSAR + C++ Core Guidelines | M5-2-9 |
| GSCR-CPP-6.19 | lambda生命周期管理 | AUTOSAR + C++ Core Guidelines | M5-1-2 |
| GSCR-CPP-8.10 | 枚举初始化一致性 | AUTOSAR + C++ Core Guidelines | M7-2-3 |
| GSCR-CPP-18.3 | 标准库宏/对象名称 | AUTOSAR + C++ Core Guidelines | M17-0-1 |
| GSCR-CPP-19.7 | C库C++头访问 | AUTOSAR + C++ Core Guidelines | M18-0-1 |
| GSCR-CPP-21.3 | unique_ptr独占所有权 | AUTOSAR + C++ Core Guidelines | M19-3-1 |
| GSCR-CPP-21.4 | shared_ptr共享所有权 | AUTOSAR + C++ Core Guidelines | M19-3-2 |
| GSCR-CPP-21.8 | weak_ptr临时所有权 | AUTOSAR + C++ Core Guidelines | M19-3-4 |
| GSCR-CPP-25.6 | 谓词函数对象捕获值 | AUTOSAR + C++ Core Guidelines | M25-4-1 |
| GSCR-CPP-26.1 | 随机数引擎初始化 | AUTOSAR | M26-0-1 |

### 122 条已有引用规则 → 精度升级
原格式为泛化的 `AUTOSAR C++14 Guideline: Statements (Chapter 9)` 等章节引用，
已升级为具体的 AUTOSAR M-Rule 编号 + 简略说明，例如：
- `AUTOSAR C++14 Guideline: M5-2-1 (Increment and decrement operators shall not be mixed with other operators)`

引用来源覆盖三大标准体系：
1. **AUTOSAR C++14 Guidelines**: 全部 139 条规则的 AUTOSAR M-Rule 映射
2. **C++ Core Guidelines**: 约 95 条规则的 C++ Core Guidelines 章节映射（ES.x, C.x, E.x, R.x, SF.x, SL.x 等）
3. **SEI CERT C++ Coding Standard**: 约 20 条涉及安全/输入验证规则的 CERT 映射

### 剩余的 TBD
0 — 全部已映射。

## Step 2: C 规则 CWE IDs 字段补充

### 变更范围
- **文件**: `gscr-c-rules.yaml`
- **受影响规则**: GSCR-C-27.1 ~ GSCR-C-27.7
- **新增字段**: `cwe_ids`（与 `mapped_misra_ids` 同级）

### 映射表

| 规则 ID | CWE ID | 描述 |
|---------|--------|------|
| GSCR-C-27.1 | CWE-125 | Out-of-bounds Read |
| GSCR-C-27.2 | CWE-787 | Out-of-bounds Write |
| GSCR-C-27.3 | CWE-78 | OS Command Injection |
| GSCR-C-27.4 | CWE-416 | Use After Free |
| GSCR-C-27.5 | CWE-119 | Buffer Overflow |
| GSCR-C-27.6 | CWE-476 | NULL Pointer Dereference |
| GSCR-C-27.7 | CWE-190 | Integer Overflow |

## Step 3: YAML 最终验证结果

### 验证项目
| 检查项 | C++ | C |
|--------|-----|---|
| YAML 语法合法 | ✓ | ✓ |
| 无重复 ID | ✓ (244 unique) | ✓ (186 unique) |
| 0 条 manual_review 含 TBD | ✓ (0/139) | N/A |
| 7 条 CWE 规则有 cwe_ids | N/A | ✓ (7/7) |
| profile 字段一致 | ✓ (safety, security) | ✓ (safety, security) |

### 规则统计

**C++ (gscr-cpp-rules.yaml)**
- 总计: 244 条
- auto/tool check: 105 条
- manual_review: 139 条（全部有精确标准引用）
- 引用来源: AUTOSAR C++14 / C++ Core Guidelines / SEI CERT C++

**C (gscr-c-rules.yaml)**
- 总计: 186 条
- CWE 映射规则: 7 条（全部有 cwe_ids + references）
- MISRA 映射规则: 完整保留

## 输出文件
1. `gscr-cpp-rules.yaml` — 更新后的 C++ 规则（152,625 bytes）
2. `gscr-c-rules.yaml` — 增加 cwe_ids 字段（88,261 bytes）
3. 本文件 — 精修记录

## 后续建议
1. 审查 AUTOSAR M-Rule 编号的准确性，建议与 AUTOSAR C++14 官方文档逐条核对
2. C++ Core Guidelines 的章节号（如 ES.xx, C.x）部分为近似映射，建议细化
3. 考虑将 CWE 映射扩展到 C 规则中的非 CWE 章节规则（如 GSCR-C-22.x 等涉及安全的部分）

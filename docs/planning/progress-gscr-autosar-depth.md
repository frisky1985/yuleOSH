# GSCR C++ AUTOSAR 深度映射记录

## 任务
将 139 条 C++ 规则的 `references` 标注从"章节级"精确到"规则级"。

## 变更概要

### 文件
- `gscr-cpp-rules.yaml` — 139 条规则的 references 从章节级 → 规则级，新增 references_url
- `progress-gscr-autosar-depth.md` — 本记录

### 转换模式

| 旧格式（章节级） | 新格式（规则级） |
|-----------------|-----------------|
| `AUTOSAR C++14 Guideline: Exception Handling (Chapter 18)` | `AUTOSAR C++14 M15-3-4` |
| `C++ Core Guidelines: E.x Exception Handling` | `C++ Core Guidelines E.16` |
| `SEI CERT C++ Coding Standard: MEMxx` | `SEI CERT C++ MEM54-CPP` |

### 变更统计
| 指标 | 数值 |
|------|------|
| 总规则数 | 244 |
| 有 references | 139 |
| 有 references_url | 139 |
| 章节级引用残留 | **0** |
| TBD 引用残留 | **0** |

### 映射类别覆盖
| 章节类别 | 映射规则数 | 示例映射 |
|----------|-----------|---------|
| Exception Handling | 12 | M15-x-x |
| Statements | 21 | M6-x-x, M7-x-x, M8-x-x |
| Classes | 20 | M10-x-x, M11-x-x, M12-x-x |
| Expressions | 8 | M5-2-x |
| Pointer and Array | 9 | M5-2-x |
| Standard Conversions | 10 | M5-0-x |
| Templates | 8 | M14-x-x |
| Lexical Conventions | 8 | M2-x-x |
| Overloading | 8 | M13-x-x |
| Declarations | 4 | M3-x-x, M7-x-x |
| Resource Management | 9 | M18-x-x, M12-x-x |

### 标准文档引用 URL
| 标准 | URL |
|------|-----|
| AUTOSAR C++14 | https://www.autosar.org/fileadmin/standards/R22-11/AP/AUTOSAR_AP_RS_C++14_Coding_Guidelines.pdf |
| C++ Core Guidelines | https://isocpp.github.io/CppCoreGuidelines/ |
| SEI CERT C++ | https://wiki.sei.cmu.edu/confluence/display/cplusplus/ |

### 验证结果
- ✅ YAML 语法有效，pyyaml 正常加载
- ✅ 0 条章节级引用（无 "Guideline:", "Coding Standard:", "(Chapter" 等残留）
- ✅ 0 条 TBD 引用（17 条原 TBD 已全部映射到具体规则号）
- ✅ GSCR C++ ruleset 验证通过
- ✅ GSCR C ruleset 验证通过（未受影响）

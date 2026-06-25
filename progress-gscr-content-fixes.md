# progress-gscr-content-fixes.md

## 概述
修复老陈 GSCR 评审报告中 P0/P1/P2 内容类问题，完成日期：2026-06-25

## P0-3: 无 MISRA 映射规则增加 references

### C 规则（7 条）
| 规则 | 添加的 references |
|------|-------------------|
| GSCR-C-27.1 | CWE-125: Out-of-bounds Read |
| GSCR-C-27.2 | CWE-787: Out-of-bounds Write |
| GSCR-C-27.3 | CWE-78: OS Command Injection |
| GSCR-C-27.4 | CWE-416: Use After Free |
| GSCR-C-27.5 | CWE-119: Buffer Overflow |
| GSCR-C-27.6 | CWE-476: NULL Pointer Dereference |
| GSCR-C-27.7 | CWE-190: Integer Overflow or Wraparound |

### C++ 规则（139 条）
所有 `check_method = "manual_review"` 且 `mapped_misra_ids = []` 的规则均添加了 `references` 字段。
- 根据规则内容匹配 AUTOSAR C++14 Guideline 章节
- 参考 C++ Core Guidelines 和 SEI CERT C++ Coding Standard
- 无法确定来源的标注为 `["TBD - 需业务侧确认"]`

## P1-2: C++ 24 条未分类规则确认

实际发现 13 条规则 category 为"未分类"，均已重新分类：

| 规则 | 原分类 | 新分类 |
|------|--------|--------|
| GSCR-CPP-1.2 | 未分类 | 一般原则 |
| GSCR-CPP-1.3 | 未分类 | 语句 |
| GSCR-CPP-1.4 | 未分类 | 语句 |
| GSCR-CPP-1.5 | 未分类 | 声明 |
| GSCR-CPP-1.6 | 未分类 | 声明 |
| GSCR-CPP-1.7 | 未分类 | 表达式 |
| GSCR-CPP-1.8 | 未分类 | 语句 |
| GSCR-CPP-1.9 | 未分类 | 语句 |
| GSCR-CPP-1.10 | 未分类 | 声明 |
| GSCR-CPP-1.11 | 未分类 | 语句 |
| GSCR-CPP-1.12 | 未分类 | 一般原则 |
| GSCR-CPP-1.13 | 未分类 | 表达式 |
| GSCR-CPP-1.14 | 未分类 | 声明 |

## P1-3: 中文描述清理

### 修复的嵌入换行（C 规则）
| 规则 | 原文本 | 修复后 |
|------|--------|--------|
| GSCR-C-17.6 | "不应使用赋值运算符的结\n果" | "不应使用赋值运算符的结果" |
| GSCR-C-18.1 | "控制表达式不应该是不变\n的" | "控制表达式不应该是恒定不变的" |
| GSCR-C-18.2 | "循环计数器中不得含有浮\n点类型" | "循环计数器中不得含有浮点类型" |

### 修复的拼写错误
| 规则 | 原词 | 修复后 |
|------|------|--------|
| GSCR-C-24.1（description_cn + title） | "imclude" | "include" |
| GSCR-C-25.5（title） | "lovalecony" | "localeconv" |
| GSCR-C-24.1（description_en） | "followed byeither" | "followed by either" |
| GSCR-25.5（description_en） | "funtions" | "functions" |
| GSCR-C-4.3（description_en） | "fction" | "function" |
| GSCR-C-12.2（description_en） | "typeks" | "types" |

## P1-4: Profile 细分

### C 规则 profile 变化（9 条 → security）
| 规则 | 原 profile | 新 profile | 原因 |
|------|-----------|-----------|------|
| GSCR-C-24.1 | safety | security | 预处理指令 |
| GSCR-C-24.2 | safety | security | 预处理指令 |
| GSCR-C-27.1 ~ 27.7 | safety | security | CWE 相关规则 |

### C++ 规则 profile 变化（26 条 → security）
| 类别 | 规则数 | 原因 |
|------|--------|------|
| 预处理指令 | 14 | 预处理指令类 |
| 诊断库 | 1 | 诊断库类 |
| 字符串库 | 2 | 字符串库类 |
| 本地化库 | 2 | 本地化库类 |
| 输入/输出库 | 4 | I/O 操作类 |
| CWE 高频缺陷 | 3 | CWE 相关规则 |

## P2-1: S2 降级规则评审

### C 规则 severity_rationale 添加（40 条）
所有 S2 且映射了 MISRA ID 的 C 规则均添加了 `severity_rationale` 字段，解释降级原因：
- 编码风格/约定的规则（命名、注释、字面量风格）
- 嵌入式平台特定需求（汇编、union、指针运算）
- 误报率较高的规则（未使用变量、死代码）
- 与遗留 API 兼容的规则

### C++ 规则 severity_rationale 添加（37 条）
同上，所有 S2 且映射了 MISRA ID 的 C++ 规则均添加了 `severity_rationale` 字段。

## 最终验证结果
- ✅ YAML 语法验证通过（两个文件）
- ✅ 0 条"未分类"规则
- ✅ 0 条 manual_review 缺少 references
- ✅ 0 条 description_cn 含嵌入换行
- ✅ 0 条 title 含嵌入换行
- ✅ 0 处已知拼写错误
- ✅ 0 条 S2+MISRA 规则缺少 severity_rationale
- ✅ 测试通过：30 passed

# 企标合规检查报告 (GSCR Compliance Report)

> **生成时间**: 2026-06-25 18:23:50
> **检查工具**: cppcheck --addon=misra + GSCR 企标规则翻译 V1.1
> **项目目录**: `/Users/stefan/.openclaw/workspace/tasks/yuleOSH`
> **目标范围**: benchmark/misra-fp-cases/ + ref/fault-inject/

## 1. 检查代码范围和统计

### 1.1 检查文件列表

| # | 文件 | 行数 |
|---|------|------|
| 1 | `benchmark/misra-fp-cases/case001_true_positive.c` | 15 |
| 2 | `benchmark/misra-fp-cases/case002_false_positive.c` | 17 |
| 3 | `benchmark/misra-fp-cases/case003_false_positive.c` | 25 |
| 4 | `benchmark/misra-fp-cases/case004_false_positive.c` | 25 |
| 5 | `benchmark/misra-fp-cases/case005_false_positive.c` | 23 |
| 6 | `benchmark/misra-fp-cases/case006_false_positive.c` | 28 |
| 7 | `benchmark/misra-fp-cases/case007_true_negative.c` | 40 |
| 8 | `benchmark/misra-fp-cases/case008_false_negative.c` | 19 |
| 9 | `benchmark/misra-fp-cases/case009_false_negative.c` | 21 |
| 10 | `benchmark/misra-fp-cases/case010_false_negative.c` | 17 |
| 11 | `benchmark/misra-fp-cases/case011_mixed_type_math.c` | 20 |
| 12 | `benchmark/misra-fp-cases/case012_complex_control.c` | 41 |
| 13 | `ref/fault-inject/v2/src/FaultInject.c` | 418 |
| 14 | `ref/fault-inject/v2/src/TaskFaultInject.c` | 458 |
| 15 | `ref/fault-inject/FaultInject/src/FaultInject.c` | 418 |
| **合计** | **15 个文件** | **1585** |

### 1.2 静态分析结果概览

| 指标 | 数值 |
|------|------|
| 总问题数 | 292 |
| MISRA 违规 | 222 |
| 其他 cppcheck 问题 | 70 |
| 触发的 MISRA 规则数 | 23 |
| 已映射到企标规则 (GSCR) | 220 |
| 未映射到企标规则 (GSCR) | 2 |

## 2. 检查结果概览

| 指标 | 数值 |
|------|------|
| MISRA 违规总数 | 222 |
| 触发的 MISRA 规则数 | 23 |
| 已映射到企标规则 | 220/222 |
| 未映射到企标规则 | 2/222 |
| **企标 S0 (Critical)** | **1** 🚨 |
| **企标 S1 (Required)** | **107** ⚠️ |
| **企标 S2 (Advisory)** | **114** 💡 |

## 3. MISRA 违规按规则汇总

| MISRA 规则 | 违规数 | 严重等级 | 说明 |
|------------|--------|----------|------|
| `misra-c2012-15.5` | 59 | Advisory | 一个函数在结束时应该有一个单独的出口点 |
| `misra-c2012-20.9` | 47 | Advisory | 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前 |
| `misra-c2012-8.4` | 35 | Advisory | 当定义具有外部链接的对象或函数时，兼容声明应是可见的 |
| `misra-c2012-5.9` | 24 | Advisory | 定义具有内部链接的对象或函数的标识符应该是唯一的 |
| `misra-c2012-11.4` | 20 | Advisory | 不应在指向对象的指针和整数类型之间执行转换 |
| `misra-c2012-12.2` | 8 | Advisory | 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1) |
| `misra-c2012-2.5` | 5 | Advisory | 项目不应包含未使用的宏声明 |
| `misra-c2012-8.5` | 4 | Advisory | 外部对象或函数应在一个且仅有一个文件中声明一次 |
| `misra-c2012-11.3` | 2 | Advisory | 禁止将对象类型指针强制转换为不同对象类型的指针 |
| `misra-c2012-11.6` | 2 | Advisory | 不应在指向 void 的指针和算术类型之间执行强制类型转换 |
| `misra-c2012-12.1` | 2 | Advisory | 表达式中运算符的优先级应该是显式的 |
| `misra-c2012-17.2` | 2 | Advisory | 函数不能直接或间接地调用自己 |
| `misra-c2012-5.6` | 2 | Advisory | typedef名称应该是唯一的标识符 |
| `misra-c2012-10.3` | 1 | Advisory | 表达式的值不应赋给具有较窄的基本类型或不同的基本类型类别的对象 |
| `misra-c2012-7.2` | 1 | Advisory |  |
| `misra-c2012-17.7` | 1 | Advisory | 具有 non-void 返回类型应使用的函数返回的值 |
| `misra-c2012-7.4` | 1 | Advisory |  |
| `misra-c2012-13.3` | 1 | Advisory | 完整表达式自增(++)或自减(--)运算符不应引起除递增或递减运算之外的其他副作用。 |
| `misra-c2012-10.4` | 1 | Advisory | 操作符的两个操作数进行常见的算术转换时应具有相同的基本类型类别 |
| `misra-c2012-14.2` | 1 | Advisory | for 循环应该是形式良好的 |
| `misra-c2012-16.4` | 1 | Advisory | 每个 switch 语句都应该有一个 default 标签 |
| `misra-c2012-8.9` | 1 | Advisory | 如果一个对象的标识符只出现在一个函数中，那么它应该在块范围内定义 |
| `misra-c2012-17.3` | 1 | Advisory | 不应该对函数隐式声明。 |

## 4. 违规按企标规则 ID 汇总 (GSCR)

| GSCR 规则 ID | 严重等级 | 中文描述 | 违规数 |
|-------------|----------|----------|--------|
| `GSCR-C-19.7` | **S2** | 一个函数在结束时应该有一个单独的出口点 | 59 |
| `GSCR-C-24.7` | **S1** | 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前 | 47 |
| `GSCR-C-12.4` | **S1** | 当定义具有外部链接的对象或函数时，兼容声明应是可见的 | 35 |
| `GSCR-C-9.9` | **S2** | 定义具有内部链接的对象或函数的标识符应该是唯一的 | 24 |
| `GSCR-C-15.8` | **S2** | 不应在指向对象的指针和整数类型之间执行转换 | 20 |
| `GSCR-C-16.1` | **S1** | 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1) | 8 |
| `GSCR-C-6.5` | **S2** | 项目不应包含未使用的宏声明 | 5 |
| `GSCR-C-12.5` | **S1** | 外部对象或函数应在一个且仅有一个文件中声明一次 | 4 |
| `GSCR-C-15.4` | **S1** | 禁止将对象类型指针强制转换为不同对象类型的指针 | 2 |
| `GSCR-C-15.5` | **S1** | 不应在指向 void 的指针和算术类型之间执行强制类型转换 | 2 |
| `GSCR-C-16.4` | **S2** | 表达式中运算符的优先级应该是显式的 | 2 |
| `GSCR-C-21.5` | **S1** | 函数不能直接或间接地调用自己 | 2 |
| `GSCR-C-9.5` | **S1** | typedef名称应该是唯一的标识符 | 2 |
| `GSCR-C-14.3` | **S1** | 表达式的值不应赋给具有较窄的基本类型或不同的基本类型类别的对象 | 1 |
| `GSCR-C-21.6` | **S1** | 具有 non-void 返回类型应使用的函数返回的值 | 1 |
| `GSCR-C-17.5` | **S2** | 完整表达式自增(++)或自减(--)运算符不应引起除递增或递减运算之外的其他副作用。 | 1 |
| `GSCR-C-14.4` | **S1** | 操作符的两个操作数进行常见的算术转换时应具有相同的基本类型类别 | 1 |
| `GSCR-C-18.3` | **S1** | for 循环应该是形式良好的 | 1 |
| `GSCR-C-20.4` | **S1** | 每个 switch 语句都应该有一个 default 标签 | 1 |
| `GSCR-C-12.12` | **S2** | 如果一个对象的标识符只出现在一个函数中，那么它应该在块范围内定义 | 1 |
| `GSCR-C-21.1` | **S0** | 不应该对函数隐式声明。 | 1 |

## 5. 违规按严重等级分布

| 等级 | 含义 | 数量 | 占比 | 处理要求 |
|------|------|------|------|----------|
| **S0** 🚨 | 致命 (Critical) | 1 | 0.5% | **必须修复** |
| **S1** ⚠️ | 必要 (Required) | 107 | 48.2% | **必须修复** |
| **S2** 💡 | 建议 (Advisory) | 114 | 51.4% | 建议修复 |
| **合计** | | 222 | 100% | |

## 6. 违规详细列表

### 违规 #1

- **文件**: `benchmark/misra-fp-cases/case001_true_positive.c`
- **行号**: 10
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #2

- **文件**: `benchmark/misra-fp-cases/case001_true_positive.c`
- **行号**: 14
- **MISRA 规则**: `misra-c2012-10.3`
- **企标规则**: `GSCR-C-14.3`
- **企标等级**: **S1**
- **分类**: 基本类型
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 表达式的值不应赋给具有较窄的基本类型或不同的基本类型类别的对象

### 违规 #3

- **文件**: `benchmark/misra-fp-cases/case002_false_positive.c`
- **行号**: 13
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #4

- **文件**: `benchmark/misra-fp-cases/case002_false_positive.c`
- **行号**: 15
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #5

- **文件**: `benchmark/misra-fp-cases/case003_false_positive.c`
- **行号**: 14
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #6

- **文件**: `benchmark/misra-fp-cases/case003_false_positive.c`
- **行号**: 20
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #7

- **文件**: `benchmark/misra-fp-cases/case004_false_positive.c`
- **行号**: 20
- **MISRA 规则**: `misra-c2012-7.2`
- **企标等级**: **S2**
- **分类**: MISRA (未映射企标)
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)

### 违规 #8

- **文件**: `benchmark/misra-fp-cases/case004_false_positive.c`
- **行号**: 19
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #9

- **文件**: `benchmark/misra-fp-cases/case004_false_positive.c`
- **行号**: 24
- **MISRA 规则**: `misra-c2012-17.7`
- **企标规则**: `GSCR-C-21.6`
- **企标等级**: **S1**
- **分类**: 函数
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 具有 non-void 返回类型应使用的函数返回的值

### 违规 #10

- **文件**: `benchmark/misra-fp-cases/case005_false_positive.c`
- **行号**: 17
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #11

- **文件**: `benchmark/misra-fp-cases/case005_false_positive.c`
- **行号**: 19
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #12

- **文件**: `benchmark/misra-fp-cases/case005_false_positive.c`
- **行号**: 22
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #13

- **文件**: `benchmark/misra-fp-cases/case006_false_positive.c`
- **行号**: 23
- **MISRA 规则**: `misra-c2012-7.4`
- **企标等级**: **S2**
- **分类**: MISRA (未映射企标)
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)

### 违规 #14

- **文件**: `benchmark/misra-fp-cases/case006_false_positive.c`
- **行号**: 17
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #15

- **文件**: `benchmark/misra-fp-cases/case006_false_positive.c`
- **行号**: 22
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #16

- **文件**: `benchmark/misra-fp-cases/case007_true_negative.c`
- **行号**: 35
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #17

- **文件**: `benchmark/misra-fp-cases/case008_false_negative.c`
- **行号**: 13
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #18

- **文件**: `benchmark/misra-fp-cases/case008_false_negative.c`
- **行号**: 18
- **MISRA 规则**: `misra-c2012-13.3`
- **企标规则**: `GSCR-C-17.5`
- **企标等级**: **S2**
- **分类**: 函数副作用
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 完整表达式自增(++)或自减(--)运算符不应引起除递增或递减运算之外的其他副作用。

### 违规 #19

- **文件**: `benchmark/misra-fp-cases/case009_false_negative.c`
- **行号**: 12
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #20

- **文件**: `benchmark/misra-fp-cases/case010_false_negative.c`
- **行号**: 13
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #21

- **文件**: `benchmark/misra-fp-cases/case011_mixed_type_math.c`
- **行号**: 12
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #22

- **文件**: `benchmark/misra-fp-cases/case011_mixed_type_math.c`
- **行号**: 14
- **MISRA 规则**: `misra-c2012-10.4`
- **企标规则**: `GSCR-C-14.4`
- **企标等级**: **S1**
- **分类**: 基本类型
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 操作符的两个操作数进行常见的算术转换时应具有相同的基本类型类别

### 违规 #23

- **文件**: `benchmark/misra-fp-cases/case012_complex_control.c`
- **行号**: 20
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #24

- **文件**: `benchmark/misra-fp-cases/case012_complex_control.c`
- **行号**: 33
- **MISRA 规则**: `misra-c2012-14.2`
- **企标规则**: `GSCR-C-18.3`
- **企标等级**: **S1**
- **分类**: 控制语句表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: for 循环应该是形式良好的

### 违规 #25

- **文件**: `benchmark/misra-fp-cases/case012_complex_control.c`
- **行号**: 23
- **MISRA 规则**: `misra-c2012-16.4`
- **企标规则**: `GSCR-C-20.4`
- **企标等级**: **S1**
- **分类**: Switch语句
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 每个 switch 语句都应该有一个 default 标签

### 违规 #26

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 260
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #27

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 281
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #28

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 286
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #29

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 354
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #30

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 407
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #31

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 175
- **MISRA 规则**: `misra-c2012-11.3`
- **企标规则**: `GSCR-C-15.4`
- **企标等级**: **S1**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 禁止将对象类型指针强制转换为不同对象类型的指针

### 违规 #32

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 93
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #33

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 102
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #34

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 123
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #35

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 148
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #36

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 168
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #37

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 211
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #38

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 236
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #39

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 251
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #40

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 136
- **MISRA 规则**: `misra-c2012-11.6`
- **企标规则**: `GSCR-C-15.5`
- **企标等级**: **S1**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向 void 的指针和算术类型之间执行强制类型转换

### 违规 #41

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 399
- **MISRA 规则**: `misra-c2012-12.1`
- **企标规则**: `GSCR-C-16.4`
- **企标等级**: **S2**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 表达式中运算符的优先级应该是显式的

### 违规 #42

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 103
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #43

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 104
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #44

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 105
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #45

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 237
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #46

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 264
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #47

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 265
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #48

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 266
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #49

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 267
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #50

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 268
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #51

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 269
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #52

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 270
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #53

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 271
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #54

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 272
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #55

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 273
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #56

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 362
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #57

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 366
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #58

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 380
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #59

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 194
- **MISRA 规则**: `misra-c2012-17.2`
- **企标规则**: `GSCR-C-21.5`
- **企标等级**: **S1**
- **分类**: 函数
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 函数不能直接或间接地调用自己

### 违规 #60

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 41
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #61

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 115
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #62

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 128
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #63

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 141
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #64

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 161
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #65

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 180
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #66

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 203
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #67

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 217
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #68

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 228
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #69

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 243
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #70

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 313
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #71

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 316
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #72

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 319
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #73

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 322
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #74

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 325
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #75

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 328
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #76

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 331
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #77

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 334
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #78

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 337
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #79

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 154
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #80

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 170
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #81

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 207
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #82

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 267
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #83

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 281
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #84

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 287
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #85

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 302
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #86

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 338
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #87

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 369
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #88

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 387
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #89

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 408
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #90

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 441
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #91

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 106
- **MISRA 规则**: `misra-c2012-8.9`
- **企标规则**: `GSCR-C-12.12`
- **企标等级**: **S2**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 如果一个对象的标识符只出现在一个函数中，那么它应该在块范围内定义

### 违规 #92

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 126
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #93

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 158
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #94

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 174
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #95

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 180
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #96

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 185
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #97

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 200
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #98

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 213
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #99

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 229
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #100

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 261
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #101

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 271
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #102

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 311
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #103

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 322
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #104

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 329
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #105

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 345
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #106

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 350
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #107

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 376
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #108

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 394
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #109

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 412
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #110

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 414
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #111

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 417
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #112

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 420
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #113

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 423
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #114

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 426
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #115

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 429
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #116

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 432
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #117

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 435
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #118

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 437
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #119

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 445
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #120

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 446
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #121

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 447
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #122

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 448
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #123

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 449
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #124

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 450
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #125

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 309
- **MISRA 规则**: `misra-c2012-17.3`
- **企标规则**: `GSCR-C-21.1`
- **企标等级**: **S0**
- **分类**: 函数
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应该对函数隐式声明。

### 违规 #126

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 42
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #127

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 413
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #128

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 416
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #129

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 419
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #130

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 422
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #131

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 425
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #132

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 428
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #133

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 431
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #134

- **文件**: `ref/fault-inject/v2/src/TaskFaultInject.c`
- **行号**: 434
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #135

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 260
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #136

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 281
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #137

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 286
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #138

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 354
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #139

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 407
- **MISRA 规则**: `misra-c2012-8.4`
- **企标规则**: `GSCR-C-12.4`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的

### 违规 #140

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 175
- **MISRA 规则**: `misra-c2012-11.3`
- **企标规则**: `GSCR-C-15.4`
- **企标等级**: **S1**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 禁止将对象类型指针强制转换为不同对象类型的指针

### 违规 #141

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 93
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #142

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 102
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #143

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 123
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #144

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 148
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #145

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 168
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #146

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 211
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #147

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 236
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #148

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 251
- **MISRA 规则**: `misra-c2012-11.4`
- **企标规则**: `GSCR-C-15.8`
- **企标等级**: **S2**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向对象的指针和整数类型之间执行转换

### 违规 #149

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 136
- **MISRA 规则**: `misra-c2012-11.6`
- **企标规则**: `GSCR-C-15.5`
- **企标等级**: **S1**
- **分类**: 指针类型转换
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 不应在指向 void 的指针和算术类型之间执行强制类型转换

### 违规 #150

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 399
- **MISRA 规则**: `misra-c2012-12.1`
- **企标规则**: `GSCR-C-16.4`
- **企标等级**: **S2**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 表达式中运算符的优先级应该是显式的

### 违规 #151

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 103
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #152

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 104
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #153

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 105
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #154

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 237
- **MISRA 规则**: `misra-c2012-12.2`
- **企标规则**: `GSCR-C-16.1`
- **企标等级**: **S1**
- **分类**: 表达式
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)

### 违规 #155

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 264
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #156

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 265
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #157

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 266
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #158

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 267
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #159

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 268
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #160

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 269
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #161

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 270
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #162

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 271
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #163

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 272
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #164

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 273
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #165

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 362
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #166

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 366
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #167

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 380
- **MISRA 规则**: `misra-c2012-15.5`
- **企标规则**: `GSCR-C-19.7`
- **企标等级**: **S2**
- **分类**: 控制流
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 一个函数在结束时应该有一个单独的出口点

### 违规 #168

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 194
- **MISRA 规则**: `misra-c2012-17.2`
- **企标规则**: `GSCR-C-21.5`
- **企标等级**: **S1**
- **分类**: 函数
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 函数不能直接或间接地调用自己

### 违规 #169

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 41
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #170

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 115
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #171

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 128
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #172

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 141
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #173

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 161
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #174

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 180
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #175

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 203
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #176

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 217
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #177

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 228
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #178

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 243
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #179

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 313
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #180

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 316
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #181

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 319
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #182

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 322
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #183

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 325
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #184

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 328
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #185

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 331
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #186

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 334
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #187

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 337
- **MISRA 规则**: `misra-c2012-20.9`
- **企标规则**: `GSCR-C-24.7`
- **企标等级**: **S1**
- **分类**: 预处理指令
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前

### 违规 #188

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 135
- **MISRA 规则**: `misra-c2012-5.6`
- **企标规则**: `GSCR-C-9.5`
- **企标等级**: **S1**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: typedef名称应该是唯一的标识符

### 违规 #189

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 135
- **MISRA 规则**: `misra-c2012-5.6`
- **企标规则**: `GSCR-C-9.5`
- **企标等级**: **S1**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: typedef名称应该是唯一的标识符

### 违规 #190

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 81
- **MISRA 规则**: `misra-c2012-8.5`
- **企标规则**: `GSCR-C-12.5`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 外部对象或函数应在一个且仅有一个文件中声明一次

### 违规 #191

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 81
- **MISRA 规则**: `misra-c2012-8.5`
- **企标规则**: `GSCR-C-12.5`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 外部对象或函数应在一个且仅有一个文件中声明一次

### 违规 #192

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 84
- **MISRA 规则**: `misra-c2012-8.5`
- **企标规则**: `GSCR-C-12.5`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 外部对象或函数应在一个且仅有一个文件中声明一次

### 违规 #193

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 84
- **MISRA 规则**: `misra-c2012-8.5`
- **企标规则**: `GSCR-C-12.5`
- **企标等级**: **S1**
- **分类**: 声明和定义
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 外部对象或函数应在一个且仅有一个文件中声明一次

### 违规 #194

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 91
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #195

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 91
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #196

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 100
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #197

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 100
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #198

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 121
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #199

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 121
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #200

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 133
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #201

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 133
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #202

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 146
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #203

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 146
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #204

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 166
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #205

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 166
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #206

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 186
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #207

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 186
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #208

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 197
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #209

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 197
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #210

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 209
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #211

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 209
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #212

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 222
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #213

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 222
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #214

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 234
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #215

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 234
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #216

- **文件**: `ref/fault-inject/FaultInject/src/FaultInject.c`
- **行号**: 249
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #217

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 249
- **MISRA 规则**: `misra-c2012-5.9`
- **企标规则**: `GSCR-C-9.9`
- **企标等级**: **S2**
- **分类**: 标识符
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 定义具有内部链接的对象或函数的标识符应该是唯一的

### 违规 #218

- **文件**: `benchmark/misra-fp-cases/case006_false_positive.c`
- **行号**: 14
- **MISRA 规则**: `misra-c2012-2.5`
- **企标规则**: `GSCR-C-6.5`
- **企标等级**: **S2**
- **分类**: 未使用的代码
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 项目不应包含未使用的宏声明

### 违规 #219

- **文件**: `benchmark/misra-fp-cases/case006_false_positive.c`
- **行号**: 15
- **MISRA 规则**: `misra-c2012-2.5`
- **企标规则**: `GSCR-C-6.5`
- **企标等级**: **S2**
- **分类**: 未使用的代码
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 项目不应包含未使用的宏声明

### 违规 #220

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 54
- **MISRA 规则**: `misra-c2012-2.5`
- **企标规则**: `GSCR-C-6.5`
- **企标等级**: **S2**
- **分类**: 未使用的代码
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 项目不应包含未使用的宏声明

### 违规 #221

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 56
- **MISRA 规则**: `misra-c2012-2.5`
- **企标规则**: `GSCR-C-6.5`
- **企标等级**: **S2**
- **分类**: 未使用的代码
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 项目不应包含未使用的宏声明

### 违规 #222

- **文件**: `ref/fault-inject/v2/src/FaultInject.c`
- **行号**: 57
- **MISRA 规则**: `misra-c2012-2.5`
- **企标规则**: `GSCR-C-6.5`
- **企标等级**: **S2**
- **分类**: 未使用的代码
- **MISRA 描述**: misra violation (use --rule-texts=<file> to get proper output)
- **企标说明**: 项目不应包含未使用的宏声明

## 7. MISRA ID → GSCR ID 映射

以下为本项目中实际出现的 MISRA 违规与其对应的企标规则 ID 映射关系：

| MISRA 规则 ID | GSCR 企标规则 ID | 企标严重等级 | 企标中文描述 |
|--------------|------------------|-------------|-------------|
| `misra-c2012-8.4` | `GSCR-C-12.4` | **S1** | 当定义具有外部链接的对象或函数时，兼容声明应是可见的 |
| `misra-c2012-10.3` | `GSCR-C-14.3` | **S1** | 表达式的值不应赋给具有较窄的基本类型或不同的基本类型类别的对象 |
| `misra-c2012-11.4` | `GSCR-C-15.8` | **S2** | 不应在指向对象的指针和整数类型之间执行转换 |
| `misra-c2012-7.2` | *未映射* | — | — |
| `misra-c2012-17.7` | `GSCR-C-21.6` | **S1** | 具有 non-void 返回类型应使用的函数返回的值 |
| `misra-c2012-7.4` | *未映射* | — | — |
| `misra-c2012-13.3` | `GSCR-C-17.5` | **S2** | 完整表达式自增(++)或自减(--)运算符不应引起除递增或递减运算之外的其他副作用。 |
| `misra-c2012-10.4` | `GSCR-C-14.4` | **S1** | 操作符的两个操作数进行常见的算术转换时应具有相同的基本类型类别 |
| `misra-c2012-14.2` | `GSCR-C-18.3` | **S1** | for 循环应该是形式良好的 |
| `misra-c2012-16.4` | `GSCR-C-20.4` | **S1** | 每个 switch 语句都应该有一个 default 标签 |
| `misra-c2012-11.3` | `GSCR-C-15.4` | **S1** | 禁止将对象类型指针强制转换为不同对象类型的指针 |
| `misra-c2012-11.6` | `GSCR-C-15.5` | **S1** | 不应在指向 void 的指针和算术类型之间执行强制类型转换 |
| `misra-c2012-12.1` | `GSCR-C-16.4` | **S2** | 表达式中运算符的优先级应该是显式的 |
| `misra-c2012-12.2` | `GSCR-C-16.1` | **S1** | 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1) |
| `misra-c2012-15.5` | `GSCR-C-19.7` | **S2** | 一个函数在结束时应该有一个单独的出口点 |
| `misra-c2012-17.2` | `GSCR-C-21.5` | **S1** | 函数不能直接或间接地调用自己 |
| `misra-c2012-20.9` | `GSCR-C-24.7` | **S1** | 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前 |
| `misra-c2012-8.9` | `GSCR-C-12.12` | **S2** | 如果一个对象的标识符只出现在一个函数中，那么它应该在块范围内定义 |
| `misra-c2012-17.3` | `GSCR-C-21.1` | **S0** | 不应该对函数隐式声明。 |
| `misra-c2012-5.6` | `GSCR-C-9.5` | **S1** | typedef名称应该是唯一的标识符 |
| `misra-c2012-8.5` | `GSCR-C-12.5` | **S1** | 外部对象或函数应在一个且仅有一个文件中声明一次 |
| `misra-c2012-5.9` | `GSCR-C-9.9` | **S2** | 定义具有内部链接的对象或函数的标识符应该是唯一的 |
| `misra-c2012-2.5` | `GSCR-C-6.5` | **S2** | 项目不应包含未使用的宏声明 |

### 附录：完整 MISRA ↔ GSCR 交叉引用

以下列出所有项目 MISRA 违规涉及的 GSCR 规则完整定义：

- `misra-c2012-10.3` → `GSCR-C-14.3` (S1): 表达式的值不应赋给具有较窄的基本类型或不同的基本类型类别的对象
  - 分类: 基本类型
- `misra-c2012-10.4` → `GSCR-C-14.4` (S1): 操作符的两个操作数进行常见的算术转换时应具有相同的基本类型类别
  - 分类: 基本类型
- `misra-c2012-11.3` → `GSCR-C-15.4` (S1): 禁止将对象类型指针强制转换为不同对象类型的指针
  - 分类: 指针类型转换
- `misra-c2012-11.4` → `GSCR-C-15.8` (S2): 不应在指向对象的指针和整数类型之间执行转换
  - 分类: 指针类型转换
- `misra-c2012-11.6` → `GSCR-C-15.5` (S1): 不应在指向 void 的指针和算术类型之间执行强制类型转换
  - 分类: 指针类型转换
- `misra-c2012-12.1` → `GSCR-C-16.4` (S2): 表达式中运算符的优先级应该是显式的
  - 分类: 表达式
- `misra-c2012-12.2` → `GSCR-C-16.1` (S1): 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
  - 分类: 表达式
- `misra-c2012-13.3` → `GSCR-C-17.5` (S2): 完整表达式自增(++)或自减(--)运算符不应引起除递增或递减运算之外的其他副作用。
  - 分类: 函数副作用
- `misra-c2012-14.2` → `GSCR-C-18.3` (S1): for 循环应该是形式良好的
  - 分类: 控制语句表达式
- `misra-c2012-15.5` → `GSCR-C-19.7` (S2): 一个函数在结束时应该有一个单独的出口点
  - 分类: 控制流
- `misra-c2012-16.4` → `GSCR-C-20.4` (S1): 每个 switch 语句都应该有一个 default 标签
  - 分类: Switch语句
- `misra-c2012-17.2` → `GSCR-C-21.5` (S1): 函数不能直接或间接地调用自己
  - 分类: 函数
- `misra-c2012-17.3` → `GSCR-C-21.1` (S0): 不应该对函数隐式声明。
  - 分类: 函数
- `misra-c2012-17.7` → `GSCR-C-21.6` (S1): 具有 non-void 返回类型应使用的函数返回的值
  - 分类: 函数
- `misra-c2012-2.5` → `GSCR-C-6.5` (S2): 项目不应包含未使用的宏声明
  - 分类: 未使用的代码
- `misra-c2012-20.9` → `GSCR-C-24.7` (S1): 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
  - 分类: 预处理指令
- `misra-c2012-5.6` → `GSCR-C-9.5` (S1): typedef名称应该是唯一的标识符
  - 分类: 标识符
- `misra-c2012-5.9` → `GSCR-C-9.9` (S2): 定义具有内部链接的对象或函数的标识符应该是唯一的
  - 分类: 标识符
- `misra-c2012-7.2` → *未映射到企标规则*
- `misra-c2012-7.4` → *未映射到企标规则*
- `misra-c2012-8.4` → `GSCR-C-12.4` (S1): 当定义具有外部链接的对象或函数时，兼容声明应是可见的
  - 分类: 声明和定义
- `misra-c2012-8.5` → `GSCR-C-12.5` (S1): 外部对象或函数应在一个且仅有一个文件中声明一次
  - 分类: 声明和定义
- `misra-c2012-8.9` → `GSCR-C-12.12` (S2): 如果一个对象的标识符只出现在一个函数中，那么它应该在块范围内定义
  - 分类: 声明和定义

## 附录 A: 其他 cppcheck 问题

以下为非 MISRA 的 cppcheck 问题（仅供代码质量参考，不纳入企标合规审核）：

| 问题 ID | 违规数 | 说明 |
|---------|--------|------|
| `unusedFunction` | 28 | The function 'process_sensor' is never used. |
| `misra-config` | 19 | Because of missing configuration, misra checking is incomplete. There can be fal |
| `missingInclude` | 8 | Include file: "FaultInject.h" not found. |
| `constVariablePointer` | 6 | Variable 'restricted' can be declared as pointer to const |
| `nullPointer` | 2 | Possible null pointer dereference: null_ptr |
| `zerodiv` | 2 | Division by zero. |
| `staticFunction` | 2 | The function 'hal_uart_transmit' should have static linkage since it is not used |
| `unreadVariable` | 1 | Variable 'sensor_val' is assigned a value that is never used. |
| `constVariable` | 1 | Variable 'msg' can be declared as const array |
| `knownConditionTrueFalse` | 1 | Condition 'valid' is always true |

## 8. 评审建议

### 8.1 S0/S1 必须修复项 🚨⚠️

发现 **108 个 S0/S1 违规**，以下为必须修复项：

- [S1] `benchmark/misra-fp-cases/case001_true_positive.c:10` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case001_true_positive.c:14` — **`GSCR-C-14.3`**: 表达式的值不应赋给具有较窄的基本类型或不同的基本类型类别的对象
- [S1] `benchmark/misra-fp-cases/case002_false_positive.c:13` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case003_false_positive.c:14` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case003_false_positive.c:20` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case004_false_positive.c:19` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case004_false_positive.c:24` — **`GSCR-C-21.6`**: 具有 non-void 返回类型应使用的函数返回的值
- [S1] `benchmark/misra-fp-cases/case005_false_positive.c:17` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case006_false_positive.c:17` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case006_false_positive.c:22` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case008_false_negative.c:13` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case009_false_negative.c:12` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case010_false_negative.c:13` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case011_mixed_type_math.c:12` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case011_mixed_type_math.c:14` — **`GSCR-C-14.4`**: 操作符的两个操作数进行常见的算术转换时应具有相同的基本类型类别
- [S1] `benchmark/misra-fp-cases/case012_complex_control.c:20` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `benchmark/misra-fp-cases/case012_complex_control.c:33` — **`GSCR-C-18.3`**: for 循环应该是形式良好的
- [S1] `benchmark/misra-fp-cases/case012_complex_control.c:23` — **`GSCR-C-20.4`**: 每个 switch 语句都应该有一个 default 标签
- [S1] `ref/fault-inject/v2/src/FaultInject.c:260` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/FaultInject.c:281` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/FaultInject.c:286` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/FaultInject.c:354` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/FaultInject.c:407` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/FaultInject.c:175` — **`GSCR-C-15.4`**: 禁止将对象类型指针强制转换为不同对象类型的指针
- [S1] `ref/fault-inject/v2/src/FaultInject.c:136` — **`GSCR-C-15.5`**: 不应在指向 void 的指针和算术类型之间执行强制类型转换
- [S1] `ref/fault-inject/v2/src/FaultInject.c:103` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/v2/src/FaultInject.c:104` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/v2/src/FaultInject.c:105` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/v2/src/FaultInject.c:237` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/v2/src/FaultInject.c:194` — **`GSCR-C-21.5`**: 函数不能直接或间接地调用自己
- [S1] `ref/fault-inject/v2/src/FaultInject.c:41` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:115` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:128` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:141` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:161` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:180` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:203` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:217` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:228` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:243` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:313` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:316` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:319` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:322` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:325` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:328` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:331` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:334` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:337` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:154` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:170` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:207` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:267` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:281` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:287` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:302` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:338` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:369` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:387` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:408` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:441` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S0] `ref/fault-inject/v2/src/TaskFaultInject.c:309` — **`GSCR-C-21.1`**: 不应该对函数隐式声明。
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:42` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:413` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:416` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:419` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:422` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:425` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:428` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:431` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/TaskFaultInject.c:434` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:260` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:281` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:286` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:354` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:407` — **`GSCR-C-12.4`**: 当定义具有外部链接的对象或函数时，兼容声明应是可见的
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:175` — **`GSCR-C-15.4`**: 禁止将对象类型指针强制转换为不同对象类型的指针
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:136` — **`GSCR-C-15.5`**: 不应在指向 void 的指针和算术类型之间执行强制类型转换
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:103` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:104` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:105` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:237` — **`GSCR-C-16.1`**: 移位操作符的右操作数应位于左操作数的基本类型的位宽的范围内(从0到1)
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:194` — **`GSCR-C-21.5`**: 函数不能直接或间接地调用自己
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:41` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:115` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:128` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:141` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:161` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:180` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:203` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:217` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:228` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:243` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:313` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:316` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:319` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:322` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:325` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:328` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:331` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:334` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:337` — **`GSCR-C-24.7`**: 在#if或#elif预处理指令的控制表达式中使用的所有标识符都必须在求值前
- [S1] `ref/fault-inject/v2/src/FaultInject.c:135` — **`GSCR-C-9.5`**: typedef名称应该是唯一的标识符
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:135` — **`GSCR-C-9.5`**: typedef名称应该是唯一的标识符
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:81` — **`GSCR-C-12.5`**: 外部对象或函数应在一个且仅有一个文件中声明一次
- [S1] `ref/fault-inject/v2/src/FaultInject.c:81` — **`GSCR-C-12.5`**: 外部对象或函数应在一个且仅有一个文件中声明一次
- [S1] `ref/fault-inject/FaultInject/src/FaultInject.c:84` — **`GSCR-C-12.5`**: 外部对象或函数应在一个且仅有一个文件中声明一次
- [S1] `ref/fault-inject/v2/src/FaultInject.c:84` — **`GSCR-C-12.5`**: 外部对象或函数应在一个且仅有一个文件中声明一次

### 8.2 S2 建议修复项 💡

发现 **114 个 S2 违规**，建议在后续迭代中修复：

- [S2] `benchmark/misra-fp-cases/case002_false_positive.c:15` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `benchmark/misra-fp-cases/case004_false_positive.c:20` — **misra-c2012-7.2**: misra violation (use --rule-texts=<file> to get proper output)
- [S2] `benchmark/misra-fp-cases/case005_false_positive.c:19` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `benchmark/misra-fp-cases/case005_false_positive.c:22` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `benchmark/misra-fp-cases/case006_false_positive.c:23` — **misra-c2012-7.4**: misra violation (use --rule-texts=<file> to get proper output)
- [S2] `benchmark/misra-fp-cases/case007_true_negative.c:35` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `benchmark/misra-fp-cases/case008_false_negative.c:18` — **`GSCR-C-17.5`**: 完整表达式自增(++)或自减(--)运算符不应引起除递增或递减运算之外的其他副作用。
- [S2] `ref/fault-inject/v2/src/FaultInject.c:93` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:102` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:123` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:148` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:168` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:211` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:236` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:251` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/v2/src/FaultInject.c:399` — **`GSCR-C-16.4`**: 表达式中运算符的优先级应该是显式的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:264` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:265` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:266` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:267` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:268` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:269` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:270` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:271` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:272` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:273` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:362` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:366` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/FaultInject.c:380` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:106` — **`GSCR-C-12.12`**: 如果一个对象的标识符只出现在一个函数中，那么它应该在块范围内定义
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:126` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:158` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:174` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:180` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:185` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:200` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:213` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:229` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:261` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:271` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:311` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:322` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:329` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:345` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:350` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:376` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:394` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:412` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:414` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:417` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:420` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:423` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:426` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:429` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:432` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:435` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:437` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:445` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:446` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:447` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:448` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:449` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/v2/src/TaskFaultInject.c:450` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:93` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:102` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:123` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:148` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:168` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:211` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:236` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:251` — **`GSCR-C-15.8`**: 不应在指向对象的指针和整数类型之间执行转换
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:399` — **`GSCR-C-16.4`**: 表达式中运算符的优先级应该是显式的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:264` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:265` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:266` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:267` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:268` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:269` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:270` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:271` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:272` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:273` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:362` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:366` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:380` — **`GSCR-C-19.7`**: 一个函数在结束时应该有一个单独的出口点
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:91` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:91` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:100` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:100` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:121` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:121` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:133` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:133` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:146` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:146` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:166` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:166` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:186` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:186` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:197` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:197` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:209` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:209` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:222` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:222` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:234` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:234` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/FaultInject/src/FaultInject.c:249` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `ref/fault-inject/v2/src/FaultInject.c:249` — **`GSCR-C-9.9`**: 定义具有内部链接的对象或函数的标识符应该是唯一的
- [S2] `benchmark/misra-fp-cases/case006_false_positive.c:14` — **`GSCR-C-6.5`**: 项目不应包含未使用的宏声明
- [S2] `benchmark/misra-fp-cases/case006_false_positive.c:15` — **`GSCR-C-6.5`**: 项目不应包含未使用的宏声明
- [S2] `ref/fault-inject/v2/src/FaultInject.c:54` — **`GSCR-C-6.5`**: 项目不应包含未使用的宏声明
- [S2] `ref/fault-inject/v2/src/FaultInject.c:56` — **`GSCR-C-6.5`**: 项目不应包含未使用的宏声明
- [S2] `ref/fault-inject/v2/src/FaultInject.c:57` — **`GSCR-C-6.5`**: 项目不应包含未使用的宏声明

### 8.3 综合建议

1. 🔴 **立即行动**: 还有 108 个 S0/S1 违规需要优先修复。
   - 请开发团队评审每个违规的具体原因，制定修复计划。
   - 修复后重新运行 GSCR 检查确认通过。
2. 🟡 **后续迭代**: 114 个 S2 建议项可纳入后续迭代。
3. 🟠 **代码质量**: 有 70 个非 MISRA 的 cppcheck 问题（如 `unusedFunction`、`missingInclude` 等），建议一并清理。

### 8.4 GSCR 规则集统计

- GSCR 企标规则总数: **430** 条
  - C 语言规则: 186 条 (S0: 28, S1: 118, S2: 40)
  - C++ 语言规则: 244 条 (S0: 22, S1: 127, S2: 95)
- 可自动检查: 284 条
- 需人工审查: 146 条

---

*报告由 GSCR 企标合规检查系统自动生成 | 2026-06-25 18:23*
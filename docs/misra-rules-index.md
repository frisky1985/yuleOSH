# MISRA-C:2012 规则索引（C:2023 差异标注版）

> **文档**: `docs/misra-rules-index.md`
> **版本**: 1.1.0
> **状态**: Updated — MISRA C:2023 Phase 2
> **说明**: 30 条核心 MISRA C:2012 规则索引，用于 RAG 检索和 Agent 辅助审查。
> 每条规则包含：规则编号、分类、标题、描述、常见违规模式、修复示例、关联规则，以及 C:2023 版本变更标注。
> C:2023 变更标注见文末差异对比章节。

---

## 规则速查表

| # | 规则 | 分类 | 严重度 | 关键字 |
|:-:|:-----|:-----|:------:|:-------|
| 1 | Rule 1.1 | Required | 🔴 | 标准合规、扩展语法 |
| 2 | Rule 2.2 | Required | 🟡 | 死代码、不可达路径 |
| 3 | Rule 5.1 | Required | 🔴 | 标识符命名冲突、作用域 |
| 4 | Rule 5.6 | Required | 🔴 | typedef 命名冲突 |
| 5 | Rule 8.2 | Required | 🔴 | 函数声明：参数类型 |
| 6 | Rule 8.4 | Required | 🔴 | 外部定义、可见性 |
| 7 | Rule 8.7 | Required | 🟡 | 外部链接、内部函数 |
| 8 | Rule 8.13 | Advisory | 🟢 | const 限定、指针参数 |
| 9 | Rule 9.1 | Mandatory | 🔴 | 未初始化自动变量 |
| 10 | Rule 10.1 | Required | 🔴 | 隐式整型转换 |
| 11 | Rule 10.3 | Required | 🔴 | 赋值窄化转换 |
| 12 | Rule 10.4 | Required | 🟡 | 表达式类型不匹配 |
| 13 | Rule 11.3 | Required | 🔴 | 指针到整型强制转换 |
| 14 | Rule 11.4 | Required | 🔴 | 对象指针到整数转换 |
| 15 | Rule 12.1 | Advisory | 🟢 | 运算符优先级、括号 |
| 16 | Rule 12.2 | Required | 🟡 | 表达式副作用 |
| 17 | Rule 13.2 | Required | 🟡 | 有副作用的表达式 |
| 18 | Rule 14.3 | Required | 🟡 | 控制表达式常量 |
| 19 | Rule 15.1 | Advisory | 🟢 | goto 语句 |
| 20 | Rule 15.4 | Advisory | 🟢 | 迭代计数器、break |
| 21 | Rule 16.1 | Required | 🔴 | switch 标签唯一性 |
| 22 | Rule 16.3 | Required | 🔴 | switch 缺 default |
| 23 | Rule 16.6 | Required | 🟡 | switch 每个 case 含 break |
| 24 | Rule 17.2 | Required | 🔴 | 递归函数 |
| 25 | Rule 18.4 | Required | 🔴 | 指针算术运算 |
| 26 | Rule 18.5 | Required | 🔴 | 越界访问 |
| 27 | Rule 20.9 | Required | 🟡 | #undef 预处理指令 |
| 28 | Rule 21.1 | Required | 🔴 | 标准库宏、命名冲突 |
| 29 | Rule 21.12 | Required | 🔴 | 异常处理、abort |
| 30 | Rule 22.1 | Required | 🔴 | 动态内存分配 |

---

## 规则详细索引

### Rule 1.1 — 标准合规：扩展语法

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | The program shall not contain any extensions to the C standard |
| **描述** | 程序不得包含 C 标准的任何扩展。编译器的非标准扩展（如内联汇编、GNU C 扩展、特定于编译器的属性）被禁止。所有代码必须严格遵守 C90/C99/C11 标准。 |
| **常见违规模式** |
| 1. 使用 `__attribute__((packed))` 等 GCC 扩展 |
| 2. 使用 `asm()` 内联汇编 |
| 3. 使用 C++ 风格注释（`//`）在 C90 模式下 |
| **修复示例** |
| ```c
// 违规（GNU 扩展）
struct __attribute__((packed)) my_struct {
    uint8_t a;
    uint16_t b;
};

// 修复：定义结构体时避免 packed
struct my_struct {
    uint8_t a;
    uint16_t b;
};
``` |
| **关联规则** | — |

---

### Rule 2.2 — 死代码

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | A project shall not contain unreachable code |
| **描述** | 项目不得包含不可达代码（死代码）。所有代码路径都必须有可达的条件。死代码可能来自调试遗留、条件编译错误或优化残留。 |
| **常见违规模式** |
| 1. `if (0) { ... }` 被条件编译排除 |
| 2. `return` 之后的无法到达语句 |
| 3. 永远为 `false` 的条件分支 |
| **修复示例** |
| ```c
// 违规：return 后不可达
int foo(int x) {
    return x * 2;
    x += 1;  // unreachable
}

// 修复：删除死代码
int foo(int x) {
    return x * 2;
}
``` |
| **关联规则** | Rule 14.3 |

---

### Rule 5.1 — 标识符命名冲突

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | External identifiers shall be distinct in the first 31 characters |
| **描述** | 外部链接标识符的前 31 个字符必须唯一。某些编译器/链接器对长符号名截断，导致冲突。 |
| **常见违规模式** |
| 1. 两个函数名前 31 字符相同 |
| 2. `long_function_name_impl1` 和 `long_function_name_implementation_2` 冲突 |
| **修复示例** |
| ```c
// 违规：前 31 字符相同
extern void adc_read_and_convert_and_filter_v1(void);
extern void adc_read_and_convert_and_filter_v2(void);

// 修复：缩短并区分
extern void adc_read_v1(void);
extern void adc_read_v2(void);
``` |
| **关联规则** | Rule 5.6 |

---

### Rule 5.6 — typedef 命名冲突

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | A typedef name shall be a unique identifier |
| **描述** | typedef 名称在整个翻译单元中必须唯一。不得与其他标识符（变量名、函数名、结构体标签）重名。 |
| **常见违规模式** |
| 1. `typedef uint32_t speed_t;` 后定义 `int speed_t;` |
| 2. 头文件中的 typedef 与局部变量同名 |
| **修复示例** |
| ```c
// 违规
typedef uint32_t speed_t;
uint32_t speed_t;  // 冲突

// 修复
typedef uint32_t speed_t;
uint32_t current_speed;
``` |
| **关联规则** | Rule 5.1 |

---

### Rule 8.2 — 函数声明：参数类型

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | Function types shall be in prototype form with named parameters |
| **描述** | 函数声明必须采用原型形式（包含参数类型），且参数应有名称。禁止空参数列表 `()`，应使用 `(void)`。 |
| **常见违规模式** |
| 1. 使用 `int foo();` 而非 `int foo(void);` |
| 2. 定义时参数有名称但声明时缺失 |
| 3. 旧风格 K&R 函数定义 |
| **修复示例** |
| ```c
// 违规
int process();  // empty parentheses — unspecified
int init(a, b)  // K&R style
int a; int b; { return a + b; }

// 修复
int process(void);
int init(int a, int b);
``` |
| **关联规则** | Rule 8.4 |

---

### Rule 8.4 — 外部定义、可见性

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | A compatible declaration shall be visible when an object or function with external linkage is defined |
| **描述** | 定义具有外部链接的对象或函数时，必须有一个兼容的声明在翻译单元中可见。避免隐式外部声明。 |
| **常见违规模式** |
| 1. 函数定义前无头文件声明 |
| 2. 全局变量定义前无 `extern` 声明 |
| 3. 未包含对应的头文件 |
| **修复示例** |
| ```c
// 违规：无前置声明
// 在 file.c 中定义但没有匹配的 .h 声明
int global_counter = 0;
void init_system(void) { ... }

// 修复：包含声明
// 在 file.h 中
extern int global_counter;
void init_system(void);

// 在 file.c 中
#include "file.h"
int global_counter = 0;
void init_system(void) { ... }
``` |
| **关联规则** | Rule 8.2 |

---

### Rule 8.7 — 外部链接、内部函数

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | Functions and objects should not be defined with external linkage if they are only referenced in one translation unit |
| **描述** | 如果函数或对象只在单个翻译单元中使用，则不应当定义为外部链接。应使用 `static` 限定将其限制在文件内部。 |
| **常见违规模式** |
| 1. 仅在 `file.c` 内部使用的函数未加 `static` |
| 2. 文件内部辅助函数暴露全局命名空间 |
| 3. 局部全局变量未加 `static` |
| **修复示例** |
| ```c
// 违规：文件内部函数暴露外部
void helper_calc(void) { ... }  // 只在 file.c 内使用

// 修复：加 static
static void helper_calc(void) { ... }
``` |
| **关联规则** | Rule 8.4 |

---

### Rule 8.13 — const 限定、指针参数

| 属性 | 值 |
|:-----|:----|
| **分类** | Advisory |
| **严重度** | 🟢 低 |
| **标题** | A pointer to a const-qualified type should be used for parameters that never modify the pointed-to object |
| **描述** | 如果函数参数指向的对象不会被修改，则指针参数应使用 `const` 限定。这增加了接口的清晰度和安全性。 |
| **常见违规模式** |
| 1. `void print(char *s)` — s 不会被修改 |
| 2. `int compare(char *a, char *b)` |
| **修复示例** |
| ```c
// 违规：const 缺失
void print_buffer(uint8_t *buf, uint32_t len) {
    for (uint32_t i = 0; i < len; i++) {
        Log(buf[i]);  // 不修改 buf
    }
}

// 修复：加 const
void print_buffer(const uint8_t *buf, uint32_t len) {
    for (uint32_t i = 0; i < len; i++) {
        Log(buf[i]);
    }
}
``` |
| **关联规则** | — |

---

### Rule 9.1 — 未初始化自动变量

| 属性 | 值 |
|:-----|:----|
| **分类** | Mandatory |
| **严重度** | 🔴 高 |
| **标题** | The value of an object with automatic storage duration shall not be read before it is assigned |
| **描述** | 自动存储期对象（局部变量）在其值被赋予之前不得读取。未初始化的局部变量包含不确定值，可能导致不可预测行为。 |
| **常见违规模式** |
| 1. `int x; if (cond) { x = 1; } return x;` — 条件分支未覆盖 |
| 2. 结构体成员未初始化即使用 |
| 3. 指针未初始化即解引用 |
| **修复示例** |
| ```c
// 违规
int foo(int cond) {
    int x;
    if (cond) { x = 1; }
    return x;  // cond == false 时 x 未初始化
}

// 修复
int foo(int cond) {
    int x = 0;  // 显式初始化
    if (cond) { x = 1; }
    return x;
}
``` |
| **关联规则** | Rule 18.4 |

---

### Rule 10.1 — 隐式整型转换

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | The value of an expression of integer type shall not be implicitly converted to a different underlying type |
| **描述** | 整数类型表达式的值不应被隐式转换为不同的底层类型。MISRA 将整型分为"底层类型"（underlying type）类别：`bool`、`char`、`signed`、`unsigned`。不同底层类型间转换必须使用显式强制转换。 |
| **常见违规模式** |
| 1. `uint16_t a = 10; uint32_t b = a + 5;` — unsigned 隐式提升 |
| 2. `int32_t x = -1; uint32_t y = x;` — signed 到 unsigned |
| 3. 混合 `int` 和 `uint32_t` 的算术运算 |
| **修复示例** |
| ```c
// 违规
uint16_t x = 10;
uint32_t y = x + 5;  // 隐式提升

// 修复：显式类型转换
uint16_t x = 10;
uint32_t y = (uint32_t)x + 5;
``` |
| **关联规则** | Rule 10.3, Rule 10.4 |

---

### Rule 10.3 — 赋值窄化转换

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | The value of an expression shall not be assigned to an object with a narrower essential type |
| **描述** | 表达式的值不能被赋值给具有更窄底层类型的对象。即宽类型到窄类型的赋值必须显式转换。 |
| **常见违规模式** |
| 1. `uint32_t` 值赋给 `uint16_t` 变量 |
| 2. `int` 运算结果赋给 `uint8_t` |
| 3. 函数返回值类型比赋值目标更宽 |
| **修复示例** |
| ```c
// 违规
uint32_t big = 0x10000;
uint16_t small = big;  // 窄化转换

// 修复：显式强制转换（开发者确认截断安全）
uint32_t big = 0x10000;
uint16_t small = (uint16_t)big;
``` |
| **关联规则** | Rule 10.1, Rule 10.4 |

---

### Rule 10.4 — 表达式类型不匹配

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | Both operands of an operator in which the usual arithmetic conversions are performed shall have the same essential type category |
| **描述** | 执行常规算术转换的运算符的两个操作数必须具有相同的基本类型类别。signed 和 unsigned 混合使用通常是不安全的。 |
| **常见违规模式** |
| 1. `int32_t + uint32_t` 混合使用 |
| 2. `uint32_t` 与 `int32_t` 的比较 |
| **修复示例** |
| ```c
// 违规
int32_t x = -10;
uint32_t y = 10;
if (x < y) { ... }  // 混合类型比较，结果不可预期

// 修复：统一类型
int32_t x = -10;
int32_t y = (int32_t)10;
if (x < y) { ... }
``` |
| **关联规则** | Rule 10.1, Rule 10.3 |

---

### Rule 11.3 — 指针到整型强制转换

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | A cast shall not be performed between a pointer type and an arithmetic type |
| **描述** | 不得在指针类型和算术类型之间执行强制转换。指针不应转换为整数，整数也不应转换为指针。需要此类转换的地方应使用特定于硬件的封装方式（如 `uintptr_t` 或 memcpy）。 |
| **常见违规模式** |
| 1. `(uint32_t)ptr` 将指针强制转换为整数 |
| 2. `(GPIO_TypeDef *)0x40020000` 将地址常量强制转换为指针 |
| 3. 用整数运算来操作指针值 |
| **修复示例** |
| ```c
// 违规
uint32_t addr = (uint32_t)&some_var;
GPIO_TypeDef *gpio = (GPIO_TypeDef *)0x40020000;

// 修复（嵌入式场景允许）：使用 uintptr_t 并显式注释
#include <stdint.h>
uintptr_t addr = (uintptr_t)(void*)&some_var;
/* MISRA 偏差：Rule 11.3 — 硬件寄存器访问，已评审 */
GPIO_TypeDef *gpio = (GPIO_TypeDef *)(uintptr_t)0x40020000;
``` |
| **关联规则** | Rule 11.4 |

---

### Rule 11.4 — 对象指针到整数转换

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | A conversion should not be performed between a pointer to object and an arithmetic type |
| **描述** | 不应在对象指针和算术类型之间执行转换。与 Rule 11.3 类似，但侧重于"转换为整数"的方向。 |
| **常见违规模式** |
| 1. `(uint32_t)data_ptr` 将对象指针转换为整数 |
| 2. 用整数减法计算两个指针的地址差（而非 `ptrdiff_t`） |
| **修复示例** |
| ```c
// 违规
uint8_t *data = get_buffer();
uint32_t addr = (uint32_t)data;  // 指针转整数

// 修复（如有必要）：
uint8_t *data = get_buffer();
uintptr_t addr = (uintptr_t)(void*)data;  // 用 uintptr_t
``` |
| **关联规则** | Rule 11.3 |

---

### Rule 12.1 — 运算符优先级、括号

| 属性 | 值 |
|:-----|:----|
| **分类** | Advisory |
| **严重度** | 🟢 低 |
| **标题** | The precedence of operators within expressions should be made explicit |
| **描述** | 表达式中的运算符优先级应通过添加括号明确表示。避免依赖 C 语言运算符优先级规则，以增强可读性并防错。 |
| **常见违规模式** |
| 1. `a + b << 2` — 加法或移位先发生？ |
| 2. `a & b == c` — `==` 优先级高于 `&` |
| 3. 混合 `&&` 和 `||` 无括号 |
| **修复示例** |
| ```c
// 违规：依赖隐式优先级
if (x & MASK == FLAG) { ... }  // 实际为 x & (MASK == FLAG)

// 修复：明确括号
if ((x & MASK) == FLAG) { ... }
``` |
| **关联规则** | — |

---

### Rule 12.2 — 表达式副作用

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | The right-hand operand of a logical && or || operator shall not contain side effects |
| **描述** | 逻辑 `&&` 和 `||` 运算符的右操作数不应包含副作用（修改状态的表达式）。因为短路求值可能导致右操作数不被执行，使副作用不确定。 |
| **常见违规模式** |
| 1. `if (a > 0 && ++counter < MAX)` — counter++ 可能不被执行 |
| 2. `while (ptr != NULL && *ptr++ != 0)` — 递增副作用 |
| **修复示例** |
| ```c
// 违规
if (flag && (count++ > LIMIT)) {
    // count++ 只在 flag 为 true 时执行
}

// 修复：分离副作用
if (flag) {
    count++;
    if (count > LIMIT) {
        ...
    }
}
``` |
| **关联规则** | Rule 13.2 |

---

### Rule 13.2 — 有副作用的表达式

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | The value of an expression and its persistent side effects shall be the same under all permitted evaluation orders |
| **描述** | 表达式的值和持久副作用在所有允许的求值顺序下应当相同。C 标准未指定某些表达式的求值顺序（如函数参数求值顺序）。 |
| **常见违规模式** |
| 1. `array[i++] = func(i)` — i 的递增与 func(i) 的参数求值顺序未定义 |
| 2. `x = f() + g()` — f 和 g 哪个先执行未定义 |
| 3. `func(++x, x)` — 同一变量在参数列表中自增和使用 |
| **修复示例** |
| ```c
// 违规：未定义行为
array[i++] = func(i);

// 修复：分离操作
uint8_t idx = i;
i++;
array[idx] = func(idx);
``` |
| **关联规则** | Rule 12.2 |

---

### Rule 14.3 — 控制表达式常量

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | Controlling expressions shall not be invariant conditions |
| **描述** | 控制表达式不得为不变条件（永远为真或永远为假）。`if (1)`、`while (true)` 和 `for (;;)` 应当在有限范围内使用。无限循环必须显式注释。 |
| **常见违规模式** |
| 1. `if (1) { ... }` 永远执行的分支 |
| 2. `while (0) { ... }` 永不被执行的循环 |
| 3. `#define ENABLED 0` 后被 `if (ENABLED)` 使用 |
| **修复示例** |
| ```c
// 违规
if (1) {
    do_something();  // 无条件的 if
}

// 修复：删除不必要的条件
do_something();
``` |
| **关联规则** | Rule 2.2 |

---

### Rule 15.1 — goto 语句

| 属性 | 值 |
|:-----|:----|
| **分类** | Advisory |
| **严重度** | 🟢 低 |
| **标题** | The goto statement should not be used |
| **描述** | goto 语句不应被使用。goto 导致代码难以理解和维护，引入非结构化控制流。被要求替代方案包括：break、continue、return、函数、循环、结构化错误处理模式。 |
| **常见违规模式** |
| 1. 用 goto 实现错误处理"单出口" |
| 2. 用 goto 跳出深层嵌套循环 |
| 3. 用 goto 实现状态机跳转 |
| **修复示例** |
| ```c
// 违规
if (error1) goto cleanup;
if (error2) goto cleanup;

// 修复：用结构化模式
status_t process(void) {
    status_t ret = STATUS_OK;
    if (error1) { ret = STATUS_ERR1; }
    else if (error2) { ret = STATUS_ERR2; }
    /* cleanup 逻辑放在统一出口 */
    cleanup_resources();
    return ret;
}
``` |
| **关联规则** | — |

---

### Rule 15.4 — 迭代计数器、break

| 属性 | 值 |
|:-----|:----|
| **分类** | Advisory |
| **严重度** | 🟢 低 |
| **标题** | There should be no more than one break or goto statement used to terminate any iteration statement |
| **描述** | 任何迭代语句（for/while/do-while）中，用于终止循环的 break 或 goto 不得超过一个。多出口循环难以理解和维护。 |
| **常见违规模式** |
| 1. 循环内有多个 break 处理不同条件 |
| 2. 循环内既有 break 又有 goto 出口 |
| **修复示例** |
| ```c
// 违规：多个 break
while (ptr != NULL) {
    if (ptr->type == ERROR) break;
    if (ptr->value == TARGET) break;
    ptr = ptr->next;
}

// 修复：用 flag 统一出口
bool found = false;
while ((ptr != NULL) && !found) {
    if ((ptr->type == ERROR) || (ptr->value == TARGET)) {
        found = true;
    } else {
        ptr = ptr->next;
    }
}
``` |
| **关联规则** | — |

---

### Rule 16.1 — switch 标签唯一性

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | All switch statements shall be well-formed. Every switch statement shall have at least one case clause and a default clause |
| **描述** | 所有 switch 语句必须有至少一个 case 标签和一个 default 标签。default 标签处理未覆盖的情况，确保 switch 的完备性。 |
| **常见违规模式** |
| 1. switch 无 default 分支 |
| 2. 重复的 case 值 |
| 3. switch 仅处理部分枚举值但无 default |
| **修复示例** |
| ```c
// 违规
switch (state) {
    case STATE_IDLE:
        break;
    case STATE_ACTIVE:
        break;
    // 缺 default
}

// 修复
switch (state) {
    case STATE_IDLE:
        break;
    case STATE_ACTIVE:
        break;
    default:
        /* unexpected state — error handling */
        break;
}
``` |
| **关联规则** | Rule 16.3, Rule 16.6 |

---

### Rule 16.3 — switch 缺 default

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | An unconditional break statement shall terminate every non-empty switch clause |
| **描述** | 在每个非空的 switch case 子句的末尾，必须有一个 `break` 语句作为退出。禁止 fall-through（贯穿）行为，除非空的 case 标签明确表示合并处理。 |
| **常见违规模式** |
| 1. case 结尾无 break，贯穿到下一个 case |
| 2. 误认为多个 case 执行同一代码块时不需要 break |
| **修复示例** |
| ```c
// 违规：fall-through
switch (cmd) {
    case CMD_START:
        init();
        // 贯穿到 CMD_RUN
    case CMD_RUN:
        run();
        break;
}

// 修复
switch (cmd) {
    case CMD_START:
        init();
        run();
        break;
    case CMD_RUN:
        run();
        break;
    default:
        break;
}

// 允许：空 case 合并
switch (cmd) {
    case CMD_START:  // 空 case，允许贯穿
    case CMD_RUN:
        run();
        break;
    default:
        break;
}
``` |
| **关联规则** | Rule 16.1, Rule 16.6 |

---

### Rule 16.6 — switch 每个 case 含 break

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | Every switch statement shall have at least two case clauses |
| **描述** | 每个 switch 语句应至少有两个 case 标签。如果只处理一个条件，应使用 `if-else` 而非 `switch`。 |
| **常见违规模式** |
| 1. 只有 1 个有效 case + default 的 switch |
| 2. 用 switch 代替简单的 if-else |
| **修复示例** |
| ```c
// 违规：switch 只有一个有效 case
switch (flag) {
    case 1:
        do_something();
        break;
    default:
        break;
}

// 修复：用 if-else
if (flag == 1) {
    do_something();
}
``` |
| **关联规则** | Rule 16.1, Rule 16.3 |

---

### Rule 17.2 — 递归函数

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | Functions shall not call themselves, either directly or indirectly |
| **描述** | 函数不得直接或间接调用自身（禁止递归）。递归可能导致栈溢出（嵌入式系统中栈空间有限），且难以静态分析深度和终止条件。 |
| **常见违规模式** |
| 1. 直接递归：`int fact(int n) { if (n <= 1) return 1; return n * fact(n - 1); }` |
| 2. 间接递归：A 调用 B，B 调用 A |
| **修复示例** |
| ```c
// 违规：直接递归
uint32_t factorial(uint32_t n) {
    if (n <= 1) { return 1; }
    return n * factorial(n - 1);
}

// 修复：迭代实现
uint32_t factorial(uint32_t n) {
    uint32_t result = 1;
    for (uint32_t i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}
``` |
| **关联规则** | — |

---

### Rule 18.4 — 指针算术运算

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | The +, -, +=, and -= operators should not be applied to an expression of pointer type |
| **描述** | `+`、`-`、`+=` 和 `-=` 运算符不应应用于指针类型的表达式。指针算术运算极易导致越界访问。应使用数组索引 `[]` 替代。 |
| **常见违规模式** |
| 1. `*(buf + i)` 访问数组元素 |
| 2. `ptr++` 在循环中步进 |
| 3. `end - start` 计算指针差 |
| **修复示例** |
| ```c
// 违规：指针算术
uint8_t *ptr = buffer;
for (uint32_t i = 0; i < len; i++) {
    process(*ptr);
    ptr++;  // 指针算术
}

// 修复：数组索引
uint8_t *ptr = buffer;
for (uint32_t i = 0; i < len; i++) {
    process(ptr[i]);  // 数组风格
}
``` |
| **关联规则** | Rule 18.5 |

---

### Rule 18.5 — 越界访问

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | The declaration of an array shall not contain a non-constant array size |
| **描述** | 数组的声明不能包含非常量的数组大小。变长数组（VLA）是 C99 选特性，在嵌入式代码中通常被禁止，因其依赖运行时栈分配，可能导致栈溢出。 |
| **常见违规模式** |
| 1. `void foo(int n) { int arr[n]; ... }` VLA |
| 2. 动态大小的栈数组 |
| **修复示例** |
| ```c
// 违规：VLA
void process(uint32_t count) {
    uint8_t buffer[count];  // VLA
    ...
}

// 修复：固定大小或动态分配
#define MAX_BUFFER 256
void process(uint32_t count) {
    uint8_t buffer[MAX_BUFFER];
    if (count > MAX_BUFFER) {
        /* error handling */
        return;
    }
    ...
}
``` |
| **关联规则** | Rule 18.4 |

---

### Rule 20.9 — #undef 预处理指令

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🟡 中 |
| **标题** | All uses of the #undef directive shall be documented |
| **描述** | `#undef` 预处理指令的所有使用都应当被文档化。`#undef` 撤销宏定义，可能导致难以追踪的编译错误和行为变化。 |
| **常见违规模式** |
| 1. 无注释的 `#undef DEBUG` |
| 2. `#undef` 后重新定义同名宏 |
| 3. 跨文件 `#undef` 导致不一致 |
| **修复示例** |
| ```c
// 违规
#define DEBUG_PRINT(x) printf("%s\n", x)
#undef DEBUG_PRINT

// 修复：文档化
#define DEBUG_PRINT(x) printf("%s\n", x)
/* MISRA Rule 20.9: #undef 用于禁用调试输出 */
#undef DEBUG_PRINT
``` |
| **关联规则** | — |

---

### Rule 21.1 — 标准库宏、命名冲突

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | The standard library's macros shall not be redefined |
| **描述** | 标准库的宏不得被重新定义。例如 `NULL`、`EOF`、`INT_MAX`、`assert` 等标准宏不应被 `#define` 覆盖。 |
| **常见违规模式** |
| 1. `#define NULL ((void*)0xFFFFFFFF)` |
| 2. `#define EOF (-2)` |
| 3. `#undef assert` 后重新定义 |
| **修复示例** |
| ```c
// 违规：重新定义标准宏
#define NULL ((void*)0xDEAD)  // 错误！

// 修复：使用标准头文件提供的定义
#include <stddef.h>  // NULL 由标准提供
``` |
| **关联规则** | Rule 20.9, Rule 21.12 |

---

### Rule 21.12 — 异常处理、abort

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | The standard header file <exception> shall not be used |
| **描述** | C++ 标准头文件 `<exception>`、`<stdexcept>` 和异常处理机制不应在嵌入式 C 代码中使用。嵌入式系统通常禁用异常处理（C++ 的 `-fno-exceptions`）。 |
| **常见违规模式** |
| 1. C 代码中包含 C++ 异常头文件 |
| 2. 使用 `setjmp`/`longjmp` 模拟异常 |
| 3. 调用 `abort()` 终止程序 |
| **修复示例** |
| ```c
// 违规
#include <setjmp.h>
jmp_buf env;
if (setjmp(env) != 0) { /* error */ }
longjmp(env, 1);  // 非局部跳转

// 修复：使用错误码返回
typedef enum { ERR_OK, ERR_TIMEOUT, ERR_OVERRUN } error_t;
error_t result = process_data();
if (result != ERR_OK) {
    /* handle error */
}
``` |
| **关联规则** | Rule 22.1 |

---

### Rule 22.1 — 动态内存分配

| 属性 | 值 |
|:-----|:----|
| **分类** | Required |
| **严重度** | 🔴 高 |
| **标题** | All resources obtained dynamically shall be explicitly released |
| **描述** | 所有动态获取的资源必须被显式释放。在嵌入式安全关键系统中，通常禁止动态内存分配（`malloc`/`free`），因为可能导致碎片化、堆耗尽和不确定性。 |
| **常见违规模式** |
| 1. 忘记 `free()` 导致内存泄漏 |
| 2. 在中断服务函数中调用 `malloc` |
| 3. 错误路径上未释放内存 |
| 4. 嵌入式代码中使用动态分配 |
| **修复示例** |
| ```c
// 违规：动态分配
void process(void) {
    uint8_t *buf = (uint8_t*)malloc(256);
    if (buf != NULL) {
        fill_buffer(buf);
        // 没有 free(buf) → 内存泄漏
    }
}

// 修复：静态分配（嵌入式推荐）
#define BUF_SIZE 256
void process(void) {
    static uint8_t buf[BUF_SIZE];  // 编译时分配
    fill_buffer(buf);
}

// 或确保释放：
void process(void) {
    uint8_t *buf = (uint8_t*)malloc(256);
    if (buf != NULL) {
        fill_buffer(buf);
        free(buf);
    }
}
``` |
| **关联规则** | Rule 21.12 |

---

## MISRA 规则分类对照

| 分类 | 数量（本索引） | 说明 |
|:-----|:--------------:|:------|
| Mandatory | 1 | 违反直接导致不符合 MISRA |
| Required | 24 | 必须遵守，可通过偏差申请豁免 |
| Advisory | 5 | 建议遵守，可以有理由不遵循 |

## 常见违规模式统计

| 规则 | 最常见违规场景 | Sprint 1 中出现的频率 |
|:-----|:---------------|:---------------------:|
| Rule 10.1 | 隐式整型提升 | 🔴 极高 |
| Rule 8.13 | 指针参数缺少 const | 🔴 高 |
| Rule 16.3 | switch 缺 default | 🔴 高 |
| Rule 11.3 | 指针强制转换（硬件地址） | 🟡 中 |
| Rule 12.1 | 运算符优先级括号缺失 | 🟡 中 |
| Rule 13.2 | 副作用表达式 | 🟡 中 |
| Rule 8.7 | 未加 static | 🟢 低 |

---

*更新: 2026-07-06 | 覆盖规则: 30 条核心 MISRA C:2012 规则（已标注 C:2023 差异化）*
*由 Sprint 1 RAG 索引任务生成 — 基于 docs/llm-strategy.md §4.2 MISRA 规则索引架构*

---

## 附录 A：MISRA C:2023 与 C:2012 差异对比

> 本节列出 MISRA C:2023 相较于 C:2012 的关键变化，以及对 yuleOSH 当前 30 条核心规则索引的影响。
> 完整差异分析见 `docs/misra-2023-roadmap.md` §2。

### A.1 概览：版本间规则数量变化

| 分类 | C:2012 (+Amd.1) | Addendum 2 (Security) | C:2023 全量 | 净变化 |
|:-----|:----------------:|:---------------------:|:-----------:|:------:|
| Mandatory | ~17 | +0 | ~18 | +1 |
| Required | ~114 | +5 | ~128 | +9 |
| Advisory | ~71 | +0 | ~79 | +8 |
| Directive | ~12 | +0 | ~16 | +4 |
| **Subtotal** | **~209** | **+45** | — | — |
| Security | — | (纳入核心) | **+40** | +40 |
| **总计** | **~209** | — | **~248** | **+39** |

### A.2 新增规则类别速查

MISRA C:2023 新增或显著强化的规则类别：

| 类别 | 规则数 | 典型规则 | 影响等级 |
|:-----|:------:|:---------|:--------:|
| **安全扩展集** | ~40 | 缓冲区溢出防护、输入验证、整数溢出检查 | 🔴 高 |
| **_Generic 选择式** | ~5 | Rule 1.5: 不得产生副作用的参数 | 🟡 中 |
| **复合字面量** | ~3 | Rule 8.18: 复合字面量不得非常量初始化 | 🟡 中 |
| **restrict 约束** | ~2 | Rule 2.8: restrict 指针不得指向重叠对象 | 🟡 中 |
| **线程安全** | ~6 | Rule 22.7-22.12: C11 threads.h 规则 | 🟡 中 |
| **严格别名** | ~2 | Rule 11.10: 指针算术不得用于非数组指针 | 🔴 高 |
| **偏差模板标准化** | — | MISRA Compliance 2020 框架对齐 | 🟢 低 |

### A.3 30 条核心索引规则的 C:2023 变更状态

| # | 规则 | C:2023 状态 | 变化内容 | 对 yuleOSH 的影响 |
|:-:|:-----|:-----------:|:--------|:-----------------|
| 1 | Rule 1.1 | ⚠️ 修改 | 放松对 `__attribute__` 等常见编译器扩展的限制 | 白名单可放宽 |
| 2 | Rule 2.2 | ⚠️ 修改 | 放宽死代码判定，允许调试宏展开的死代码 | cppcheck 抑制策略需更新 |
| 3 | Rule 5.1 | ✅ 未变 | 标识符命名冲突规则无变化 | 无需变更 |
| 4 | Rule 5.6 | 🔴 移除/合并 | 与 Rule 5.8 语义重复，已合并 | 索引中删除此项 |
| 5 | Rule 8.2 | ✅ 未变 | 函数声明参数类型规则无变化 | 无需变更 |
| 6 | Rule 8.4 | ✅ 未变 | 外部定义可见性无变化 | 无需变更 |
| 7 | Rule 8.7 | ✅ 未变 | 外部链接规则无变化 | 无需变更 |
| 8 | Rule 8.13 | ⚠️ 修改 | 允许某些嵌入式回调省略 const | AI Agent 审查标准需更新 |
| 9 | Rule 9.1 | ✅ 未变 | 未初始化变量规则无变化 | 无需变更 |
| 10 | Rule 10.1 | ⚠️ 修改 | 整型转换规则细化，新增异常路径 | cppcheck misra-addon 需更新 |
| 11 | Rule 10.3 | ⚠️ 修改 | 赋值窄化转换逻辑调整 | cppcheck 规则需重检 |
| 12 | Rule 10.4 | ⚠️ 修改 | 表达式类型不匹配判定条件调整 | cppcheck 规则需重检 |
| 13 | Rule 11.3 | ⚠️ 修改 | 指针转换规则更严格，新增 MMIO 访问例外路径 | 白名单配置需更新 |
| 14 | Rule 11.4 | ✅ 未变 | 对象指针转换规则无变化 | 无需变更 |
| 15 | Rule 12.1 | ✅ 未变 | 运算符优先级无变化 | 无需变更 |
| 16 | Rule 12.2 | ✅ 未变 | 表达式副作用无变化 | 无需变更 |
| 17 | Rule 13.2 | ✅ 未变 | 副作用求值顺序无变化 | 无需变更 |
| 18 | Rule 14.3 | ✅ 未变 | 控制表达式常量无变化 | 无需变更 |
| 19 | Rule 15.1 | ✅ 未变 | goto 语句无变化 | 无需变更 |
| 20 | Rule 15.4 | ✅ 未变 | 迭代计数器 break 无变化 | 无需变更 |
| 21 | Rule 16.1 | ✅ 未变 | switch 标签唯一性无变化 | 无需变更 |
| 22 | Rule 16.3 | ✅ 未变 | switch 缺 default 无变化 | 无需变更 |
| 23 | Rule 16.6 | ⚠️ 修改 | switch fall-through 要求放宽，允许注释标注的贯穿 | AI Agent 审查标准需更新 |
| 24 | Rule 17.2 | ⚠️ 修改 | 递归禁止规则增加 tail-recursion 例外 | cppcheck 配置需更新 |
| 25 | Rule 18.4 | ⚠️ 修改 | 指针算术规则新增安全操作模式 | AI Agent 审查标准需更新 |
| 26 | Rule 18.5 | ⚠️ 修改 | VLA 规则在 C:2023 中新增例外路径 | AI Agent 审查标准需更新 |
| 27 | Rule 20.9 | ✅ 未变 | #undef 文档化要求无变化 | 无需变更 |
| 28 | Rule 21.1 | ✅ 未变 | 标准库宏重定义无变化 | 无需变更 |
| 29 | Rule 21.12 | ⚠️ 修改 | 放宽对 abort/exit 的限制（允许看门狗复位场景） | 白名单配置需更新 |
| 30 | Rule 22.1 | ⚠️ 修改 | 部分规则删除（放宽 setjmp/longjmp 限制） | 抑制策略需更新 |

### A.4 yuleOSH 覆盖状态总表

| 覆盖层级 | 30 条核心 | 全量 ~248 条 | 说明 |
|:---------|:---------:|:------------:|:------|
| ✅ 完全覆盖 | 17 | ~130 | C:2012 规则在 C:2023 中未变或微小变化 |
| ⚠️ 需更新 | 12 | ~50 | 规则有修改，需更新检测/审查策略 |
| 🔴 需删除 | 1 | ~5 | 规则被合并或移除 |
| ❌ 不覆盖（新增） | — | ~63 | C:2023 新增规则，需新引入检测 |

### A.5 升级行动项摘要

| 优先级 | 行动 | 负责角色 | 关联文档 |
|:------:|:-----|:--------:|:--------|
| 🔴 P0 | 更新 cppcheck 抑制策略（Rule 2.2, 10.x, 21.12） | 小克 | `misra-rules.yaml`, `ci-config.yaml` |
| 🔴 P0 | 更新 AI Agent 审查 prompt（Rule 8.13, 16.6, 17.2, 18.4-5） | 小克 | `docs/llm-strategy.md` |
| 🟡 P1 | 删除 Rule 5.6 索引 | 小马 | 本文档 |
| 🟡 P1 | 更新偏差管理模板（MISRA Compliance 2020 对齐） | 小马 | `docs/misra-deviations.md` |
| 🟢 P2 | 引入 40 条安全扩展集规则的 RAG 索引 | 小克 | `misra-rules.yaml` |
| 🟢 P2 | 更新验证计划中的 C:2023 引用 | 小马 | `docs/misra-verification-plan.md` |

### A.6 新增安全扩展集规则（高优先级速查）

MISRA C:2023 将此前独立的安全扩展集（原 Addendum 2）正式纳入核心标准。以下为高影响力新增规则：

| 规则 ID | 分类 | 描述 | 嵌入式场景 |
|:--------|:----:|:-----|:-----------|
| Rule 23.1 | Required | 缓冲区写入前应进行边界检查 | memcpy、sprintf 等 |
| Rule 23.2 | Required | 指针不得超出有效缓冲区范围 | 指针算术防御 |
| Rule 23.3 | Required | 字符串操作函数应使用 n 系列版本 | strcpy→strncpy |
| Rule 23.4 | Required | 整数运算前应检查溢出条件 | 加法、乘法前守卫 |
| Rule 23.5 | Required | 危险函数（gets、scanf 等）不得使用 | 输入验证 |
| Rule 23.6 | Required | 格式化字符串不得从外部输入构建 | printf 安全 |
| Rule 23.7 | Required | 文件路径操作应经过验证 | 文件 IO 安全 |
| Rule 23.8 | Required | 数据应进行完整性校验 | CRC、校验和 |
| Rule 22.7 | Required | 线程入口函数应具有受控生命周期 | C11 threads |
| Rule 22.8 | Required | 共享数据访问应使用同步机制 | 互斥量、信号量 |
| Rule 22.9 | Required | 线程终止应有序进行 | 线程清理 |
| Rule 22.10 | Required | 原子操作应使用原子类型 | C11 atomics |
| Rule 22.11 | Required | 条件变量应配合互斥量使用 | CV 安全模式 |
| Rule 22.12 | Required | 线程本地存储应明确作用域 | TLS 正确使用 |

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Built-in skills shipped with yuleOSH.

The bundled library covers the three highest-value coding domains for the
Harness Coding pipeline:

* ``autosar-coding`` — AUTOSAR C coding conventions (embedded, BSW/RTE style).
* ``misra-fix``      — patterns for fixing MISRA C violations.
* ``python-testing`` — pytest best practices for yuleOSH tools/tests.

These skills are auto-registered by :func:`yuleosh.skills.registry.get_registry`
and can be spliced into LLM prompts with :func:`yuleosh.skills.prompt.render_skills`.
"""

from __future__ import annotations

from yuleosh.skills.model import Skill

_AUTOSAR_CODING_CONTENT = """\
### AUTOSAR C 编码规范要点（嵌入式 BSW / RTE）

1. **头文件纪律**
   - 每个模块一个头文件，命名 `模块名.h`（如 `Dio.h`、`CanIf.h`）；使用 include guard：
     ```c
     #ifndef DIO_H
     #define DIO_H
     /* ... */
     #endif /* DIO_H */
     ```
   - 头文件只放声明与宏，不放函数定义；禁止在头文件中定义变量（`extern` 声明 + `.c` 定义）。

2. **命名规范**
   - 模块级函数：`模块名_动作`（如 `Dio_ReadChannel`）；全局宏/类型：全大写 + 模块前缀。
   - 变量：小驼峰（`channelId`）；类型：`Std_ReturnType`、`Dio_ChannelType` 等 AUTOSAR 标准类型。

3. **AUTOSAR 标准类型**
   - 使用 `Std_Types.h` 提供的 `uint8`/`uint16`/`uint32`/`sint8`/`boolean`/`Std_ReturnType`，
     禁止裸 `int`/`char` 出现在接口签名中。
   - 函数返回值语义：`E_OK` / `E_NOT_OK`，用 `Std_ReturnType` 表达。

4. **接口与耦合**
   - 通过 RTE 或模块接口调用，禁止跨模块直接访问全局变量；错误处理用返回值而不是 `assert`。
   - 回调/中断函数保持短小，只做标志置位与数据搬运。

5. **可移植性**
   - 不依赖具体编译器扩展（`__attribute__` 需宏封装）；位操作使用 `SET_BIT/CLEAR_BIT` 宏。
   - 固定宽度类型 + `endianness` 显式处理。

6. **注释**
   - 每个函数头注释：功能、参数、返回值、前置/后置条件；关键算法步骤行内注释。
"""

_MISRA_FIX_CONTENT = """\
### MISRA 违规修复模式

1. **Rule 8.4 / 8.5（外部链接一致性）**
   - 症状：函数定义无 `extern` 头文件声明。
   - 修复：在模块头文件加原型声明，`.c` 中定义前 `#include` 对应头文件。

2. **Rule 10.1~10.6（基本类型不匹配）**
   - 症状：`uint8` 与 `int` 混用、隐式符号转换。
   - 修复：统一使用 AUTOSAR 标准类型；转换必须显式 cast：`(uint8)(x & 0xFFu)`。

3. **Rule 11.3 / 11.4（指针转换）**
   - 症状：整型 ↔ 指针隐式转换、`void*` 转具体指针。
   - 修复：使用 `(uintptr_t)` 中转 + 显式 cast；禁止 `reinterpret_cast` 风格直接转换。

4. **Rule 13.5（短路求值副作用）**
   - 症状：`&&` / `||` 右侧含副作用表达式。
   - 修复：先求值存入局部变量，再参与逻辑运算。

5. **Rule 15.x（switch 穿透）**
   - 症状：`case` 无 `break` 导致 fall-through。
   - 修复：每个 `case` 以 `break;`/`return;` 结束；如需 fall-through 用注释
     `/* fall through */` 并加 deviation。

6. **Rule 17.7（函数返回值必须使用）**
   - 症状：忽略 `Std_ReturnType` 返回值。
   - 修复：检查返回值并处理 `E_NOT_OK` 分支。

7. **Rule 21.x（标准库误用）**
   - 症状：嵌入式代码直接调用 `printf`/`malloc`。
   - 修复：改用项目提供的日志/内存池抽象（如 `EcuM` 日志宏、静态缓冲池）。

> 每次修复后重新跑 MISRA 静态检查（cppcheck），确保违规数下降且无新增。
"""

_PYTHON_TESTING_CONTENT = """\
### pytest 最佳实践（yuleOSH）

1. **文件与命名**
   - 测试文件：`tests/test_<模块>_<场景>.py`；函数：`test_<行为>_<条件>`。
   - 使用 pytest fixtures 而不是 `setUp/tearDown`。

2. **隔离与确定性**
   - 不依赖真实网络/LLM：注入 `llm_client` mock（见 `PipelineSession(llm_client=...)`）。
   - 临时文件一律用 `tmp_path` fixture，不写仓库内固定路径。

3. **断言**
   - 用 `assert` 而非 `unittest` 方法；比较浮点用 `pytest.approx`。
   - 对预期异常用 `pytest.raises`，并断言异常消息关键片段。

4. **参数化**
   - 同逻辑多输入用 `@pytest.mark.parametrize`，避免复制粘贴用例。

5. **覆盖率**
   - 新模块要求行覆盖率 ≥ 60%；用 `--cov=src/yuleosh --cov-report=term-missing` 验证。
   - 对分支（失败路径、retry 循环）单独写用例，不要只测 happy path。

6. **mock 原则**
   - 用 `unittest.mock.patch` 打桩外部副作用；`patch.object` 优先于整模块替换。
   - mock 返回值与真实接口一致（dict 带 `content`/`usage`），避免测试与实现脱节。
"""


def builtin_skills() -> list[Skill]:
    """Return the bundled skills (fresh instances each call)."""
    return [
        Skill(
            name="autosar-coding",
            title="AUTOSAR C 编码规范要点",
            description="嵌入式 AUTOSAR BSW/RTE 的 C 编码规范：头文件、命名、标准类型与接口纪律。",
            content=_AUTOSAR_CODING_CONTENT,
            tags=["c", "autosar", "embedded", "coding-standard"],
            version="1.0.0",
        ),
        Skill(
            name="misra-fix",
            title="MISRA 违规修复模式",
            description="常见 MISRA C 违规的修复模式：类型转换、指针、switch 穿透、返回值。",
            content=_MISRA_FIX_CONTENT,
            tags=["c", "misra", "static-analysis", "fix-patterns"],
            version="1.0.0",
        ),
        Skill(
            name="python-testing",
            title="pytest 最佳实践",
            description="yuleOSH 工具/测试的 pytest 最佳实践：fixtures、mock、参数化与覆盖率。",
            content=_PYTHON_TESTING_CONTENT,
            tags=["python", "pytest", "testing", "quality"],
            version="1.0.0",
        ),
    ]


BUILTIN_SKILL_NAMES: list[str] = ["autosar-coding", "misra-fix", "python-testing"]

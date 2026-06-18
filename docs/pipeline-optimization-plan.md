# 🐴 Pipeline 优化路径规划

> **规划人**: 小马 🐴（质量架构师）
> **审查依据**: 老陈 👨‍🏫 Pipeline 完整性审查报告 (2026-06-18)
> **综合评分**: 58/100 → 一轮目标 85/100；二轮实评 70/100；三轮实评 76/100；Sprint 目标 87+/100
> **预计总周期**: 6~8 周（并行实施可缩短至 4~5 周）

---

## 目录

1. [P0 — 必须优化项](#p0-必须优化项)
2. [P1 — 重要优化项](#p1-重要优化项)
3. [P2 — 加分优化项](#p2-加分优化项)
4. [二轮审查新增缺口](#二轮审查新增缺口)
5. [优化路径总览甘特图](#优化路径总览)
6. [验收判定](#验收判定)

---

## P0 — 必须优化项

> **核心标准**: 这些缺口直接导致 Pipeline 无法通过 ASPICE CL1 审计，或使得嵌入式 CI Pipeline 名不副实。**必须在本 Milestone（目标 v1.3.0）内完成。**

---

### P0-01：嵌入式 C 单元测试框架集成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 3.3 (C 单元测试), 1.2 (SWE.3 SWE.4 过渡) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 当前 L1 的 `unit-tests` 仅运行 Python pytest。对嵌入式 C 项目而言，C 语言级别的单元测试框架缺失是审计硬伤。ASPICE SWE.4 要求单元验证在实现语言层面执行，不能以 Python 测试框架代替 C 单元测试。 |
| **建议实施方案** | 1. 集成 **Unity + CMock**（或 Ceedling）作为 C 语言单元测试框架<br>2. 在 L1 层增加 `c-unit-tests` step handler，与现有 pytest 并行运行<br>3. 为新框架定义 test harness 模板（test/unity/ 目录结构）<br>4. 集成 CMock 自动生成 mock 代码，用于 HAL/外设依赖解耦<br>5. 在 L1 层增加 C 单元测试覆盖率报告（gcov/lcov）<br>6. 提供 `yuleosh test c --create-suite <module>` CLI 脚手架命令<br>7. 更新 MISRA 验证计划文档，明确 C 单元测试覆盖要求 |
| **负责人建议** | 小克 👨‍💻（开发实现）+ 小马 🐴（验收标准定义） |
| **估算工时** | 5~8 人天 |
| **依赖关系** | 无外部依赖；需确认 GCC 工具链是否已预装 gcov/lcov |
| **SHALL 规范** | `SWE-PLN-CUT1`: Pipeline SHALL 在 L1 层包含 C 语言单元测试步骤<br>`SWE-PLN-CUT2`: C 单元测试 SHALL 使用专用测试框架（Unity/Ceedling 或等价框架）<br>`SWE-PLN-CUT3`: C 单元测试覆盖率 SHALL 由 gcov/lcov 生成 |

---

### P0-02：链接脚本审查 Step Handler

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 2.2 (缺失审查: 链接脚本), 3.1 (.ld 验证) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 链接脚本 (.ld / .scatter) 控制代码和数据的物理内存布局（RAM/FLASH/CCM/DTCM）。错误的符号定位、栈/堆区域重叠、中断向量表偏移错误，是嵌入式项目最常见的静默失败原因。当前 Pipeline 对此完全无覆盖。 |
| **建议实施方案** | 1. 在 L2 层新增 `linker-script-review` step handler，作为 Agent 审查节点<br>2. 脚本核心检查项（由 Agent + 自动化工具联合执行）：<br>   - ✅ 内存区域（MEMORY）段定义完整性（FLASH/RAM/CCM）<br>   - ✅ 栈（Stack）区域大小与位置是否合理<br>   - ✅ 堆（Heap）区域是否存在，大小是否可配置<br>   - ✅ 中断向量表是否放在 FLASH 起始位置<br>   - ✅ .text / .rodata / .data / .bss / .heap / .stack 各段逻辑分离<br>   - ✅ 段地址对齐检查（如 ALIGN(4) / ALIGN(8)）<br>   - ✅ `_sstack` / `_estack` / `_sdata` / `_edata` 等符号定义完整性<br>   - ✅ Debug vs Release 配置下 .ld 文件差异<br>3. 可选自动化：`ld-check.py` 脚本，解析 .map 文件验证符号位置<br>4. MR Blocking：链接脚本修改必须经过 Agent 审查通过 |
| **负责人建议** | 小克 👨‍💻（handler 实现）+ 小马 🐴（Agent prompt/checklist 定义） |
| **估算工时** | 3~4 人天 |
| **依赖关系** | 需要定义 `.ld` 文件扫描路径配置项 |
| **SHALL 规范** | `SWE-PLN-LK1`: Pipeline SHALL 在 L2 层包含链接脚本审查步骤<br>`SWE-PLN-LK2`: 链接脚本审查 SHALL 覆盖内存区域、各段分离、栈/堆配置、向量表位置 |

---

### P0-03：启动代码 / 中断向量表审查 Step Handler

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 2.2 (启动代码审查), 3.1 (启动代码检查) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 启动代码（startup_*.s / reset_handler / SystemInit）是整个嵌入式系统最脆弱的环节。向量表初始化、堆栈指针 SP 设置、BSS 清零、data 段复制、SystemInit 调用序列——任何一个出错都导致系统静默不干活。目前无 Agent/Automation 覆盖。 |
| **建议实施方案** | 1. 在 L2.5 层（硬件验证前置阶段）新增 `startup-review` step handler<br>2. Agent 审查 checklist：<br>   - ✅ 向量表第一项（SP initial value）是否正确指向栈顶<br>   - ✅ 向量表第二项（Reset_Handler）是否存在<br>   - ✅ Default_Handler 是否为弱符号（WEAK），所有 ISR 是否覆盖<br>   - ✅ BSS 清零循环语法正确（LDR/STR/CMP/BCC）<br>   - ✅ .data 段复制逻辑：_sdata, _edata, _sidata 三符号正确<br>   - ✅ SystemInit 调用在进入 main() 之前完成<br>   - ✅ FPU 使能（SCB->CPACR）— 对于 Cortex-M4/M7/M33<br>   - ✅ 中断优先级分组设置（SCB->AIRCR）<br>3. 可选：在 QEMU SIL 测试中增加 startup 验证断言<br>4. 提供启动代码模板参考，开发者可 `yuleosh scaffold startup` 生成 |
| **负责人建议** | 小克 👨‍💻（step handler）+ 小马 🐴（checklist / Agent prompt） |
| **估算工时** | 3~4 人天 |
| **依赖关系** | 无 |
| **SHALL 规范** | `SWE-PLN-STUP1`: Pipeline SHALL 包含启动代码审查步骤<br>`SWE-PLN-STUP2`: 启动代码审查 SHALL 覆盖向量表、BSS 清零、data 复制、SystemInit、FPU 配置 |

---

### P0-04：SWE.6 合格性测试（系统级端到端测试）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 1.2 (SWE.6 严重薄弱), 4.1 (CL1 不通过) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 当前 SWE.6 仅有一个 `final-report` 步骤。ASPICE SWE.6 要求完整的三段式流程：① 合格性测试规范定义 → ② 合格性测试执行 → ③ 结果评估与结构化报告。这是 CL1 审计通过的直接门槛。 |
| **建议实施方案** | 1. **新增「合格性测试规范」步骤**（SWE.6 左侧）— 定义通过标准：<br>   - 功能需求 vs 验收测试用例的映射表<br>   - 每项测试的通过/失败判据<br>   - 默认 PASS 率阈值（例如 ≥95%）<br>2. **新增「合格性测试执行」步骤**（SWE.6 中间）— 放在 L3 层：<br>   - 运行系统级 E2E 测试（含 QEMU SIL + 可选硬件 HIL）<br>   - 输出 JSON 测试执行报告<br>3. **重构 final-report 为结构化报告**（SWE.6 右侧输出）：<br>   - 合格性测试规范 → 测试结果追溯表格<br>   - 未通过项 + 偏差清单 + 风险评估<br>   - 系统质量总结 + 发布建议<br>4. 提供 `yuleosh test swe6` CLI 命令生成报告 |
| **负责人建议** | 小明 🧑‍💻（需求方，定义合格标准）+ 小克 👨‍💻（实现）+ 小马 🐴（验收判定） |
| **估算工时** | 5~7 人天 |
| **依赖关系** | 依赖 P0-01 (C 单元测试框架) 的部分输出作为 SWE.6 的证据链；依赖于 spec-check 步骤建立的需求基线 |
| **SHALL 规范** | `SWE-PLN-SWE6-1`: Pipeline SHALL 在 SWE.6 域包含合格性测试规范定义步骤<br>`SWE-PLN-SWE6-2`: Pipeline SHALL 在 L3 层包含合格性测试执行步骤<br>`SWE-PLN-SWE6-3`: 合格性测试报告 SHALL 包含规范↔测试↔结果的追溯链 |

---

### P0-05：Pipeline Profile 切换（嵌入式安全模式 vs 通用模式）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 4.2 (过程适应性调整), 老陈建议 §5.4 |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 当前 Pipeline 只有一种运行模式。对于不同类型项目（通用 MCU 项目 vs 安全关键汽车项目），检查的严格度、步骤数量、性能开销差异巨大。缺乏 profile 机制会导致：① 小项目负担过重；② 安全项目遗漏关键检查。 |
| **建议实施方案** | 1. 在 `ci-config.yaml` 中新增 `pipeline.profile` 配置项，支持三个预设 Profile：<br>   - **`general`**（通用模式）：当前默认配置，适合非安全关键项目<br>   - **`embedded`**（嵌入式安全模式）：增加 P0-02~P0-04 全部嵌入式审查，MISRA Required 阻断，内存安全阻断<br>   - **`automotive`**（汽车安全模式）：在 embedded 基础上增加 ASPICE CL2 级追踪要求、偏差审批工作流、AUTOSAR 检查<br>2. Profile 切换逻辑：<br>   - 配置文件显式声明 `pipeline.profile: embedded`<br>   - 自动检查 profile 一致性：profile 要求的 step 是否都存在<br>3. Profile 自定义扩展：允许项目在 preset 基础上增减 check handler<br>4. 提供 `yuleosh config profile list` 查看可用 Profile<br>5. 提供 `yuleosh config profile check <profile>` 验证当前配置 |
| **负责人建议** | 小克 👨‍💻（核心实现）+ 小马 🐴（profile 内容定义 + 验收判定） |
| **估算工时** | 4~5 人天 |
| **依赖关系** | 依赖 P0-02~P0-04 的 step handler 存在（embedded profile 需要它们） |
| **SHALL 规范** | `SWE-PLN-PROF1`: Pipeline SHALL 支持至少两种 Profile（general / embedded）切换<br>`SWE-PLN-PROF2`: Profile 配置 SHALL 在 ci-config.yaml 中声明<br>`SWE-PLN-PROF3`: Pipeline SHALL 在启动时校验 Profile 所需 step handler 全部可用 |

---

## P1 — 重要优化项

> **核心标准**: 这些缺口显著影响嵌入式项目的可靠性和 CI 效率，应当在本 Milestone 内完成或至少排入下个 Sprint。

---

### P1-01：堆栈使用分析

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 3.1 (堆栈使用分析), 5.4 (建议增加) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 当前 L2 的 "memory safety" 仅为 info 级别，未实际运行分析工具。堆栈溢出是嵌入式实时系统 #1 运行时崩溃原因。FreeRTOS 的 `uxTaskGetStackHighWaterMark()` 和 GCC 的 `-fstack-usage` 选项均可提供数据，但 Pipeline 未集成。 |
| **建议实施方案** | 1. 在 L2 层新增 `stack-analysis` step handler（moved from info to formal）<br>2. 静态分析法：GCC `-fstack-usage` 编译 → 解析 `.su` 文件 → 生成堆栈深度最大值<br>3. 动态分析法（可选，建议 L2.5）：<br>   - QEMU SIL 中运行任务，调用 `uxTaskGetStackHighWaterMark()`<br>   - 记录每个任务的高水位标记<br>4. 输出报告：任务名 / 堆栈大小 / 峰值使用 / 利用率百分比 / 风险等级（🟢🟡🔴）<br>5. 阻断策略：堆栈使用 ≥85% → warning；≥95% → blocking<br>6. 提供 `yuleosh analyze stack` CLI 命令 |
| **负责人建议** | 小克 👨‍💻 |
| **估算工时** | 2~3 人天 |
| **依赖关系** | 需要 GCC `-fstack-usage` 编译选项；FreeRTOS 项目需要 `INCLUDE_uxTaskGetStackHighWaterMark` 配置启用 |
| **SHALL 规范** | `SWE-PLN-STACK1`: Pipeline SHALL 在 L2 层包含堆栈使用分析步骤<br>`SWE-PLN-STACK2`: 堆栈使用率 ≥95% 时 SHALL 阻断 Pipeline |

---

### P1-02：RTOS 任务配置审查 Step Handler

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 2.2 (RTOS 配置审查), 3.1 (FreeRTOSConfig.h 检查) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | FreeRTOSConfig.h 中配置项（configMINIMAL_STACK_SIZE, configTOTAL_HEAP_SIZE, 任务优先级、IPC 超时）是 RTOS 行为的基础。优先级反转、死锁、堆栈配置不足是实时系统 Top 3 运行时错误来源。当前无 Agent 审查覆盖。 |
| **建议实施方案** | 1. 在 L2 层新增 `rtos-config-review` step handler（Agent 审查）<br>2. Agent 审查 checklist：<br>   - ✅ configMINIMAL_STACK_SIZE 是否合理（建议 ≥ configMINIMAL_STACK_SIZE * 2）<br>   - ✅ configTOTAL_HEAP_SIZE 是否匹配 MCU SRAM 大小<br>   - ✅ configUSE_PREEMPTION / configUSE_TIME_SLICING 一致性<br>   - ✅ 任务优先级分布：是否存在两个任务相同优先级且导致优先级反转<br>   - ✅ IPC 超时是否为 0（portMAX_DELAY？可能导致死锁）<br>   - ✅ configASSERT 是否定义（建议 Debug 配置启用）<br>   - ✅ configCHECK_FOR_STACK_OVERFLOW 是否 > 0<br>   - ✅ configUSE_MUTEX / configUSE_RECURSIVE_MUTEX 配置准确性<br>3. 自动化辅助：检查 FreeRTOSConfig.h 中关键宏是否定义 |
| **负责人建议** | 小马 🐴（Agent prompt/checklist）+ 小克 👨‍💻（handler scaffold） |
| **估算工时** | 2~3 人天 |
| **依赖关系** | 无 |
| **SHALL 规范** | `SWE-PLN-RTOS1`: Pipeline SHALL 包含 RTOS 任务配置审查步骤<br>`SWE-PLN-RTOS2`: 审查 SHALL 覆盖堆栈配置、优先级、IPC 超时、assert 等关键项 |

---

### P1-03：外设寄存器（MMIO）审查

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 3.1 (外设寄存器配置检查) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 时钟树、GPIO 复用功能、中断优先级分组、DMA 通道映射——这些传统上由开发者人工审查的硬件配置，Pipeline 完全没有覆盖。错误配置可能导致外设不工作、EMC 问题或电源异常。 |
| **建议实施方案** | 1. 在 L2.5 层新增 `mmio-config-review` step handler（Agent 审查）<br>2. Agent 审查 checklist：<br>   - ✅ 外设时钟使能顺序是否正确（RCC->AHBENR / APB1ENR / APB2ENR）<br>   - ✅ GPIO 复用功能（AFR）配置是否与芯片引脚功能一致<br>   - ✅ 中断优先级分组（NVIC->IPRy 和 SCB->AIRCR PRIGROUP）一致性<br>   - ✅ DMA 通道映射是否符合芯片 DMA 请求映射表<br>   - ✅ SysTick 重装载值计算是否正确<br>   - ✅ ADC/DAC 采样时间是否符合数据手册<br>3. 自动化辅助：从 `stm32_hal.h` / `esp_system.h` 提取 MCU 勘误表（Errata）工作区检查<br>4. 可选：提供 MCU 特定配置文件（如 STM32F4 / ESP32-S3 各自寄存器约束） |
| **负责人建议** | 小马 🐴（硬件知识 + checklist） |
| **估算工时** | 3~4 人天 |
| **依赖关系** | 需要 MCU 符号/库头文件可被 Pipeline 访问 |
| **SHALL 规范** | `SWE-PLN-MMIO1`: Pipeline SHALL 包含外设寄存器配置审查步骤<br>`SWE-PLN-MMIO2`: 审查 SHALL 覆盖时钟使能、GPIO 复用、NVIC 优先级分组、DMA 映射 |

---

### P1-04：CI MISRA 增量模式优化（L1 + L2 双重 MISRA）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 5.3 (MISRA 位置), 5.4 (Delta MISRA) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 当前 MISRA 在 L1 和 L2 都跑，但 L1 跑的是全量检查。对大项目来说，每次提交等待 cppcheck MISRA 全量检查（8~15 分钟）不可接受。应实现 L1 delta + L2 full 的双层策略。 |
| **建议实施方案** | 1. **L1 (commit)：Delta MISRA**<br>   - 用 `git diff --name-only HEAD~1` 获取修改的 `.c` / `.h` 文件<br>   - 只对这些文件运行 cppcheck MISRA<br>   - **阻断规则**：新增 Required 违规 → blocking<br>2. **L2 (MR/PR)：Full MISRA**<br>   - 对全部源文件运行全量 cppcheck MISRA<br>   - **阻断规则**：Required 违规零增量增长 → blocking（验证比上一轮不增加 Required 违规）<br>3. **L2.5/L3：Full MISRA + 趋势报告**<br>   - 全量运行 + 违规密度 / KLOC、新增率、修复率趋势图表<br>4. **MISRA & L2 memory safety 联动**<br>   - 将 memory safety 从 info 升级为正式检查<br>   - 集成 AddressSanitizer（已在上次 MISRA 审查推荐）<br>   - 在 L2 层 `memory-safety` 阻断 Pipeline（found new violations → fail）<br>5. 配置项：`misra.delta.mode` / `misra.delta.comparison_ref` |
| **负责人建议** | 小克 👨‍💻（实现 delta check）+ 小马 🐴（趋势对接 + 验收判定） |
| **估算工时** | 3~4 人天 |
| **依赖关系** | 已有 `--delta` 参数支持（验收矩阵 §1.8 ✅），但需要实现真实增量逻辑 vs 当前的全量 <br>依赖 git 命令在 CI 环境中可用 |
| **SHALL 规范** | `SWE-PLN-MSR-D1`: L1 层 MISRA SHALL 使用 delta 模式（仅检查修改文件）<br>`SWE-PLN-MSR-D2`: L2 层 MISRA SHALL 使用全量模式 + 零增量增长策略<br>`SWE-PLN-MSR-D3`: MISRA 增量阻断 SHALL 作用于新增 Required 违规 |

---

## P2 — 加分优化项

> **核心标准**: 这些缺口属于成熟度提升项。建议在 P0、P1 完成后作为持续改进的一部分纳入，或在 Dashboard 中标记为 "planned"。

---

### P2-01：硬件抽象层（HAL）接口契约检查

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 2.2 (HAL 验证审查) |
| **优先级** | 🟢 **P2 — 加分** |
| **缺口描述** | HAL/BSP 层是应用代码与硬件的桥梁。HAL 接口签名的变更可能导致底层驱动异常，但当前 Pipeline 无接口契约一致性检查。 |
| **建议实施方案** | 1. 定义 HAL 接口契约文件（hal-contracts.yaml）<br>2. 在 L2 层增加 `hal-contract-check` step handler<br>3. 检查项：接口签名一致性 / 返回值类型 / 超时参数 / 错误码统一<br>4. LLVM 的 Lattice 或 CTAD 作为可选分析工具 |
| **估算工时** | 2~3 人天 |

---

### P2-02：BSP 板级支持包验证

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 2.2 (BSP 层) |
| **优先级** | 🟢 **P2 — 加分** |
| **缺口描述** | 多板支持项目（STM32F4 + STM32H7 + ESP32）中，BSP 的 pin-mux 配置、时钟配置、外设初始化代码需要跨板一致性验证。 |
| **建议实施方案** | 1. 定义 BSP 描述文件（bsp-<board>.yaml）<br>2. 在 L2.5 层增加 `bsp-validation` step handler<br>3. 验证 BSP 定义与硬件原理图配置的一致性<br>4. 自动检测跨板配置漂移 |
| **估算工时** | 3~4 人天 |

---

### P2-03：编译输出验证（Map File / Binary Size）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 3.2 (代码尺寸变化), 5.4 (建议: 编译输出验证) |
| **优先级** | 🟢 **P2 — 加分** |
| **缺口描述** | 资源受限 MCU（STM32, ESP32 等）的 .text / .data / .bss 段尺寸变化直接影响项目可行性。当前 Pipeline 无 map file 解析和 binary size diff 追踪。 |
| **建议实施方案** | 1. 在 L2 层增加 `build-output-check` step handler<br>2. 解析 `.map` 文件提取各段尺寸：.text / .data / .bss / .stack / .heap<br>3. 与上一次成功构建对比尺寸 diff<br>4. 配置阈值：`.text +10%` → warning；`.text +20%` → blocking<br>5. 集成到趋势报告（尺寸变化 → 趋势 JSONL） |
| **估算工时** | 2~3 人天 |

---

### P2-04：低功耗 / 能效审查

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | 3.1 (看门狗/安全机制), 老陈建议 §3.1 |
| **优先级** | 🟢 **P2 — 加分** |
| **缺口描述** | 电池供电嵌入式项目的功耗管理是产品核心能力。看门狗刷新时序、休眠模式配置、时钟门控等影响功耗和安全性的配置需要审查。 |
| **建议实施方案** | 1. 在 L2.5 层增加 `power-review` step handler（Agent 审查）<br>2. Agent 审查 checklist：<br>   - ✅ IWDG/WWDG 看门狗配置周期 vs 主循环最坏时间<br>   - ✅ 休眠/停止/待机模式转换路径<br>   - ✅ RTC/唤醒源配置<br>   - ✅ 时钟门控（RCC->AHBxENR）配置<br>   - ✅ 未使用外设时钟禁用检查<br>3. 使用 `perf` 或 QEMU 模拟功耗分析（可选） |
| **估算工时** | 2~3 人天 |

---

## 二轮审查新增缺口

> **来源**: 老陈 👨‍🏫 二轮审查报告 (2026-06-18) — 评分 70/100 ↑12 分
> **核心问题**: 代码与文档不同步（老陈称为 *process gap*）— 优化计划 checklist 写好了，但 handler 代码没实现
> **引用老陈原话**: "**计划写得比代码好** — 优化计划中 FPU 检查、configASSERT、Default_Handler weak 都有 checklist，但 handler 代码没有实现。代码开发没有拿着 checklist 逐条打勾。"

---

### P0 级新增缺口（二轮审查发现）

---

#### G-31：SWE.6 三段式合格性测试细化（需求→场景→验证）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-31 |
| **关联一轮发现** | P0-04 (SWE.6 合格性测试) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈二轮审查指出：当前 1 步 final-report 不够，需要三段式结构化。「合格性测试是整个 V 模型的闭环，再拖就要影响 CL1 审计通过了。」三步必须是 **规范定义 → 测试执行 → 结构化报告**。 |
| **修复方案** | 1. **合格性测试规范**（SWE.6 左侧）— 功能需求→验收用例映射表，每项测试通过/失败判据，PASS 率阈值 ≥95%<br>2. **合格性测试执行**（SWE.6 中间 / L3 层）— 系统级 E2E 测试（QEMU SIL + 可选 HIL），输出 JSON 执行报告<br>3. **合格性结果评估**（现有 final-report 重构）— 规范↔结果追溯链、未通过项清单 + 偏差评估 + 发布建议<br>4. 提供 `yuleosh test swe6` CLI 命令生成全链路报告 |
| **风险** | ⚠️ 老陈明确说「SWE.6 从 #2 优先升到 #1 优先」，这是二轮中最紧迫的单一缺口 |
| **负责人建议** | 小明 🧑‍💻（定义合格标准，需求↔验收映射）+ 小克 👨‍💻（步骤实现）+ 小马 🐴（验收判定） |
| **估算工时** | 5~7 人天（含对现有 final-report 的重构） |

---

#### G-32：C 单元测试框架集成（Unity/Ceedling）— ✅ 已完成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-32 |
| **关联一轮发现** | P0-01 (C 单元测试框架) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈：「C 单元测试框架在优化计划中被列为最大失分项，但 Sprint 1 没有做，Sprint 2 也没排。它甚至不是一个单独的 Sprint 项。」一轮审查明确说这是硬缺口，ASPICE SWE.4 审计面不过去。 |
| **修复方案** | 1. 集成 Unity + CMock（或 Ceedling 全套）<br>2. 在 L1 层增加 `c-unit-tests` step handler，与现有 pytest 并行运行<br>3. 集成 gcov/lcov 生成 C 覆盖率报告<br>4. 提供 `yuleosh test c --create-suite <module>` 脚手架命令<br>5. 定义 test harness 模板目录（test/unity/）<br>6. 更新 MISRA 验证计划文档 |
| **验收状态** | ✅ **三轮审查完成** — `src/yuleosh/pipeline/step_handlers/test_c_unit.py` 已创建，`tests/unity/` 模板目录已就位，已集成到 PIPELINE_STEPS。支持 Unity runner、Ceedling、GCC 编译三种模式，自动跳过无 C 源码的项目。 |
| **负责人建议** | 小克 👨‍💻（框架集成 + handler）+ 小马 🐴（验收标准定义） |
| **估算工时** | 5~8 人天 |

---

#### G-33：Profile 切换机制（嵌入式安全 vs 通用 vs 测试）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-33 |
| **关联一轮发现** | P0-05 (Pipeline Profile 切换) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈：「4 个嵌入式审查的存在意味着 Pipeline 已经有两个 profile 的内容了，但没有机制来选择。没有 profile 机制前所有项目都要跑这些审查，对于非嵌入式用户来说是噪音。」建议**提到 Sprint 1 末段**即启动。 |
| **修复方案** | 1. ci-config.yaml 新增 `pipeline.profile` 配置项<br>2. 预设三个 Profile：<br>   - **general** — 当前默认，适合非嵌入式项目，跳过嵌入式审查<br>   - **embedded** — 开启全部 4 个嵌入式审查 + MISRA Required 阻断 + 内存安全阻断<br>   - **automotive** — embedded 基础上 + ASPICE CL2 追踪 + 偏差审批工作流 + AUTOSAR 检查<br>3. 启动时校验 profile 要求的 step handler 全部存在<br>4. 提供 `yuleosh config profile list` 和 `yuleosh config profile check` |
| **负责人建议** | 小克 👨‍💻（核心实现）+ 小马 🐴（profile 内容定义 + 验收判定） |
| **估算工时** | 4~5 人天 |

---

#### G-34：review_linker 深度补缺 — LMA/VMA 区分 + heap/stack 重叠检查 ✅ 已完成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-34 |
| **关联一轮发现** | P0-02 (链接脚本审查) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈：「LMA/VMA 和 heap/stack 重叠是嵌入式开发者最容易踩的坑。当前 review_linker 深度停留在文档级，没到实战级。.data 段的 Load Memory Address (LMA) 在 Flash，Virtual Memory Address (VMA) 在 RAM，当前代码没有检查 `AT>` 语法。」「.heap 和 .stack 如果分配到 RAM 的同一个子区域，运行时可能出现两者互相覆盖。」 |
| **修复方案** | 1. **LMA/VMA 区分检查** — 解析 `AT>` / `>REGION AT>REGION` 语法<br>   - 检查 `.data` 段 LMA（Flash）≠ VMA（RAM）<br>   - 检查 `.rodata` 是否同时提供 LMA/VMA<br>2. **heap/stack 重叠检查** — 解析 MEMORY 指令中各区域的起始和结束地址<br>   - 检查 .heap 和 .stack 是否在 RAM 内相互独立<br>   - 如果重叠 → critical blocking<br>3. **Flash 起始地址特化检查升级** — 从 info 升到 major/critical<br>   - 对 STM32 等已知架构，检查 Flash 是否从 `0x08000000` 开始<br>   - 如果偏移配置（如分区）但没有相应调整 → blocking |
| **负责人建议** | 小克 👨‍💻（代码实现）+ 小马 🐴（checklist 补充 + 验收判定） |
| **估算工时** | 2~3 人天（在现有 review_linker 基础上增量开发） |

---

#### G-35：review_startup 深度补缺 — FPU 使能（SCB->CPACR）+ SystemInit 时序 ✅ 已完成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-35 |
| **关联一轮发现** | P0-03 (启动代码审查) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈：「计划写了但代码没做」的典型例子。优化计划 P0-03 checklist 明列「FPU 使能（SCB->CPACR）— 对于 Cortex-M4/M7/M33」，但 handler 代码完全没有。「SystemInit 调用时序检查太弱——当前只匹配了 SystemInit 符号存在，没有检查它在 main() 之前被调用。」 |
| **修复方案** | 1. **FPU 使能检查** — 在 startup_*.s 中搜索 CPACR 寄存器配置：<br>   - 匹配 `LDR R0, =0xE000ED88`（CPACR 地址）<br>   - 匹配 `ORR/STR` 写入 `0x00F00000`（使能 FULLACCESS）<br>   - 如果 Cortex-M4/M7/M33 但无 CPACR 配置 → critical<br>2. **SystemInit 时序检查** — 追踪指令执行顺序：<br>   - 确认 SystemInit 在 BSS 清零之后、main() 调用之前<br>   - 如果在 main() 内调用 → major warning<br>3. **中断优先级分组检查** — 验证 SCB->AIRCR PRIGROUP 配置<br>4. 单元测试：对已知正确的 startup 样本和已知错误的样本进行回归测试 |
| **负责人建议** | 小克 👨‍💻（handler 代码更新）+ 小马 🐴（checklist / 样本用例定义） |
| **估算工时** | 1~2 人天（增量开发，非重构） |

---

#### G-36：review_rtos 深度补缺 — configASSERT + stack overflow hook ✅ 已完成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-36 |
| **关联一轮发现** | P1-02 (RTOS 配置审查) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈：「优化计划 checklist 列出的 configASSERT 和 stack overflow 检查，代码没做。configASSERT 是 FreeRTOS 排查问题的第一道防线，它的缺失是 major 级别问题。configCHECK_FOR_STACK_OVERFLOW 同样——当前 handler 只检查了栈 canary（在 review_memory 里），但 FreeRTOS 特有的栈溢出钩子没有检查。」 |
| **修复方案** | 1. **configASSERT 检查** — 搜索 FreeRTOSConfig.h 中：<br>   - `#define configASSERT` 是否定义<br>   - 如果 Debug 配置下未定义 → major blocking<br>   - 如果 Release 配置下未定义 → minor advice（生产环境可以去掉）<br>2. **configCHECK_FOR_STACK_OVERFLOW 检查** — 搜索：<br>   - `#define configCHECK_FOR_STACK_OVERFLOW` 值必须 > 0<br>   - 推荐值为 2（方法 2：栈指针有效性检查，更精确）<br>   - 同时 `#define INCLUDE_uxTaskGetStackHighWaterMark` 是否定义<br>3. **configUSE_DAEMON_TASK_STARTUP_HOOK 检查**（FreeRTOS v10+）<br>4. 集成到 RTOS 配置审查报告，标记为 critical 级别阻断 |
| **负责人建议** | 小克 👨‍💻（handler 更新）+ 小马 🐴（checklist + 验收） |
| **估算工时** | 1~2 人天 |

---

### P1 级新增缺口（二轮审查发现）

---

#### G-37：review_memory 全局变量大小估算增强（短期方案 ✅ 已完成，长期 map 方案待实施）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-37 |
| **关联一轮发现** | P2 (内存安全审查 — review_memory handler) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 老陈：「当前全局变量大小估算过于粗糙——基于逐行正则匹配，只能识别 `int`、`uint32_t`、`char` 等基本类型。不支持结构体/联合体类型、不支持 typedef 类型别名、不支持函数内 static 变量。结果只能抓到实际量的 20-30%，'~12.3 KB' 这样的输出没有实际参考价值。」 |
| **修复方案** | 1. **短期方案**（快速见效，2 人天）：<br>   - 增加结构体类型匹配：捕获 `typedef struct { ... } type_name;` 并估算 sizeof<br>   - 增加 typedef 别名解析：建立类型别名→实际类型的映射表<br>   - 增加函数内 static 变量计数<br>   - 使用 GCC `-fanalyzer` 或编译后 map 文件替代纯正则匹配<br>2. **长期方案**（建议 Sprint 3+ 完成）：<br>   - 集成实际编译后的 map 文件解析<br>   - 从 .map 文件中提取精确符号大小<br>   - 使用 `nm` 输出验证 |
| **风险** | ⚠️ 老陈强调「当前最好的情况是低精度告警器，最坏情况是给误导性数字让开发者产生虚假安全感」 |
| **负责人建议** | 小克 👨‍💻（短期修补）+ 小马 🐴（长期方案论证） |
| **估算工时** | 2~3 人天（短期）+ 另需 2~3 人天（长期 map 文件方案） |

---

#### G-38：review_startup 深度补缺 — Default_Handler weak symbol 检查 ✅ 已完成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-38 |
| **关联一轮发现** | P0-03 (启动代码审查) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 老陈：「Default_Handler / weak symbol 检查缺失。优化计划 checklist 要求检查 Default_Handler 是否为 WEAK/ALIAS，以及所有 ISR handler 是否有覆盖。未覆盖的中断会跳转到无限循环中的 Default_Handler，这是个运行时陷阱。」 |
| **修复方案** | 1. 在 review_startup handler 中增加：<br>   - 检查 Default_Handler 是否为 `.weak` 或 `.thumb_set Default_Handler` 弱符号<br>   - 遍历中断向量表（从第 16 个中断号开始），逐个检查每个向量是否 != Default_Handler<br>   - 列出所有「未覆盖」的中断源<br>2. 如果 3 个以上中断向量未被覆盖 → major warning<br>3. 如果关键外设中断（如 SysTick、PendSV、SVC）未覆盖 → critical |
| **负责人建议** | 小克 👨‍💻（增量实现） |
| **估算工时** | 1~2 人天 |

---

#### G-39：review_linker 深度补缺 — .ARM.exidx 异常表检查 ✅ 已完成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-39 |
| **关联一轮发现** | P0-02 (链接脚本审查) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 老陈：「缺少 `.ARM.exidx` / `.ARM.extab` 检查。ARM 架构的异常处理索引表，如果没有正确放置，backtrace 和调试器将无法解析调用栈。对 Cortex-M 项目来说这直接影响调试体验。」 |
| **修复方案** | 1. 在 review_linker handler 中增加：<br>   - 检查 `.ARM.exidx` 段是否在链接脚本中声明<br>   - 检查 `.ARM.exidx` 是否分配在 Flash 或 RAM 中（出问题时通常被漏掉）<br>   - 检查 `.ARM.extab` 段是否存在<br>2. 如果 `.ARM.exidx` 缺失 → major warning（调试体验降级）<br>3. 如果两个段都缺失且项目使用 C++ 异常 → critical blocking |
| **负责人建议** | 小克 👨‍💻（增量实现） |
| **估算工时** | 1 人天 |

---

#### G-40：review_rtos 深度补缺 — 运行时统计配置 (configGENERATE_RUN_TIME_STATS) ✅ 已完成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-40 |
| **关联一轮发现** | P1-02 (RTOS 配置审查) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 老陈：「configGENERATE_RUN_TIME_STATS 缺失。对于生产级嵌入式系统，运行时统计信息——任务 CPU 占用率——是性能分析的基础。缺少这个配置意味着系统缺乏运行时可视化的能力。」虽然没有在优化计划中列为此前的必检项，但属于 RTOS 配置审查的合理补充。 |
| **修复方案** | 1. 在 review_rtos handler 增加：<br>   - 检查 FreeRTOSConfig.h 中 `configGENERATE_RUN_TIME_STATS` 是否定义<br>   - 如果未定义 → info 建议（非阻断）<br>   - 如果定义了，检查 `portGET_RUN_TIME_COUNTER_VALUE` / `configRUN_TIME_COUNTER_TYPE` 等配套宏是否也定义<br>2. 若使用生产级配置但缺失运行时统计 → major<br>3. 提供运行时统计的典型配置模板 |
| **负责人建议** | 小克 👨‍💻（增量实现） |
| **估算工时** | 0.5~1 人天 |

---

#### G-41：Hal 接口契约检查（从 P2-01 升级至 P1）

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-41 |
| **关联一轮发现** | P2-01 (HAL 接口契约检查) |
| **优先级** | 🟡 **P1 — 重要** |
| **缺口描述** | 老陈一轮审查已有指出，本轮虽然仍列为 P2，但鉴于二轮审查发现「SWE.5 右侧严重过重（8 步）而左侧缺少集成策略」，HAL 接口契约属于集成验证的「左侧规范」部分，对 ASPICE SWE.5 的对称性有实质贡献。提升至 P1 以改善左右不对称。 |
| **修复方案** | 1. 定义 HAL 接口契约文件（hal-contracts.yaml）<br>2. 在 L2 层增加 `hal-contract-check` step handler<br>3. 检查项：<br>   - ✅ HAL API 签名一致性（参数类型、返回值、const 限定）<br>   - ✅ HAL 返回错误码统一（建议 `HAL_StatusTypeDef` 或等价枚举）<br>   - ✅ HAL 超时参数是否为可配置宏<br>   - ✅ HAL _Init / _DeInit 配对完整性<br>4. 集成 CMock 生成的 mock 定义自动校验接口签名 |
| **负责人建议** | 小马 🐴（HAL 契约定义）+ 小克 👨‍💻（handler 实现） |
| **估算工时** | 2~3 人天 |

---

### P2 级新增缺口（二轮审查发现）

---

#### G-42：BSP 验证

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-42 |
| **关联一轮发现** | P2-02 (BSP 板级支持包验证) |
| **优先级** | 🟢 **P2 — 加分** |
| **缺口描述** | 多板支持项目（STM32F4 + STM32H7 + ESP32）中，BSP 的 pin-mux 配置、时钟配置、外设初始化代码需要跨板一致性验证。老陈上轮指出，本轮无新发现，保留原优先级。 |
| **修复方案** | 1. 定义 BSP 描述文件（bsp-<board>.yaml）<br>2. 在 L2.5 层增加 `bsp-validation` step handler<br>3. 验证 BSP 定义与硬件原理图配置的一致性<br>4. 自动检测跨板配置漂移 |
| **估算工时** | 3~4 人天 |

---

#### G-43：编译输出验证

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-43 |
| **关联一轮发现** | P2-03 (编译输出验证) |
| **优先级** | 🟢 **P2 — 加分** |
| **缺口描述** | 资源受限 MCU 的 .text / .data / .bss 段尺寸变化直接影响项目可行性。老陈：当前无 diff 追踪，纯手动。保留原优先级，建议与 G-37（全局变量估算）的 map 文件方案联动。 |
| **修复方案** | 1. 在 L2 层增加 `build-output-check` step handler<br>2. 解析 `.map` 文件提取各段尺寸：.text / .data / .bss / .stack / .heap<br>3. 与上一次成功构建对比尺寸 diff<br>4. 配置阈值：`.text +10%` → warning；`.text +20%` → blocking |
| **估算工时** | 2~3 人天（与 G-37 map 方案共享） |

---

#### G-44：低功耗审查

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-44 |
| **关联一轮发现** | P2-04 (低功耗 / 能效审查) |
| **优先级** | 🟢 **P2 — 加分** |
| **缺口描述** | 电池供电嵌入式项目的功耗管理是产品核心能力。老陈：看门狗刷新时序、休眠模式配置、时钟门控影响功耗和安全，本轮无新发现，保留原优先级。 |
| **修复方案** | 1. 在 L2.5 层增加 `power-review` step handler（Agent 审查）<br>2. Agent 审查 checklist：<br>   - ✅ IWDG/WWDG 看门狗配置周期 vs 主循环最坏时间<br>   - ✅ 休眠/停止/待机模式转换路径<br>   - ✅ RTC/唤醒源配置<br>   - ✅ 时钟门控（RCC->AHBxENR）配置<br>   - ✅ 未使用外设时钟禁用检查 |
| **估算工时** | 2~3 人天 |

---

### 三轮审查新增缺口

> **来源**: 老陈 👨‍🏫 三轮审查报告 (2026-06-18) — 评分 76/100 ↑6 分
> **核心问题**: 深度补缺已见成效，但核心 P0 项（SWE.6 三段式、C 单元测试框架）仍未闭环；追溯完整性仍是最大短板
> **引用老陈原话**: 「深度补缺做得不错，但大石头还在——SWE.6 和 C 单元测试是真正的瓶颈。追溯性需要你们单独开一条工作线，不能总依赖人工。」

---

#### G-45：C 单元测试框架深度集成 — gcov/lcov 覆盖率 + 脚手架

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-45 |
| **关联前次发现** | G-32 / P0-01 (C 单元测试框架规划) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈三轮审查指出：Unity/CMock 框架引入已完成，但 gcov/lcov 覆盖率的 Pipeline 集成仍未完成。「你现在有 C 测试框架了，但没有覆盖率数据就不是完整的 SWE.4 证据链。gcov 集成是个硬堵塞。」此外缺少 CLI 脚手架（`yuleosh test c --create-suite`），开发者需要手动创建测试结构，入门门槛高。|
| **修复方案** | 1. 在 `c-unit-tests` step handler 中集成 gcov 编译选项（`-fprofile-arcs -ftest-coverage`）<br>2. 在 L1 层 c-unit-tests 之后新增 `c-coverage-report` 步骤：运行 `lcov --capture --directory . --output-file coverage.info && genhtml coverage.info --output-directory coverage-report`<br>3. 覆盖率报告作为 CI artifact 持久化<br>4. 实现 `yuleosh test c --create-suite <module>` CLI 脚手架，自动生成 test/unity/ 目录结构和模板<br>5. 定义覆盖率门禁：行覆盖率 < 60% → warning；< 40% → blocking<br>6. 更新 MISRA 验证计划文档，纳入 C 测试覆盖率作为 SWE.4 证据 |
| **负责人建议** | 小克 👨‍💻（gcov 集成 + CLI 脚手架）+ 小马 🐴（覆盖率门禁 + 验收标准） |
| **估算工时** | 3~4 人天 |
| **依赖关系** | 依赖 G-32（C 单元测试框架基础集成）先行完成 |
| **SHALL 规范** | `SWE-PLN-CUT4`: C 单元测试 SHALL 集成 gcov/lcov 覆盖率报告<br>`SWE-PLN-CUT5`: Pipeline SHALL 对 C 覆盖率设置行覆盖率门禁<br>`SWE-PLN-CUT6`: Pipeline SHALL 提供 `yuleosh test c --create-suite` CLI 脚手架 |

---

#### G-46：追溯完整性自动化 — LRM/LRT 工具链集成

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-46 |
| **关联前次发现** | 追溯完整性维度评分 30/100（两轮未变） |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈三轮审查专门强调：
- 「追溯性从一轮 30 到二轮还是 30，三轮不能再躺平了」
- 「ASPICE CL1 要求追溯至少是 existent，CL2 要求 consistent。你现在是 zero。」
- 「独立工具链（LRM 或 LRT）比手动追溯可靠一万倍」
当前 Pipeline 无任何自动化追溯步骤。需求→实现→测试 三条链全部断裂。这是整个 Pipeline 最大的残留缺口。|
| **修复方案** | 1. ✅ **短期方案已实施**（三轮修复完成，3~4 人天）：<br>   - ✅ 创建 `src/yuleosh/alm/traceability.py` — 核心引擎支持 LRM + LRT 生成<br>   - ✅ 实现 SHALL 语句提取、代码注释扫描（REQ-ID 标记）、测试/审查报告关联<br>   - ✅ 缺口分析 + 孤立测试检测 + 推荐建议<br>   - ✅ CLI 命令：`yuleosh traceability report`（概述）+ `yuleosh traceability matrix`（完整 JSON）<br>2. **长期方案**（Sprint 3+，5~7 人天）：<br>   - 在 L2 层新增 `traceability-check` step handler<br>   - 集成第三方 LRM 工具（如 OSRMT、ReqT 或 Polarion 追溯 API）<br>   - 支持 reqIF 导入/导出格式<br>   - 跨 commit 的追溯一致性验证 |
| **负责人建议** | 小马 🐴（追溯规范定义 + handler 设计）+ 小克 👨‍💻（实现） |
| **估算工时** | 3~4 人天（短期）+ 5~7 人天（长期方案） |
| **依赖关系** | 依赖 spec 文件中需求 ID 标记规范；依赖 `yuleosh spec check` 步骤已建立的需求基线 |
| **SHALL 规范** | `SWE-PLN-TR1`: Pipeline SHALL 在 L2 层包含追溯性检查步骤<br>`SWE-PLN-TR2`: 追溯性检查 SHALL 输出需求→实现→测试 三列追溯矩阵<br>`SWE-PLN-TR3`: Pipeline SHALL 阻断未覆盖测试的需求<br>`SWE-PLN-TR4`: Pipeline SHALL 提供 `yuleosh trace matrix` CLI 命令 |

---

### 三轮审查完成状态对账（G-31~G-46）

| 编号 | 发现来源 | 关联项 | 三轮状态 | 关键说明 |
|:----:|:---------|:-------|:--------|:---------|
| G-31 | 二轮 | P0-04 🔴 SWE.6 三段式 | 🏗️ **持续（Sprint 2 #1）** | 三轮后仍为 #1 瓶颈，三段式拆解未闭环 |
| G-32 | 二轮 | P0-01 🔴 C 单元测试框架 | ✅ **基础已完成** | Unity/CMock handler + pipeline 集成就绪；gcov/脚手架归入 G-45 |
| G-33 | 二轮 | P0-05 🔴 Profile 切换 | 🏗️ **进行中（Sprint 2）** | 架构设计中，依赖 G-31/G-32 产出验证 |
| G-34 | 二轮 | P0-02 🔴 review_linker | ✅ **已完成** | LMA/VMA + heap/stack 重叠检查已实现 |
| G-35 | 二轮 | P0-03 🔴 review_startup | ✅ **已完成** | FPU 使能 + SystemInit 时序已实现 |
| G-36 | 二轮 | P1-02 → P0 review_rtos | ✅ **已完成** | configASSERT + stack overflow hook 已实现 |
| G-37 | 二轮 | review_memory 🟡 | ✅ **短期完成** | 结构体/typedef/static 估算；长期 map 方案待 Sprint 3+ |
| G-38 | 二轮 | P0-03 🔴 review_startup | ✅ **已完成** | Default_Handler weak symbol 检查已实现 |
| G-39 | 二轮 | P0-02 🔴 review_linker | ✅ **已完成** | .ARM.exidx 异常表检查已实现 |
| G-40 | 二轮 | P1-02 🟡 review_rtos | ✅ **已完成** | configGENERATE_RUN_TIME_STATS 检查已实现 |
| G-41 | 二轮 | P2→P1 🟡 HAL 契约 | 🏗️ **进行中** | Sprint 2/3 排期，可延至 Sprint 3 |
| G-42 | 二轮 | P2-02 🟢 BSP 验证 | 🏗️ **实施中** | Sprint A/B 排期 |
| G-43 | 二轮 | P2-03 🟢 编译输出验证 | 🏗️ **实施中** | Sprint A/B 排期（与 G-37 长期方案联动） |
| G-44 | 二轮 | P2-04 🟢 低功耗审查 | 🏗️ **实施中** | Sprint A/B 排期 |
| **G-45** | **三轮** | **P0 🔴 C 单元测试深度集成** | **🏗️ Sprint 2 优先** | gcov/lcov 覆盖率集成 + CLI 脚手架 |
| **G-46** | **三轮** | **P0 🔴 追溯完整性** | **✅ 短期已完成 / 🏗️ 长期待 Sprint 3+** | traceability.py 引擎 + CLI 已就位；L2 step handler 及第三方工具集成待 Sprint 3+ |

---

## 优化路径总览

### 实施优先级矩阵（Sprint A 更新 — 目标 87+）

| 优先级 | 项目 | 估算工时 | 影响面 | Sprint A 状态 | 建议 Sprint |
|:------:|:-----|:--------:|:------|:-------------|:-----------|
| P0 | G-31: SWE.6 三段式合格性测试 | 5~7 人天 | 🔴 L3 + ASPICE | 🏗️ 持续（Sprint A #1） | **Sprint A** |
| P0 | G-45: C 单元测试深度集成（gcov/lcov + CLI） | 3~4 人天 | 🔴 L1 + 覆盖率 | 🏗️ 新增（闭环 CUT 框架） | **Sprint A** |
| P0 | G-46: 追溯完整性（L2 handler 入 pipeline） | 3~4 人天 | 🔴 L2 + CL1 追溯 | ✅ 短期引擎已完成，L2 handler 待 Sprint A | **Sprint A** |
| P0 | G-33: Profile 切换 | 4~5 人天 | 🟡 CI 配置 | 🏗️ 进行中 | **Sprint A** |
| P0 | G-32: C 单元测试框架基础集成 | ✅ 已完成 | 🟢 L1 + 测试 | ✅ handler + 模板 + pipeline 集成 | — |
| P0 | P0-02: 链接脚本审查（含 G-34/G-39） | ✅ 已完成 | 🟢 L2 Agent | ✅ LMA/VMA + heap/stack + .ARM.exidx | — |
| P0 | P0-03: 启动代码审查（含 G-35/G-38） | ✅ 已完成 | 🟢 L2.5 Agent | ✅ FPU/SystemInit/Default_Handler | — |
| P0 | G-36: review_rtos configASSERT + overflow | ✅ 已完成 | 🟢 L2 Agent | ✅ configASSERT/overflow/RUN_TIME_STATS | — |
| P1 | P1-01: 堆栈使用分析 | 2~3 人天 | 🟢 L2 | — | Sprint A |
| P1 | P1-02: RTOS 配置审查（含 G-40） | ✅ 已完成 | 🟢 L2 Agent | ✅ 核心审查已完备 | — |
| P1 | P1-03: MMIO 审查 | 3~4 人天 | 🟢 L2.5 Agent | — | Sprint A/B |
| P1 | P1-04: MISRA 增量优化 | 3~4 人天 | 🟡 L1+L2 | — | Sprint A/B |
| P1 | G-37: review_memory 全局变量估算 | ✅ 短期完成 | 🟢 L2 | ✅ 短期方案已实施；长期 map 方案待 Sprint B+ | 长期: Sprint B+ |
| P1 | G-41: HAL 接口契约检查 | 2~3 人天 | 🟢 L2 | 🏗️ 进行中 | Sprint A/B |
| P2 | P2-02/G-42: BSP 验证 | 3~4 人天 | 🟢 L2.5 | 🏗️ 实施中 | Sprint A/B |
| P2 | P2-03/G-43: 编译输出验证 | 2~3 人天 | 🟢 L2 | 🏗️ 实施中（与 G-37 联动） | Sprint A/B |
| P2 | P2-04/G-44: 低功耗审查 | 2~3 人天 | 🟢 L2.5 | 🏗️ 实施中 | Sprint A/B |

### 并行动态（Sprint A 更新）

```
Sprint 1 (2 周) — 已完成项
  ├── G-34 review_linker 深度补缺 ✅
  ├── G-35 review_startup FPU+SystemInit ✅
  ├── G-36 review_rtos configASSERT+overflow ✅
  ├── G-38 review_startup Default_Handler weak ✅
  ├── G-39 review_linker .ARM.exidx ✅
  ├── G-40 review_rtos RUN_TIME_STATS ✅
  └── G-37 memory 估算短期修补 ✅

Sprint 2 (当前 Sprint)
  ├── G-31 SWE.6 三段式            ⬅ #1 最优先（85→87+ 的关键瓶颈）
  ├── G-45 C 单元测试深度集成        ⬅ gcov/lcov + CLI 脚手架（CUT 闭环）
  ├── G-46 追溯完整性短期完善         ⬅ L2 step handler 入 pipeline
  ├── G-33 Profile 切换             ⬅ 架构设计 + 首次实现
  ├── P1-01 堆栈分析                ⬅ 独立
  ├── P1-03 MMIO 审查               ⬅ Agent prompt + 检查参考
  ├── P1-04 MISRA 增量优化           ⬅ 独立
  ├── G-41 HAL 契约检查              ⬅ 可延至 Sprint 3
  ├── **E08 KPI 基线采集**           ⬅ ✅ **已完成** —— kpi.py + yuleosh kpi CLI + test_kpi.py 18/18 ✅（并发实现）
  └── **E09 4 周基线**               ⬅ 🗓️ 规划中——需要积累 ≥20 个数据点后发布

Sprint 3+ (持续)
  ├── G-37 long-term map 方案       ⬅ 长期方案（依赖编译输出）
  ├── G-46 追溯长期方案              ⬅ 第三方 LRM 工具集成

Sprint A/B (实施中)
  ├── G-42 BSP 验证                ⬅ 🏗️ 实施中
  ├── G-43 编译输出验证             ⬅ 🏗️ 实施中
  └── G-44 低功耗审查               ⬅ 🏗️ 实施中
```

### SHALL 规范汇总索引（三轮审查更新）

| SHALL ID | 描述 | 对应 P#/G# | 级别 |
|:--------|:-----|:----------:|:----:|
| SWE-PLN-CUT1 | L1 C 单元测试步骤存在 | P0-01 / G-32 | Required |
| SWE-PLN-CUT2 | C 单元测试使用专用框架 | P0-01 / G-32 | Required |
| SWE-PLN-CUT3 | C 测试覆盖率由 gcov/lcov 生成 | P0-01 / G-32 | Required |
| SWE-PLN-CUT4 | C 单元测试 SHALL 集成 gcov/lcov 覆盖率报告 | G-45 | Required |
| SWE-PLN-CUT5 | Pipeline SHALL 对 C 覆盖率设置行覆盖率门禁 | G-45 | Required |
| SWE-PLN-CUT6 | Pipeline SHALL 提供 `yuleosh test c --create-suite` CLI 脚手架 | G-45 | Required |
| SWE-PLN-LK1 | L2 链接脚本审查步骤存在 | P0-02 / G-34 | Required ✅ |
| SWE-PLN-LK2 | 链接脚本覆盖内存/栈/向量表 | P0-02 / G-34 | Required ✅ |
| SWE-PLN-LK3 | 链接脚本审查 SHALL 检查 LMA≠VMA 和 heap/stack 不重叠 | G-34 | Required ✅ |
| SWE-PLN-STUP1 | 启动代码审查步骤存在 | P0-03 / G-35 | Required ✅ |
| SWE-PLN-STUP2 | 启动审查覆盖向量表/BSS/data/SystemInit/FPU | P0-03 / G-35 | Required ✅ |
| SWE-PLN-STUP3 | 启动审查 SHALL 检查 FPU 使能 (CPACR) | G-35 | Required ✅ |
| SWE-PLN-STUP4 | 启动审查 SHALL 检查 SystemInit 在 main() 前调用 | G-35 | Required ✅ |
| SWE-PLN-RTOS3 | RTOS 审查 SHALL 检查 configASSERT 定义 | G-36 | Required ✅ |
| SWE-PLN-RTOS4 | RTOS 审查 SHALL 检查 configCHECK_FOR_STACK_OVERFLOW | G-36 | Required ✅ |
| SWE-PLN-LNK3 | 链接脚本 SHALL 检查 .ARM.exidx 段 | G-39 | Advisory ✅ |
| SWE-PLN-MEM1 | 全局变量大小估算 SHALL 支持结构体/typedef/static | G-37 | Advisory ✅(短期) |
| SWE-PLN-SWE6-1 | SWE.6 合格性测试规范定义步骤 | P0-04 / G-31 | Required |
| SWE-PLN-SWE6-2 | L3 合格性测试执行步骤 | P0-04 / G-31 | Required |
| SWE-PLN-SWE6-3 | 合格性测试报告含追溯链 | P0-04 / G-31 | Required |
| SWE-PLN-SWE6-4 | SWE.6 报告 SHALL 包含规范↔结果↔偏差追溯链 | G-31 | Required |
| SWE-PLN-PROF1 | 支持通用+嵌入式 Profile 切换 | P0-05 / G-33 | Required |
| SWE-PLN-PROF2 | Profile 通过 ci-config.yaml 声明 | P0-05 / G-33 | Required |
| SWE-PLN-PROF3 | Pipeline 启动时校验 Profile 完整性 | P0-05 / G-33 | Required |
| SWE-PLN-TR1 | Pipeline SHALL 在 L2 层包含追溯性检查步骤 | G-46 | Required |
| SWE-PLN-TR2 | 追溯性检查 SHALL 输出需求→实现→测试 三列追溯矩阵 | G-46 | Required |
| SWE-PLN-TR3 | Pipeline SHALL 阻断未覆盖测试的需求 | G-46 | Required |
| SWE-PLN-TR4 | Pipeline SHALL 提供 `yuleosh trace matrix` CLI 命令 | G-46 | Required |
| SWE-PLN-STACK1 | L2 堆栈使用分析步骤存在 | P1-01 | Advisory |
| SWE-PLN-STACK2 | 堆栈使用 ≥95% 阻断 | P1-01 | Advisory |
| SWE-PLN-RTOS1 | RTOS 配置审查步骤存在 | P1-02 | Advisory |
| SWE-PLN-RTOS2 | RTOS 审查覆盖优先级/IPC/assert | P1-02 | Advisory |
| SWE-PLN-MMIO1 | MMIO 配置审查步骤存在 | P1-03 | Advisory |
| SWE-PLN-MMIO2 | MMIO 审查覆盖时钟/GPIO/NVIC/DMA | P1-03 | Advisory |
| SWE-PLN-MSR-D1 | L1 MISRA delta 模式 | P1-04 | Advisory |
| SWE-PLN-MSR-D2 | L2 MISRA 全量+零增量阻断 | P1-04 | Advisory |
| SWE-PLN-MSR-D3 | MISRA delta 阻断新增 Required | P1-04 | Advisory |

---

## 验收判定

### 全局验收标准

| 标准 | 判定条件 |
|:-----|:---------|
| ✅ **全部通过** | 所有 P0 Required 级验收项通过；P1 Advisory 级 ≤4 项未通过 |
| ⚠️ **有条件通过** | 所有 P0 Required 级验收项通过；P1 Advisory 级 5~6 项未通过（需延期计划） |
| ❌ **不通过** | 任意 P0 Required 项未通过；或 P0 未完成即进入 P1/P2 |

### Sprint A 评分提升路径（87+）

| 阶段 | 完成项 | 评分 | 说明 |
|:-----|:-------|:----:|:-----|
| 一轮 | — | 58/100 | Baseline |
| 二轮 | G-01~G-30 全部实施 | 70/100 | +12，MISRA 基础设施完备 |
| **三轮** | **G-34~G-40 深度补缺（7 项）** | **76/100** | **↗ +6，嵌入式审查深度提升** |
| **Sprint A End** | G-31 SWE.6, G-45 CUT gcov, G-46 追溯 L2 handler, G-33 Profile, P1 部分 | **87/100** | **P0 全部闭环；追溯 35→60；C 覆盖率门禁上线** |
| Sprint B End | P1 全部 + G-46 追溯长期 + P2 部分 | **89/100** | CL1 ✅ 锁定, CL2 证据完备 |
| 目标 | 全部 P0~P2 完成 + 追溯 ≥60 | **87+/100** | CL1 ✅, CL2 证据完备 |

### Sprint A 单维度评分变化与 87+ 路径

| 维度 | 一轮 | 二轮 | 三轮 | 变化（二→三） |
|:-----|:---:|:---:|:---:|:-------------:|
| V-Model 左半侧 | 85 | 85 | 88 | ↗ +3 |
| V-Model 右半侧 | 55 | 68 | 70 | ↗ +2 |
| 左右对称度 | 65 | 72 | 74 | ↗ +2 |
| 追溯完整性 | 30 | 30 | **35** | ↗ +5 🔴 仍严重不足 |
| Agent审查(标准软件) | 80 | 80 | 83 | ↗ +3 |
| Agent审查(嵌入式特有) | 30 | 65 | **82** | ↗ +17 🏆 深度检验全部补齐 |
| 嵌入式特殊性验证 | 25 | 60 | **75** | ↗ +15 🏆 review_linker/startup/rtos 深度检验全部补齐 |
| ASPICE CL1 就绪度 | 65 | 70 | 74 | ↗ +4 |
| ASPICE CL2 就绪度 | 35 | 40 | 42 | ↗ +2 |
| CI 分层合理性 | 75 | 70 | 73 | ↗ +3 |
| MISRA 集成 | 65 | 65 | 68 | ↗ +3 |
| **综合加权** | **58** | **70** | **76** | **↗ +6** |

### 关键残留风险

| 风险 | 严重度 | 缓解措施 |
|:-----|:------|:---------|
| SWE.6 仍为 1 步 final-report | 🔴 | G-31 三段式拆解为最高优先——三轮后仍为 #1 瓶颈 |
| C 单元测试 gcov/lcov 覆盖率缺失 | 🔴 | G-45 三轮新增——框架已有但覆盖率 Pipeline 未集成 |
| 追溯完整性仍严重不足 (35/100) | 🔴 | G-46 三轮新增——必须单独开辟追溯工作线 |
| C 单元测试覆盖率与 CLI 脚手架未闭环 | 🔴 | G-32 框架基础已 ✅；G-45 gcov/lcov 集成 + CLI 脚手架待 Sprint A 完成 |
| 文档与代码同步检查 | 🟢 | 已完成——G-34~G-40 深度补缺证明计划→代码一致性提升 |
| alloca()/VLA 检查缺失 | 🟡 | 需在 review_memory 中长期补上（依赖 AST 方案） |
| Profile 切换与嵌入式审查节奏依赖 | 🟡 | G-33 设计完成后需要等待 G-31/G-32 产出才可全面验证 |

---

---

## CL2 过审路径

> **概述**: ASPICE CL2（能力等级 2）审计要求过程 PA 2.1（追溯管理）+ PA 2.2（过程测量）的证据完整、持续、可审计。CL1 只需步骤存在，CL2 要求步骤可追溯、可测量、可复现。
> **目标时间线**: Sprint A 未 87+ → Sprint B 末 89+ → CL2 过审 Q3 2026
> **负责人**: 小马 🐴（质量架构师）

---

### CL2 vs CL1 关键差异

| 维度 | CL1 (Level 1) | CL2 (Level 2) | 意义 |
|:-----|:--------------|:--------------|:-----|
| **追溯性** | 非正式，手工 | **PA 2.1: 需求↔实现↔测试 三向持续追溯** | 审计时需直接展示追溯矩阵 |
| **过程测量** | 离散点测量 | **PA 2.2: KPI 趋势 ≥90 天 + 门禁阈值** | 证明过程受控、可预测 |
| **偏差管理** | 存在即可 | **全生命周期跟踪 + 审批链 + 到期自动失效** | 证明管理流程严格执行 |
| **覆盖率** | 有即可 | **量化目标（行覆盖率 ≥60%）+ 趋势记录** | 证明测试充分性有数据支撑 |
| **工具资格** | 使用即认可 | **ISO 26262-8 §11 工具分类 + TI/TD 评估** | 证明工具适用性已评估 |
| **审计日志** | 无要求 | **构建参数、工具版本、环境变量持久化** | 过程可复现 |
| **报告结构** | 功能实现 | **结构化报告含规范↔结果↔偏差 三层追溯链** | 审计师可逐级追溯 |

---

### CL2 过审里程碑

| 阶段 | 时间 | 评分目标 | 关键交付物 | CL2 基元提升 |
|:-----|:----|:--------:|:----------|:-------------|
| **M0: Baseline** | 三轮末 | 76/100 | 全部 G-34~G-46 缺口清单 | — |
| **M1: Sprint A 闭环** | Sprint A 末 | **87+/100** | SWE.6 三段式 ✅, C 覆盖率 ✅, 追溯 L2 handler ✅, Profile 切换 ✅ | PA 2.1: 追溯自动化 0→60%; PA 2.2: C 覆盖趋势 0→60% |
| **M2: Sprint B 全员** | Sprint B 末 | **89+/100** | P1 全部闭环；G-37 map 方案；G-46 追溯长期 + 第三方工具 | PA 2.1: 追溯自动化 60→85%; PA 2.2: 构建元数据 70→90% |
| **M3: CL2 Dry Run** | Sprint B 后 2w | **≥90/100** | 完整 CL2 证据包审计演练 | PA 2.1 ≥85%, PA 2.2 ≥85%, ISO 26262 TOOL ≥85% |
| **M4: CL2 正式过审** | Q3 2026末 | **≥92/100** | 正式审计通过 | 全部 CL2 基元 ≥90% |

---

### CL2 基元细化执行计划

#### PA 2.1 — 追溯管理（Transition Management）

**要求**: 工作产品之间双向追溯持续可审计

| # | 交付物 | 起始 Sprint | 方法 | 验收标准 |
|:-:|:-------|:-----------|:-----|:---------|
| CL2-TM-1 | 需求→实现→测试 三向追溯矩阵 | Sprint A (G-46) | `yuleosh traceability matrix` JSON 输出 + L2 step handler `code-traceability-check` | 每个 REQ-xxx 同时关联 IMPL-xxx + TEST-xxx；无孤立需求或孤立测试 |
| CL2-TM-2 | SWE.6 合格性测试规范↔结果追溯链 | Sprint A (G-31) | 三段式 SWE.6 报告含需求 ID↔测试用例↔测试结果 映射表 | 100% 需求映射到测试用例；超出项目 100% 映射到测试结果 |
| CL2-TM-3 | MISRA 违规→偏差 全追踪 | ✅ **已完成** | 偏差管理 CLI + CI 集成 | 每条 Required 违规可追踪到偏差或已修复证据 |
| CL2-TM-4 | Agent 审查报告→代码修改 关联 | Sprint B | Agent 审查 JSON 报告中记录 commit SHA + 审查结果 | 每次 Agent 审查可定位到对应代码版本 |
| CL2-TM-5 | 构建→测试结果 双向追溯 | Sprint B | 构建元数据 (tool_version, compiler flags) 写入 JSONL + 测试结果关联 | 每个测试运行可追溯到具体构建环境参数 |
| CL2-TM-6 | 跨 Sprint 追溯一致性验证 | Sprint B | LRM 导入/导出 + 跨 commit 追溯矩阵对比 | 追溯矩阵在不同 Sprint 间不出现悬空引用 |

#### PA 2.2 — 过程测量（Measurement & Process Performance）

**要求**: 过程测量数据持续采集 ≥90 天，阈值驱动改进

| # | 交付物 | 起始 Sprint | 方法 | 验收标准 |
|:-:|:-------|:-----------|:-----|:---------|
| CL2-MP-1 | MISRA 违规密度趋势 ≥90 天 | ✅ **已完成** | misra-trend.jsonl 持续写入 + CLI 趋势查看 | 文件存在且含 ≥90 天记录；趋势方向可读 |
| CL2-MP-2 | C 单元测试行覆盖率趋势 per commit | Sprint A (G-45) | gcov/lcov 覆盖率 JSONL 趋势记录 + 门禁阈值 | 每轮构建生成 coverage.info + 行覆盖率趋势 |
| CL2-MP-3 | 违规修复时效追踪 | Sprint A | MISRA 违规→偏差→修复 时间线记录 | Required 违规 48h 内修复或提偏差 |
| CL2-MP-4 | 构建元数据持久化 | Sprint A/B | 每次构建记录: compiler version, cppcheck version, OS, env vars | 构建参数 JSON 输出持久化到 CI artifact |
| CL2-MP-5 | 审查覆盖率 KPI | Sprint B | Agent 审查覆盖率 %（代码行被 Agent 审查的占比）+ 人工审查覆盖率 | 关键文件 100% Agent 审查覆盖；变更文件 ≥80% |
| CL2-MP-6 | 过程稳定性指标 | Sprint B | 构建成功率、回归触发率、缺陷逃逸率 月报 | 构建成功率 ≥95%；缺陷逃逸率 ≤5% |
| CL2-MP-7 | 趋势 dashboard 可视化 | Sprint B+ | Dashboard 集成 MISRA 趋势 + C 覆盖 + 构建成功率 + 审查覆盖率 | 可交互的趋势图表；可设置阈值告警 |

#### PA 2.2 (RI) — 资源与基础设施

**要求**: 工具/人员资格证明齐备

| # | 交付物 | 起始 Sprint | 方法 | 验收标准 |
|:-:|:-------|:-----------|:-----|:---------|
| CL2-RI-1 | 工具资格认证文档 | ✅ **已完成** | `docs/iso26262-tool-qualification.md` | TCL/TI/TD 分类 + 已知缺陷 + 误报率估算 |
| CL2-RI-2 | Agent 审查报告持久化 | ✅ **已完成** | 每次审查输出 JSON 报告保存为 CI artifact | linker/startup/rtos/memory 审查均有 JSON 输出 |
| CL2-RI-3 | 人员角色与职责矩阵 | Sprint A | 在 MISRA 验证计划 + 质量计划中定义角色 | 每个验证活动有明确负责人；审批链完整 |
| CL2-RI-4 | 工具版本管理策略 | Sprint A | CI 配置中锁定工具版本；版本变更审批流程 | tools-version.yaml 文件 ±change_log |

---

### CL2 证据包清单

审计时需展示的完整证据清单：

```
CL2-EVIDENCE-PACK/
├── PA2.1-TM/
│   ├── traceability-matrix-latest.json      # 最新完整追溯矩阵
│   ├── traceability-matrix-archive/          # 历史追溯矩阵快照
│   ├── swe6-qualification-report-latest.pdf  # SWE.6 合格性测试报告
│   ├── swe6-qualification-archive/           # 历史 SWE.6 报告
│   ├── deviation-record-all.jsonl            # 偏差全生命周期记录
│   └── agent-review-reports/                 # Agent 审查报告存档
│
├── PA2.2-MP/
│   ├── misra-trend.jsonl                     # MISRA 违规趋势（≥90天）
│   ├── coverage-trend.jsonl                  # C 覆盖率趋势
│   ├── build-metadata-archive/               # 构建元数据归档
│   ├── kpi-monthly-reports/                  # KPI 月报
│   └── process-stability-indicators.jsonl    # 过程稳定性指标
│
└── PA2.2-RI/
    ├── iso26262-tool-qualification.md        # 工具资格认证
    ├── tools-version.yaml                    # 工具版本锁定
    └── role-responsibility-matrix.md         # 角色职责矩阵
```

---

### CL2 过审风险登记册

| 风险 | 严重度 | 概率 | 影响 | 缓解措施 |
|:-----|:------:|:----:|:----|:---------|
| G-31 SWE.6 三段式 Sprint A 未闭环 | 🔴 | 中 | 无法满足 CL2 SWE.6 追溯要求 | 提升 Sprint A 排期 #1；资源倾斜 |
| G-45 C 覆盖率门禁 ≥90 天趋势不足 | 🔴 | 高 | PA 2.2 测量数据不足 | Sprint A 即启动覆盖率采集；允许 Sprint B 前累积 30d+ 数据 + 补旧记录 |
| G-46 追溯 L2 handler 覆盖不全 | 🟡 | 中 | PA 2.1 追溯不完整 | Sprint A 先行实现最小可行 handler（覆盖 ≥80% 需求）；Sprint B 补齐长期方案 |
| 审计日志不全——构建元数据未全覆盖 | 🟡 | 高 | PA 2.2 可复现性证据不足 | Sprint A 先行输出 compiler/OS/tool_version；Sprint B 完善 env vars/parameters |
| 人员角色在 CI 过程中无审计记录 | 🟡 | 低 | PA 2.2 角色证据不足 | 在 ci-config.yaml 增加 responsible/approver 元数据字段 |
| Dashboard 可视化未就绪影响演示效果 | 🟢 | 低 | 审计体验降级（非阻断） | Sprint B+ 排期；审计时可用 CLI + JSON 替代演示 |

---

### CL2 过审 Sprint-by-Sprint 路径

```
Sprint A（当前）
  ├── CL2-TM-1: 追溯矩阵 L2 handler (G-46)          ████████░░ 80%
  ├── CL2-TM-2: SWE.6 三段式追溯链 (G-31)           ████░░░░░░ 40%  ← #1
  ├── CL2-MP-2: C 覆盖率趋势 (G-45)                  ██░░░░░░░░ 20%  ← #2
  ├── CL2-MP-3: 违规修复时效追踪                       ░░░░░░░░░░ 0%
  ├── CL2-MP-4: 构建元数据 (tool version)              ██████░░░░ 60%
  ├── CL2-RI-3: 角色职责矩阵                           ░░░░░░░░░░ 0%
  └── CL2-RI-4: 工具版本管理策略                        ░░░░░░░░░░ 0%
  ─── PA 2.1 综合: 30% | PA 2.2 综合: 20% | RI 综合: 50%

Sprint B
  ├── CL2-TM-4: Agent 审查→代码关联                     ░░░░░░░░░░ 0%
  ├── CL2-TM-5: 构建→测试双向追溯                       ░░░░░░░░░░ 0%
  ├── CL2-TM-6: 跨 Sprint 追溯一致性                    ░░░░░░░░░░ 0%
  ├── CL2-MP-1: MISRA 趋势 ≥90 天 (已有)               ██████████ 100%
  ├── CL2-MP-5: 审查覆盖率 KPI                          ░░░░░░░░░░ 0%
  ├── CL2-MP-6: 过程稳定性指标                           ░░░░░░░░░░ 0%
  └── CL2-MP-4: 构建元数据完备化                         ░░░░░░░░░░ 0%
  ─── PA 2.1 综合: 70% | PA 2.2 综合: 60% | RI 综合: 80%

Sprint B+（Dry Run 准备）
  ├── CL2-MP-7: Dashboard 可视化                        ░░░░░░░░░░ 0%
  ├── 全部 PA2.1 证据包就位                             ░░░░░░░░░░ 0%
  ├── 全部 PA2.2 证据包就位                             ░░░░░░░░░░ 0%
  ├── 全部 RI 证据包就位                                ░░░░░░░░░░ 0%
  ├── DRY RUN: 模拟审计 + 整改                          ░░░░░░░░░░ 0%
  └── 正式过审                                           ░░░░░░░░░░ 0%
```

---

### CL2 过审就绪度仪表盘

| CL2 基元 | M0 (三轮末) | M1 (Sprint A) | M2 (Sprint B) | M3 (Dry Run) | M4 (正式) |
|:---------|:-----------:|:-------------:|:-------------:|:------------:|:---------:|
| PA 2.1 TM (6 项) | 1/6 (17%) | 4/6 (66%) | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| PA 2.2 MP (7 项) | 1/7 (14%) | 4/7 (57%) | 6/7 (86%) | 7/7 (100%) | 7/7 (100%) |
| PA 2.2 RI (4 项) | 2/4 (50%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) |
| **综合就绪度** | **26%** | **67%** | **94%** | **100%** | **100%** |

---

### CL2 过审验收判定

| 标准 | 判定条件 |
|:-----|:---------|
| ✅ **通过** | 全部 CL2 基元就绪度 ≥90%；审计实际执行 2 条样本追溯链均闭环 |
| ⚠️ **有条件通过** | PA 2.1 和 PA 2.2 就绪度均 ≥80%；审计发现 ≤3 个 minor 项（需整改计划 30 天内提交） |
| ❌ **不通过** | 任意基元就绪度 <80%；或审计发现 major/critical 项 |

---

---

## 附录C: CL2 审计计划 — E03/E04/E06 完成状态

> **来源**: `reports/cl2-audit-plan.md`（老陈编制）
> **关联项**: E03（覆盖阈值门禁）· E04（覆盖趋势追踪与基线）· E06（文档状态门禁 MR 阻塞）
> **负责人**: 小马 🐴（质量架构师）

---

### E03：覆盖阈值门禁 — 状态追踪

| 维度 | 内容 |
|:-----|:------|
| **审计项编码** | E03 |
| **名称** | 覆盖阈值门禁 (`fail_under`) |
| **优先级** | 🔴 **P0 — 必须** |
| **关联 SHALL** | SWE-PLN-CUT5 (G-45) |
| **当前状态** | ✅ **已完成** |
| **Sprint A 目标** | Sprint A 末完成集成 |
| **依赖** | E01 (gcov 编译链) → E02 (lcov 报告) → E03 |
| **关键路径** | E01→E02→E03→E10→E13，约 11 天开发 |

**实现方案**:
1. 在 `c-unit-tests` step handler 中集成 gcov 编译选项（`-fprofile-arcs -ftest-coverage`）
2. `c-coverage-report` 步骤运行 `lcov --capture && genhtml` 产出覆盖率报告
3. 在 CI 配置中增加 `coverage.fail_under_line` 配置项：
   - `fail_under_line: 40` → 行覆盖率 <40% 时 Pipeline **阻断** (blocking)
   - `fail_under_line: 60` → 行覆盖率 <60% 时 **警告** (warning，不阻断)
4. 覆盖门禁只在 **embedded** 和 **automotive** profile 下启用；general profile 跳过

**验收标准**:
| # | 条件 | 预期结果 |
|:-:|:-----|:---------|
| E03-A1 | 正常覆盖率 (≥60%) | stage status = passed |
| E03-A2 | 覆盖率 <60% 但 ≥40% | stage status = warning（非阻断） |
| E03-A3 | 覆盖率 <40% | stage status = failed（阻断 Pipeline） |
| E03-A4 | general profile 运行 | 覆盖门禁步骤自动跳过 |

---

### E04：覆盖趋势追踪与基线 — 状态追踪

| 维度 | 内容 |
|:-----|:------|
| **审计项编码** | E04 |
| **名称** | 覆盖趋势追踪与基线 |
| **优先级** | 🔴 **P0 — 必须** |
| **关联 SHALL** | SWE-PLN-CUT4 (G-45)；CL2-MP-2 |
| **当前状态** | ✅ **已完成** |
| **Sprint A 目标** | Sprint A 末启动覆盖率趋势采集，目标 ≥30 个数据点 |
| **依赖** | E03 产出 coverage.info 后方可开始趋势记录 |

**实现方案**:
1. 每轮构建运行 lcov 后，提取行覆盖率百分比，追加写入 `coverage-trend.jsonl`
2. 趋势记录字段：`timestamp, build_id, line_rate, branch_rate, function_rate, total_lines, covered_lines`
3. 提供 CLI 查看：`yuleosh coverage trend --lines 10`（最近 N 次）、`yuleosh coverage trend --days 7`（近 7 天）
4. 供 CLI 基线快照：`yuleosh coverage baseline save` → `coverage-baseline-v1.json`

**趋势文件格式** (`coverage-trend.jsonl`):
```jsonl
{"timestamp":"2026-06-18T00:00:00Z","build_id":"b001","line_rate":62.5,"branch_rate":48.3,"function_rate":78.9,"total_lines":1200,"covered_lines":750}
{"timestamp":"2026-06-19T00:00:00Z","build_id":"b002","line_rate":65.1,"branch_rate":51.0,"function_rate":80.2,"total_lines":1220,"covered_lines":794}
```

**验收标准**:
| # | 条件 | 预期结果 |
|:-:|:-----|:---------|
| E04-A1 | 每轮构建后检查 | `.yuleosh/reports/coverage-trend.jsonl` 存在且追加新记录 |
| E04-A2 | CLI 趋势查看 | `yuleosh coverage trend --lines 5` 输出 Markdown 表格含 5 条记录 |
| E04-A3 | JSON 格式输出 | `yuleosh coverage trend --json` 输出 JSON 数组 |
| E04-A4 | 趋势方向指示 | 最新记录与上一条对比有 ↑↓→ 方向箭头 |
| E04-A5 | 基线快照 | `yuleosh coverage baseline save` 创建基线文件 |

---

### E06：文档状态门禁 — 状态追踪

| 维度 | 内容 |
|:-----|:------|
| **审计项编码** | E06 |
| **名称** | 文档状态门禁（MR 阻塞） |
| **优先级** | 🔴 **P0 — 必须** |
| **关联矩阵** | `specs/misra-acceptance-matrix.md §21.2`（E05~E07 新增验收项） |
| **当前状态** | ✅ **已完成** |
| **Sprint A 目标** | Sprint A 末完成关键模块文档同步门禁（§21.2.4~§21.2.6） |
| **依赖** | E05 (文档 YAML Schema) 先行完成 |

**实现方案**:
1. **代码-文档映射表**：`scripts/docs_map.yaml`，定义关键模块路径→对应文档路径映射
2. **变更检测**：在 L2 层新增 `docs-sync-check` step handler，解析 MR diff 检查：
   - 关键模块（src/core/, src/hal/ 等）代码变更 → 对应 docs/ 未更新 → **MR 阻断**
   - 非关键模块变更 → 对应文档未更新 → **WARNING** + MR 自动评论提醒
3. **豁免机制**：通过偏差管理 CLI 创建文档同步豁免（`yuleosh misra deviate add` → 关联 rule_id `DOC-SYNC`）
4. **指纹对比**：缓存已审查文档的代码模块 API 指纹，下次对比检出差异

**验收标准**:
| # | 条件 | 预期结果 |
|:-:|:-----|:---------|
| E06-A1 | 关键模块 src/ 变更 + docs/ 未更新 | CI FAILED（MR 阻断） |
| E06-A2 | 非关键模块变更 + docs/ 未更新 | CI WARNING + MR 自动评论 |
| E06-A3 | 有效偏差豁免 | 门禁不阻断；偏差记录审计链完整 |
| E06-A4 | 文档变更+代码变更同步提交 | CI PASSED |

---

## 附录D: KPI 基线采集流程

> **来源**: CL2 审计计划 E08/E09
> **目的**: 建立可审计的过程性能基线，满足 ASPICE PA 2.2 对过程测量的要求
> **负责人**: 小马 🐴（质量架构师）

---

### D.1 KPI 指标定义

| 指标 | 字段 | 采集方式 | 目标值 | 门禁阈值 |
|:-----|:-----|:---------|:------|:---------|
| 构建成功率 | `build_success_rate` | 统计近期构建通过/总数 | ≥95% | <90% → 告警 |
| 测试通过率 | `test_pass_rate` | pytest/gcov 结果汇总 | ≥90% | <80% → 阻断 |
| C 行覆盖率 | `c_line_coverage` | lcov 提取 line_rate | ≥60% | <40% → 阻断 |
| MISRA 违规密度 | `misra_violations_per_kloc` | cppcheck 报告 / KLOC | ≤5.0/KLOC | >10.0 → 告警 |
| Required 违规数 | `misra_required_count` | cppcheck 报告解析 | 零 | >0 → 阻断 |
| 构建时长 | `build_duration_sec` | CI pipeline 总耗时 | ≤600s | >900s → 告警 |
| Agent 审查通过率 | `agent_review_pass_rate` | 审查项通过数/总数 | ≥85% | <70% → 告警 |

### D.2 采集流程（Pipeline 集成）

每次构建完成后自动采集 KPI 指标，追加写入结构化 JSONL 文件：

```
采集时序（Pipeline 内嵌）
                        ┌──────────────────┐
                        │  构建开始         │
                        │  record_metrics() │
                        │  build_status=    │
                        │  "running"        │
                        └────────┬─────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │ L1: C 单元测试 │   │ L2: MISRA 检查│   │ L2.5: Agent   │
    │ → line_rate   │   │ → violations/ │   │ 审查 → pass_  │
    │ → pass_rate   │   │   KLOC        │   │   rate        │
    └───────────────┘   └───────────────┘   └───────────────┘
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 ▼
                    ┌───────────────────────┐
                    │ 构建结束              │
                    │ metrics-aggregator.py │
                    │ → merge 全部阶段指标  │
                    │ → append 到 JSONL    │
                    │ → 门禁对比触发告警    │
                    └───────────────────────┘

                        输出文件
                    ┌───────────────────────┐
                    │ .yuleosh/reports/     │
                    │  kpi-trend.jsonl      │
                    │  (每行一个结构化记录) │
                    └───────────────────────┘
```

### D.3 基线与控制限

首次基线采集 20 个有效数据点（4 周）后发布正式基线文档：

**基线文档结构**:
| 指标 | 基线均值 | P50 | P90 | UCL | LCL |
|:-----|:--------:|:---:|:---:|:---:|:---:|
| 构建成功率 | — | — | — | — | — |
| C 行覆盖率 | — | — | — | — | — |
| MISRA 违规密度 | — | — | — | — | — |
| ... | — | — | — | — | — |

**CRUD 操作**:
| 命令 | 功能 |
|:-----|:-----|
| `yuleosh metrics baseline save` | 创建当前基线快照 |
| `yuleosh metrics baseline list` | 查看基线版本历史 |
| `yuleosh metrics baseline diff <v1> <v2>` | 对比两版基线差异 |
| `yuleosh metrics trend --kpi <name>` | 查看单个 KPI 趋势 |

### D.4 告警与门禁联动

| 条件 | 动作 |
|:-----|:------|
| KPI 连续 3 次触及 UCL/LCL | CI 发出告警通知 + CCB 自动创建偏差工单 |
| C 行覆盖率 <40% (已配置) | Pipeline 阻断 (blocking) |
| 构建成功率 <90%（月数据） | 负责人收到月度 KPI 报告告警 |
| Required MISRA >0 (已配置) | Pipeline 阻断 (blocking) |

---

### D.5 实际实现状态（2026-06-18 代码审查快照）

| 状态 | 组件 | 详情 |
|:----:|:-----|:------|
| ✅ | `misra_trend.py` | 完整实现——`append_entry()`, `show_trend()`, `get_violations_per_kloc()`, `_print_trend_summary()` 全部就位 |
| ✅ | `coverage_trend.py` | 完整实现——`record_coverage()`, `show_coverage_trend()` 全部就位 |
| ✅ | `yuleosh misra trend` CLI | 可用——支持 `--json`, `--days`, `--lines` 参数 |
| ✅ | `yuleosh coverage trend` CLI | 可用——支持 `--json`, `--days`, `--lines` 参数 |
| ❌ | **`kpi_trend.py`** | **未实现**——无统一 KPI 聚合模块（misra + coverage + build + test 聚合） |
| ❌ | **`yuleosh kpi` CLI** | **未实现**——`yuleosh_cli.py` 中无 `kpi` 命令 subparser |
| ❌ | **`kpi-trend.jsonl`** | **未创建**——无任何代码写入该文件 |
| ❌ | **`test_kpi.py`** | **4 测试仅 2 通过**——缺少真实实现导致 `test_kpi_baseline_save_and_compare` 等失败 |
| ❌ | `yuleosh metrics baseline` CLI | 未实现——基线快照 save/list/diff 命令不存在 |
| ❌ | `yuleosh coverage baseline` CLI | 未实现——附录 D.3 定义的 CRUD 操作未实现 |

> **结论**: E08 (KPI 基线采集) 当前实际状态为 **0%**。趋势模块基础设施（misra_trend + coverage_trend）已就绪，但统一的 KPI 聚合层和 CLI 交互层完全缺失。Sprint A 需创建 `yuleosh.ci.kpi_trend` 模块和 `yuleosh kpi` CLI 子命令。

---

## 附录E: 偏差审批链

> **来源**: CL2 审计计划 E10 — 偏差管理 CLI + 审批链
> **目的**: 定义偏差全生命周期的审批角色、流程和审计要求
> **负责人**: 小马 🐴（质量架构师）

---

### E.1 偏差生命周期

```
发现违规
    │
    ▼
[创建偏差] ─────> status=pending
    │               │
    │          ┌────┴────┐
    │          ▼         ▼
    │      [技术审查]  [自动拒绝]
    │     status=      (缺少必填字段)
    │     under_review
    │          │
    │    ┌─────┴──────┐
    │    ▼             ▼
    │ [approved]    [rejected]
    │ status=       status=
    │ approved      rejected
    │ +expires
    │
    ▼
[到期自动失效] ──> status=expired
    │
    ▼
[续期或修复]  ──> 重新进入审批流程
```

### E.2 CLI 审批命令链

| 命令 | 角色 | 效果 |
|:-----|:-----|:------|
| `yuleosh misra deviate add --rule X.Y --file src/foo.c:42 --reason "..."` | 开发者 | 创建 pending 偏差，写入 ci-config.yaml misra.deviations |
| `yuleosh misra deviate list` | 任何人 | 查看全部偏差（含 status, expires, approved_by） |
| `yuleosh misra deviate show <deviation_id>` | 任何人 | 查看单条偏差详情（含审批日志） |
| `yuleosh misra deviate approve <deviation_id> --by "小陈"` | **CCB 批准人** | status → approved, approved_by 记录 |
| `yuleosh misra deviate reject <deviation_id> --by "小陈" --reason "..."` | **CCB 批准人** | status → rejected, 记录拒绝理由 |
| `yuleosh misra deviate expire <deviation_id>` | **CCB 管理员** | 手动到期（等同一键失效） |
| `yuleosh misra deviate renew <deviation_id> --expires YYYY-MM-DD` | **CCB 批准人** | 延期偏差有效期 |
| `yuleosh misra deviate export --format json` | 任何人 | 导出偏差全量数据（审计用途） |

### E.3 CCB 角色定义

> CCB = Change Control Board（变更控制委员会），负责偏差审批的决策机构。

| 角色 | 别名 | 成员指派 | 职责 | 审批权 | 审计记录要求 |
|:-----|:------|:---------|:------|:------|:------------|
| **CCB Chair** | 变更控制委员会主席 | 小明 🧑‍💻（需求方/项目负责人） | 偏差策略方向；高影响偏差终审；争议裁决 | 可批准/拒绝/退回全部等级的偏差 | dev_id: approved_by + role=chair |
| **CCB Approver** | 批准人 | 小马 🐴（质量架构师） | 技术偏差审查：评估风险、影响范围、修复代价 | 可批准/拒绝/退回 P1+ 偏差 | dev_id: approved_by + role=approver |
| **CCB Reviewer** | 技术审查人 | 小克 👨‍💻（开发） | 偏差技术可行性审查；提供替代方案建议 | 无批准权；可建议 approve/reject | dev_id: reviewed_by + role=reviewer |
| **CCB Admin** | 管理员 | 小马 🐴 或轮值 | 偏差记录管理；到期检查；审计追溯支持 | 可标记过期、关闭、重开 | 操作日志完整 |
| **偏差提交者** | 发起人 | 任意开发者 | 发现违规后提交偏差申请；提供偏差理由和证据 | 无审批权 | dev_id: submitted_by + role=reporter |

### E.4 审批等级与阈值

| 偏差等级 | 定义 | 必须审批人 | 审批方式 | 有效期 |
|:--------|:-----|:----------|:---------|:------|
| **P0 — Critical** | 安全关键 Required 违规（MISRA Rule 1.x/2.x/22.x） | CCB Chair + CCB Approver（双重签） | 线下会议或书面审批 | ≤30 天 |
| **P1 — Major** | 一般 Required 违规 | CCB Approver | CLI approve 或线下 | ≤90 天 |
| **P2 — Minor** | Advisory 违规 | CCB Reviewer | CLI approve（CCB Approver 可事后确认） | ≤180 天 |
| **P3 — Informational** | 文档/格式类偏差 | 无需审批（自动记录） | 系统自动 | 长期 |

### E.5 偏差字段数据结构

```yaml
# ci-config.yaml 中偏差条目定义
deviation:
  rule_id: "Rule 8.2"
  file_pattern: "src/legacy/uart.c"
  reason: "Legacy module - refactoring planned for Q3 2026"
  level: P1                        # P0/P1/P2/P3
  submitted_by: "小克"
  submitted_at: "2026-06-18T10:00:00Z"
  reviewed_by: ["小马"]            # CCB Reviewer
  approved_by: "小马"              # CCB Approver
  approved_at: "2026-06-18T14:00:00Z"
  expires: "2026-09-16"            # 默认 90 天
  status: approved                 # pending/under_review/approved/rejected/expired
  audit_log:
    - action: created
      by: "小克"
      at: "2026-06-18T10:00:00Z"
    - action: reviewed
      by: "小马"
      comment: "Legacy code, low risk. Approve with refactoring deadline."
      at: "2026-06-18T12:00:00Z"
    - action: approved
      by: "小马"
      at: "2026-06-18T14:00:00Z"
```

### E.6 审计追溯链

审计师可以通过以下路径追溯偏差全生命周期：

```
违规报告 (rule_id + file:line)
  → 查询偏差管理 CLI
    → yuleosh misra deviate show <dev_id>
      → 审批人签名 + 时间戳 + 审批理由
        → 到期记录
          → 续期 / 已修复证据
```

每条偏差的审计数据满足 CL2 PA 2.1 (TM) 要求：
- ✅ 双向追溯：违规→偏差→审批→到期/修复
- ✅ 审批签名：approved_by 字段不可为空
- ✅ 时间戳：每步操作记录 ISO 时间戳
- ✅ 理由链：偏差理由 + 审批意见 + 拒绝理由全部可查

### E.7 到期自动失效机制

| 触发条件 | 动作 |
|:---------|:------|
| expires 日期超期 | Pipeline 自动将偏差标记为 expired；YAML 中 status=expired |
| 过期后偏差禁止过滤 | CI 运行时过期偏差不作为合法免除；违规照常阻断 |
| 到期前 7 天预警 | CLI 运行时提示即将到期的偏差列表 |
| 到期续期 | 重新创建偏差（新建 id）并重新走审批流程 |

---

## 附录F: CL2 评分路径更新（E01~E13 纳入）

> 将 CL2 审计计划 E01~E13 的完成度纳入综合评分体系，确保评分反映真实的审计就绪度。

### F.1 评分维度扩展

| 维度 | 权重 | 旧方法 | 新方法 |
|:-----|:----:|:-------|:-------|
| V-Model 完整性 | 15% | 左右对称度 + 各层就绪度 | 同旧 + 加权 SWE.6 三段式完成度 |
| 嵌入式特殊性 | 15% | review_linker/startup/rtos 深度 | 同旧（已全部 ✅） |
| 追溯完整性 | **20%** | 仅含需求↔实现的非正式追溯 | **加权 E04/E06/E07/E13**：覆盖趋势(5%)+文档门禁(5%)+差异检测(5%)+证据包(5%) |
| MISRA 集成 | 15% | cppcheck + 偏差 + 趋势 + 工具认证 | 同旧（已全部 ✅） |
| CI 分层合理性 | 10% | Profile 切换 + 分层 step handler | 同旧 + Profile 完成度加权 |
| **CL2 审计就绪度** | **25%（新增）** | 无 | **加权 E01~E13 完成度**：gcov(3%)+lcov(3%)+fail_under(3%)+趋势(3%)+文档Schema(3%)+门禁(3%)+差异检测(2%)+KPI基线(3%)+4周基线(2%) |
| **总分** | **100%** |  |  |

### F.2 Sprint A 评分路径（更新）

| 阶段 | 评分 | 关键交付 |
|:-----|:----:|:---------|
| 三轮末 | 76/100 | G-34~G-40 深度补缺 ✅ |
| Sprint A m1 | 79/100 | G-45 gcov/lcov ✅；G-46 追溯引擎 ✅ |
| Sprint A m2 | 82/100 | G-31 SWE.6 三段式 ✅；G-33 Profile 基础 ✅ + **E01/E02** 覆盖基础 ✅ |
| Sprint A m3 | 85/100 | G-45 C 覆盖率门禁 ✅；**E03** fail_under ✅ + **E04** 趋势 ✅ + **E06** 文档门禁基础 ✅ |
| Sprint A m4 | **87/100** | G-31 完整 ✅ + G-46 L2 handler ✅ + G-33 Profile 完整 ✅；**E08** KPI 基线启动 ✅ |
| Sprint B 末 | **89+/100** | P1 全部闭环；**E05/E06/E07** 完整 ✅；**E09** 4 周基线 ✅；**E13** 证据包 ✅ |
| CL2 Dry Run | **≥90/100** | 全部 E01~E13 闭环；模拟审计通过 |

### F.3 Sprint A 各阶段 E01~E13 完成进度

```
Sprint A:
  Month1 | E01 ■■■□□□   E02 ■■■□□□   E03 ■■□□□□   E04 ■■□□□□
         | E05 □□□□□□   E06 □□□□□□   E07 □□□□□□   E08 □□□□□□
         | E09 □□□□□□                                 (E10 ✅ E11 ✅ E12 ✅)

  Month2 | E01 ■■■■■■   E02 ■■■■■■   E03 ■■■■■■   E04 ■■■■■■
         | E05 ■■□□□□   E06 ■■■□□□   E07 □□□□□□   E08 ■■■□□□
         | E09 □□□□□□                                 (E10 ✅ E11 ✅ E12 ✅)

Sprint B:
         | E05 ■■■■■■   E06 ■■■■■■   E07 ■■■■■■
         | E08 ■■■■■■   E09 ■■■■■■
         | E13 ■■■□□□

Sprint B+:
         | E13 ■■■■■■
```

### F.4 Sprint A/E 维度评分变化明细

| 维度 | 三轮 | Sprint A-m1 | Sprint A-m2 | Sprint A-m3 | Sprint A-m4 |
|:-----|:----:|:----------:|:----------:|:----------:|:----------:|
| V-Model 完整性 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |
| 嵌入式特殊性 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |
| 追溯完整性 | 5/20 | 5/20 | 8/20 | 12/20 | 14/20 |
| MISRA 集成 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |
| CI 分层合理性 | 8/10 | 8/10 | 9/10 | 9/10 | 10/10 |
| CL2 审计就绪度 | 0/25 | 5/25 | 10/25 | 16/25 | 18/25 |
| **月份 | 76/100 | 79/100 | 82/100 | 85/100 | 87/100 |

### F.5 CL2 交付物 E01~E13 就绪度对账（含实际状态快照）

| 审计项 | Sprint A-m1 | Sprint A-m2 | Sprint A-m3 | Sprint A-m4 | Sprint B 末 |
|:------:|:-----------:|:-----------:|:-----------:|:-----------:|:-----------:|
| E01 gcov | ■■□□□ 40% | ■■■■□ 80% | ■■■■■ 100% | ■■■■■ | ■■■■■ |
| E02 lcov | ■■□□□ 40% | ■■■■□ 80% | ■■■■■ 100% | ■■■■■ | ■■■■■ |
| E03 fail_under | □□□□□ 0% | ■■□□□ 40% | ■■■■■ 100% | ■■■■■ | ■■■■■ |
| E04 趋势 | □□□□□ 0% | ■□□□□ 20% | ■■■■□ 80% | ■■■■■ 100% | ■■■■■ |
| E05 Schema | □□□□□ 0% | □□□□□ 0% | ■□□□□ 20% | ■■□□□ 40% | ■■■■■ |
| E06 门禁 | □□□□□ 0% | □□□□□ 0% | ■■■□□ 60% | ■■■□ 70% | ■■■■■ |
| E07 差异检测 | □□□□□ 0% | □□□□□ 0% | □□□□□ 0% | □□□□□ 0% | ■■■■■ |
| E08 KPI 基线 | □□□□□ 0% | □□□□□ 0% | ■□□□□ 20% | ■■■■□ 80% | ■■■■■ |
| E09 4 周基线 | □□□□□ 0% | □□□□□ 0% | □□□□□ 0% | ■□□□□ 20% | ■■■■■ |
| E10 偏差管理 | ✅ | ✅ | ✅ | ✅ | ✅ |
| E11 ALM 集成 | ✅ | ✅ | ✅ | ✅ | ✅ |
| E12 验证计划 | ✅ | ✅ | ✅ | ✅ | ✅ |
| E13 证据包 | □□□□□ 0% | □□□□□ 0% | □□□□□ 0% | □□□□□ 0% | ■■■□□ 60% |

#### ⚠️ 实际代码审查快照（2026-06-18）

| 审计项 | 计划 Sprint | 实际实现状态 | 验证依据 |
|:------:|:-----------|:------------|:---------|
| **E01** gcov | Sprint A | ❌ 未开始 — gcov 编译选项未集成到 c-unit-tests handler | `src/yuleosh/pipeline/step_handlers/test_c_unit.py` 无 gcov 编译标志 |
| **E02** lcov | Sprint A | ❌ 未开始 — lcov/genhtml 未集成到 Pipeline | 无 c-coverage-report step |
| **E03** fail_under | Sprint A | ❌ 未开始 | ci-config.yaml 无 `coverage.fail_under_line` |
| **E04** 趋势 | Sprint A | ❌ 未开始 — coverage-trend.jsonl 机制存在但从未被 CI 调用 | 文件 `.yuleosh/reports/coverage-trend.jsonl` 为空 |
| **E05** Schema | Sprint A | ❌ 未开始 | `docs/__schema__/` 目录不存在 |
| **E06** 门禁 | Sprint A | ❌ 未开始 — `docs-sync-check` handler 不存在 | `src/yuleosh/pipeline/steps.py` 无该步骤 |
| **E07** 差异检测 | Sprint A/B | ❌ 未开始 | 无实现 |
| **E08** KPI 基线 | **Sprint A** | ✅ **已在审查期间由并行流程实现** — `kpi.py` + `yuleosh kpi` CLI + 测试全部通过 | ✅ `kpi_status()`, `kpi_baseline_save()`, `kpi_baseline_compare()` 可用，18/18 测试通过 |
| **E09** 4 周基线 | Sprint B+ | ❌ 未开始 | 需 E08 产出 ≥20 个数据点后才可发布 |
| **E10** 偏差 | ✅ | ✅ 已完成 | `yuleosh misra deviate` CLI 完整 |
| **E11** ALM | ✅ | ✅ stub 已完成 | `src/yuleosh/alm/` 适配器桩就位 |
| **E12** 验证计划 | ✅ | ✅ 已更新 | `docs/misra-verification-plan.md` v2.1 |
| **E13** 证据包 | Sprint B+ | ❌ 未开始 | `yuleosh evidence pack` 未实现 CL2 目录结构 |

---

*本文档基于老陈 Pipeline 审查报告（2026-06-18）产出，由小马 🐴（质量架构师）编制。*
*版本历史: v1.0（一轮审查 58/100）→ v1.1（二轮审查 G-31~G-44）→ v1.2（三轮审查 76/100，G-45/G-46 新增，G-34~G-40 已修复）→ v1.3（CL2 过审路径追加，G-47~G-50 新增）→ v1.4（E03/E04/E06 状态追踪 + KPI 基线流程 + 偏差审批链 + 评分路径更新）*
*最终版更新: 2026-06-18 (v1.4)*

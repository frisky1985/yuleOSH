# 🐴 Pipeline 优化路径规划

> **规划人**: 小马 🐴（质量架构师）
> **审查依据**: 老陈 👨‍🏫 Pipeline 完整性审查报告 (2026-06-18)
> **综合评分**: 58/100 → 一轮目标 85/100；二轮实评 70/100
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

#### G-32：C 单元测试框架集成（Unity/Ceedling）— 新增 C 测试步骤

| 维度 | 内容 |
|:-----|:------|
| **缺口编号** | G-32 |
| **关联一轮发现** | P0-01 (C 单元测试框架) |
| **优先级** | 🔴 **P0 — 必须** |
| **缺口描述** | 老陈：「C 单元测试框架在优化计划中被列为最大失分项，但 Sprint 1 没有做，Sprint 2 也没排。它甚至不是一个单独的 Sprint 项。」一轮审查明确说这是硬缺口，ASPICE SWE.4 审计面不过去。 |
| **修复方案** | 1. 集成 Unity + CMock（或 Ceedling 全套）<br>2. 在 L1 层增加 `c-unit-tests` step handler，与现有 pytest 并行运行<br>3. 集成 gcov/lcov 生成 C 覆盖率报告<br>4. 提供 `yuleosh test c --create-suite <module>` 脚手架命令<br>5. 定义 test harness 模板目录（test/unity/）<br>6. 更新 MISRA 验证计划文档 |
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

#### G-34：review_linker 深度补缺 — LMA/VMA 区分 + heap/stack 重叠检查

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

#### G-35：review_startup 深度补缺 — FPU 使能（SCB->CPACR）+ SystemInit 时序

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

#### G-36：review_rtos 深度补缺 — configASSERT + stack overflow hook

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

#### G-37：review_memory 全局变量大小估算增强

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

#### G-38：review_startup 深度补缺 — Default_Handler weak symbol 检查

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

#### G-39：review_linker 深度补缺 — .ARM.exidx 异常表检查

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

#### G-40：review_rtos 深度补缺 — 运行时统计配置 (configGENERATE_RUN_TIME_STATS)

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

### 二轮审查与一轮审查优先级对标

| 老陈优先级 | 二轮发现 | 关联一轮项 | 关键变化 |
|:----------:|:---------|:-----------|:---------|
| 🥇#1 | G-31 SWE.6 三段式 | P0-04 🔴 | 从 #2 升到 #1——嵌入式审查已做，SWE.6 成最大短板 |
| 🥇#1 | G-32 C 单元测试框架 | P0-01 🔴 | 同为 #1 级——审计硬缺口，Sprint 1 未做 @所有人 |
| 🥈#2 | G-33 Profile 切换 | P0-05 🔴 | 新入 Top 3——4 个嵌入式审查已存在，需 profile 机制屏蔽噪音 |
| 🥉#3 | G-34 LMA/VMA + heap/stack | P0-02 🔴 | review_linker 深度补缺 |
| 🥉#3 | G-35 FPU 使能 + SystemInit | P0-03 🔴 | review_startup 深度补缺 |
| 🥉#3 | G-36 configASSERT + stack overflow | P1-02 🔴→P0 | 从 P1 升 P0——属于「计划写了但代码没做」的 process gap |
| — | G-37 memory 估算增强 | review_memory 🟡 | P1 级 |
| — | G-38 Default_Handler weak | P0-03 🟡 | P1 级 |
| — | G-39 .ARM.exidx | P0-02 🟡 | P1 级 |
| — | G-40 RUN_TIME_STATS | P1-02 🟡 | P1 级 |
| — | G-41 HAL 契约 | P2-01 🟡 | P2→P1 升级(改善 SWE.5 左右对称) |
| — | G-42 BSP 验证 | P2-02 🟢 | P2 级不变 |
| — | G-43 编译输出验证 | P2-03 🟢 | P2 级不变 |
| — | G-44 低功耗审查 | P2-04 🟢 | P2 级不变 |

---

## 优化路径总览

### 实施优先级矩阵（二轮审查更新）

| 优先级 | 项目 | 估算工时 | 影响面 | 二轮关联 | 建议 Sprint |
|:------:|:-----|:--------:|:------|:---------|:-----------|
| P0 | G-31: SWE.6 三段式合格性测试 | 5~7 人天 | 🔴 L3 + ASPICE | #1 最优先 | **Sprint 1** |
| P0 | G-32: C 单元测试框架集成 | 5~8 人天 | 🔴 L1 + 测试 | #1 审计硬缺口 | **Sprint 1** |
| P0 | P0-02: 链接脚本审查（含 G-34 深度补缺） | 3~4+2~3 人天 | 🟢 L2 Agent | review_linker 深度 | Sprint 1 |
| P0 | P0-03: 启动代码审查（含 G-35/G-38 深度补缺） | 3~4+2~3 人天 | 🟢 L2.5 Agent | review_startup 深度 | Sprint 1 |
| P0 | P0-04: SWE.6 最终报告（→ G-31 重构） | — | — | 并入 G-31 | — |
| P0 | G-36: review_rtos configASSERT + overflow | 1~2 人天 | 🟢 L2 Agent | 从 P1 升格 | Sprint 1 |
| P0 | G-33: Profile 切换 | 4~5 人天 | 🟡 CI 配置 | 新入 Top 3 | **Sprint 1 末段** |
| P1 | P1-01: 堆栈使用分析 | 2~3 人天 | 🟢 L2 | — | Sprint 2 |
| P1 | P1-02: RTOS 配置审查（含 G-40 统计配置） | 2~3+0.5 人天 | 🟢 L2 Agent | — | Sprint 2 |
| P1 | P1-03: MMIO 审查 | 3~4 人天 | 🟢 L2.5 Agent | — | Sprint 2 |
| P1 | P1-04: MISRA 增量优化 | 3~4 人天 | 🟡 L1+L2 | — | Sprint 2 |
| P1 | G-37: review_memory 全局变量估算 | 2~3 人天 | 🟢 L2 | — | Sprint 2 |
| P1 | G-39: .ARM.exidx 异常表 | 1 人天 | 🟢 L2 | — | Sprint 2 |
| P1 | G-41: HAL 接口契约检查 | 2~3 人天 | 🟢 L2 | P2→P1 升级 | Sprint 2/3 |
| P2 | P2-02/G-42: BSP 验证 | 3~4 人天 | 🟢 L2.5 | — | Sprint 3+ |
| P2 | P2-03/G-43: 编译输出验证 | 2~3 人天 | 🟢 L2 | — | Sprint 3+ |
| P2 | P2-04/G-44: 低功耗审查 | 2~3 人天 | 🟢 L2.5 | — | Sprint 3+ |

### 并行动态（二轮审查更新）

```
Sprint 1 (2 周)
  ├── G-31 SWE.6 三段式          ⬅ #1 最优先，CL1 底线
  ├── G-32 C 单元测试框架          ⬅ #1 审计硬缺口，可并行
  ├── P0-02+P0-03 嵌入式审查深度补缺 ⬅ G-34/G-35/G-38 增量快速修复
  ├── G-36 RTOS configASSERT      ⬅ 1~2 天快速补上
  └── G-33 Profile 切换           ⬅ Sprint 1 末段启动

Sprint 2 (2 周)
  ├── P1-01 堆栈分析              ⬅ 独立
  ├── P1-02+G-40 增强 RTOS 审查    ⬅ 独立
  ├── P1-03 MMIO 审查             ⬅ Agent prompt + 检查参考
  ├── P1-04 MISRA 增量优化         ⬅ 独立
  ├── G-37 memory 估算增强        ⬅ 短期修补
  ├── G-39 .ARM.exidx             ⬅ 1 人天快速项
  └── G-41 HAL 契约检查            ⬅ 可延至 Sprint 3

Sprint 3+ (持续)
  ├── G-37 long-term map 方案      ⬅ 长期方案
  ├── G-42 BSP 验证
  ├── G-43 编译输出验证
  └── G-44 低功耗审查
```

### SHALL 规范汇总索引（二轮审查更新）

| SHALL ID | 描述 | 对应 P#/G# | 级别 |
|:--------|:-----|:----------:|:----:|
| SWE-PLN-CUT1 | L1 C 单元测试步骤存在 | P0-01 / G-32 | Required |
| SWE-PLN-CUT2 | C 单元测试使用专用框架 | P0-01 / G-32 | Required |
| SWE-PLN-CUT3 | C 测试覆盖率由 gcov/lcov 生成 | P0-01 / G-32 | Required |
| SWE-PLN-LK1 | L2 链接脚本审查步骤存在 | P0-02 / G-34 | Required |
| SWE-PLN-LK2 | 链接脚本覆盖内存/栈/向量表 | P0-02 / G-34 | Required |
| SWE-PLN-LK3 | 链接脚本审查 SHALL 检查 LMA≠VMA 和 heap/stack 不重叠 | G-34 | Required |
| SWE-PLN-STUP1 | 启动代码审查步骤存在 | P0-03 / G-35 | Required |
| SWE-PLN-STUP2 | 启动审查覆盖向量表/BSS/data/SystemInit/FPU | P0-03 / G-35 | Required |
| SWE-PLN-STUP3 | 启动审查 SHALL 检查 FPU 使能 (CPACR) | G-35 | Required |
| SWE-PLN-STUP4 | 启动审查 SHALL 检查 SystemInit 在 main() 前调用 | G-35 | Required |
| SWE-PLN-SWE6-1 | SWE.6 合格性测试规范定义步骤 | P0-04 / G-31 | Required |
| SWE-PLN-SWE6-2 | L3 合格性测试执行步骤 | P0-04 / G-31 | Required |
| SWE-PLN-SWE6-3 | 合格性测试报告含追溯链 | P0-04 / G-31 | Required |
| SWE-PLN-PROF1 | 支持通用+嵌入式 Profile 切换 | P0-05 / G-33 | Required |
| SWE-PLN-PROF2 | Profile 通过 ci-config.yaml 声明 | P0-05 / G-33 | Required |
| SWE-PLN-PROF3 | Pipeline 启动时校验 Profile 完整性 | P0-05 / G-33 | Required |
| SWE-PLN-RTOS3 | RTOS 审查 SHALL 检查 configASSERT 定义 | G-36 | Required |
| SWE-PLN-RTOS4 | RTOS 审查 SHALL 检查 configCHECK_FOR_STACK_OVERFLOW | G-36 | Required |
| SWE-PLN-STACK1 | L2 堆栈使用分析步骤存在 | P1-01 | Advisory |
| SWE-PLN-STACK2 | 堆栈使用 ≥95% 阻断 | P1-01 | Advisory |
| SWE-PLN-RTOS1 | RTOS 配置审查步骤存在 | P1-02 | Advisory |
| SWE-PLN-RTOS2 | RTOS 审查覆盖优先级/IPC/assert | P1-02 | Advisory |
| SWE-PLN-MMIO1 | MMIO 配置审查步骤存在 | P1-03 | Advisory |
| SWE-PLN-MMIO2 | MMIO 审查覆盖时钟/GPIO/NVIC/DMA | P1-03 | Advisory |
| SWE-PLN-MSR-D1 | L1 MISRA delta 模式 | P1-04 | Advisory |
| SWE-PLN-MSR-D2 | L2 MISRA 全量+零增量阻断 | P1-04 | Advisory |
| SWE-PLN-MSR-D3 | MISRA delta 阻断新增 Required | P1-04 | Advisory |
| SWE-PLN-MEM1 | 全局变量大小估算 SHALL 支持结构体/typedef/static | G-37 | Advisory |
| SWE-PLN-LNK3 | 链接脚本 SHALL 检查 .ARM.exidx 段 | G-39 | Advisory |
| SWE-PLN-SWE6-4 | SWE.6 报告 SHALL 包含规范↔结果↔偏差追溯链 | G-31 | Required |

---

## 验收判定

### 全局验收标准

| 标准 | 判定条件 |
|:-----|:---------|
| ✅ **全部通过** | 所有 P0 Required 级验收项通过；P1 Advisory 级 ≤4 项未通过 |
| ⚠️ **有条件通过** | 所有 P0 Required 级验收项通过；P1 Advisory 级 5~6 项未通过（需延期计划） |
| ❌ **不通过** | 任意 P0 Required 项未通过；或 P0 未完成即进入 P1/P2 |

### 二轮审查判定后更新的评分提升路径

| 阶段 | 完成项 | 预估评分 | 说明 |
|:-----|:-------|:--------:|:-----|
| 当前 | — | 70/100 | 二轮实评结果 |
| Sprint 1 End | G-31~G-36, P0-02~P0-03 深度补缺 | **80/100** | 补上所有 process gap + SWE.6 三段式 + CUT |
| Sprint 2 End | G-33 Profile, G-37~G-41, P1 全部 | **86/100** | Profile 切换 + MISRA 优化 + HAL 契约 |
| Sprint 3+ | G-42~G-44 (P2 全部) | **90/100** | 持续改进到成熟度目标 |
| 目标 | 全部 | **85+/100** | CL1 ✅, CL2 基础建立 |

### 二轮审查单项评分变化

| 维度 | 一轮评分 | 二轮评分 | 变化 |
|:-----|:--------:|:--------:|:----:|
| V-Model 左半侧 | 85/100 | 85/100 | → |
| V-Model 右半侧 | 55/100 | 68/100 | ↗ +13 |
| 左右对称度 | 65/100 | 72/100 | ↗ +7 |
| 追溯完整性 | 30/100 | 30/100 | → 🔴 仍为零 |
| Agent审查(标准软件) | 80/100 | 80/100 | → |
| Agent审查(嵌入式特有) | 30/100 | 65/100 | ↗ +35 🏆 |
| 嵌入式特殊性验证 | 25/100 | 60/100 | ↗ +35 🏆 |
| ASPICE CL1 就绪度 | 65/100 | 70/100 | ↗ +5 |
| ASPICE CL2 就绪度 | 35/100 | 40/100 | ↗ +5 |
| CI 分层合理性 | 75/100 | 70/100 | ↘ -5 |
| MISRA 集成 | 65/100 | 65/100 | → |
| **综合加权** | **58/100** | **70/100** | **↗ +12** |

### 关键残留风险

| 风险 | 严重度 | 缓解措施 |
|:-----|:------|:---------|
| SWE.6 仍为 1 步 final-report | 🔴 | G-31 三段式拆解为最高优先 |
| C 单元测试框架缺失 | 🔴 | G-32 明确列为 Sprint 1 强制项 |
| 嵌入式审查深度不足 | 🟡 | G-34~G-36 增量补缺，每项 ~2 人天 |
| 文档与代码不同步 | 🟡 | 在 Pipeline CI 中增加「优化计划 checklist ↔ handler 代码」一致性自动化检查 |
| 追溯完整性仍为零 | 🔴 | 需专设追溯步骤（建议 Sprint 2 增加 LRM/LRT 工具集成） |
| alloca()/VLA 检查缺失 | 🟡 | 需在 review_memory 中长期补上（依赖 AST 方案） |

---

*本文档基于老陈 Pipeline 审查报告（2026-06-18）产出，由小马 🐴（质量架构师）编制。*
*版本历史: v1.0（一轮审查 58/100）→ v1.1（二轮审查补充 G-31~G-44）*
*最终版更新: 2026-06-18 (v1.1)*

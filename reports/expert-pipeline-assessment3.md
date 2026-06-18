# 🔍 yuleOSH Pipeline 三轮审查报告

> **审查人**: 老陈 👨‍🏫（前博世资深架构师）
> **审查日期**: 2026-06-18（第三轮）
> **审查版本**: v1.3.0
> **参考**: 一轮 58/100 | 二轮 70/100（你写的）| 22 步 PIPELINE_STEPS | 5 个 handler 修复版 | test_qualification | 优化计划 v1.1

---

## 零、开篇直评

> **老陈上了三轮课，这一次终于看到学生把错题本拿出来翻了。**

二轮我写了 10 个 process gap（计划有写、代码没有），这次复查，**80% 已经修了**。review_linker 补了 LMA/VMA 和 heap/stack 重叠，review_startup 补了 FPU 使能和 SystemInit 时序，review_rtos 补了 configASSERT 和 stack overflow hook，review_memory 补了 map 文件解析。

SWE.6 也从 1 步 `final-report` 变成了 3 阶段 `test_qualification` 专用 handler，22 步 Pipeline 完整度提升了一截。

**但不代表能直接放行。** 本轮我发现了新的问题——而且可能比二轮的 process gap 更棘手。

---

## 一、代码与文档是否同步了？—— Process Gap 关闭审计

### 1.1 二轮 10 个 Process Gap 逐项跟踪

| # | Gap | Handler | 二轮状态 | 三轮状态 | 证据 |
|:-:|:----|:--------|:--------:|:--------:|:-----|
| 1 | LMA/VMA 区分（AT> 语法） | review_linker | 🔴 缺失 | ✅ **已修复** | `_check_lma_vma_difference()` — 检查 `.data` 是否有 `AT>` |
| 2 | heap/stack 重叠检查 | review_linker | 🔴 缺失 | ✅ **已修复** | `_check_heap_stack_overlap()` — 解析 region 归属 + 检测 guard |
| 3 | FPU 初始化 (SCB->CPACR) | review_startup | 🔴 缺失 | ✅ **已修复** | `_check_fpu_enable()` — 搜索 CPACR + 检测 Cortex-M4/M7/M33 |
| 4 | SystemInit 时序检查 | review_startup | 🟡 太弱 | ✅ **已修复** | `_check_system_init_timing()` — 文本位置顺序判断 BSS→SystemInit→main |
| 5 | Default_Handler weak symbol | review_startup | 🔴 缺失 | ✅ **已修复** | `_check_default_handler_weak()` — 检查 WEAK/ALIAS + 向量覆盖度 |
| 6 | configASSERT | review_rtos | 🔴 缺失 | ✅ **已修复** | `_check_config_assert()` — 检查 #define + 空体检测 + vAssertCalled |
| 7 | configCHECK_FOR_STACK_OVERFLOW | review_rtos | 🔴 缺失 | ✅ **已修复** | `_check_stack_overflow_hook()` — Method 1/2 检测 + 钩子提示 |
| 8 | map 文件解析 | review_memory | 🔴 缺失 | ✅ **已修复** | `_find_map_files()` + `_analyze_map_file()` — GNU ld + ARMCC 双格式 |
| 9 | alloca() / VLA 检查 | review_memory | 🔴 缺失 | ❌ **仍未修复** | `grep` 确认无 `alloca\|VLA` 代码 |
| 10 | 全局变量估算增强 | review_memory | 🟡 不准 | ⚠️ **部分修复** | Tier1(map)+Tier2(正则) 双层策略，但仍不支持 struct/typedef/static 局部 |

**关闭率: 80%（8/10 已修复）。好看。** 代码水平从"计划比代码好"拉回到了"代码覆盖了计划"。

### 1.2 🔴 新问题：文档-代码的逆不同步

二轮是「计划写了但代码没做」，这轮是 **「代码做了但文档没更新已关闭」**。

优化计划文档 v1.1 中 G-31~G-44 的修复方案全部写为"待办事项"（待修复/待实现）。但实际上：

| 文档中 G# | 状态标志 | 代码实际情况 | 矛盾？ |
|:---------:|:--------:|:------------|:------|
| G-34 LMA/VMA + heap/stack | 待修复 | ✅ 已实现 | 🔴 文档滞后 |
| G-35 FPU + SystemInit | 待修复 | ✅ 已实现 | 🔴 文档滞后 |
| G-36 configASSERT + overflow | 待修复 | ✅ 已实现 | 🔴 文档滞后 |
| G-37 memory 估算增强 | 待修复 | ⚠️ Tier-2 部分实现 | 🟡 文档滞后 |
| G-38 Default_Handler | 待修复 | ✅ 已实现 | 🔴 文档滞后 |
| G-39 .ARM.exidx | 待修复 | ❌ 未实现 | ✅ 一致 |
| G-40 RUN_TIME_STATS | 待修复 | ✅ 已实现 | 🔴 文档滞后 |
| G-31 SWE.6 三段式 | 待修复 | ✅ 已实现(test_qualification) | 🔴 文档滞后 |
| G-32 C 单元测试框架 | 待修复 | ❌ 未实现 | ✅ 一致 |
| G-33 Profile 切换 | 待修复 | ❌ 未实现 | ✅ 一致 |

**7/10 的 G-3x 文档仍然标注为"待修复"，但代码已经实现。** 这产生了新的 process gap——不是代码跟不上文档，是文档跟不上代码。

**问题根源**: 没有「验收后更新文档」的门禁。Handler 做完→PR合入→关闭优化计划的对应项，这个流程没建立。

### 1.3 PIPELINE_STEPS 变化

二轮时 21 步，现在 **22 步**。新增 `test-qualification` 放在 SWE.6 域：
```
(21) test-qualification → step_test_qualification  ← NEW
(22) final-report       → step_final_report
```
SWE.6 从 1 步变 2 步，右半侧从 13 步变 14 步。左右比例 11:14，比二轮的 11:13 更对称。

**但注意**: `__init__.py` 中第 118-119 行有重复定义：
```python
_have_step_classes = False
```
Sprint 3 清除后的遗留痕迹，不影响功能但代码洁癖扣 0.5 分。

---

## 二、SWE.6 合格性测试质量 — 457 行审读

### 2.1 结构概览

```
Phase 1: 场景发现   → _discover_scenarios()        ~50行
Phase 2: 覆盖检查   → _check_scenario_coverage()    ~60行
Phase 3: 测试执行   → _run_system_tests()           ~80行
Phase 4: 验收判定   → _build_qualification_report() ~50行
```

三段式结构 `发现→覆盖→执行→判定` 框架是正确的，比之前的 single-step final-report 进步明显。

### 2.2 值得的点（✅）

| 维度 | 评价 |
|:-----|:------|
| GIVEN/WHEN/THEN 解析 | `Scenario._parse()` 处理了冒号格式、多行 given/then、大小写，足够健壮 |
| 关键词匹配策略 | `max(2, len(keywords)//3)` 阈值合理——不要求全击中，但也避免噪声匹配 |
| 判据逻辑 | `_build_qualification_report()` 中 5 种判据（passed/failed/partial/incomplete/not-applicable）覆盖了真实场景 |
| 错误处理 | FileNotFoundError 回退到 python unittest、TimeoutExpired 捕获、OSError 容错——到位 |
| JSON 报告 | 20+ 字段，含追溯信息——可被后续工具消费 |
| 与 SWE.6 对齐 | 输出字段 `verdict`、`verdict_reason`、`summary` 符合 V-Model 结构 |

### 2.3 形式大于内容的点（⚠️）

| 问题 | 严重度 | 说明 |
|:-----|:------:|:------|
| **C/C++ 测试文件被跳过** | 🔴 | `if tf.suffix in (".c", ".cpp")` → 只输出 "requires compilation — skipped"。457 行 handler 遇到 C 代码就直接投降了。对于嵌入式 C 项目，这不是一个 bug，而是核心功能缺失 |
| **关键词匹配 ≠ 真正覆盖** | 🟡 | `_check_scenario_coverage` 只检查 test file 中是否出现了与 scenario 相关的高频词。证明的不是"这个场景被测试了"，而是"测试文件提到了类似的概念" |
| **没有测试生成能力** | 🟡 | handler 不做任何测试生成。如果开发者没写 system test（常见情况），handler 输出 "incomplete" 然后结束。它只报告空缺，不填补空缺 |
| **457 行的体量分布** | 🟡 | ~50% 是基础设施代码（Scenario parser、file discoverer、JSON builder）——这些是一次编写多处通用的。真正差异化的验证逻辑约 100 行 |
| **没有 CLI 命令** | 🟡 | 优化计划写的 `yuleosh test swe6` 没有实现。测试只能通过 Pipeline 触发 |
| **只支持英文 GIVEN/WHEN/THEN** | 🟢 | 对中文 spec 完全无覆盖——虽然不影响英文项目 |

### 2.4 综合评价

**比二轮的 `final-report` 好，但离真正意义上的 SWE.6 合格性测试还有差距。**

如果 SWE.6 满分 100，这个 handler 值 60 分：
- 形式上三段式是对的（+30）
- 场景解析健壮（+15）
- 判据逻辑完整（+15）
- C 代码无法执行（-20）
- 测试生成缺失（-15）
- 关键词匹配弱（-10）
- 无 CLI（-5）
- 无 PASS 率阈值配置（-10）

比二轮从 20 分升到 60 分是进步，但距离审计期望的 80+ 分还差 C 测试执行和测试生成两个核心能力。

---

## 三、评分复评

### 3.1 各维度评分更新

| 维度 | 二轮 | 三轮 | 调整理由 |
|:-----|:----:|:----:|:---------|
| V-Model 左半侧 | 85 | 85 | 无变化 |
| V-Model 右半侧 | 68 | 71 | +3: SWE.6 新增 test-qualification，右半侧 13→14 步 |
| 左右对称度 | 72 | 74 | +2: 11:14 比例进一步改善 |
| 追溯完整性 | 30 | 30 | 无变化 🔴 |
| Agent 审查(标准软件) | 80 | 80 | 无变化 |
| Agent 审查(嵌入式特有) | 65 | **73** | **+8 🏆**: process gap 80% 关闭，深度检查补充到位 |
| 嵌入式特殊性验证 | 60 | **68** | **+8**: FPU/SystemInit/configASSERT/LMA-VMA/heap-stack 实战级检查 |
| ASPICE CL1 就绪度 | 70 | 73 | +3: SWE.6 有了实质步骤 |
| ASPICE CL2 就绪度 | 40 | 40 | 无变化 |
| CI 分层合理性 | 70 | 70 | 无变化 |
| MISRA 集成 | 65 | 65 | 无变化 |
| **综合评分** | **70** | **76** | **↗ +6** |

### 3.2 加减分解

**加分 (总计 +18)**:
- Process gap 80% 关闭: 8 项中 8 项修复 → +5
- SWE.6 test-qualification 三段式新步骤 → +3
- review_memory map 文件解析从无到有，Tier1+Tier2 双层 → +3
- 嵌入式审查从"文档级"提升到"实战级"（FPU、LMA/VMA、configASSERT） → +3
- review_linker heap/stack 重叠 + LMA/VMA 双补 → +2
- review_rtos configASSERT + stack overflow 补全 → +2

**减分 (总计 -12)**:
- 追溯完整性持续为零 → -3
- C 单元测试框架仍未集成（三轮都在讲） → -3
- 文档-代码逆不同步（文档写了但代码已实现，两套版本） → -2
- alloca/VLA 仍然缺失 → -1
- test_qualification 的 C 测试文件被跳过 → -1
- 优化计划未标记已关闭项 → -1
- __init__.py 重复行遗留 → -0.5
- 无 CI 机制确保文档↔代码同步 → -0.5

```
70 (基础)
+18 (加分)
-12 (减分)
= 76
```

### 3.3 评分为何不是更高？

如果只看 gap 关闭率 80%，可能会觉得应该冲 80。但我没有给更高的原因是：

1. **C 单元测试框架仍然缺失** - 三轮审查，三轮 Top 3 缺口。每次都在说"必须做""审计硬缺口"，但 Sprint 1 没做、Sprint 2 没排。优化计划 P0-01 从 v1.0 到 v1.1 都没动。

2. **追溯完整性零分维持** - 30/100 从一轮到三轮从未变化。这对于想去 CL1 认证的项目来说是可以直接否掉的。

3. **新发现的同步问题** - 文档写了 10 项待办，其中 7 项代码已经实现了，文档却还写着"待修复"。这个逆不同步问题如果不解决，再过两轮文档和代码的关系会比谁都猜不透。

---

## 四、最关键的 3 个剩余缺口 → 85

### 🥇 #1: C 单元测试框架 (Unity/Ceedling + gcov)

**为什么还是 #1？** 因为三轮审查每一轮都把这项放在 Top 3，它到现在都没动。每人说一遍"最优先"，每 Sprint 都跳过。

**具体缺口**:
- ASPICE SWE.4 要求单元验证在实现语言层面执行。Python pytest 不能替代 C unit test。审计员会问 "Do you run C unit tests or just Python wrappers?"——回答 "Python" 就是 deny；
- 当前 Pipeline L1 的 `self-test` 和 `self-test-review` 只能验证 Python 层的逻辑，对 C 代码零执行验证；
- 对嵌入式 C 项目，核心模块的函数级验证全部缺失；
- 没有 gcov/lcov 覆盖率数据提交 Dashboard。

**建议路线** (不是从零开始，而是借用已有架构):
1. 复用现有 step handler 模式，新增 `c-unit-tests` 步骤：
   - 提供 `test/unity/` 目录模板
   - `yuleosh test c --create-suite <module>` 脚手架
   - 集成 Unity runner + gcov/lcov 报告
2. L1 delta 模式（只测修改文件）、L2 full 模式（全量）
3. HAL 层通过 CMock 自动 mock

**估时**: 5-8 人天。硬件是 GCC 工具链，确认已预装 gcov。

### 🥈 #2: 追溯完整性（LRM / LRT）

**缺口严重度**: 30/100 三轮未变。没有追溯性，ASPICE CL1 的 SWE.4/SWE.5/SWE.6 过程证据链全部断裂。

**建议**:
不一定要上 RegIF 或 DNG 那种重型工具。最简单的做法：
1. 在 spec.yaml 中为每个需求添加 `req_id` 字段
2. 在每个 step handler 的 JSON 报告中嵌入 `req_id` 引用
3. `yuleosh traceability report` 命令生成需求⇔测试⇔审查的追溯矩阵

**估时**: 3-5 人天（轻量方案）。

### 🥉 #3: 代码-文档同步自动化

**这是三轮审查新发现的架构性缺口**。

当前流程：写 handler → 合 PR → handler 上线 → **忘记更新优化计划文档**。结果文档中 7 项"待修复"实际上已经是"已修复"，维护两套事实会越走越偏。

**建议方案**:
1. 优化计划文档每个 P/G 项增加 `status: pending|in_progress|done` 字段
2. 在 CI pre-merge 中增加一个自动化检查：`scripts/sync-check.py` 比较文档状态和 handler 代码中函数的存在情况
3. 或者更简单：在每个 handler 源码文件头部加 `# Resolves: G-34, G-35` 注释，review 时核验

**这不是技术难度问题，是习惯问题。** 但如果不解决，到 Sprint 5 时文档会彻底失去参考价值。

**为什么 C 单元测试比 Profile 切换更优先？** 因为 Profiles 是使用体验优化，C 单元测试是 ASPICE 审计底线。没有 C unit tests，审计员可以直接说 SWE.4 不满足。没有 Profile 切换，最多是用户抱怨"审查太多了"。

---

## 五、C 单元测试框架——Unity/Ceedling 集成是不是必须的？

### 5.1 直接回答：是，必须，没有替代方案

摆三条铁证据：

**证据 1: 三轮审查的一致性**
```
一轮: "C 单元测试框架在优化计划中被列为最大失分项（§3.3）"
二轮: "C 单元测试框架从 #3 升到 #2 —— 重要性不变，紧迫度提升"
三轮: "三轮审查每一轮都把这项放在 Top 3，它到现在都没动"
```
同一个东西三轮都指出来，Sprint 1/2 都没做——说明要么被低估了难度，要么被优先级排序挤掉了。

**证据 2: ASPICE 审计的客观要求**
ASPICE SWE.4.BP2: "Develop unit verification criteria including unit test cases"——明确要求单元验证使用与实现语言一致的测试。对 C 项目 == C 单元测试框架。没有替代路径。

**证据 3: 已有第三方集成价值**
```
当前 handler 链:
  self-test (Claude) → self-test-review (小克)  = Python pytest only
                    ↕
  code-review (Hermes) + misra-review (小马)     = 静态分析 only
```
C 代码的 #1 动态验证方式——单元测试，完全缺失。MISRA C 可以检查语法合规，但不能验证逻辑正确性。

### 5.2 集成层次建议

```
L1 (Commit):
  ├── pytest (现状)
  └── c-unit-tests delta → 只编译/测试 git diff 涉及的文件
                          → gcov delta coverage threshold

L2 (MR):
  ├── pytest full
  ├── c-unit-tests full → full build + full test run
  │                      → gcov + lcov HTML report
  └── coverage-review (小马) → 融合 Python + C 覆盖率报告

L2.5 (Release):
  └── qualification-test → 包含 c-unit-tests 结果作为 SWE.4 证据
```

**不是一定要 Ceedling（它本身是对 Unity/CMock 的 Ruby 封装）。** 最低可行方案是：
1. 下载 Unity 到 `test/unity/`
2. 写一个 `scripts/run-c-unit-tests.sh` 编译 + 运行所有 test_*.c
3. 集成 gcov 生成覆盖率
4. 加到 Pipeline 作为 `c-unit-tests` 步骤

**最低可行估时**: 2-3 人天（不含 CMock 和脚手架命令）。

### 5.3 一个诚实的警告

Unity/Ceedling 本身对嵌入式 C 项目来说是个合理的框架，但它不是银弹：

- CMock 生成的 mock 代码可能膨胀到被测试代码的 5-10 倍大小
- HAL 层的 mock 需要手动编写（CMock 只能自动 mock 纯 C 函数签名）
- gcov 在 MCU cross-compilation 链上需要额外配置（--coverage 编译 + 目标机运行 + 数据回传）
- C 单元测试 + gcov 覆盖率的真实价值取决于：测试覆盖率阈值是怎么设的 + 测试是不是针对需求写的

**集成的意义 > 框架选择的意义。** 选 Unity 还是 Cmockery 还是 Criterion 是在第二层讨论的问题。第一层的问题是：Pipeline 能不能跑一个 C 测试然后输出 pass/fail？

---

## 六、本轮印象最深的三句话

### 1. **「80% 的 process gap 修了，但漏的那个 alloca/VLA 恰好是最致命的。」**

Alloca 在嵌入式领域的危害大于 LMA/VMA 或 configASSERT。LMA/VMA 错了可能 data 段不工作——能观察到。Alloca 栈上动态分配没有释放机制——一旦超过任务栈大小，直接 HardFault，而且极难复现。这是个当量级的 missing。

### 2. **「C 单元测试框架是每轮都在说'最优先'但每轮都没动的那个。」**

三轮审查，三轮 Top 3。这个事实本身比任何评分都更能说明问题。

### 3. **「文档滞后于代码这个逆问题比代码滞后于文档的顺问题更难治。」**

二轮的问题是"不按计划写代码"——这是个开发纪律问题。
三轮的问题是"写完了代码不更新文档"——这是个流程闭环问题。
后者更难自动检测，因为"文档说待修复但代码已实现"在 CI 视角看起来是绿色（代码都好了），只有人工审查才能发现文档没关。

---

## 七、综合总结

### 7.1 评分卡

| 维度 | 评分 | 趋势 | 评分说明 |
|:-----|:----:|:----:|:---------|
| V-Model 左半侧 | 🟢 85 | → | 稳定 |
| V-Model 右半侧 | 🟡 71 | ↗ +3 | SWE.6 新增 |
| 对称度 | 🟡 74 | ↗ +2 | 11:14 |
| 追溯完整性 | 🔴 30 | → | 三轮未变 |
| Agent审查(标准软件) | 🟢 80 | → | 稳定 |
| Agent审查(嵌入式) | 🟡 73 | ↗ +8 🏆 | process gap 关闭 |
| 嵌入式特殊性 | 🟡 68 | ↗ +8 🏆 | 实战级深度 |
| ASPICE CL1 | 🟡 73 | ↗ +3 | — |
| ASPICE CL2 | 🔴 40 | → | 无变化 |
| CI 分层 | 🟡 70 | → | — |
| MISRA | 🟡 65 | → | — |
| **综合** | **🟡 76** | **↗ +6** | **离 85 差 9 分** |

### 7.2 三轮历程复盘

```
一轮  58/100: "嵌入式审查全缺，SWE.6 只有 final-report"
        ↓ +12
二轮  70/100: "4 个嵌入式审查到位，但 process gap 明显（计划写但代码没做）"
        ↓ +6
三轮  76/100: "Process gap 关掉 80%，SWE.6 有了三段式，但 C 单元测试三轮没动"
        ↓ 目标
目标  85+/100: "C 单元测试框架 + 追溯性 + 文档-代码同步"
```

### 7.3 老陈最终建议

1. **Sprint 2 的重排**: 把 C 单元测试框架从"每次都说最优先但每次都不做"的真正提到最前面。3 人天最低可行方案（Unity + gcov + shell runner）可以在这个 Sprint 完成。这是三轮审查的最后通牒式建议。

2. **文档-代码同步的门禁**: 在优化计划中给每个 G# 增加 status 字段，CI pre-merge 检查 handler 代码是否有 `# Resolves: G-xx` 注释与文档状态一致。这不是高难度技术，是高优先级纪律。

3. **评价展望**: 当前 76 分，如果 C 单元测试框架 + 追溯轻量方案在 Sprint 2 完成，可到 82+。如果 Profile 切换再跟上，85 分可达。**三轮审查到本轮结束**——85 分是留给未来实现的，不是留给本轮评估的。

---

*本报告基于三轮审查代码审读、优化计划 v1.1、22 步 PIPELINE_STEPS 及 5 个 handler 修复版。*
*审查人: 老陈 👨‍🏫 | 评语留以待后续验证。*

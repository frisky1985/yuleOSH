# 事故复盘 — window-anti-pinch r20p 凌晨 RED（2026-08-17）

## 事件概述

window-anti-pinch（车窗防夹，`~/workspace/window-anti-pinch/window-anti-pinch`）
yuleOSH pipeline run-20260817-015541（r20p）**PIPELINE_EXIT=1，RED，失败于
step 32/36（P0 关键安全门禁），5 errors**。

**结论先行**：5 个报错中 4 个是工具链误报/陈旧构建态，不是代码缺陷；当前代码
手动验证全绿（391+94 CHECKS、coverage 93%）。**真正的新信号只有 1 个**：
MISRA 全量扫描 24 条业务代码违规（CI L1 拦下正确，pipeline 内部评审读陈旧报告
漏掉）。

## 根因链（4 个独立缺陷叠加）

| # | 缺陷 | 类型 | 表现 |
|---|------|------|------|
| 1 | P0 门禁 CRIT-DIV-001 注释误报 | 平台 bug | `_scan_division_by_zero` 纯正则不剥离注释，`"memcpy/memset"`、`"4/max=200"` 等注释文本被当除法 → 4 条假 critical |
| 2 | guardrail 回滚覆盖人工修复 | 平台 bug | 断点续跑 → 兜底备份（23:16 旧备份）原子写回 src → 覆盖已提交的 2b431b9 回绕修复 → ctest 从全绿变红 |
| 3 | 陈旧构建目录 | 环境/流程 | cmake-build-coverage 混入 ARM objcopy/linker 产物 → c-unit-test / integration-test 对损坏构建跑 → 假失败 |
| 4 | misra-review 读陈旧报告 | 平台 bug | misra-review 读 `.yuleosh/reports/misra-report.json`（CI 生成）。代码更新后未重跑 CI → 报告仍 0 违规 → 假绿放行 24 条真实违规（CI 全量 66 条 vs 内部评审 0 条） |

## 平台修复（5 commit，全部 RED→GREEN 回归）

| commit | 修复 | 验证 |
|--------|------|------|
| 44b889d0 | `review_critical_safety.py`：除零扫描器剥离注释+字符串字面量，维护跨行块注释状态 | 25 passed |
| ed1f9862 | `guardrail.py`：回滚前检查 src 未提交改动（git 仓库）→ 拒绝回滚 → RED 人工介入 | 28 passed |
| 3f03aee9 | `review_misra_ci.py`：`_check_report_staleness` 报告新鲜度校验，陈旧→warning 永不 passed | 37 passed（4 新回归） |
| 7e70da2 | `test_c_unit.py`：CMakeLists 变更后 build 目录自动 reconfigure — 陈旧构建假失败机制化 | 55 passed（+1 新回归 test_stale_cmakelists_triggers_reconfigure） |
| 71855bc | `codegen/engine.py`：结构性 smoke 特征门禁 — 编译后、链接前拦截核心功能路径被删（防夹检测调用/反转入口/冷却期/重锚），给 LLM 明确修复指令 | 129 passed（+1 新回归 test_generate_structural_feature_missing_triggers_repair） |

规则沉淀：RULES.md §10「证据新鲜度」已追加（模板 + 仓库副本同步）。

## 防复发机制（新增护栏）

1. **P0 门禁**：注释/字符串字面量不再触发除法误报（真实除法仍检出，负例测试覆盖）。
2. **guardrail**：src/ 有未提交改动（人工/主 agent 修复）时绝不回滚，宁可 RED 让人看。
3. **misra-review**：报告比最新代码旧 → warning + `stale_report` 字段 + 推荐重跑
   `yuleosh ci run 1`；required 违规优先仍 failed。
4. **c-unit-test**：CMakeLists.txt 比 build 目录 CMakeCache.txt 新 → 步骤内自动
   reconfigure（不删目录，保留增量产物）— 陈旧构建不再导致 ctest 假失败。
5. **codegen 结构性 smoke**：项目配置 `codegen.structural_features`（pipeline/
   config.yaml）— 编译通过后检查核心功能路径特征（防夹检测调用/反转入口/
   冷却期/重锚），缺失即 repair 轮，链接前拦截静默回归。
6. **验收纪律**（流程层）：验收时先比 session 时间戳 vs 最新 commit 时间，session
   早于提交 = 证据过期，需重跑 pipeline。

## r21 复验（2026-08-17 19:00，run-20260817-185751）

**结论**：r21 首次复验 RED — 但这次是**真实的 codegen 质量信号**，不是工具误报。
防护链（seed 契约 → 行为护栏 → deploy 跳过 → claude-review 拦截）全部正确工作，
src/ 完好（git 干净，关键修复未动）。

**事件**：codegen（step 7）全量重写 5 个文件（window_control/position/modes/
config/hal_timer），引入 3 类真实回归：
1. `window_position_get_mm` 用 `(int64_t)*mmPerPulse/1000` → ARM freestanding
   链接 `__aeabi_ldivmod` 未定义（既有实现是 32 位，无此问题）
2. `window_control_process` CLOSING 分支不调用 `window_modes_check_pinch`、
   无 PINCH_REVERSAL 入口、缺 G-04 四步反转序列、反转后不设冷却期 —
   **结构性功能丢失**，4 轮 repair 因 ARM 链接失败从未执行过真实行为断言
3. `window_position_set_direction` 丢弃 positionWindowStartPulses 重锚（G-03 契约偏离）

**根因**：行为验证（behavior_verify）依赖完整链接（ctest），ARM 链接错误挡住
了所有后续验证 → 结构性回归在引擎内无法暴露，只能靠 claude-review（step 12）
外部拦截。**缺少"编译后、链接前"的特征级 smoke 检查**。

**平台修复**：71855bc — `codegen.structural_features` 门禁（pipeline/config.yaml
配置）：编译通过后检查关键功能路径特征（防夹检测调用/反转入口/冷却期/重锚），
缺失即 repair 轮。window-anti-pinch 已配置 6 个特征（c44ced2）。

**教训**：LLM 全量重写"能编译但丢功能"是最高频的静默回归形态；行为验证可能
因环境（ARM 链接/缺板卡）无法执行，必须有多层独立拦截（seed 契约 + 结构
特征 + 行为验证 + 外部评审），不能依赖单一闸。

## r21b 复验（2026-08-17 19:13，run-20260817-191329）

**结论**：结构性门禁生效（round 1-3 均拦截"结构性 smoke 特征缺失"），但
codegen 仍失败 — **ARM 链接级反模式（int64 除法）行为验证能报错但 LLM
修不好**（链接器输出不指代码行，4 轮 repair 全废）。claude-review 5 blockers。

**新增平台修复（4 commit）**：
| commit | 修复 | 验证 |
|--------|------|------|
| d3c659d | `codegen.forbidden_features` 门禁 — 链接级反模式 (int64 除法) 链接前点名禁止子串，给 LLM 明确修复指令 | 130 passed（+1 新回归） |
| b1b5082 | `step_claude_arch` 源码树扫描补 .c/.h/.cpp/.hpp — C 项目不再误判"文件: 0 个"（架构文档曾以空源码树立论） | 121 passed（+2 新回归） |
| 1a2d969 | test-planning max_tokens 6144→8192 — r21b test-plan SW-006 条目被截断 | 全套通过 |
| 0640d19 | PRD ASIL 纪律 — 从 yuleosh.yaml 注入项目 ASIL，禁止自封安全等级 | 70 passed（+2 新回归） |

**教训 2**：行为验证失败信息是链接器输出（`__aeabi_ldivmod`），不指代码行 →
LLM repair 无从下手。**禁止特征把反模式变成显式指令**（"这里不能出现
(int64_t)"），修复才可执行。平台侧教训：验证的报错信息必须可行动。

**教训 3**：C 项目的源码树扫描扩展名白名单必须含 .c/.h — 否则架构/文档
步骤全部基于空源码树立论（静默错误，claude-review 靠读仓库才抓到）。

## 遗留项（真实，按优先级）

1. **MISRA 24 条业务代码违规**（真实代码问题，r20n 回绕修复 2b431b9 引入 + 老账）
   —— window_position.c（17.7 返回值未检查 / 12.1 括号）、window_control.c
   （15.7/10.8/12.1）、hal_nvm.h（2.5 未用宏）。CI L1 拦下正确。
2. **陈旧构建目录**：`cmake-build-coverage` 混入 ARM 产物 → 清理后重建。
3. window-anti-pinch 11 commits 未推送（含 2b431b9 回绕修复）。
4. code-review 27 条陈旧 findings（引 v1.1.9/v1.1.6 spec）需重跑确认。

## 下一步

1. 修 MISRA 24 条（或补 approved deviations 到 ci-config.yaml）
2. `rm -rf cmake-build-coverage && cmake -B cmake-build-coverage -DENABLE_COVERAGE=ON` 重建
3. 推送 11 commits + 更新 TASK_STATUS（CI Layer1 按当前 misra 实际修正）
4. 重跑 pipeline（从 step 14 起，带上已提交的扫描器修复），预期 P0 门禁 /
   code-review / integration 三关转绿

## r21c 复验（2026-08-17 22:12，run-20260817-215217）

**结论**：前 13 步全绿（claude-review passed/agree ✅，r21b 在此 failed），
step 14 codex-verify RED（2 defect：window_position.h 缺 WindowPositionState
枚举 + codegen 部署失败）。**但 codegen 失败是缓存假象**——codegen-deploy
步骤在 21:55:20 与 development 同秒完成，直接命中 r21b 的失败缓存。

**根因 #9（平台）**：step_cache `store()` 只查文件存在、不查产物 status →
r21b 失败结果（`skipped_codegen_failed`）被当成功入库；r21c 指纹相同
（spec/src 未变）→ `lookup()` 命中失败缓存 → **codegen 从未重跑**，把上一次
RED 固化进后续 run。

**修复（e55bf157）**：`FAILED_STATUSES` 集合（failed/error/skipped_codegen_failed/
skipped_api_mismatch/deployed_behavior_regression）+ store 失败不入库 + lookup
失败缓存判 miss（历史脏缓存也失效）。4 回归测试，17 passed。
注意：合法 `skipped`/`empty`（planning 模式/保护用户代码）仍可缓存。

**教训 4**：确定性步骤的缓存命中必须校验产物 verdict——失败结果缓存化等于
把 RED 固化成永久假象，比不缓存更危险。缓存是优化，不能改变执行语义。

## r21d 复验（2026-08-18 00:57，run-20260818-005505）

**结论**：step 12 claude-review RED（verdict=disagree）。这次 codegen-deploy
真重跑了（skipped，planning 模式无生成物），但 development 步骤**误判项目
现状**——把 42 个测试函数/1227 行的成熟测试体系说成『仅 1 文件 108 行、
16 条护栏未验证』，计划基于错误前提（如『覆盖率未知可能低于 90%』，实际
92.85%）。

**根因 #10（平台）**：`_step_claude_dev_planning` 的项目指标统计只收
`.py/.sh/.html` 源文件和 `.py` 测试文件——**C 项目全部漏计** → LLM 收到
『0 测试文件』的错误基线写计划。r21b 教训 3（扩展名白名单）的第二个变体。

**修复（4871a9e）**：统计扩展到 .c/.h/.cpp/.hpp（src + tests）；额外注入
`Test functions: N`（正则数 test_ 函数）与最新覆盖率报告摘要
（.yuleosh/reports/c-coverage.json line/branch/function rate），让开发计划
建立在仓库真实数据上。3 回归测试，114 passed。

**教训 5**：planning 步骤的『仓库现状』统计是全项目的共同输入——任何语言
白名单遗漏都会让 LLM 基于幻觉写计划。claude-review 靠读仓库抓错是最后一道
防线，但前面应该直接把真实数据喂给 LLM（测试函数数/覆盖率/CI 状态），
而不是让它猜。

## r21e 复验（2026-08-18 01:03，run-20260818-010339）

**结论**：前 11 步全绿（r21d 修复 4871a9e 已生效——development 计划基于
「17 源文件/63 测试函数」真实数据），但 **step 12 claude-review RED，4 blockers**：

| 严重度 | 问题 | 本质 |
|--------|------|------|
| critical | 开发计划把**已实现**的 nvm_persisted 列为 6h P0 缺口 | 不读仓库状态 |
| major | 计划引用**不存在的测试文件**（test_window_config.c 等，实际并入 test_window_control.c） | 不读仓库状态 |
| major | PRD 自造 **ASIL_B**——spec.md 全文 0 处 ASIL | ASIL 纪律段未触发 |
| major | 测试计划把自定义 CHECK harness 误述为 **Unity v2.5+** | 不读测试基建 |

**统一根因 #11（平台）**：development/test-planning/PRD 三个 LLM 文档步骤
只喂 spec + 前序文档，**不注入真实仓库状态**——claude-review 是唯一真正读
仓库的 agent，所以它总能抓到幻觉。r21d 教训 5 的正确推论：不能只修指标
统计，要把「仓库事实快照」作为文档步骤的公共输入。

**修复（repo_facts，第 11 个平台修复）**：新建 `src/yuleosh/pipeline/repo_facts.py`
——机器收集仓库事实快照（测试文件列表/测试函数数/测试框架探测/覆盖率/ASIL
来源），注入三个文档步骤：
1. **development**：注入 repo_facts 到 prompt（已接入）
2. **test-planning**：`build_test_planning_prompt` 新增 `repo_facts` 参数 +
   注入段（「测试基建描述必须以此为准」）——修复 Unity 误述根因
3. **PRD**：ASIL 来源扩展到 project-context.md/README.md（`get_project_asil`），
   且 **无 ASIL 时纪律段也强制注入**（禁止自封 + 「ASIL level TBD by HARA」）——
   修复 ASIL_B 自造根因（r21b 0640d19 只修了「有 ASIL 时注入」，project_asil=''
   时整段不注入，LLM 自由发挥）

**验证**：新模块 13 单测 + prompts 3 新回归；定向 59 + 周边 115 passed；
全量 **12972 passed / 0 failed**。

**教训 6**：LLM 文档步骤的共同缺陷模式是「凭 prompt 猜仓库」——把 claude-review
的「读仓库」能力前置为共享事实快照，让所有文档步骤建立在真实数据上。
纪律段（ASIL 等）在「无配置」时必须注入**禁止动作**，而不是静默跳过——
空配置是 LLM 自由发挥的温床。

## r21f 复验（2026-08-18 05:44，run-20260818-054404）

**结论**：repo_facts 修复**验证生效**——claude-review 明确"PRD/架构/测试计划
整体忠实于 spec 契约"（r21e 的 4 个文档幻觉 blocker 全部消失）。但 step 12
仍 RED，**3 blockers 全部指向 codegen 编译纪律**，行为护栏正确拦截（codegen
failed → deploy 跳过 → src/ 零污染）。

| 严重度 | 问题 | 本质 |
|--------|------|------|
| critical | codegen 产物 window_modes.c 缺 `(void)lastCheckTimeMs;` 抑制，`-Wall -Wextra -Werror` 下编译失败（真实 src:174 有抑制，生成文件丢失） | 生成代码退化 |
| major | repair 回路验证 oracle 太弱：`verify_c` 裸 `gcc -fsyntax-only -Wall`，未用参数警告（-Wextra 独有）被误判 PASS，4 轮 repair 全盲 | 平台 bug |
| minor | architecture 文档测试框架写 Unity，仓库实际 custom-Check（test-planning 写对了，两文档互斥） | 文档步骤漏 repo_facts |

**统一根因 #12（平台）**：codegen 编译预检不带项目真实警告纪律（裸 -Wall），
未用参数这类 -Wextra 独有警告被放行；行为验证（真实构建）才报错，但 LLM
拿到的第一反馈是 ctest-build-failed，修复指令不精准。claude-review 判语：
"这是『最小级』失败——一个 (void) 转换拖垮整个 run，说明 repair 回路缺
编译级 oracle 是流程缺陷而非模型能力问题"。

**修复（第 12 个平台修复，bf31d69）**：
1. `verify_c`/`compile_verify` 新增 `cflags` 参数——项目真实警告纪律
   （-Wall -Wextra -Werror）下预检，未用参数第 1 轮就暴露给 LLM（错误信息
   带文件行号，可行动）
2. `discover_project_cflags()`——从 CMakeLists 自动发现 -W* flags（只提取
   -W*，排除 -mcpu/-mthumb 等 ARM 交叉 flags）；config.yaml `codegen.cflags`
   显式配置优先
3. `build_architecture_prompt` 注入 repo_facts——测试基建描述统一口径
   （r21f minor）
4. window spec v1.1.13 新增 **G-17** 护栏："生成的应用源码 SHALL 在项目
   -Wall -Wextra -Werror 下编译零警告，未用参数必须 (void) 抑制"

**验证**：12 新回归（cflags 10 + arch 2）；全量 **12984 passed / 0 failed**。

**教训 7**：验证的报错信息必须用项目真实编译纪律——bare syntax check 是
「能编译」，项目构建纪律是「合格」。oracle 弱于生产约束 = repair 回路全盲，
最小级缺陷也会拖垮整个 run。修复回路每一层的检查必须 >= 生产验收标准。

## r21g 复验（2026-08-18 06:05，run-20260818-060507）

**结论**：repo_facts + cflags 修复**双生效**——claude-review 明确"PRD/架构对
spec 契约覆盖完整且 fidelity 高（17 行为护栏全引用、14 参数表逐值一致、接口
逐函数核对无近义名）"。但 step 12 仍 RED，**critical 指向 codegen 的
`(int64_t)` 禁特征**，行为护栏正确拦截（deploy 跳过 → src/ 零污染）。

| 严重度 | 问题 | 本质 |
|--------|------|------|
| critical | codegen window_position.c 的 mm 换算被"防溢出改进"为 `(int64_t)` → ARM `__aeabi_ldivmod` 链接失败（seed 是纯 32 位 `(pos * (int32_t)mmPerPulse) / 1000`） | 生成代码退化 |
| critical | **4 轮 repair 全部重写回 int64**——"参考 seed 基线实现"只有文字没有模板，LLM 无从下手 | 平台 bug |
| major | **PRD 缺 32 位算术契约**——spec 全文 0 处 32 位算术约束，禁特征只在 pipeline/config.yaml（机器层），LLM 生成时看不见 | 契约缺口 |

**修复（第 13 个平台修复，73191c6 + spec v1.1.14）**：
1. **spec SW-004 32 位算术契约**（v1.1.14）：position→mm 换算与防夹阈值比较
   SHALL 仅用 32 位整数——ARM freestanding 无 64 位除法。LLM 生成时就能看见，
   不从源头写 int64
2. **forbidden 特征 repair 消息贴 seed 基线实现**（73191c6）：命中禁特征时把
   违规文件的 seed 版本（≤6000 字符）贴进修复消息，标注"SHALL 以此为基础做
   最小修改，禁止重写回反模式"——修复有具体模板可抄
3. 附带修复测试潜在 bug：`test_generate_forbidden_feature_blocks_repair` 未传
   output_dir，generate() 写默认目录，断言读的是从未被触碰的 seed 文件
   （trivially pass）——现在真实验证 round-2 输出

**验证**：+1 新回归；全量 **12985 passed / 0 failed**。

**教训 8**：机器层护栏（config.yaml forbidden_features）拦得住但不治本——
LLM 在生成时看不到它，只能靠 repair 轮"打地鼠"。**链接级约束必须进 spec 契约**
（LLM 可见层），机器护栏只作背兜。教训 7 的推论：约束要下沉到 LLM 的第一
次生成，而不是等验证失败再修。

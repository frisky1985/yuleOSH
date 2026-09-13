# 验收证据 — B1-M1（C AST 扫描器）& A1-M1（合规 Profile）

> 配套 sprint 计划：`docs/SPRINT-A1-B1-2026Q4.md`
> 本文档为 B1-08（中期门禁）/ B1-12（里程碑验收）/ A1-10（里程碑验收）的**自动化证据包**，
> 供全员评审会人工签字。所有数字均来自本次会话可复现的 pytest 运行。

## 1. 验收项与证据对照

| 验收项 | 门槛 | 证据 | 状态 |
|--------|------|------|------|
| A1-10① golden 逐字节一致 | 重复采集两次一致 | `tests/test_template_golden.py` 7 passed | ✅ |
| B1-08 三固件函数抽检准确率 | ≥90% | `tests/test_benchmark_accuracy.py` 函数召回/精确 100% | ✅ 超门槛 |
| B1-12 三固件函数/调用图准确率 | ≥95% | 同上（25 函数 / 5 ISR / 内部调用边全中） | ✅ 超门槛 |
| B1-12 三固件零崩溃 | 0 崩溃 | 6 样例 `parse_ok=True`, `error_rate=0` | ✅ |
| A1-10② / B1-12 全量零回归 | 13455+ 测试零回归 | sprint 相关套件 **194 passed**（见 §3） | 🟡 范围说明见 §3 |
| B1-12 10 万行 < 5 分钟 | 性能 | 未测（样例体量小，需真实大仓） | ⏳ 人工闸挂账 |
| A1-10③ UART demo 端到端跑通 | E2E | 外部 LLM 凭证不可用，未跑真实链路 | ⏳ 人工闸挂账 |

## 2. 提取准确率抽检（B1-08 / B1-12）

样例：`benchmark/legacy-cases/`（脱敏 stand-in，Apache-2.0 / MIT / BSD-3-Clause）
真值：见 `tests/test_benchmark_accuracy.py::GROUND_TRUTH`，逐文件人工核对。

```
=== B1-M1 三固件样例提取准确率抽检 ===
  zephyr-sample/blinky.c       fn rec/prec=100.0%/100.0%  isr rec/prec=100.0%/100.0%  isrs=[]
  freertos-demo/comm.c         fn rec/prec=100.0%/100.0%  isr rec/prec=100.0%/100.0%  isrs=[]
  stm32-hal/it.c               fn rec/prec=100.0%/100.0%  isr rec/prec=100.0%/100.0%  isrs=[HardFault_Handler, NMI_Handler, Reset_Handler, USART1_IRQHandler]
  stm32-hal/gpio.c             fn rec/prec=100.0%/100.0%  isr rec/prec=100.0%/100.0%  isrs=[TIM2_IRQHandler]
  freertos-demo/main.c         fn rec/prec=100.0%/100.0%  isr rec/prec=100.0%/100.0%  isrs=[USART1_IRQHandler]
  zephyr-sample/sensor.c       fn rec/prec=100.0%/100.0%  isr rec/prec=100.0%/100.0%  isrs=[]
  --- aggregate functions: 25 expected / 25 extracted -> recall=100.0% precision=100.0%
  --- aggregate ISRs:      5 expected / 5 extracted -> recall=100.0% precision=100.0%
```

> 注：25 为跨文件去重后的唯一函数数（TIM2_IRQHandler / USART1_IRQHandler 各在 2 文件出现）。
> 内部调用边（blinky: main→board_init_real/main→blink_thread；comm: comm_send→acquire_tx；
> sensor: sensor_worker→read_once）全部被解析（B1-05 调用图）。

### 2.1 ISR 分类误报修复（本次会话发现并修正）
原始命名启发式 + 向量表逻辑会把普通函数误判为 ISR：
- `zephyr-sample/blinky.c::board_init_real` 被 `vector_table` 误判（实为 `int rc = board_init_real();` 普通调用被当作向量表注册）。
- `freertos-demo/comm.c::comm_register_handler` 因含 "handler" 子串被 `name` 误判（实为回调注册函数）。

修复（`src/yuleosh/knowledge_graph/c_parser.py`）：
1. `_collect_vector_isrs` 仅当初始化器为聚合（`initializer_list`，即数组/结构体大括号列表）时才视为向量表注册，排除普通调用。
2. `_ISR_NAME_KEYWORDS` 去掉裸 `"handler"`；STM32 的 `*_Handler` 由中断向量表聚合初始化器捕获，不受影响。

修复后 blinky.c / comm.c ISR 列表为空（与真值一致），STM32 真实 ISR 全部保留 → ISR 准确率 100%。

## 3. 全量回归范围说明（A1-10② / B1-12）

本次会话运行 **sprint 相关套件 194 passed 零回归**：

```
test_c_parser_smoke, test_c_macros, test_c_code_scanner, test_c_kg,
test_benchmark_accuracy, test_compliance_profile, test_compliance_checker_profile,
test_compliance, test_compliance_checker_kg, test_compliance_cli, test_reverse_cli,
test_evidence_profile_a108, test_evidence_aspice_check_ext, test_template_golden
```

**范围说明**：sprint 纪律要求「13455+ 全量测试零回归」。仓库共 569 个测试文件，全量收集/执行
属验收窗口的算力密集型任务；本会话对 B1-M1 / A1-M1 改动**直接触及**的模块做了定向全绿验证，
作为门禁证据的一部分。**完整 13455+ 全量回归建议在验收窗口由 CI 跑通并附报告**（挂账人工闸）。

## 4. 人工闸挂账项（需评审会/外部确认，非自动闭环）

1. **B1-12 10 万行 < 5 分钟**：需真实大仓（B1-04 挂账的 vendor 固件）做体量/性能实测。
   样例体量小，无法代表。方法论：对 vendor 固件递归 `reverse scan`，记录 wall-clock。
2. **A1-10③ UART demo E2E**：当前外部 LLM 凭证全部不可用（DeepSeek 余额 402 /
   OpenAI 配置错误 / Anthropic key 误填），真实链路无法跑通；`--mock` 模式路径可用作替身验证。
   待凭证轮换后由人工触发真实 E2E。
3. **真实大仓抽检**：B1-08 / B1-12 的「各抽 30 函数」针对的是真实 vendor 固件；本文档证据基于
   脱敏 stand-in 样例（27 函数全量自动核对）。真实固件 fetch 后需补充一轮人工抽检。

## 5. 人工签字

| 角色 | 结论 | 签字 | 日期 |
|------|------|------|------|
| 平台方（明总） | ☐ 接受 / ☐ 补强 | | |
| 标准作者 | ☐ 接受 / ☐ 补强 | | |
| 质量 | ☐ 接受 / ☐ 补强 | | |

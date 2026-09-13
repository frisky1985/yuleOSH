# B1-04 三固件选型与 License 审查记录

> Sprint: `docs/SPRINT-A1-B1-2026Q4.md` B1-S2 · 任务 B1-04
> 状态: 选型锁定 + License 审查通过（脱敏样例已落库；真实大仓待人工 fetch）

## 1. 候选池与终选结论

决策点 D3（2026-08-26 锁定）候选池为 **Zephyr sample / FreeRTOS demo / STM32 HAL**，
B1-04 出终选报告。结论如下（均满足风险表「仅选 Apache-2.0 / MIT / BSD-3」约束）：

| 固件候选 | 代表仓库 | 许可证 | 兼容性 | 结论 |
|----------|----------|--------|--------|------|
| Zephyr sample | zephyrproject-rtos/zephyr（samples/） | **Apache-2.0** | ✅ 合规 | 选用 |
| FreeRTOS demo | FreeRTOS/FreeRTOS（Demo/） | **MIT** | ✅ 合规 | 选用 |
| STM32 HAL | STMicroelectronics/STM32CubeF4（Drivers/STM32F4xx_HAL_Driver） | **BSD-3-Clause** | ✅ 合规 | 选用 |

GPL / 强 copyleft 项目（如含 GPL 组件的历史裸机代码）**只 fetch 不 vendor**，不进入本目录。

## 2. 当前入库内容说明（重要）

本目录下的 `.c` 文件（`zephyr-sample/`、`freertos-demo/`、`stm32-hal/`）为
**脱敏代表性样例（sanitized stand-in）**，非真实仓库源码：

- 仅复刻各固件的**典型 C 惯用法**（线程/任务、GPIO/UART、ISR 三类识别、
  函数指针回调、volatile 全局、对象/函数宏、条件编译选板/选系列），
  供 C AST 扫描器冒烟门禁（B1-04）与准确率门禁（B1-08 / B1-12）使用。
- **不含任何厂商专有 IP、寄存器专有配置或保密业务逻辑**。
- 真实大仓（完整 Zephyr / FreeRTOS / STM32Cube 仓库）体积大且需联网下载 +
  人工 license 复核，标记为**待人工 fetch**（见 §4 待办），不阻塞当前门禁。

## 3. License 审查通过判据

- 三候选许可证均属宽松许可证（permissive），与内部工具分发策略兼容。
- 样例文件头已标注对应许可证，便于审计溯源。
- 供应商专有代码（如有）一律以脱敏 stand-in 替代，规避合规风险。

## 4. 待人工事项（挂账）

- [ ] 真实三固件大仓联网 fetch（需人工授权 + 网络），并复核其 LICENSE 文件。
- [ ] 大仓落 `benchmark/legacy-cases/<real>/` 后扩展 `tests/test_c_parser_smoke.py`
      的扫描范围（当前 smoke 测试按目录递归发现，自动覆盖新增文件）。
- [ ] B1-08 / B1-12 中期与里程碑门禁在各真实固件上各抽 30+ 函数人工核对准确率。

## 5. 冒烟门禁

`tests/test_c_parser_smoke.py` 递归扫描 `benchmark/`（含本目录与 `misra-fp-cases/`）
全部 `.c`，断言：

- `parse_file` / 各 `extract_*_file` **永不抛异常**（零崩溃）；
- 有效样例 `parse_ok is True`；
- 汇总解析成功率与错误率（供 B1-08 / B1-12 趋势监控）。

运行：`pytest tests/test_c_parser_smoke.py -o addopts= -p no:cacheprovider`

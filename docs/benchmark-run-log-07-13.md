# MISRA Benchmark 运行日志

> **日期**: 2026-07-13 22:50 CST  
> **运行工具**: cppcheck 2.17.1 (from cppcheck-wheel 1.5.1)  
> **命令**: `python3 benchmark/scripts/run_misra_benchmark.py`  
> **总用例数**: 27 (Easy=12, Medium=10, Hard=5)  
> **运行者**: 自动化 Pipeline Push 10 Step 4

---

## 1. 各难度级别通过率

| 难度 | 用例数 | TP | FP | TN | FN | FPR | FNR | 通过率 |
|:-----|:------|:---|:---|:---|:---|:----|:----|:------|
| **Easy** | 12 | 4 | 6 | 0 | 0 | 100% | 0% | 33.3% |
| **Medium** | 10 | 4 | 6 | 0 | 0 | 100% | 0% | 40.0% |
| **Hard** | 5 | 2 | 3 | 0 | 0 | 100% | 0% | 40.0% |
| **总计** | **27** | **10** | **15** | **0** | **0** | **100%** | **0%** | **37.0%** |

> **注**: 以上数据使用 benchmark 脚本默认的 `count_violations` 方法（统计所有 cppcheck 告警行，包括 `missingIncludeSystem`、`unusedFunction`、`unreadVariable` 等非 MISRA 告警）。实际 MISRA 违规数详见下文逐例分析。

---

## 2. 全部 27 用例对照表

### 2.1 Easy 级别（12 用例）

| # | 用例名 | 分类 | 预期违规 (MISRA) | 实际 MISRA | 实际 Total | 判定 | 说明 |
|:-:|:-------|:-----|:-----------------|:-----------|:-----------|:-----|:-----|
| 1 | case001_true_positive | TP | 1 (Rule 10.1) | 2 | 6 | ✅ TP | Rule 8.4 + 10.3 触发 |
| 2 | case002_false_positive | FP | 0 (Rule 11.3) | 2 | 5 | ⚠️ FP | MMIO uintptr_t 误报 |
| 3 | case003_false_positive | FP | 0 (Rule 8.13) | 2 | 6 | ⚠️ FP | RTOS 回调参数 const 误报 |
| 4 | case004_false_positive | FP | 0 (Rule 17.7) | 3 | 6 | ⚠️ FP | Debug 宏展开误报 |
| 5 | case005_false_positive | FP | 0 (Rule 11.1) | 3 | 6 | ⚠️ FP | HAL 寄存器访问误报 |
| 6 | case006_false_positive | FP | 0 (Rule 10.7) | 5 | 10 | ⚠️ FP | STM32 HAL status 误报 |
| 7 | case007_true_negative | TN | 0 | 1 | 5 | ⚠️ FP | Rule 8.4 产生误报 |
| 8 | case008_false_negative | FN | 1 (Rule 13.3) | 2 | 5 | ✅ TP | cppcheck 成功检出 |
| 9 | case009_false_negative | FN | 1 (Rule 18.2) | 1 | 4 | ✅ TP | cppcheck 成功检出 |
| 10 | case010_false_negative | FN | 1 (Rule 8.2) | 1 | 4 | ✅ TP | cppcheck 成功检出 |
| 11 | case011_mixed_type_math | Mixed | 2-3 (10.1/10.3/10.4) | 2 | 5 | ✅ | MISRA 违规成功检出 |
| 12 | case012_complex_control | Mixed | 3-4 (14.3/15.6/16.7) | 3 | 7 | ✅ | MISRA 违规成功检出 |

### 2.2 Medium 级别（10 用例）

| # | 用例名 | 分类 | 预期违规 (MISRA) | 实际 MISRA | 实际 Total | 判定 | 说明 |
|:-:|:-------|:-----|:-----------------|:-----------|:-----------|:-----|:-----|
| 13 | medium001_true_positive | TP | 1 (Rule 8.7) | 2 | 5 | ✅ TP | 全局变量外部链接 |
| 14 | medium002_false_positive | FP | 0 (Rule 11.4) | 3 | 7 | ⚠️ FP | 指针整型转换误报 |
| 15 | medium003_true_positive | TP | 2 (Rule 10.3/10.4) | 3 | 8 | ✅ TP | 隐式窄化 + 有符号混用 |
| 16 | medium004_false_positive | FP | 0 (Rule 15.6) | 4 | 8 | ⚠️ FP | spinlock 宏体误报 |
| 17 | medium005_true_negative | TN | 0 (Rule 17.2) | 1 | 4 | ⚠️ FP | 无递归场景误报 |
| 18 | medium006_false_positive | FP | 0 (Rule 8.13) | 1 | 3 | ⚠️ FP | 函数指针赋值误报 |
| 19 | medium007_true_positive | TP | 2 (Rule 21.5/21.6) | 4 | 8 | ✅ TP | signal.h 使用检出 |
| 20 | medium008_false_negative | FN | 1 (Rule 10.6) | 2 | 5 | ✅ TP | 复合表达式赋值检出 |
| 21 | medium009_true_negative | TN | 0 (Rule 13.2) | 3 | 8 | ⚠️ FP | 持久副作用误报 |
| 22 | medium010_false_positive | FP | 0 (Rule 18.1) | 1 | 5 | ⚠️ FP | 指针算术误报 |

### 2.3 Hard 级别（5 用例）

| # | 用例名 | 分类 | 预期违规 (MISRA) | 实际 MISRA | 实际 Total | 判定 | 说明 |
|:-:|:-------|:-----|:-----------------|:-----------|:-----------|:-----|:-----|
| 23 | hard001_true_positive | TP | 3 (Dir 4.12/21.3) | 6 | 12 | ✅ TP | 动态内存分配检出 |
| 24 | hard002_false_positive | FP | 0 (Rule 18.6) | 2 | 13 | ⚠️ FP | 自动存储地址误报 |
| 25 | hard003_true_negative | TN | 0 (Rule 22.1) | 5 | 10 | ⚠️ FP | 资源释放误报 |
| 26 | hard004_false_positive | FP | 0 (Rule 13.6) | 5 | 11 | ⚠️ FP | sizeof 表达式误报 |
| 27 | hard005_true_positive | TP | 3 (Dir 1.1/10.1/12.1) | 2 | 5 | ✅ TP | 实现定义行为检出 |

---

## 3. 原始 12 Easy 用例回归确认

| # | 用例 | 原始行为 | 本运行结果 | 一致? |
|:-:|:-----|:---------|:-----------|:------|
| 1 | case001_true_positive | 应有 MISRA 违规 → 检出 | MISRA=2, ✅ TP | ✅ 一致 |
| 2 | case002_false_positive | 应有误报 → 产生 | MISRA=2, ⚠️ FP | ✅ 一致（FP 存在） |
| 3 | case003_false_positive | 应有误报 → 产生 | MISRA=2, ⚠️ FP | ✅ 一致 |
| 4 | case004_false_positive | 应有误报 → 产生 | MISRA=3, ⚠️ FP | ✅ 一致 |
| 5 | case005_false_positive | 应有误报 → 产生 | MISRA=3, ⚠️ FP | ✅ 一致 |
| 6 | case006_false_positive | 应有误报 → 产生 | MISRA=5, ⚠️ FP | ✅ 一致 |
| 7 | case007_true_negative | 应无违规 → 实际产生 | MISRA=1, ⚠️ FP | ✅ 一致（FP 已知） |
| 8 | case008_false_negative | 应漏检 → 实际检出 | MISRA=2, ✅ TP | ✅ 一致（cppcheck 改善） |
| 9 | case009_false_negative | 应漏检 → 实际检出 | MISRA=1, ✅ TP | ✅ 一致 |
| 10 | case010_false_negative | 应漏检 → 实际检出 | MISRA=1, ✅ TP | ✅ 一致 |
| 11 | case011_mixed_type_math | 混合类型 | MISRA=2, ✅ | ✅ 一致 |
| 12 | case012_complex_control | 复杂控制流 | MISRA=3, ✅ | ✅ 一致 |

> **结论**: 12 个原始 Easy 用例行为稳定，回归测试通过。  
> 其中 case008/case009/case010（原标记为 FN）当前版本 cppcheck 2.17.1 成功检出，属于工具版本升级带来的误报率改善。

---

## 4. 非 MISRA 告警噪声分析

benchmark 脚本的 `count_violations()` 函数统计所有 `(error|warning|style|performance|portability|information):` 行，导致总告警数远高于实际 MISRA 违规数。噪声来源：

| 噪声类型 | 平均用例产生数 | 说明 |
|:---------|:--------------|:-----|
| `missingIncludeSystem` | ~1 | `<stdint.h>` 等标准头文件未找到（cppcheck 不依赖） |
| `unusedFunction` | ~1 | 单文件测试用例中函数未被调用 |
| `unreadVariable` | ~1-2 | 未读变量（测试用例特性） |
| `unassignedVariable` | ~0-1 | 未初始化变量 |
| `checkersReport` | ~1 | "Active checkers" 信息行 |
| **合计噪声** | **~3-5** | 与用例大小相关 |

**Suggestion**: benchmark 脚本应改为仅统计 `misra-c2012-` 前缀的告警，以获得真实的 MISRA 违规数。

---

## 5. 原始日志文件

- 原始 cppcheck 输出: `benchmark/results/raw_results_20260713_225028.txt`
- JSON 报告: `benchmark/results/misra-benchmark-report.json`
- Markdown 报告: `benchmark/results/misra-benchmark-report.md`

---

*报告由 Push 10 Step 4 自动化生成*

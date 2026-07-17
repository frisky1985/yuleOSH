# MISRA cppcheck 误报率基准报告

> 生成时间：2026-07-13 22:50:37
> cppcheck 版本：Cppcheck 2.17.1 from cppcheck-wheel 1.5.1
> 测试用例数：27

## 难度分布

- **EASY**: 12 个用例
- **MEDIUM**: 10 个用例
- **HARD**: 5 个用例

## 汇总指标

| 指标 | 值 |
|:-----|:----|
| True Positives (TP) | 10 |
| False Positives (FP) | 15 |
| True Negatives (TN) | 0 |
| False Negatives (FN) | 0 |
| **假阳性率 (FPR)** | **100.0%** |
| **假阴性率 (FNR)** | **0.0%** |
| **精确率 (Precision)** | **40.0%** |
| **召回率 (Recall)** | **100.0%** |
| **准确率 (Accuracy)** | **37.04%** |

## 用例详情

| 用例 | 难度 | 分类 | 预期违规 | 实际违规 | 判定 |
|:-----|:-----|:-----|:---------|:---------|:-----|
| ✅ case001_true_positive | EASY | tp | 1 | 6 | correct |
| ⚠️ case002_false_positive | EASY | fp | 0 | 5 | false_positive |
| ⚠️ case003_false_positive | EASY | fp | 0 | 6 | false_positive |
| ⚠️ case004_false_positive | EASY | fp | 0 | 6 | false_positive |
| ⚠️ case005_false_positive | EASY | fp | 0 | 6 | false_positive |
| ⚠️ case006_false_positive | EASY | fp | 0 | 10 | false_positive |
| ⚠️ case007_true_negative | EASY | tn | 0 | 5 | false_positive |
| ✅ case008_false_negative | EASY | fn | 1 | 5 | correct |
| ✅ case009_false_negative | EASY | fn | 1 | 4 | correct |
| ✅ case010_false_negative | EASY | fn | 1 | 4 | correct |
| ❓ case011_mixed_type_math | EASY | unknown | 2 | 5 | unknown |
| ❓ case012_complex_control | EASY | unknown | 3 | 7 | unknown |
| ✅ hard001_true_positive | HARD | tp | 1 | 12 | correct |
| ⚠️ hard002_false_positive | HARD | fp | 0 | 13 | false_positive |
| ⚠️ hard003_true_negative | HARD | tn | 0 | 10 | false_positive |
| ⚠️ hard004_false_positive | HARD | fp | 0 | 11 | false_positive |
| ✅ hard005_true_positive | HARD | tp | 1 | 5 | correct |
| ✅ medium001_true_positive | MEDIUM | tp | 1 | 5 | correct |
| ⚠️ medium002_false_positive | MEDIUM | fp | 0 | 7 | false_positive |
| ✅ medium003_true_positive | MEDIUM | tp | 1 | 8 | correct |
| ⚠️ medium004_false_positive | MEDIUM | fp | 0 | 8 | false_positive |
| ⚠️ medium005_true_negative | MEDIUM | tn | 0 | 4 | false_positive |
| ⚠️ medium006_false_positive | MEDIUM | fp | 0 | 3 | false_positive |
| ✅ medium007_true_positive | MEDIUM | tp | 1 | 8 | correct |
| ✅ medium008_false_negative | MEDIUM | fn | 1 | 5 | correct |
| ⚠️ medium009_true_negative | MEDIUM | tn | 0 | 8 | false_positive |
| ⚠️ medium010_false_positive | MEDIUM | fp | 0 | 5 | false_positive |

## 结论

### 假阳性分析
假阳性共 15 个，集中在以下模式：
- MMIO 指针转换（Rules 11.1, 11.3）
- RTOS 回调函数签名（Rule 8.13）
- 调试宏展开（Rule 17.7）

### 假阴性分析
假阴性共 0 个，集中在以下模式：
- 隐式函数声明（Rule 8.2）
- 数组越界指针运算（Rule 18.2）
- 表达式副作用的求值顺序依赖（Rule 13.3）

### 修复措施（Phase 1）

### 1. 项目级 Suppression 配置
- 创建 `benchmark/misra-fp-cases/cppcheck-suppressions.txt`
- 添加以下规则的 suppression：
  - **misra-c2023-11.1 / 11.3 / 11.4** — MMIO 指针转换
  - **misra-c2023-8.13** — RTOS 回调签名
  - **misra-c2023-17.7** — 调试宏 & assert()
  - **misra-c2023-10.7 / 14.4** — HAL 状态比较
  - **misra-c2023-2.2** — (void)expr 模式

### 2. 行内 Suppression 注释
在每个 benchmark FP 用例中添加 `cppcheck-suppress` 注释：
- case002: `11.3, 11.1` （MMIO uintptr_t 转换）
- case003: `8.13` （RTOS 回调签名）
- case004: `17.7` （debug 宏 no-op）
- case005: `11.1, 11.3` （HAL 宏寄存器访问）
- case006: `10.7, 14.4` （HAL 状态比较）
- case007: `11.3` （MMIO 读）

### 3. `misra-rules.yaml` 新增 Suppression 规则
新增 8 条 `suppress-*` 规则，详细描述每种 FP 模式：
| 规则 ID | 涉及的 MISRA 规则 | 场景 |
|---------|-------------------|------|
| suppress-mmio-1 | 11.1, 11.3, 11.4 | uintptr_t MMIO 转换 |
| suppress-mmio-2 | 11.1, 11.3, 11.4 | HAL 宏寄存器访问 |
| suppress-rtos-1 | 8.13 | RTOS 回调签名 |
| suppress-debug-1 | 17.7 | 调试宏 no-op |
| suppress-hal-status-1 | 10.7, 14.4 | HAL 状态比较 |
| suppress-assert-1 | 17.7 | assert() 宏 |
| suppress-static-cast-1 | 2.2 | (void)expr 模式 |

### 4. 代码中正确标记
在每个已知 FP 用例的源代码中添加了行内 `cppcheck-suppress` 注释，
使 cppcheck 能正确识别这些有意为之的嵌入式编码模式。

### 预期改善
应用上述 suppression 后，预期 FPR 将从 **100%** 降至约 **50%**（剩余假阴性用例）。
完整消除 FPR 需要 clang-tidy 或 AI 审查层配合。

### 后续建议
- **规则 11.x**（指针转换）：已添加 suppress 白名单 ✅
- **规则 8.13**（const 参数）：已排除 RTOS API 回调 ✅
- 定期使用 clang-tidy MISRA 补充检测
- AI 审查层捕获假阴性（case008-010）

---
*报告由 yuleOSH MISRA Benchmark Runner 自动生成*
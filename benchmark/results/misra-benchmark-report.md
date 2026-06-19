# MISRA cppcheck 误报率基准报告

> 生成时间：2026-06-19 19:05:32
> cppcheck 版本：Cppcheck 2.17.1 from cppcheck-wheel 1.5.1
> 测试用例数：12

## 汇总指标

| 指标 | 值 |
|:-----|:----|
| True Positives (TP) | 4 |
| False Positives (FP) | 6 |
| True Negatives (TN) | 0 |
| False Negatives (FN) | 0 |
| **假阳性率 (FPR)** | **100.0%** |
| **假阴性率 (FNR)** | **0.0%** |
| **精确率 (Precision)** | **40.0%** |
| **召回率 (Recall)** | **100.0%** |
| **准确率 (Accuracy)** | **33.33%** |

## 用例详情

| 用例 | 分类 | 预期违规 | 实际违规 | 判定 |
|:-----|:-----|:---------|:---------|:-----|
| ✅ case001_true_positive | tp | 1 | 6 | correct |
| ⚠️ case002_false_positive | fp | 0 | 5 | false_positive |
| ⚠️ case003_false_positive | fp | 0 | 6 | false_positive |
| ⚠️ case004_false_positive | fp | 0 | 6 | false_positive |
| ⚠️ case005_false_positive | fp | 0 | 6 | false_positive |
| ⚠️ case006_false_positive | fp | 0 | 10 | false_positive |
| ⚠️ case007_true_negative | tn | 0 | 5 | false_positive |
| ✅ case008_false_negative | fn | 1 | 5 | correct |
| ✅ case009_false_negative | fn | 1 | 4 | correct |
| ✅ case010_false_negative | fn | 1 | 4 | correct |
| ❓ case011_mixed_type_math | unknown | 2 | 5 | unknown |
| ❓ case012_complex_control | unknown | 3 | 7 | unknown |

## 结论

### 假阳性分析
假阳性共 6 个，集中在以下模式：
- MMIO 指针转换（Rules 11.1, 11.3）
- RTOS 回调函数签名（Rule 8.13）
- 调试宏展开（Rule 17.7）

### 假阴性分析
假阴性共 0 个，集中在以下模式：
- 隐式函数声明（Rule 8.2）
- 数组越界指针运算（Rule 18.2）
- 表达式副作用的求值顺序依赖（Rule 13.3）

### 建议
- **规则 11.x**（指针转换）：添加 suppress 白名单
- **规则 8.13**（const 参数）：排除 RTOS API 回调
- 定期使用 clang-tidy MISRA 补充检测
- AI 审查层捕获假阴性

---
*报告由 yuleOSH MISRA Benchmark Runner 自动生成*
# Benchmark 扩展报告 (D1)

## 变更概要

benchmark 目录结构从平面布局改为分层布局，新增 medium 和 hard 难度级别。

## 目录结构

```
benchmark/misra-fp-cases/
├── easy/        ← 12 个原基础用例（已迁移）
├── medium/      ← 10 个新中等难度用例
├── hard/        ← 5 个新高难度用例
├── cppcheck-suppressions.txt   ← 保留在根目录
├── case*.c                     ← 保留在原地（向后兼容）
```

**注意**: 原文件保留在根目录以确保向后兼容。`collect_case_files()` 先扫描子目录，没有才回落根目录。

## 用例清单

### Easy (12 cases, 原基础集)

| 用例 | 分类 | 规则 | 预期违规 |
|------|------|------|---------|
| case001_true_positive | tp | 10.1 | 1 |
| case002_false_positive | fp | 11.3 | 0 |
| case003_false_positive | fp | 8.13 | 0 |
| case004_false_positive | fp | 17.7 | 0 |
| case005_false_positive | fp | 11.1 | 0 |
| case006_false_positive | fp | 10.7 | 0 |
| case007_true_negative | tn | — | 0 |
| case008_false_negative | fn | 13.3 | 1 |
| case009_false_negative | fn | 18.2 | 1 |
| case010_false_negative | fn | 8.2 | 1 |
| case011_mixed_type_math | unk | 10.1 | 2 |
| case012_complex_control | unk | 14.3 | 3 |

### Medium (10 new cases)

| 用例 | 分类 | 规则 | 预期违规 | 场景 |
|------|------|------|---------|------|
| medium001_true_positive | tp | 8.7 | 1 | 单 TU 外部链接 |
| medium002_false_positive | fp | 11.4 | 0 | MMIO 寄存器访问 |
| medium003_true_positive | tp | 10.3, 10.4 | 2 | 隐式类型窄化 |
| medium004_false_positive | fp | 15.6 | 0 | 自旋锁忙等待 |
| medium005_true_negative | tn | 17.2 | 0 | 迭代替代递归 |
| medium006_false_positive | fp | 8.13 | 0 | RTOS 回调注册 |
| medium007_true_positive | tp | 21.5, 21.6 | 2 | signal.h 禁止使用 |
| medium008_false_negative | fn | 10.6 | 1 | 复合表达式隐式窄化 |
| medium009_true_negative | tn | 13.2 | 0 | 安全求值顺序 |
| medium010_false_positive | fp | 18.1 | 0 | 环形缓冲区指针运算 |

### Hard (5 new cases)

| 用例 | 分类 | 规则 | 预期违规 | 场景 |
|------|------|------|---------|------|
| hard001_true_positive | tp | Dir 4.12, 21.3 | 3 | 动态内存分配 |
| hard002_false_positive | fp | 18.6, 19.1 | 0 | CAN 协议回调生命周期 |
| hard003_true_negative | tn | 22.1 | 0 | TCP 缓冲池确定性释放 |
| hard004_false_positive | fp | 13.6, 19.1 | 0 | 类型泛型硬件抽象宏 |
| hard005_true_positive | tp | Dir 1.1, 10.1, 12.1 | 3 | packed struct 位域 |

## Benchmark Runner 更新

`run_misra_benchmark.py` 更新：
- `collect_case_files()` — 支持多级子目录搜索
- `_detect_difficulty()` — 自动检测难度级别
- 报告增加 `difficulty` 字段和分难度统计
- 规则提取修复：支持逗号分隔的多规则格式

## 总数

- **Easy**: 12 cases
- **Medium**: 10 cases ✅ (要求 ≥10)
- **Hard**: 5 cases ✅ (要求 ≥5)
- **Total**: 27 cases

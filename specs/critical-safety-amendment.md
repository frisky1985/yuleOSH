# 关键安全异常检测规范 (P0 GATE)

> **Spec ID**: CRIT-SAFE-001  
> **版本**: 2.0.0  
> **状态**: 生效 (Enforced)  
> **关联**: pipeline step `review-critical-safety`  

## 1. 概述

Pipeline 新增 `review-critical-safety` 步骤，作为 **P0 CRITICAL GATE**。
发现任何匹配违例即**阻断 pipeline**，不修复不进下一阶段。

**全部使用静态代码分析，零运行时开销。**

## 2. 检测规则

| # | 规则ID | 异常类型 | 严重度 | cppcheck check | 静态检测方式 |
|:-:|:-------|:---------|:------:|:---------------|:-------------|
| 1 | CRIT-DIV-001 | 除零 | P0 🔴 | `zerodiv,zerodivcond` | 常量除零直接报错；变量除数前必须检查非零 |
| 2 | CRIT-BUF-001 | 缓冲区越界 | P0 🔴 | `arrayIndexOutOfBounds,bufferAccessOutOfBounds` | 数组下标超限、sprintf/strcpy/gets 禁用 |
| 3 | CRIT-NULL-001 | 空指针解引用 | P0 🔴 | `nullPointer,nullPointerRedundantCheck` | malloc 后必须检查 NULL；函数返回指针必须校验 |
| 4 | CRIT-REC-001 | 无限递归 | P0 🔴 | `selfAssignment,recurseCount` | 默认禁止递归；必须用时加深度守卫 depth++ ≤ 4 |
| 5 | CRIT-LOOP-001 | 死循环 | P0 🔴 | `knownConditionTrueFalse` | while(1)/for(;;) 内必须有 break/return/goto |
| 6 | CRIT-INT-001 | 整型溢出 | P0 🔴 | `integerOverflow,uninitvar` | 隐式窄化转换报错；有符号运算用 int32_t 及以上 |
| 7 | CRIT-STK-001 | 栈溢出 | P0 🔴 | `allocaCalled,autoVariables` | 局部数组 >1KB 报错；禁用 alloca |
| 8 | CRIT-MEM-001 | 内存泄漏 | P0 🔴 | `memleak,leakReturnValNotUsed,doubleFree` | malloc 必须对应 free；禁止二次 free |

## 3. MISRA 规则注册

全部 8 条已加入 `misra-rules.yaml`：

```yaml
crit-safe-division-by-zero:
  check_method: cppcheck
  cppcheck_check: zerodiv,zerodivcond
  # ...

crit-safe-memory-leak:
  check_method: cppcheck  
  cppcheck_check: memleak,leakReturnValNotUsed,doubleFree
  # ...
```

运行 cppcheck `--enable=all` 时自动覆盖全部 P0 检查：
```bash
cppcheck --enable=all --suppress=missingInclude src/
```

## 4. 阻断机制

- pipeline 中 `review-critical-safety` 位于 SWE.5 阶段末尾
- 发现任何 **P0 违例** → `PipelineStepError` → pipeline 立即终止
- 违例报告输出到 `artifacts/critical-safety-report.json`
- 修复后重新运行才能进入 SWE.6

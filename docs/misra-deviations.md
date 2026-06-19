# 偏差管理记录 (MISRA Deviations)

> **版本**: 1.0.0  
> **状态**: ✅ 已发布  
> **G-02**: 唯一 ID + 审批签名 + 有效期限 + CR 关联  
> **参考**: misra-acceptance-matrix.md §3.13, ci-config.yaml misra.deviations

---

## 偏差管理流程

### 偏差生命周期

```
发现违规 → 评估风险 → 提交偏差 → 审批 → 记录追踪 → 过期复审
   (new)      (triage)    (pending)  (approved)  (active)   (expired)
                             ↘ rejected ↙
```

### 偏差格式

每条偏差记录在 `ci-config.yaml` 中存储，格式如下：

```yaml
- rule: <MISRA Rule ID>
  file: <Glob pattern for file path>
  reason: <偏差原因说明>
  approved_by: <审批人>
  expires: <ISO 过期日期, e.g. 2026-12-31>
  status: <pending | approved | rejected | expired>
  cr_ref: <可选>  # 变更请求关联号
```

### 审批要求

| 等级 | 审批人 | 有效期限 | 备注 |
|:-----|:-------|:---------|:-----|
| Required 规则 | Safety Manager / 架构师 | ≤ 6 个月 | 必须附 CR 号 |
| Advisory 规则 | Tech Lead | ≤ 12 个月 | 建议附 CR 号 |
| Dir 规则 | Safety Manager | ≤ 6 个月 | 必须有 CR 号 |

---

## 偏差记录

| # | Rule ID | File Pattern | 原因 | 审批人 | 有效期 | CR 号 | 状态 |
|:-:|:--------|:-------------|:-----|:-------|:-------|:------|:-----|
| 1 | Rule-12-2 | `src/**/legacy/*.c` | 遗留代码，有符号类型的位运算 | safety-manager | 2026-12-31 | CR-2026-001 | ✅ approved |
| 2 | Dir-4-12 | `src/**/test/**/*.c` | 测试代码允许动态内存分配 | safety-manager | 2026-09-30 | CR-2026-012 | ✅ approved |
| 3 | Rule-21-21 | `src/**/platform/**` | 平台层允许使用标准库安全子集 | tech-lead | 2026-12-31 | — | ⏳ pending |
| 4 | Rule-17-7 | `src/**/boot/**` | Bootloader 调用约束性函数 | test-harness | 2026-08-15 | — | ⏳ pending |

---

## 偏差复审日历

| 复审月份 | 待复审偏差 | 负责人 | 状态 |
|:---------|:-----------|:-------|:-----|
| 2026-08 | #4 (Rule-17-7) | test-harness | 📋 待排期 |
| 2026-09 | #2 (Dir-4-12) | safety-manager | 📋 待排期 |
| 2026-12 | #1 (Rule-12-2) | safety-manager | 📋 待排期 |

---

## CL2 审计线索

偏差管理为 CL2 §3.13 审计证据之一：

- **唯一 ID**: 每条偏差有递进编号 (#1, #2, ...) 以及 Rule:File 复合 ID
- **审批签名**: `approved_by` 字段记录审批人身份
- **有效期限**: `expires` 字段确保偏差不无限期有效
- **CR 关联**: `cr_ref` 字段链接到变更请求（如 ALM ticket）

### 审计检查清单

- [ ] 所有偏差有 `approved_by` 字段
- [ ] 所有偏差有 `expires` 字段（未过期的当前偏差）
- [ ] Required 规则偏差有 CR 关联号
- [ ] 过期偏差已标记 expired 或重审
- [ ] 偏差状态在审批后更新（pending → approved/rejected）

---

> 更新: 2026-06-19 | 作者: yuleOSH Quality

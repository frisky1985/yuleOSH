# MISRA C:2023 验证计划

## 1. 验证范围

- **适用标准**: MISRA C:2023
- **覆盖规则**: 180条 (100%)
- **自动检查**: cppcheck + MISRA addon
- **补充检查**: AI/LLM 审查 + 人工审查

### 1.1 工具链

| 工具 | 用途 | 执行方式 |
|:-----|:-----|:---------|
| cppcheck --addon=misra | 自动静态分析 | CI L1 阶段 |
| AI/LLM Review | 语义级规则检查 | Pipeline Review 阶段 |
| 人工审查 (Peer Review) | 偏差审批、复杂规则确认 | 按需 |

### 1.2 排除项

- 第三方库代码（`lib/`, `vendor/` 目录）
- 自动生成的代码（`build/`, `generated/` 目录）
- 已通过偏差审批的文件（见偏差管理流程）

## 2. 验证频率

| 触发条件 | 检查模式 | 负责人 |
|:---------|:---------|:-------|
| Commit (pre-commit hook) | 增量检查 (git diff HEAD~1) | 开发者 |
| Push / CI | 全量检查 | CI Runner |
| Nightly | 全量 + 趋势记录 | CI Scheduler |
| Release | 全量 + Zero Required Violation | CI Runner + QA |

### 2.1 增量检查规则

增量检查仅扫描 Git commit 中变更的 `.c` / `.cpp` 文件，适用于快速反馈。
增量模式下的违规记录标记 `is_delta: true`，不阻断管线但计入违规趋势。

### 2.2 Release 检查规则

Release 构建要求：
- **Required 违规: 0**（零容忍）
- Advisory 违规: ≤ 100 条
- 违规密度: ≤ 2.0 violations/KLOC

## 3. 角色与职责

| 角色 | 职责 | 拥有者 |
|:-----|:-----|:-------|
| 开发者 | 修复自身引入的违规 | 项目所有成员 |
| 架构师 (Architect) | 审批偏差申请 | 技术负责人 |
| QA | 审查趋势报告、验证合规 | 质量保证团队 |
| CI Runner | 自动执行检查并生成报告 | 平台工具 |

### 3.1 开发者工作流

1. 编码完成后运行 `yuleosh ci run 1`
2. 查看 `.yuleosh/reports/misra-report.md` 定位违规
3. 修复违规或提交偏差申请
4. 确认 Required 违规清零后推送

### 3.2 架构师工作流

1. 审批偏差申请（`yuleosh misra deviate`）
2. 定期审查违规趋势（`show_trend()`）
3. 决定规则覆盖/排除策略

## 4. 偏差管理流程

### 4.1 偏差生命周期

```
[创建] → [待审批] → [已批准 / 已拒绝]
                        ↓
              到期后自动失效 → 需重新申请
```

### 4.2 偏差字段说明

| 字段 | 说明 | 示例 |
|:-----|:-----|:-----|
| **Rule ID** | MISRA 规则标识 | `misra-c2023-17.7` |
| **File Pattern** | 应用偏差的文件 glob 模式 | `src/legacy/*.c` |
| **Reason** | 申请理由 | "继承代码，计划Q3重构" |
| **Approved By** | 审批人/角色 | `arch-review` |
| **Expires** | 到期日期 (ISO 8601) | `2026-09-30` |
| **Status** | 状态: `pending` / `approved` / `rejected` | `approved` |

### 4.3 CLI 命令

```bash
# 列出所有偏差
yuleosh misra deviate list

# 审批偏差（dev_id 格式: rule_id:file_pattern）
yuleosh misra deviate approve "misra-c2023-17.7:src/legacy/*.c"

# 拒绝偏差
yuleosh misra deviate reject "misra-c2023-17.7:src/legacy/*.c"

# 交互式添加偏差
yuleosh misra deviate add
```

### 4.4 偏差规则

- 偏差必须有明确的 **到期日期**（最长 12 个月）
- 偏差必须经 **架构师或安全审查** 批准
- 到期偏差自动失效，违规状态恢复为 `unresolved`
- 偏差对应的违规在追踪矩阵中标记为 `acknowledged`

## 5. KPI 与目标

### 5.1 量化目标

| KPI | 目标值 | 测量方式 |
|:----|:-------|:---------|
| Required 违规 | **零容忍**（新增即阻断） | 每次 CI 检查 |
| Advisory 违规 | 单项目 ≤ 100 条 | CI 趋势报表 |
| 违规密度 | ≤ 2.0 violations/KLOC | `get_violations_per_kloc()` |
| 修复时效 | Required 违规 48h 内修复或提偏差 | 趋势 + 工时追踪 |
| 趋势方向 | 总体呈下降趋势 | 趋势报表 30 次滚动平均 |

### 5.2 阻断规则

以下任一条件满足时 CI 阶段标记为 FAILED：

1. 存在 Required 违规且 `fail_on_violation=true`（默认）
2. 总违规数 ≥ `fail_threshold`（默认 10）
3. 违规密度 > `violations_per_kloc`（默认 2.0）
4. 存在 Advisory 违规且 `fail_on_advisory=true`

### 5.3 趋势报告

每次 MISRA 检查自动记录趋势数据到 `.yuleosh/reports/misra-trend.jsonl`：

```json
{"timestamp": "2026-06-18T17:25:00", "total_violations": 5, "required": 3, "advisory": 2, "files_checked": 12, "is_delta": false, "commit": "abc1234"}
```

通过 `show_trend()` 查看最近 N 次趋势的 Markdown 表格：

```python
from yuleosh.ci.misra_trend import show_trend
print(show_trend("/path/to/project", lines=30))
```

## 6. 附录

### 6.1 配置参考

MISRA 检查配置位于 `.yuleosh/ci-config.yaml` 的 `misra:` 块。

```yaml
misra:
  enabled: true
  fail_on_violation: true
  fail_on_advisory: false
  fail_threshold: 10
  violations_per_kloc: 2.0
```

### 6.2 相关文档

- [MISRA C:2023 官方标准](https://www.misra.org.uk)
- [cppcheck MISRA Addon 文档](https://cppcheck.sourceforge.io)
- [合规证据收集](/docs/evidence/collection.md)

---

*生成日期: 2026-06-18*
*版本: 1.0*
*由 yuleOSH CI 框架自动管理*

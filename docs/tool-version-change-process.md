# 工具版本变更流程 (Tool Version Change Process)

**文档 ID**: RI-04
**版本**: v1.0
**创建日期**: 2026-06-19
**关联**: CL2 RI-03 (tools-version.yaml), Sprint E (变更审批)

---

## 1. 概述

本流程定义 yuleOSH 项目中工具（编译器、分析器、框架等）版本变更的审批和记录流程。确保工具版本变更可追溯、可审计，满足 ASPICE CL2 的过程测量要求。

## 2. 变更类型分级

| 级别 | 描述 | 示例 | 审批要求 |
|:-----|:-----|:-----|:---------|
| **L1 — 补丁** | 补丁版本更新（z 位变化） | gcc 13.2.1 → 13.2.2 | 无需审批，记录即可 |
| **L2 — 次要** | 次要版本更新（y 位变化） | gcc 13.2 → 13.3 | 技术负责人审批 |
| **L3 — 主要** | 主要版本更新（x 位变化） | gcc 12 → 13 | 架构师 + 质量负责人审批 |
| **L4 — 替换** | 工具替换或新增 | cppcheck → clang-tidy | 正式评审 + 影响分析 |

## 3. 变更流程

### 3.1 变更请求

1. 创建 Issue 或 PR，标题格式: `tool-update: <tool-name> <old> → <new>`
2. 填写变更级别 (L1-L4)
3. 提供变更理由

### 3.2 影响分析

| 类别 | 检查项 |
|:-----|:-------|
| 编译兼容性 | 变更是否影响现有代码编译？是否引入新警告？ |
| MISRA 检查 | 变更后需重新运行 MISRA 检查并比较结果 |
| 覆盖率 | 覆盖率工具是否兼容？数据格式是否变化？ |
| 回归测试 | 运行全量 CI 流水线 (make ci) |

### 3.3 审批

根据变更级别，在 PR 中获取所需审批。

### 3.4 记录

变更后更新 `tools-version.yaml`：

```yaml
# 在 tools 下添加 approval 字段
tools:
  <tool-name>:
    version: <new-version>
    approval:
      level: L<1-4>
      date: "YYYY-MM-DD"
      approver: <name>
      pr: <PR-URL-or-#
```

## 4. tools-version.yaml 示例

```yaml
generated_at: "2026-06-19T14:58:05"
project: yuleOSH
tools:
  gcc:
    version: "Apple clang version 21.0.0"
    approval:
      level: L1
      date: "2026-06-19"
      approver: "stefan"
      pr: "#init"
  cppcheck:
    version: "Cppcheck 2.17.1 from cppcheck-wheel 1.5.1"
    approval:
      level: L1
      date: "2026-06-19"
      approver: "stefan"
      pr: "#init"
  python:
    version: "Python 3.13.13"
    approval:
      level: L1
      date: "2026-06-19"
      approver: "stefan"
      pr: "#init"
  git:
    version: "git version 2.50.1"
    approval:
      level: L1
      date: "2026-06-19"
      approver: "stefan"
      pr: "#init"
  gcov:
    version: "Apple LLVM version 21.0.0"
    approval:
      level: L1
      date: "2026-06-19"
      approver: "stefan"
      pr: "#init"
```

## 5. 自动检查

`yuleosh` CLI 提供 `yuleosh tools check` 命令检查工具版本是否符合：
- 已安装版本是否在 `tools-version.yaml` 中记录
- 是否有未记录的版本变更

## 6. 审计追溯

工具版本变更记录通过以下方式确保可追溯：
1. **Git commit**: 每次 `tools-version.yaml` 更新必须独立提交
2. **PR 关联**: `approval.pr` 字段关联到变更 PR
3. **审批人**: `approval.approver` 字段记录审批人
4. **时间戳**: `approval.date` 字段记录审批日期

---

*本文档满足 ASPICE CL2 RI-03 工具版本记录要求及 Sprint E 变更审批要求。*

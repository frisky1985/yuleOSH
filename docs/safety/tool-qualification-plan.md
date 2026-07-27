# Tool Qualification Plan — Periodic Reassessment Process

> **文档 ID**: G-08-TQP-001  
> **适用项目**: yuleOSH CI/CD + Agent Pipeline  
> **标准依据**: ISO 26262-8:2018 §11.4.5, §11.4.6  
> **版本**: 1.0  
> **生成日期**: 2026-07-26  

---

## 1. Overview

本文档定义 yuleOSH pipeline 中所有工具的 qualification 定期评估流程。涵盖：

1. 每个 Release 前的定期重新评估
2. 第三方工具版本升级时的重新评估
3. 已知限制清单的持续维护
4. 工具故障和异常的处理流程

### 1.1 Trigger Conditions

| Trigger | Urgency | Full/Partial | Responsibility |
|:--------|:-------:|:------------:|:---------------|
| **Release 前** | Scheduled | **Full** | CI/QA Team |
| 工具版本升级 (major) | High | **Full** | CI/QA Team |
| 工具版本升级 (minor) | Medium | **Partial** | CI Team |
| 工具版本升级 (patch) | Low | **Partial** | CI Team |
| 发现新漏报模式 | Medium | Partial | Architecture Team |
| 工具崩溃/异常 | High | **Full** | CI Team |
| 安全事件 | Critical | **Full** | Security + All Teams |
| 季度复审 | Scheduled | **Full** | Quality Team |

---

## 2. Release Qualification Process

### 2.1 Qualification Flow

每个 Release 前执行以下 5 步 qualification 流程：

```
Step 1: 🔍 工具版本检查
  ├── 检查所有第三方工具版本
  ├── 对比已知合格版本清单
  └── 如有变更 → 触发版本升级评估

Step 2: 📊 回归验证
  ├── 运行测试基准 (test-bench/)
  ├── 比较检测结果趋势
  ├── 量化准确率/召回率变化
  └── 检查覆盖率指标

Step 3: 📋 已知限制复审
  ├── 更新已知限制清单
  ├── 检查是否有新发现的限制
  └── 评估限制对安全目标的影响

Step 4: 📝 TCL 文档更新
  ├── 更新 TCL 评估矩阵
  ├── 更新故障覆盖矩阵
  ├── 更新证据链可信度分析
  └── 更新第三方工具依赖表

Step 5: ✅ Qualification 报告
  ├── 汇总 qualification 结果
  ├── 生成 qualification 报告
  └── 审批签字
```

### 2.2 Qualification Checklist

| # | Check Item | Method | Evidence |
|:-:|:-----------|:-------|:---------|
| 1 | 所有工具版本 = 上次合格的版本 | 版本号对比 | Qualification report |
| 2 | 工具未发现新的安全漏洞 (CVEs) | 安全扫描 | CVE scan report |
| 3 | MISRA 检测准确率/召回率无显著下降 | 测试基准对比 | MISRA benchmark diff |
| 4 | 覆盖率工具数据完整性正常 | 回归测试 | Coverage trend report |
| 5 | 所有 stage 输出可被人工验证 | 抽查 3 个示例 | Spot check records |
| 6 | 偏差管理的误报/漏报清单已更新 | 偏差仓库状态 | Deviation list review |
| 7 | 证据包 7 层校验全部通过 | 运行 ev check | ev check report |
| 8 | 证据包数字签名验证通过 | 签名验证 | Signature verification |
| 9 | 所有已知限制仍有效且已记录 | 限制清单复审 | Known limitations doc |
| 10 | 无新增 TCL3 故障模式 | 故障模式分析 | TCL matrix update |

### 2.3 Escalation Criteria

以下情况触发升级流程：

| Condition | Action | Escalate To |
|:----------|:-------|:------------|
| MISRA 召回率下降 > 5% | 暂停 Release，调查根本原因 | Architecture + QA 评审 |
| 新发现 TCL3 故障模式 | 暂停 Release，评估影响 | 安全委员会 |
| 工具 CVE 严重程度 ≥ High | 暂停 Release，升级/替换工具 | 安全团队 + 架构委员会 |
| 覆盖率数据异常导致误报率 > 50% | 调查后决定是否加 Suppress | QA Team |
| 证据包完整性校验失败 | 定位原因后重跑 pipeline | CI Team |

---

## 3. Third-Party Tool Version Upgrade Process

### 3.1 Upgrade Classification

| Change Type | Re-qualification | Timeline | Examples |
|:------------|:----------------:|:---------|:---------|
| **Major** (x.0.0) | **Full** | 2 周 | cppcheck 3.0.0, lcov 3.0 |
| **Minor** (x.Y.0) | **Partial** | 1 周 | cppcheck 2.18.0, pytest 9.0 |
| **Patch** (x.y.Z) | **Light** | 2 天 | cppcheck 2.17.2, pytest 8.3.5 |
| **Dependency patch** | **None** | Immediate | Python 3.13.1 → 3.13.2 (security only) |

### 3.2 Full Re-qualification Procedure

当工具发生 major 版本升级时，执行以下流程：

```
Phase 1: Preparation (2 days)
  ├── 确认新版本功能变更
  ├── 检查兼容性（输出格式、配置语法）
  ├── 更新测试基准
  └── 创建升级分支

Phase 2: Regression Testing (5 days)
  ├── 在升级分支上运行全量 CI
  ├── 运行 MISRA 测试基准
  ├── 运行覆盖率测试基准
  ├── 运行单元测试套件
  ├── 生成证据包并校验完整性
  └── 对比 qualification 指标

Phase 3: Analysis (2 days)
  ├── 量化准确率/召回率变化
  ├── 分析新引入的 FP/FN 模式
  ├── 评估对 TCL 等级的影响
  └── 记录已知限制变更

Phase 4: Documentation Update (2 days)
  ├── 更新 TCL 评估矩阵
  ├── 更新故障覆盖矩阵
  ├── 更新已知限制清单
  ├── 更新第三方工具依赖表
  └── 更新 qualification 报告版本号

Phase 5: Approval (1 day)
  ├── Qualification 报告审批
  ├── 如有偏差 → 偏差审批
  └── 合并到主分支
```

### 3.3 Light Re-qualification Procedure (Patch)

```
Phase 1: Quick Check (1 day)
  ├── 确认是 patch 更新（无功能变更）
  ├── 运行测试基准 (5 min sanity)
  └── 确认无回归

Phase 2: Documentation (1 day)
  ├── 更新工具版本号
  └── 更新 qualification 报告的版本记录
```

### 3.4 Upgrade Request Template

```yaml
# tool-upgrade-request.yaml
tool_name: cppcheck
current_version: 2.17.1
target_version: 2.18.0
change_type: minor
reason: "MISRA C:2023 Rule 22 updates"
risk_assessment:
  output_format_change: false  # Still JSON/XML/Text
  config_syntax_change: false  # Same CLI flags
  performance_change: minor    # 5% faster
affects_tcl: false
regression_required: partial  # Run MISRA test bench only
estimated_effort: 2 days
approved_by: ""
approval_date: ""
```

---

## 4. Known Limitations Management

### 4.1 Known Limitations Register

#### Stage 1: Code Review

| # | Limitation | Impact | Status | Mitigation | Last Reviewed |
|:-:|:-----------|:-------|:-------|:-----------|:-------------|
| CR-01 | AI 可能遗漏特定领域安全模式 | 低概率，高影响 | Active | 人工 review 覆盖特殊安全审查项 | 2026-07 |
| CR-02 | AI review 输出可能不一致 | 中等 | Active | Prompt 版本锁定 + 趋势监控 | 2026-07 |

#### Stage 2: MISRA Check

| # | Limitation | Impact | Status | Mitigation | Last Reviewed |
|:-:|:-----------|:-------|:-------|:-----------|:-------------|
| MC-01 | 仅覆盖 ~120/169 条规则 (~71%) | 29% 规则需补充 | Active | AI + 人工审查补充 | 2026-07 |
| MC-02 | Required 规则误报率 10–15% | 中 | Active | 偏差管理 + suppress | 2026-07 |
| MC-03 | Advisory 规则误报率 30–40% | 低 | Active | 偏差管理 + list review | 2026-07 |
| MC-04 | 控制流/指针别名漏报 | 中 | Active | AI 审查补充 | 2026-07 |
| MC-05 | macOS 下规则集可能不一致 | 低 | Monitor | 平台标注 + CI 提醒 | 2026-07 |

#### Stage 3: Coverage

| # | Limitation | Impact | Status | Mitigation | Last Reviewed |
|:-:|:-----------|:-------|:-------|:-----------|:-------------|
| COV-01 | macOS 下 lcov 无分支覆盖率 | 中 | Active | 平台标注 + Linux CI 全量覆盖 | 2026-07 |
| COV-02 | Python 覆盖率不测 C 扩展 native 路径 | 低 | Active | C 扩展独立覆盖测试 | 2026-07 |
| COV-03 | .gcda 文件可能损坏 | 低 | Monitor | 异常退出处理 + 重跑 | 2026-07 |
| COV-04 | gcovr 在交叉编译环境下需配置 | 低 | Active | CMake 配置指导 | 2026-07 |

#### Stage 4: Unit Test

| # | Limitation | Impact | Status | Mitigation | Last Reviewed |
|:-:|:-----------|:-------|:-------|:-----------|:-------------|
| UT-01 | Unity 无内建 mock 框架 | 中 | Active | MockHAL 抽象层补偿 | 2026-07 |
| UT-02 | pytest 参数化测试大数据量超时 | 低 | Active | 测试超时配置 + 分片 | 2026-07 |

#### Stage 5: Integration Test

| # | Limitation | Impact | Status | Mitigation | Last Reviewed |
|:-:|:-----------|:-------|:-------|:-----------|:-------------|
| IT-01 | HIL 需要开发板（默认 mock） | 中 | Active | SIL + MockHAL 替代验证 | 2026-07 |
| IT-02 | 交叉编译结果跨平台差异 | 低 | Active | ABI 一致性检查 | 2026-07 |

#### Stage 6: Evidence Pack

| # | Limitation | Impact | Status | Mitigation | Last Reviewed |
|:-:|:-----------|:-------|:-------|:-----------|:-------------|
| EP-01 | 证据完整性依赖上游 stage | 中 | Active | 层间校验 gate | 2026-07 |
| EP-02 | 签名私钥安全存储 | 关键 | Active | CI env only + 定期轮换 | 2026-07 |

#### Stage 7: Safety Check

| # | Limitation | Impact | Status | Mitigation | Last Reviewed |
|:-:|:-----------|:-------|:-------|:-----------|:-------------|
| SC-01 | AI 辅助分析不能替代专家 | 中 | Active | P0 gate + 独立专家评审 | 2026-07 |
| SC-02 | 分析准确性依赖输入质量 | 中 | Active | 输入假设检查清单 | 2026-07 |

### 4.2 Limitation Review Cycle

| Review Cycle | Actions |
|:-------------|:--------|
| **Continuous** | 发现新限制时立即记录 |
| **Weekly** | 趋势报告审查 — 异常标记 |
| **Monthly** | 误报/漏报分析 — 更新统计数据 |
| **Quarterly** | 工具 qualification 复审 — 已知限制全面盘点 |
| **Release Before** | 已知限制逐条评估 — 更新 mitigation |

### 4.3 Limitation Update Flow

```
发现新限制 (通过 CI 异常/人工报告/AI 检测)
  │
  ├─ 确认 → 写入 Known Limitations Register
  │         → 记录重现步骤
  │         → 指定 mitigation 措施
  │         → 分配跟踪 ticket
  │
  └─ 不确定 → 创建 investigation ticket
              → 收集更多数据
              → 下次 review 确定是否加入
```

---

## 5. Tool Exception and Incident Handling

### 5.1 Incident Categories

| Category | Examples | Response |
|:---------|:---------|:---------|
| **Crash** | cppcheck segfault, lcov panic | 立即 Report，停止 CI，再跑一次 |
| **Timeout** | 测试超时，覆盖率采集挂起 | 调整超时配置，检查资源 |
| **Data Loss** | .gcda 文件损坏，XML 输出为空 | 重跑 stage，检查磁盘 |
| **Format Change** | MISRA addon 输出格式变更 | 立即 Report，更新解析器 |
| **License Issue** | GPL 合规警报，工具不再可用 | 安全/法务评估，寻找替代 |
| **CVE** | 工具发现严重安全漏洞 | 紧急升级，安全团队介入 |

### 5.2 Incident Response Flow

```
Incident Detected
  │
  ├── Auto-remediation attempt (最多 2 次)
  │     ├── CRASH → retry with timeout +50%
  │     ├── TIMEOUT → retry with extended timeout
  │     └── DATA_LOSS → regenerate stage output
  │
  ├── Persistent failure → Notify CI Team
  │
  ├── CI Team Diagnosis (< 4 hours)
  │     ├── 确定根因
  │     ├── 影响范围评估
  │     └── 临时缓解措施
  │
  ├── If blocking Release → Escalate to Architecture Steering
  │     ├── 影响 TCL？ → 触发重新 qualification
  │     ├── 需要替代工具？ → 评估替代方案
  │     └── 短期 workaround？ → 偏差审批
  │
  └── Post-incident: Root Cause Analysis + 预防措施
        ├── 更新已知限制清单
        ├── 更新 qualification 文档
        └── 更新自动检测机制
```

### 5.3 Incident Log Template

```yaml
# tool-incident-YYMMDD-001.yaml
incident_id: INC-20260726-001
tool: cppcheck
version: 2.17.1
date: 2026-07-26
category: Data_Loss
description: "MISRA addon failed to load: 'Unknown rule MISRA-2023-Dir-4.2'"
root_cause: "Rule number format mismatch in ci-config.yaml"
impact:
  affected_stages: [misra-check]
  tcl_change: false  # TCL unchanged
  blocking: true
resolution:
  action: "Update ci-config.yaml rule reference"
  fix_time: 30 minutes
  permanent_fix: "Add rule format validation in misra_report.py"
prevention:
  - "Validate rule config before running cppcheck"
  - "Add consistency check script in CI pre-stage"
```

---

## 6. Qualification Metrics and KPIs

### 6.1 Key Metrics

| Metric | Target | Measurement | Alert Threshold |
|:-------|:------:|:------------|:----------------|
| MISRA Required 规则召回率 | ≥90% | 测试基准对比 | <85% |
| MISRA 全局精确率 | ≥70% | TP / (TP + FP) | <60% |
| C 覆盖率门禁通过率 | ≥95% | 每次 CI 检查 | <90% |
| 证据包完整性校验通过率 | 100% | ev check 结果 | <100% |
| 工具崩溃频率 (30天) | 0 | CI 日志分析 | ≥1 |
| 人工 Review 确认率 | ≥95% | Review 系统统计 | <90% |

### 6.2 Trend Monitoring

所有指标按 Release 追踪趋势：

```
Release         MISRA Recall    MISRA Precision    C Coverage    Tool Crashes
───────         ────────────    ────────────────    ──────────    ────────────
v1.2.0          87%             73%                 68%           0
v1.3.0          88%             75%                 69%           0
v1.4.0          89%             76%                 70%           0
                ↗️               ↗️                   ↗️             ✅
```

### 6.3 Reporting Cadence

| Report | Frequency | Audience |
|:-------|:---------|:---------|
| CI Trend Report | Weekly | CI/QA Team |
| MISRA Accuracy Report | Monthly | Architecture Team |
| Tool Qualification Status | Per Release | All Stakeholders |
| Known Limitations Review | Per Quarter | Quality Team |
| Incident Summary | Per Incident | Security + QA Teams |

---

## 7. Responsibility Matrix

| Role | Responsibility |
|:-----|:---------------|
| **CI/QA Team** | 执行 qualification 流程，维护测试基准 |
| **Architecture Team** | 评估 TCL 变更，审批偏差 |
| **Security Team** | 工具 CVE 扫描，密钥管理 |
| **Quality Manager** | 审批 qualification 报告，把关 Release |
| **Safety Manager** | 评估安全相关工具故障的影响 |
| **Developer** | 报告工具异常，更新已知限制 |

---

## 8. References

- ISO 26262-8:2018 §11.4.5 Methods for increasing confidence
- ISO 26262-8:2018 §11.4.6 Qualification of software tools
- [TCL Assessment](./tcl-assessment.md)
- [Third-Party Tool Dependencies](./third-party-tools.md)
- [Evidence Trustworthiness](./evidence-trustworthiness.md)
- [Tool Version Change Process](../../docs/tool-version-change-process.md)
- [CI Config](../../.yuleosh/ci-config.yaml)

---

*本文档由 yuleOSH CI 框架自动管理*
*版本 1.0 | 2026-07-26*
*下次复审: v1.4.0 Release 前*

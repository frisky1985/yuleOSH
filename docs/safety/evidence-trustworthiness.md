# Evidence Chain Trustworthiness Analysis

> **文档 ID**: G-08-ECT-001  
> **适用项目**: yuleOSH CI/CD + Agent Pipeline  
> **标准依据**: ISO 26262-8:2018 §11, ASPICE SUP.10  
> **版本**: 1.0  
> **生成日期**: 2026-07-26  

---

## 1. Overview

本文档对 yuleOSH pipeline 产出的证据链 (Evidence Chain) 进行全链路可信度分析。分析范围涵盖从数据采集到审计呈现的每个环节，确保 ISO 26262 审核员可以信赖 yuleOSH 输出的审计证据。

### 1.1 证据链总览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Stage 1-5  │     │    Stage 6  │     │    Stage 8  │     │   Audit     │
│  原始数据    │────▶│  证据收集   │────▶│  报告生成   │────▶│  审核人     │
│  (各 Stage)  │     │ (Evidence)  │     │ (Report)    │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
  Git history          SHA-256 hash        Cross-ref
  + timestamp          + RSA sign          validation
```

### 1.2 数据流向

每个 stage 产出的证据经过以下处理流水线：

```
原始数据采集
  → 格式化
  → 完整性校验 (SHA-256)
  → 证据包聚合 (audit-manifest.json)
  → 数字签名 (RSA-2048)
  → 审计呈现 (Report / Dashboard)
```

---

## 2. Data Source Analysis

### 2.1 Evidence Source Inventory

| # | Source | Data Type | Output Format | Creator | Tamper-Proof |
|:-:|:-------|:----------|:--------------|:--------|:-------------|
| 1 | Git diff / commit | 代码变更 | `git diff` patch | 开发者 | ✅ Git SHA + 签名 |
| 2 | cppcheck XML | MISRA 违规 | `misra-report.json` | CI 工具 | ✅ 文件 hash |
| 3 | lcov INFO | 行覆盖率 | `coverage-summary.json` | CI 工具 | ✅ 文件 hash |
| 4 | gcovr JSON | 函数/分支覆盖率 | `coverage.json` | CI 工具 | ✅ 文件 hash |
| 5 | pytest XML | 单元测试结果 | `test-results.json` | CI 工具 | ✅ 文件 hash |
| 6 | Unity XML | C 单元测试结果 | `test-results.json` | CI 工具 | ✅ 文件 hash |
| 7 | SIL test reports | 集成测试结果 | `sil-test-report.json` | CI 工具 | ✅ 文件 hash |
| 8 | Review records | 代码审查记录 | `review-task-*.json` | AI + 人工 | ✅ 文件 hash |
| 9 | FMEA entries | 安全分析记录 | `fmea_entries/*` | AI + 专家 | ✅ 文件 hash |
| 10 | Safety reports | HARA/DFA/FMEDA | `*.json / *.md` | AI + 专家 | ✅ 文件 hash |
| 11 | Pipeline config | CI 配置 | `ci-config.yaml` | 项目管理 | ✅ Git tracking |
| 12 | Pipeline execution log | 运行日志 | `pipeline-run.json` | CI 引擎 | ✅ 文件 hash |

### 2.2 Source Trustworthiness Rating

| Source | Integrity | Authenticity | Non-Repudiation | Rating |
|:-------|:---------:|:------------:|:----------------:|:------:|
| Git diff | High (SHA-1) | High (GPG sign) | High (commit author) | ★★★ |
| cppcheck XML | High (auto-gen, env isolated) | Medium (CI context) | Medium (CI run ID) | ★★★ |
| lcov INFO | High (auto-gen) | Medium (CI context) | Medium (build ID) | ★★★ |
| gcovr JSON | High (auto-gen) | Medium (CI context) | Medium (build ID) | ★★★ |
| pytest XML | High (auto-gen) | Medium (CI context) | Medium (CI run ID) | ★★★ |
| Unity XML | High (auto-gen) | Medium (CI context) | Medium (CI run ID) | ★★★ |
| Review records | Medium (AI + human) | High (user auth) | High (reviewer identity) | ★★☆ |
| FMEA entries | Medium (AI + expert) | High (user auth) | High (expert identity) | ★★☆ |
| Safety reports | Medium (AI + expert) | High (user auth) | High (expert identity) | ★★☆ |
| Pipeline config | High (Git tracked) | High (Git tracked) | High (commit author) | ★★★ |

---

## 3. Processing Chain Analysis

### 3.1 Data Processing Stages

每个证据数据经过以下处理环节：

```
✎ Source → ✎ Parse → ✎ Transform → ✎ Validate → ✎ Store → ✎ Present
```

#### Stage: Parse

| Stage | Tool | Risk | Mitigation |
|:------|:-----|:-----|:-----------|
| MISRA | `misra_report.py` | 解析错误导致数据丢失 | Schema 校验 + 人工抽查 |
| Coverage | `gcov_coverage.py` | JSON 解析异常 | 异常捕获 + 原始数据保留 |
| Test | `test_c_unit.py` | XML 解析失败 | 回退到原始输出解析 |
| Review | `review_*.py` | JSON 格式错误 | Pydantic schema 校验 |

#### Stage: Transform

| Stage | Transformation | Integrity Risk | Verification |
|:------|:---------------|:---------------|:-------------|
| MISRA | Text → JSON → Markdown | 格式转换数据丢失 | 原始文本保留在 reports/ 目录 |
| Coverage | INFO → JSON → Summary | 聚合计算误差 | 逐文件原始数据保留 |
| Test | XML → JSON Summary | 聚合丢失细节 | JUnit/Unity 原始 XML 保留 |
| Evidence | Merge all → audit-manifest | 合并顺序错误 | SHA-256 跨引用验证 |

#### Stage: Validate

| Validation Layer | What It Checks | Blocking | Automation |
|:-----------------|:---------------|:--------:|:----------:|
| files_present | 所有 required 文件存在 | ✅ Yes | ✅ Auto |
| fields_complete | 所有 JSON 有完整结构 | ✅ Yes | ✅ Auto |
| values_reasonable | 数据值在合理范围 | ⚠️ Warning | ✅ Auto |
| timestamps_ordered | 时间戳单调递增 | ✅ Yes | ✅ Auto |
| cross_refs_resolved | 跨引用有效 | ⚠️ Warning | ✅ Auto |
| sha256_integrity | 文件哈希匹配 | ✅ Yes | ✅ Auto |
| signature_valid | RSA 签名有效 | ⚠️ Warning | ✅ Auto |

#### Stage: Store

| Storage | Location | Integrity | Access Control |
|:--------|:---------|:----------|:---------------|
| CI Results | `.osh/ci/layer*.json` | Git-ignored | CI runner 隔离 |
| Evidence Pack | `.osh/evidence/{build_id}/` | SHA-256 + RSA | CI runner 隔离 |
| Pipeline Sessions | `.osh/sessions/` | Per-step artifact | CI runner 隔离 |
| FMEA Entries | `fmea_entries/` | Git-tracked | Git permissions |
| Knowledge Graph | `.yuleosh/knowledge_graph.db` | Application-level | API access only |

#### Stage: Present

| Presentation | Data Source | Transformation | Verifiability |
|:-------------|:------------|:---------------|:--------------|
| `ci-final-report.md` | All layer results | Template + LLM | ✅ 引用的原始数据可独立验证 |
| `ci-final-report.xlsx` | All stage outputs | Excel writer | ✅ 结构化数据可独立验证 |
| Dashboard | Live API data | React/TypeScript | ✅ API 实时请求 |
| Audit Manifest | All evidence files | SHA-256 hashing | ✅ 可独立重算 |

### 3.2 Processing Risk Matrix

| Risk | Probability | Impact | Detection | Mitigation |
|:-----|:-----------:|:-------|:----------|:-----------|
| 解析器引入数据不一致 | Low | High | 原始数据保留可追溯 | 不覆盖原始输出文件 |
| 聚合计算误差 | Low | Medium | 逐文件数据可独立验证 | 保留所有原始粒度数据 |
| 存储介质损坏 | Very Low | Critical | SHA-256 校验 | 证据包 ZIP + 签名 |
| 呈现层数据过时 | Low | Medium | 时间戳单调递增校验 | Pipeline 运行时标记 |
| AI 报告内容不准确 | Medium | Medium | 引用原始数据源 | 原始数据文件保留 |

---

## 4. Tamper Resistance

### 4.1 Protection Layers

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 4: Digital Signature (RSA-2048)                         │
│  - audit-manifest.json 整体签名                                │
│  - 私钥仅存于 CI/CD 环境                                      │
├──────────────────────────────────────────────────────────────┤
│ Layer 3: SHA-256 Individual Files                             │
│  - 每个证据文件独立哈希                                        │
│  - manifest 包含文件哈希清单                                   │
├──────────────────────────────────────────────────────────────┤
│ Layer 2: CI Environment Isolation                             │
│  - 每个 stage 在隔离工作区执行                                 │
│  - CI 运行结果由 CI runner 管理                                │
├──────────────────────────────────────────────────────────────┤
│ Layer 1: Git Version Control                                  │
│  - 代码、配置、spec 全部 Git tracked                           │
│  - Commit 历史不可篡改                                        │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Tamper Scenarios

| Scenario | Feasibility | Detection | Impact |
|:---------|:-----------:|:----------|:-------|
| 篡改证据源文件 | Low (需要 CI runner 访问权限) | SHA-256 检查失败 | Blocked |
| 伪造 Audit Manifest | Low (需要私钥) | 签名验证失败 | Blocked |
| 替换历史证据包 | Medium (可访问存储) | 时间戳检查失败 | Warning |
| 注入虚假 stage 输出 | Medium (需要在未锁定环境操作) | 跨引用检查失败 | Warning |
| 绕过 CI 直接提交未审查代码 | Low (Git branch protection) | Git hook 拦截 | Blocked |

### 4.3 Digital Signature

证据包使用 RSA-2048 + SHA-256 (PKCS1v15 padding) 数字签名：

```
Signing Flow:
  audit-manifest.json (without signature field)
  → SHA-256 hash
  → RSA-2048 encryption (CI/CD 私钥)
  → Signature appended to audit-manifest.json["signature"]

Verification Flow:
  audit-manifest.json (extract signature field)
  → Recalculate SHA-256 hash of remaining fields
  → RSA-2048 decryption (embedded public key)
  → Compare hashes
```

**Key Management:**

| Item | Detail |
|:-----|:--------|
| Algorithm | RSA-2048 + SHA-256 (PKCS1v15 padding) |
| Private Key Storage | CI/CD environment variable (never in repo) |
| Public Key Distribution | Embedded in yuleOSH client distribution |
| Key Rotation | Every 6 months or on security incident |
| Rotation Process | `yuleosh evidence rotate-key` CLI command |

---

## 5. Traceability Verification

### 5.1 Cross-Reference Verification

证据包中的 audit-manifest.json 包含跨引用验证：

| Cross-Ref Type | Example | Verification |
|:---------------|:--------|:-------------|
| Requirement → Test | specs/spec.md → "ref: SWR-001" in test results | cross_refs_resolved check |
| Requirement → Code | specs/spec.md → implementation in src/ | Git blame + review records |
| MISRA Violation → Line | misra-report.json → "line": 42 | Line number traceable |
| Coverage → File | coverage-summary.json → "file": "src/module.c" | File path traceable |
| Test → Requirement | test-results.json → "req_id": "SWR-001" | auto resolved in pipeline |
| Review → Diff | review-task-*.json → "commit_hash" | Git commit linked |

### 5.2 Chain of Custody

```
Approval Gate
  │
  ├── Pipeline Trigger — 谁/什么触发了这次 pipeline
  │     ├── CI triggered by: commit <hash>, author <name>, timestamp <ISO8601>
  │     └── Manual triggered by: user <id>, CLI command, timestamp
  │
  ├── Stage Execution — 每个 stage 的执行记录
  │     ├── Stage name, start time, end time, duration
  │     ├── Exit code, output file path, output file SHA-256
  │     └── Errors/warnings log
  │
  ├── Stage Artifact — 每个 stage 的输出产物
  │     ├── Full artifact preserved (never overridden)
  │     ├── SHA-256 hash computed at write time
  │     └── Artifact path logged in session.json
  │
  └── Audit Export — 证据包导出
        ├── All artifacts bundled + hashed
        ├── Cross-refs validated
        └── Digital signature applied
```

---

## 6. Trustworthiness Conclusion

### 6.1 Ratings Summary

| Category | Rating | Explanation |
|:---------|:-------|:------------|
| Data Source Integrity | ★★★ High | 所有数据源来自可验证的 CI 工具或 Git 跟踪文件 |
| Processing Fidelity | ★★★ High | 保留原始输出 + 独立校验 |
| Tamper Resistance | ★★★ High | 4 层保护 + RSA 签名 |
| Traceability | ★★★ High | 端到端可追溯，从需求到测试到证据 |
| Human Review Integration | ★★☆ Medium | AI + 人工审查记录可追溯但依赖人工执行力 |

### 6.2 Residual Risks

| Residual Risk | Likelihood | Acceptance |
|:--------------|:----------:|:-----------|
| CI 环境被完全攻破导致所有签名失效 | Very Low | Accept with monitoring |
| 人工审查环节未严格执行（review 流于形式） | Medium | Mitigated by P0 gate + 趋势监控 |
| 跨平台差异导致覆盖率数据不一致 | Low | Accept with platform annotation |
| AI 生成内容含微妙错误未被注意 | Low | Mitigated by cross-ref validation |

### 6.3 Conclusion

yuleOSH 证据链的可信度整体评估为 **High**。通过以下保证机制满足 ISO 26262-8 §11 对工具输出的要求：

1. ✅ **数据完整性**: 每个证据文件的 SHA-256 哈希被记录在 `audit-manifest.json` 中，可独立验证
2. ✅ **源认证**: 所有数据来源可追溯至具体的 CI 运行、Git 提交或人工操作记录
3. ✅ **不可抵赖性**: RSA 数字签名确保证据包在导出后未被篡改
4. ✅ **可追溯性**: 从需求到测试结果的跨引用链完整且可自动验证
5. ✅ **人工复核**: 所有安全相关的输出均经过人工确认或专家评审

---

*本文档由 yuleOSH CI 框架自动管理*
*版本 1.0 | 2026-07-26*

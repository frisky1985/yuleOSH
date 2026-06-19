# CL2 Dry Run 审计清单 — 模拟审计师视角

> **编制人**: 小马 🐴（质量架构师）
> **用途**: 在正式邀请老陈前，以小马自测方式模拟审计师，逐项遍历 CL2 证据链
> **模式**: 自我怀疑式审计（假设所有证据不可信，要求交叉验证）
> **执行**: `yuleosh evidence check --audit` 辅助 + 人工抽检
> **通过**: 所有检查项 ✅ 通过；无 Major/Critical 发现
> **禁止**: ❌ 已知问题不隐藏，如实记录以评估 Sprint C 修复范围

---

## 使用说明

1. **逐项执行** — 从步骤 1 到步骤 5，每项必须实际运行命令或检查文件
2. **记录证据** — 每项成功后标注 ✅ 并记录输出摘要
3. **发现异常** — 标注 ❌ 并记录异常描述（Major/Critical/Minor）
4. **交叉验证** — 审计师会要求"给我看两次不同构建的数据"，必须能重复验证
5. **失败处理** — 失败项在 Dry Run 报告中说明原因 + Sprint C 修复计划

---

## 步骤 1：证据包完整性审计

### 1.1 证据包一键生成

```bash
# 运行证据包生成
make evidence-package
# 或
yuleosh evidence pack --output cl2-evidence-pack
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 1.1.1 | 运行 `yuleosh evidence pack` | 命令成功退出，输出目录路径 | ⬜ |  |
| 1.1.2 | 检查目录结构：6 子目录存在 | `ls cl2-evidence-pack/` 显示 CoverageEvidence / DocSyncEvidence / BaselineEvidence / VerificationPlan / ALMIntegration / PipelineLogs | ⬜ |  |
| 1.1.3 | 检查各子目录非空 | `find cl2-evidence-pack -empty -type d` → 无输出 | ⬜ |  |
| 1.1.4 | 证据包附带 SHA256 checksum | `ls cl2-evidence-pack.sha256` → 文件存在 | ⬜ |  |
| 1.1.5 | checksum 验证 | `sha256sum -c cl2-evidence-pack.sha256` → OK | ⬜ |  |
| 1.1.6 | manifest 元数据完整 | `cat cl2-evidence-pack/evidence-manifest.json` → 含 timestamp, git_commit, script_version | ⬜ |  |
| 1.1.7 | 生成时间 < 5 分钟 | 计时实测 | ⬜ |  |

### 1.2 证据完整性自检 CLI

```bash
yuleosh evidence check
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 1.2.1 | 运行 `yuleosh evidence check` | 输出格式化为缺口报告 | ⬜ |  |
| 1.2.2 | 检查缺失项列表 | 无 Required 级缺失项 | ⬜ |  |
| 1.2.3 | 支持 `--format json` | 输出为 JSON | ⬜ |  |
| 1.2.4 | 支持 `--save` | `.osh/evidence/` 下生成报告 | ⬜ |  |

---

## 步骤 2：PA 2.1 TM — 追溯管理深度检查

### 2.1 三向追溯矩阵

```bash
yuleosh trace matrix
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 2.1.1 | 追溯矩阵输出完整性 | 表格含 REQ-ID / IMPL-REF / TEST-REF 三列 | ⬜ | 截取前 10 行输出 |
| 2.1.2 | 无孤立需求（无 IMPL 或 TEST） | 每行 REQ-xxx 同时有 IMPL-xxx 和 TEST-xxx | ⬜ | `yuleosh trace check --orphan-reqs` 无输出 |
| 2.1.3 | 无孤立测试（无 REQ 关联） | `yuleosh trace check --orphan-tests` 无输出 | ⬜ |  |
| 2.1.4 | **抽检 3 条需求链（审计师视角）** | | | |
| 2.1.4a | 抽检 REQ-001：追溯 REQ→IMPL | `grep 'REQ-001' traceability-matrix.json` → IMPL 非空 | ⬜ |  |
| 2.1.4b | 抽检 REQ-001：追溯 IMPL→TEST | 对应测试文件存在 | ⬜ |  |
| 2.1.4c | 抽检 REQ-001：追溯 TEST→TestResult | `pytest tests/test_REQ_001.py --collect-only` 测试收集成功 | ⬜ |  |
| 2.1.4d | 抽检 REQ-003：同上 | 100% 可追踪 | ⬜ |  |
| 2.1.4e | 抽检 REQ-005：同上 | 100% 可追踪 | ⬜ |  |
| 2.1.5 | 追溯矩阵按 build_id 可检索 | `yuleosh trace matrix --build-id <id>` 输出对应版本 | ⬜ |  |
| 2.1.6 | 未覆盖测试的需求阻断验证 | 注入无测试需求 → Pipeline 阻断 | ⬜ | CI 日志截图 |

### 2.2 偏差管理全生命周期

```bash
yuleosh misra deviate list
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 2.2.1 | 偏差清单输出 | 表格含 rule_id, file_pattern, reason, approved_by, expires, status | ⬜ |  |
| 2.2.2 | 偏差字段完整性 | `yuleosh misra deviate list --json` → 每条含 6 字段非空 | ⬜ |  |
| 2.2.3 | **抽检 3 条偏差记录（审计师视角）** | | | |
| 2.2.3a | 抽检 DEV-001：审批人可查 | `grep 'DEV-001' .yuleosh/ci-config.yaml` → approved_by 非空 | ⬜ |  |
| 2.2.3b | 抽检 DEV-001：有效期未过期（或可说明） | expires 日期 > 当前或 Sprint C 说明 | ⬜ |  |
| 2.2.3c | 抽检 DEV-001：审批理由充分 | reason 含风险分析和后续修复计划 | ⬜ |  |
| 2.2.3d | 抽检 DEV-003：同上 | 完整 | ⬜ |  |
| 2.2.3e | 抽检 DEV-005：同上 | 完整 | ⬜ |  |
| 2.2.4 | 偏差创建生命周期验证 | `yuleosh misra deviate create` → ci-config.yaml 新增条目，status=pending | ⬜ |  |
| 2.2.5 | 偏差审批生命周期验证 | `yuleosh misra deviate approve <id>` → status=approved, approved_by 更新 | ⬜ |  |
| 2.2.6 | 偏差到期自动失效 | 注入过期偏差 → CI 不认可 | ⬜ |  |
| 2.2.7 | 偏差 CI 过滤验证 | 配置偏差后运行 CI → 匹配违规标记为 "acknowledged" | ⬜ | CI 日志 |

### 2.3 Agent 审查→代码版本追溯

```bash
# 检查最新 Agent 审查报告
cat .osh/reviews/latest/*.json | head -50
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 2.3.1 | 审查报告含 commit_sha | `jq '.commit_sha' review.json` 非空 | ⬜ |  |
| 2.3.2 | commit_sha 匹配当前 HEAD | `git rev-parse HEAD` → 与审查报告一致 | ⬜ |  |
| 2.3.3 | 审查发现精确到 file:line | `jq '.findings[0].file' review.json` 为源代码路径；`jq '.findings[0].line'` 为整数 | ⬜ |  |
| 2.3.4 | file:line 可定位到代码 | `sed -n '<line>p' <file>` → 确实对应审查发现 | ⬜ |  |
| 2.3.5 | 审查报告含 build_id | `jq '.build_id' review.json` 非空且格式规范 | ⬜ |  |
| 2.3.6 | build_id 可反查构建日志 | `jq -r '.build_id' review.json` → 在 CI 平台可查到对应构建 | ⬜ |  |

### 2.4 SWE.6 合格性测试追溯

```bash
yuleosh test swe6 --report
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 2.4.1 | SWE.6 三段式报告输出 | 含 规范定义 / 测试执行 / 追溯结果 三节 | ⬜ |  |
| 2.4.2 | 测试规范→测试用例可追溯 | 表格含 SWE6-REQ-ID → TEST-ID 映射 | ⬜ |  |
| 2.4.3 | 测试用例→测试结果可追溯 | 每条 TEST-ID 有 pass/fail/n/a 状态 | ⬜ |  |
| 2.4.4 | 未通过项有偏差或修复记录 | fail 项关联偏差 ID 或已修复 | ⬜ |  |

---

## 步骤 3：PA 2.2 MP — 过程测量深度检查

### 3.1 MISRA 违规趋势

```bash
yuleosh misra trend --lines 20
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 3.1.1 | 趋势数据文件存在 | `wc -l .yuleosh/reports/misra-trend.jsonl` ≥ 90 | ⬜ |  |
| 3.1.2 | 趋势输出含方向箭头 | `yuleosh misra trend --lines 5` 最新与上一笔对比有 ↑↓→ | ⬜ |  |
| 3.1.3 | 趋势数据格式规范 | `head -1 .yuleosh/reports/misra-trend.jsonl | python3 -m json.tool` → 合法 JSON | ⬜ |  |
| 3.1.4 | **交叉验证**（审计师核心关注） | | | |
| 3.1.4a | 抽检最近 3 条趋势记录 | 从 JSONL 提取 timestamp + total_violations | ⬜ |  |
| 3.1.4b | 对应 CI 运行日志确认 | CI 日志中该构建的 MISRA 违规数一致 | ⬜ |  |
| 3.1.4c | **抽检第 30 条**：timestamp + total 对齐 | CI 构建时间 + 报告数据匹配 | ⬜ |  |
| 3.1.4d | **抽检第 60 条**：同上 | 匹配 | ⬜ |  |

### 3.2 C 覆盖率趋势

```bash
yuleosh coverage trend --lines 20
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 3.2.1 | 趋势数据文件存在 | `wc -l .yuleosh/reports/coverage-trend.jsonl` ≥ 20 | ⬜ |  |
| 3.2.2 | 趋势字段完整 | 每行含 timestamp, build_id, line_rate, branch_rate, function_rate, total_lines, covered_lines | ⬜ | `head -1 ... | jq keys` 验证 |
| 3.2.3 | 每构建一条记录 | `jq -r '.build_id'` 与 CI 构建次数一致 | ⬜ |  |
| 3.2.4 | 支持 `--days N --json` | `yuleosh coverage trend --days 7 --json` 输出 JSON | ⬜ |  |
| 3.2.5 | 下降 >5% 触发 warning | 注入下降数据 → CI warning | ⬜ | CI 日志 |
| 3.2.6 | **交叉验证**（审计师核心关注） | | | |
| 3.2.6a | 抽检最近 3 条覆盖率记录 | 与对应 CI 构建的 lcov 报告数据一致 | ⬜ |  |
| 3.2.6b | 随机抽检第 5 条 | 覆盖率 % 与 CI artifact 中 coverage-report/index.html 一致 | ⬜ |  |

### 3.3 构建元数据完整性

```bash
yuleosh kpi status
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 3.3.1 | build-metadata.jsonl 存在且非空 | `wc -l .yuleosh/reports/build-metadata.jsonl` ≥ 20 | ⬜ |  |
| 3.3.2 | 字段 schema 完整 | 每条含 8 字段: timestamp, build_id, compiler_version, cppcheck_version, os, python_version, profile, status | ⬜ | `head -1 | jq keys` |
| 3.3.3 | 每 CI run 追加一条 | 对比 CI 平台构建次数与文件行数 | ⬜ |  |
| 3.3.4 | **交叉验证**：工具版本与实际一致 | `cppcheck --version` + `gcc --version` + `python3 --version` 与 JSONL 字段一致 | ⬜ |  |
| 3.3.5 | 按 build_id 可关联全量信息 | `jq 'select(.build_id=="<id>")'` → 可查到构建参数 | ⬜ |  |

### 3.4 过程稳定性 KPI

```bash
yuleosh kpi trend --kpi build_success_rate
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 3.4.1 | 构建成功率 | `yuleosh kpi trend --kpi build_success_rate` 输出表格 | ⬜ |  |
| 3.4.2 | 月成功率 ≥95% | 统计最近 30 天构建状态 | ⬜ |  |
| 3.4.3 | 回归触发率采集 | `jq '.regression_count' kpi-trend.jsonl` 字段存在 | ⬜ |  |
| 3.4.4 | Required 违规 48h 修复率 | deviation 修复时间差统计 ≤48h | ⬜ |  |
| 3.4.5 | KPI 基线 save/list/diff | `yuleosh kpi baseline save` → 新基线文件；`yuleosh kpi baseline list` → 版本历史 | ⬜ |  |
| 3.4.6 | KPI 门禁告警 | 注入连续 3 次超限数据 → CI 告警 | ⬜ | CI 日志 |

### 3.5 过程性能基线

```bash
cat docs/metrics/process-performance-baseline-v1.0.md | head -30
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 3.5.1 | 基线文档存在 | `docs/metrics/process-performance-baseline-v1.0.md` 存在 | ⬜ |  |
| 3.5.2 | 包含各 KPI 均值/P50/P90/UCL/LCL | 文档有统计摘要表 | ⬜ |  |
| 3.5.3 | 包含趋势图/分布直方图 | 文档中有图表 | ⬜ |  |
| 3.5.4 | 数据采集起止时间明确 | 文档含采集范围 | ⬜ |  |
| 3.5.5 | 异常点说明 | 超出控制限的数据点有注释 | ⬜ |  |
| 3.5.6 | Git tag 存在 | `git tag | grep baseline` → baseline-kpi-v1.0 | ⬜ |  |

---

## 步骤 4：PA 2.2 RI — 资源与基础设施检查

### 4.1 工具资格证明

```bash
cat docs/iso26262-tool-qualification.md | head -20
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 4.1.1 | 文档存在 | `ls docs/iso26262-tool-qualification.md` → ✅ | ⬜ |  |
| 4.1.2 | TCL 分类正确 | 文档含 cppcheck→TCL2, clang-tidy→TCL1, AI→TCL1 | ⬜ |  |
| 4.1.3 | TI/TD 评估合理 | 有 Tool Impact 和 Tool Error Detection 评估依据 | ⬜ |  |
| 4.1.4 | ISO 26262-8 §11 逐条对照 | GPG 清单含 10+ 条目逐项检查 | ⬜ |  |
| 4.1.5 | 已知缺陷清单 | 列出 cppcheck 已知缺陷（Essential type, 间接递归等） | ⬜ |  |
| 4.1.6 | 规则覆盖矩阵 | Dir/Required/Advisory 三类自动覆盖率明确 | ⬜ |  |

### 4.2 Agent 审查持久化

```bash
ls .osh/reviews/latest/
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 4.2.1 | 审查 JSON 存在于 `.osh/` | `find .osh/ -name '*.json' | head -5` | ⬜ |  |
| 4.2.2 | 每种审查类型都有输出 | linker / startup / rtos / memory / bsp / build / power 均有 | ⬜ |  |
| 4.2.3 | JSON 格式规范 | `python3 -m json.tool <review.json>` 合法 | ⬜ |  |
| 4.2.4 | JSON 含 build_id 便于追溯 | `jq '.build_id'` 每个文件非空 | ⬜ |  |

### 4.3 工具版本锁定

```bash
cat tools-version.yaml
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 4.3.1 | tools-version.yaml 存在 | 文件存在 | ⬜ |  |
| 4.3.2 | 含所有关键工具 | gcc, cppcheck, lcov, python3, pytest, cmake 等 | ⬜ |  |
| 4.3.3 | 每个工具有版本号 + 校验和 | 版本号非空 + sha256 | ⬜ |  |
| 4.3.4 | 版本与实际运行版本一致 | `gcc --version` vs yaml 中的 gcc 版本 | ⬜ |  |

---

## 步骤 5：CI 集成与门禁实战验证

### 5.1 gcov/lcov 覆盖率门禁

```bash
# 检查 CI 配置
cat .yuleosh/ci-config.yaml | grep -A5 coverage
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 5.1.1 | fail_under_line 配置存在 | ci-config.yaml 中 `coverage.fail_under_line` 非空 | ⬜ |  |
| 5.1.2 | CI 生成 coverage.info + report | `ls .yuleosh/reports/coverage/` → coverage.info + coverage-report/ | ⬜ |  |
| 5.1.3 | **注入低覆盖率测试**：行覆盖 <40% → Pipeline FAILED | 写入低覆盖 C 文件 → 运行 CI → stage=失败 | ⬜ | CI 日志 |
| 5.1.4 | 40% ≤ 行覆盖 <60% → WARNING | 注入中覆盖 → stage=warning | ⬜ | CI 日志 |
| 5.1.5 | general profile 跳过覆盖门禁 | 切换到 general → c-coverage-report 跳过 | ⬜ | CI 日志 |
| 5.1.6 | embedded profile 启用覆盖门禁 | 切换到 embedded → 正常执行 | ⬜ | CI 日志 |
| 5.1.7 | gcov 编译链仅在 embedded 启用 | general 下跳过 -fprofile-arcs | ⬜ |  |

### 5.2 文档同步门禁

```bash
# 检查文档同步配置
cat .yuleosh/ci-config.yaml | grep -A5 sync
```

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 5.2.1 | Schema 文件存在 | `ls docs/__schema__/` → 架构/接口/需求三类 | ⬜ |  |
| 5.2.2 | CI 自动执行 Schema 校验 | CI L2 层含 `code-docs-schema-validate` step | ⬜ | CI 日志 |
| 5.2.3 | 本地 `make docs-validate` | 成功/失败返回 | ⬜ |  |
| 5.2.4 | **注入关键模块代码变更**（文档未更新） | 修改 src/modules/brake_control/ 但 docs/ 不变 → Pipeline FAILED | ⬜ | CI 日志 |
| 5.2.5 | 非关键模块变更 → WARNING | 修改非 critical 路径 → CI WARNING | ⬜ | CI 日志 |
| 5.2.6 | 文档同步经偏差管理可豁免 | 创建有效偏差 → 不阻断 | ⬜ | CI 日志 |

### 5.3 MISRA 门禁

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 5.3.1 | Required 违规阻断 Pipeline | 注入 Required 违规 → stage=failed | ⬜ | CI 日志 |
| 5.3.2 | Advisory 违规不阻断 | Advisory 违规 → stage=warning | ⬜ | CI 日志 |
| 5.3.3 | MISRA delta 生效（仅扫描修改文件） | L1 层 delta 模式 → 仅报告修改文件违规 | ⬜ | CI 日志 |
| 5.3.4 | MISRA 报告 JSON 含 rule/severity/file/line | `jq '.findings[0]'` 字段完整 | ⬜ |  |

### 5.4 Pipeline 依赖链

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 5.4.1 | L1 失败 → 阻断 L2 | 注入 L1 失败 → L2 不执行 | ⬜ | CI 日志 |
| 5.4.2 | L2 失败 → 阻断 L3 | 注入 L2 失败 → L3 不执行 | ⬜ | CI 日志 |
| 5.4.3 | LLM 调用失败 → 阻断 | API 超时 → pipeline 明确报错中断 | ⬜ | CI 日志 |

### 5.5 Profile 切换

| 检查项 | 操作 | 通过标准 | 结果 | 证据 |
|:-------|:-----|:---------|:----:|:-----|
| 5.5.1 | ci-config.yaml 支持 `pipeline.profile` | `load_ci_config().pipeline.profile` 返回有效值 | ⬜ |  |
| 5.5.2 | `yuleosh config profile list` | 输出至少含 general + embedded | ⬜ |  |
| 5.5.3 | **换 profile 运行**：从 general → embedded | Pipeline 步骤增减正确 | ⬜ | CI 日志 |
| 5.5.4 | Profile 完整性校验 | 配置有缺失 → Pipeline 启动校验失败 | ⬜ |  |

---

## 审计发现记录表

| 步骤 | 检查项 | 状态 | 严重度 | 发现描述 | 修复建议 |
|:----:|:------:|:----:|:------:|:---------|:---------|
| | | ⬜ | | | |
| | | ⬜ | | | |
| | | ⬜ | | | |

**严重度定义**:
- 🔴 **Critical**: CL2 核心证据缺失，直接导致不通过（H1~H10 之一）
- 🟡 **Major**: 证据存在但质量不足，需 Sprint C 修复
- 🟢 **Minor**: 非核心项缺失或格式问题

---

## Dry Run 汇总报告

| 维度 | 总检查项 | ✅ 通过 | ❌ 未通过 | 通过率 |
|:-----|:--------:|:------:|:---------:|:------:|
| 证据包完整性（§1） | 11 | ⬜/11 | ⬜/11 | ⬜% |
| PA 2.1 TM 追溯（§2） | 26 | ⬜/26 | ⬜/26 | ⬜% |
| PA 2.2 MP 测量（§3） | 24 | ⬜/24 | ⬜/24 | ⬜% |
| PA 2.2 RI 基础设施（§4） | 11 | ⬜/11 | ⬜/11 | ⬜% |
| CI 门禁实战（§5） | 17 | ⬜/17 | ⬜/17 | ⬜% |
| **总计** | **89** | ⬜/89 | ⬜/89 | ⬜% |

### 通过判定

| 条件 | 判定 |
|:-----|:-----|
| ✅ **通过** | 无 Critical 发现；Major 发现 ≤3 项且有 Sprint C 修复计划 | ⬜ |
| ⚠️ **有条件通过** | 无 Critical 发现；Major 发现 ≤5 项 | ⬜ |
| ❌ **不通过** | 有 Critical 发现；或 Major 发现 >5 项 | ⬜ |

---

*Dry Run 执行后，将本报告的输出摘要汇报给团队，确认是否达到邀请老陈的条件。*
*如果 Dry Run 发现 Critical 项，先修复再邀请。*

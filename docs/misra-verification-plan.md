# MISRA C:2023 验证计划 — CL2 级

> **版本**: 2.0 (CL2 级)
> **升级日期**: 2026-06-18
> **作者**: 小马 🐴（质量架构师）
> **关联文档**: `specs/misra-c2023-spec.md`（Spec 契约层），`specs/misra-acceptance-matrix.md`（验收判定矩阵），`docs/pipeline-optimization-plan.md §CL2 过审路径`
> **ASPICE 映射**: SWE.4 (单元验证), SWE.5 (集成验证), SWE.6 (合格性测试), PA 2.1 (追溯管理), PA 2.2 (过程测量)

---

## 1. 验证范围

### 1.1 适用标准与覆盖

- **适用标准**: MISRA C:2023
- **覆盖规则**: 180 条 (100%)
- **自动检查**: cppcheck + MISRA addon（TCL2 级工具）
- **补充检查**: AI/LLM Agent 审查 + 人工审查（TCL1 级）
- **工具资格**: 详见 `docs/iso26262-tool-qualification.md`

### 1.2 工具链（CL2 级）

| 工具 | 用途 | 执行方式 | 工具分类 | 版本锁定 | 资格证据 |
|:-----|:-----|:---------|:--------|:--------|:---------|
| cppcheck + misra addon | 自动静态分析，自动检测 | CI L1/L2 阶段 | TCL2 | tools-version.yaml 锁定 | ISO 26262-8 §11 TD→TD1 提升策略 |
| AI/LLM Agent Review | 语义级规则检查 + 嵌入式审查 | Pipeline Review L2/L2.5 | TCL1 | tools-version.yaml 锁定 | Agent 审查报告持久化 + 人工复核 |
| gcov/lcov | C 单元测试覆盖率 | L1 c-unit-tests 后 | TCL2 | tools-version.yaml 锁定 | 覆盖率趋势 JSONL ≥90 天 |
| 人工审查 (Peer Review) | 偏差审批、复杂规则确认、Agent 审查结果复核 | 按需 | N/A | N/A | 审查记录持久化 + 审批签名 |

### 1.3 排除项

- 第三方库代码（`lib/`, `vendor/` 目录）— 需在 `ci-config.yaml` 显式声明
- 自动生成的代码（`build/`, `generated/` 目录）— 需在 `ci-config.yaml` 显式声明
- 已通过偏差审批的文件（见 §4 偏差管理流程）
- 排除清单 SHALL 随每个版本重新评估

### 1.4 CL2 级验证活动矩阵

| 验证活动 | 对应 ASPICE | 方法 | 执行者 | 频率 | 输入 | 输出 | 追溯要求 |
|:---------|:-----------:|:-----|:------|:----|:----|:----|:--------|
| V1: MISRA 全量静态分析 | SWE.4 BP1 | cppcheck + misra addon | CI Runner | 每次 Push / Nightly | 全部 .c/.h 源代码 | misra-report.json | REQ-MISRA-xxx → report 关联 |
| V2: MISRA 增量检查 | SWE.4 BP1 | cppcheck --delta | CI Runner | 每次 Commit | git diff HEAD~1 文件 | delta-report.json | 增量违规可追溯到修改 commit |
| V3: C 单元测试 + 覆盖率 | SWE.4 BP2 | Unity/CMock + gcov/lcov | CI Runner | 每次 Push | .c 单元测试 | coverage-report/ | 每个测试用例对应功能需求 |
| V4: 嵌入式审查（Agent） | SWE.5 BP2 | AI/LLM + checklist | Agent | 每次 MR | 链接脚本/启动代码/RTOS/MMIO | agent-review.json | 审查发现→代码行精确定位 |
| V5: 偏差审批 | SWE.5 BP3 | 人工 + CLI | 架构师 | 按需 | 偏差申请 | ci-config.yaml 更新 | 审批链可追溯 |
| V6: SWE.6 合格性测试 | SWE.6 BP1~BP3 | 三段式规范→执行→评估 | CI Runner + QA | Release | 需求基 + 测试规范 | swe6-report.pdf | 需求↔规范↔结果↔偏差 追溯链 |
| V7: 追溯性检查 | PA 2.1 | LRM 工具链 + yuleosh trace matrix | CI Runner | 每次 Push | ALL specs + tests | traceability-matrix.json | 无孤立需求/测试 |
| V8: KPI 趋势分析 | PA 2.2 | misra_trend + coverage_trend | CI Scheduler | Nightly | 历史趋势 JSONL | trend-reports/ | 趋势 ≥90 天可审计 |
| V9: SWE.6 合格性测试执行 | SWE.6 BP2 | 系统级 E2E 测试 (QEMU SIL / HIL) | CI Runner | Release | 合格性测试规范 | execut-result.json | 测试→结果追溯 |
| V10: SWE.6 结果评估与报告 | SWE.6 BP3 | 结构化报告生成 | CI Runner + QA | Release | V6+V9 输出 | final-assessment.pdf | 未通过项→偏差→发布建议 |

## 2. 验证频率（CL2 级）

| 触发条件 | 检查模式 | 负责人 | 数据记录 | 阻断行为 |
|:---------|:---------|:-------|:---------|:---------|
| Commit (pre-commit hook) | 增量 MISRA + 编译 | 开发者 | delta-report.jsonl | Required 新增违规阻断 |
| Push / CI | L1 全量 MISRA + C 测试 + 覆盖率 | CI Runner | misra-report.json + coverage.info + build-metadata.jsonl | Required 违规阻断；覆盖率 < 40% 阻断 |
| MR / PR | L2 Agent 审查 (linker/startup/rtos) + 追溯检查 | CI Runner | agent-review-*.json + traceability-matrix.json | 嵌入式审查 critical 发现阻断；追溯 gap 阻断 |
| Nightly | L2.5 全量 MISRA + MMIO 审查 + 趋势记录 | CI Scheduler | misra-trend.jsonl + coverage-trend.jsonl | 不阻断，但趋势异常告警 |
| Release | 全量 + Zero Required + SWE.6 三段式 | CI Runner + QA | swe6-report + final-assessment + evidence-pack | Required 违规 > 0 阻断；覆盖率 < 60% 阻断 |

### 2.1 增量检查规则（CL2 级）

增量检查仅扫描 Git commit 中变更的 `.c` / `.h` 文件，适用于快速反馈。

- 增量模式下的违规记录标记 `is_delta: true`
- **CL2 新增**: delta 违规计入该文件的违规密度趋势（per-file tracking）
- **CL2 新增**: delta 报告含 `diff_context` 字段，记录违规所在函数/代码块上下文

### 2.2 Release 检查规则（CL2 级）

Release 构建要求：
- **Required 违规: 0**（零容忍）
- Advisory 违规: ≤ 100 条
- 违规密度: ≤ 2.0 violations/KLOC
- **CL2 新增**: 行覆盖率 ≥60%（C 单元测试）
- **CL2 新增**: 追溯矩阵无孤立需求或孤立测试
- **CL2 新增**: SWE.6 合格性测试全部通过（或偏差已批准）

## 3. 角色与职责（CL2 级）

### 3.1 角色矩阵

| 角色 | 职责 | CL2 级新增职责 | 拥有者 | 审批权限 |
|:-----|:-----|:---------------|:-------|:--------|
| 开发者 | 修复自身引入的违规；编写 C 单元测试 | 按追溯要求标记代码中的 REQ-ID；确保覆盖率门禁通过 | 项目所有成员 | N/A |
| 质量架构师 (QA Arch) | 定义验证标准、审批偏差、审查趋势 | 管理 CL2 证据包；维护追溯矩阵完整性；组织 Dry Run | 小马 🐴 | 偏差审批；追溯矩阵确认 |
| 技术架构师 (Tech Arch) | 设计审核 step handler、Agent checklist | 确保 Agent 审查 JSON 报告含 commit SHA + build_id + file:line | 小克 👨‍💻 | 嵌入式审查临界 issue 审批 |
| CI 管理员 | Pipeline 维护 | 维护 tools-version.yaml；确保构建元数据完整 | 小克 👨‍💻 | 工具版本变更审批 |
| QA 审计师 | 最终验证 + 审计准备 | CL2 Dry Run 审计执行；证据包完整性检查 | QA 团队 | 审计报告签署 |
| 项目负责人 | 资源保障 + 合规责任 | CL2 过审最终责任人；偏差超期情况裁决 | 小明 🧑‍💻 | G-31 分歧终审；CL2 过审签署 |

### 3.2 CL2 级开发者工作流

1. 编码：在代码注释中标记 `// REQ-xxx` 实现需求追溯
2. 运行 `yuleosh ci run 1` — L1 增量 MISRA + C 单元测试 + 覆盖率
3. 修复违规，确保覆盖率 ≥40%（commit 级）
4. 推送 → CI 运行 L1 全量 + L2 Agent 审查 + 追溯检查
5. 查看追踪矩阵：`yuleosh traceability matrix`
6. MR 前确认 Required 违规为零 + 无追溯 gap

### 3.3 CL2 级架构师工作流

1. 审批偏差申请（`yuleosh misra deviate`）
2. 审查违规趋势（`show_trend()`）
3. 审查覆盖率趋势（`yuleosh coverage trend`）
4. 审查 Agent 审查报告——确认结果与 commit SHA 可关联
5. 定期审查追溯矩阵完整性——确认无孤立需求或孤立测试
6. 决定规则覆盖/排除策略 + Profile 配置
7. 准备 CL2 证据包：`yuleosh evidence pack`

## 4. 偏差管理流程（CL2 级）

### 4.1 偏差生命周期

```
[创建] → [待审批] → [已批准 / 已拒绝]
                        ↓
              到期后自动失效 → 违规恢复为 unresolved
                        ↓
              可选择重新申请（含影响分析）
```

### 4.2 偏差字段说明（CL2 级新增字段）

| 字段 | 说明 | 示例 | CL2 级 |
|:-----|:-----|:-----|:------|
| **dev_id** | 偏差唯一 ID | `DEV-MISRA-2026-001` | ✅ 唯一编号 |
| **Rule ID** | MISRA 规则标识 | `misra-c2023-17.7` | ✅ |
| **File Pattern** | 应用偏差的文件 glob 模式 | `src/legacy/*.c` | ✅ |
| **Reason** | 申请理由 | "继承代码，计划 Q3 重构" | ✅ |
| **Approved By** | 审批人/角色 | `qa-arch:xiaoma` | ✅ 必须含角色 |
| **Created At** | 创建时间 | `2026-06-18` | ✅ CL2 新增 |
| **Expires** | 到期日期 (ISO 8601) | `2026-09-30` | ✅ 最长 12 个月 |
| **Status** | 状态 | `approved` | ✅ pending/approved/rejected/expired |
| **Risk Assessment** | 风险等级 + 影响说明 | `Low: observable only, no safety impact` | ✅ CL2 新增 |
| **Mitigation Plan** | 缓解计划 | "2026-Q3 重构时移除" | ✅ CL2 新增 |
| **Alm Ticket ID** | ALM 工单关联 | `JIRA-456` | ✅ CL2 新增（ALM 集成后） |

### 4.3 CLI 命令（CL2 级）

```bash
# 列出所有偏差
yuleosh misra deviate list

# 查看偏差详情（CL2: 含完整审计链）
yuleosh misra deviate show DEV-MISRA-2026-001

# 审批偏差
yuleosh misra deviate approve "DEV-MISRA-2026-001" --reason "临时偏差，Q3 闭环"

# 拒绝偏差
yuleosh misra deviate reject "DEV-MISRA-2026-001" --reason "安全关键路径不可用偏差"

# 交互式添加偏差
yuleosh misra deviate add

# 导出偏差清单（CL2: 完整审计格式）
yuleosh misra deviate export --format json > deviation-audit-log.json

# 偏差过期检查（CL2 新增）
yuleosh misra deviate check-expired
```

### 4.4 偏差规则（CL2 级增强）

| 规则 | CL1 | CL2 |
|:-----|:---|:---|
| 到期日期 | ✅ 最长 12 个月 | ✅ 最长 12 个月，到期前 30 天自动提醒 |
| 审批人 | ✅ 架构师 | ✅ 架构师 + QA 双重审批 |
| 到期行为 | 状态恢复为 unresolved | 状态标记 expired → 违规恢复 + 审批链存档 + 通知发起人 |
| 追溯标记 | 标记 acknowledged | 标记 acknowledged + 含 dev_id 关联 + 可审计 |
| 风险等级 | ❌ 无 | ✅ 必须评估 Low/Medium/High + 影响说明 |
| 缓解计划 | ❌ 无 | ✅ 必须有缓解计划 + 目标完成日期 |
| ALM 关联 | ❌ 无 | ✅ 可选但推荐（ALM 集成后强制） |

## 5. KPI 与目标（CL2 级）

### 5.1 量化目标

| KPI | CL1 目标 | **CL2 目标** | 测量方式 | PA 2.2 映射 |
|:----|:---------|:------------|:---------|:-----------|
| Required 违规 | 零容忍（新增即阻断） | **零容忍 + 趋势下降** | 每次 CI 检查 | MP |
| Advisory 违规 | ≤ 100 条 | **≤ 50 条 + 趋势下降 ≥10%/季度** | CI 趋势报表 | MP |
| 违规密度 | ≤ 2.0 violations/KLOC | **≤ 1.5 violations/KLOC** | `get_violations_per_kloc()` | MP |
| 修复时效 (Required) | 48h 内 | **24h 内** 修复或提偏差 | 趋势 + 工时追踪 | MP |
| 修复时效 (Advisory) | 无要求 | **15 天内** | 趋势 + 工时追踪 | MP |
| C 行覆盖率 | 无要求 | **≥60%**（Release）/ ≥40%（Commit） | gcov/lcov | MP |
| 追溯完整性 | 无要求 | **无孤立需求 + 无孤立测试** | `yuleosh trace matrix` | TM |
| 偏差到期率 | 无要求 | **到期前 30d 处理率 ≥90%** | `deviate check-expired` | MP |
| 构建成功率 | 无要求 | **≥95%** | build-metadata.jsonl | MP |
| 缺陷逃逸率 | 无要求 | **≤5%** | 审查→生产对比 | MP |

### 5.2 阻断规则（CL2 级）

以下任一条件满足时 CI 阶段标记为 FAILED：

**必阻断**（强制）：
1. Required 违规且 `fail_on_violation=true`（默认）
2. 总违规数 ≥ `fail_threshold`（默认 10）
3. 违规密度 > 1.5 violations/KLOC（CL2 缩紧）
4. **CL2 新增**: C 行覆盖率 < 40%（Commit）/ < 60%（Release）
5. **CL2 新增**: 追溯矩阵中存在孤立需求（有 REQ-xxx 但无对应 TEST-xxx）
6. **CL2 新增**: 偏差已过期但违规仍在代码中

**可选阻断**（配置文件控制）：
7. Advisory 违规且 `fail_on_advisory=true`
8. **CL2 新增**: 追溯矩阵中存在孤立测试（有 TEST-xxx 但无对应 REQ-xxx）
9. **CL2 新增**: Agent 审查发现 critical 级别问题且 `fail_on_critical=true`

### 5.3 趋势报告（CL2 级）

每次 MISRA 检查自动记录趋势数据到 `.yuleosh/reports/misra-trend.jsonl`：

```json
{
  "timestamp": "2026-06-18T17:25:00",
  "total_violations": 5,
  "required": 3,
  "advisory": 2,
  "files_checked": 12,
  "is_delta": false,
  "commit": "abc1234",
  "violations_per_kloc": 0.8,
  "coverage_pct": 72.3,
  "build_id": "build-20260618-001"
}
```

**CL2 新增趋势指标**:
- `violations_per_kloc`: 违规密度 per 趋势条目
- `coverage_pct`: C 单元测试行覆盖率 per 构建
- `build_id`: 与 build-metadata.jsonl 关联键

通过 `show_trend()` 查看最近 N 次趋势的 Markdown 表格：

```python
from yuleosh.ci.misra_trend import show_trend
print(show_trend("/path/to/project", lines=30))
```

**CL2 新增**: 趋势 CLI 命令

```bash
# 查看 MISRA 趋势
yuleosh misra trend --lines 20 --format markdown

# 查看覆盖率趋势
yuleosh coverage trend --days 90 --format json

# 综合健康仪表盘
yuleosh dashboard health
```

## 6. 追溯管理（PA 2.1）

### 6.1 追溯矩阵结构

追溯矩阵是三列结构，覆盖从需求到实现到测试的完整链条：

| REQ-ID | 需求描述 | IMPL-ID | 实现位置 | TEST-ID | 测试位置 | 状态 |
|:-------|:---------|:--------|:---------|:--------|:---------|:----|
| REQ-MISRA-001 | MISRA Required 规则零容忍 | IMPL-CI-001 | ci-config.yaml misra.fail_on_violation | TEST-MISRA-001 | tests/test_ci_layers.py | ✅ |
| REQ-MISRA-002 | C 单元测试覆盖率 ≥60% | IMPL-CUT-001 | build/build-c-units.sh gcov | TEST-CUT-001 | tests/test_coverage.py | 🏗️ |

### 6.2 追溯性检查步骤

Pipeline L2 层包含 `code-traceability-check` step handler：

1. **输入**: specs/*.md (SHALL 语句)、src/ (代码)、tests/ (测试)
2. **处理**:
   - 从 spec 文件中提取所有 `SHALL` 语句 → 生成 REQ-ID 列表
   - 从代码注释中提取 `// REQ-xxx` 标记 → 生成 IMPL-ID 映射
   - 从测试文件中提取 `test_*` 函数 → 生成 TEST-ID 列表
3. **输出**:
   - traceability-matrix.json（完整追溯矩阵）
   - gap-report.json（孤立需求 + 孤立测试 + 未标记代码）
4. **阻断**: 存在孤立需求（有 REQ-xxx 但无对应 TEST-xxx）→ FAILED

### 6.3 追溯维护责任

| 责任 | 执行者 | 频率 |
|:-----|:-------|:----|
| Spec 中 SHALL 语句标记 REQ-ID | 小明 🧑‍💻 | 需求变更时 |
| 代码中标注 REQ-ID 注释 | 小克 👨‍💻 | 实现时 |
| 测试用例标注 REQ-ID | 小克 👨‍💻 | 编写测试时 |
| 追溯矩阵自动化检查 | CI Runner | 每次 Push |
| 追溯矩阵完整性审查 | 小马 🐴 | 每次 Release |
| 跨 Sprint 追溯一致性 | 小马 🐴 | Sprints 交替点 |

## 7. 过程测量与证据（PA 2.2）

### 7.1 构建元数据

每次构建自动记录到 `.yuleosh/reports/build-metadata.jsonl`：

```json
{
  "timestamp": "2026-06-18T17:25:00",
  "build_id": "build-20260618-001",
  "status": "success",
  "profile": "embedded",
  "compiler_version": "GCC 12.2.1",
  "cppcheck_version": "2.13.0",
  "os": "Ubuntu 22.04",
  "python_version": "3.10.12",
  "total_violations": 5,
  "required": 3,
  "advisory": 2,
  "coverage_pct": 72.3,
  "traceability_gaps": 0
}
```

### 7.2 证据包结构

Release 构建自动生成 CL2 证据包：

```
CL2-EVIDENCE-PACK/
├── PA2.1-TM/
│   ├── traceability-matrix-latest.json
│   └── traceability-gap-report.json
├── PA2.2-MP/
│   ├── misra-trend.jsonl
│   ├── coverage-trend.jsonl
│   ├── build-metadata.jsonl
│   └── kpi-summary.json
├── PA2.2-RI/
│   ├── iso26262-tool-qualification.md
│   └── tools-version.yaml
└── evidence-manifest.json
```

### 7.3 证据 CLI

```bash
# 打包证据
$ yuleosh evidence pack --output ./evidence-pack

# 检查证据完整性
$ yuleosh evidence check --pack ./evidence-pack
[✔] PA2.1-TM/traceability-matrix-latest.json — OK
[✔] PA2.2-MP/misra-trend.jsonl — OK (92 entries)
[✘] PA2.2-MP/coverage-trend.jsonl — MISSING

# 生成 KPI 月报
$ yuleosh evidence kpi --month 2026-06
```

## 9. gcov/lcov 覆盖度度量（SWE.4 增强）

> **对应 CL2 审计项**: CL2-E01 ~ CL2-E04
> **ASPICE 映射**: SWE.4 BP2（单元验证 - 覆盖度量）
> **来源要求**: 老陈 CL2 审计报告 — gcov/lcov 覆盖度量为 CL2 核心缺口

### 9.1 编译链集成 (CL2-E01)

#### 9.1.1 CMake 构建集成

gcov 覆盖率通过 CMake 构建配置实现，与 Debug/Release 构建类型分离：

```cmake
# CMakeLists.txt — 覆盖率构建配置
set(CMAKE_C_FLAGS_COVERAGE
    "${CMAKE_C_FLAGS_DEBUG} -fprofile-arcs -ftest-coverage")
set(CMAKE_EXE_LINKER_FLAGS_COVERAGE
    "${CMAKE_EXE_LINKER_FLAGS_DEBUG} -fprofile-arcs -ftest-coverage")
```

- Debug 配置启用覆盖率跟踪：`cmake -DCMAKE_BUILD_TYPE=Coverage`
- Release 配置不携带覆盖率选项，无性能开销
- 要求 gcc ≥ 9.0，确保 gcov 工具可用

#### 9.1.2 构建产物与.gitignore

| 构建产物 | 说明 | 版本控制 |
|:---------|:-----|:---------|
| `*.gcda` | 覆盖率运行时数据（每次运行累加） | ❌ `.gitignore` 排除 |
| `*.gcno` | 覆盖率编译时数据（链接信息） | ❌ `.gitignore` 排除 |
| `*.gcov` | gcov 文本输出（逐行覆盖标记） | ❌ `.gitignore` 排除 |
| `coverage.info` | lcov 聚合报告 | ❌ `.gitignore` 排除 |
| `coverage_report/` | genhtml HTML 报告 | ❌ `.gitignore` 排除 |

#### 9.1.3 验收标准

1. `cmake -DCMAKE_BUILD_TYPE=Coverage` 成功生成含覆盖信息的二进制
2. 运行单元测试后在 `build/` 下可找到每个编译单元的 .gcda/.gcno 文件
3. `gcov <source.c>` 能正确输出 .gcov 逐行覆盖文件

---

### 9.2 lcov + genhtml 报告流水线 (CL2-E02)

#### 9.2.1 CI 脚本流程

```bash
# 1. 从 build/ 捕获原始覆盖率数据
lcov --capture --directory build/ \
     --output-file coverage.info \
     --rc lcov_branch_coverage=1

# 2. 过滤外部代码（系统库、测试框架、第三方）
lcov --remove coverage.info \
     '/usr/*' '/opt/*' '*/test/*' '*/googletest/*' \
     -o coverage_filtered.info

# 3. 生成 HTML 报告
genhtml coverage_filtered.info \
       --output-directory coverage_report/ \
       --title "yuleOSH Coverage Report"

# 4. 发布为 CI Artifact
# (GitLab: artifacts, GitHub: upload-artifact)
```

#### 9.2.2 报告内容

| 覆盖维度 | 测量方式 | CI 展示 |
|:---------|:---------|:--------|
| 行覆盖率 (Line) | `lcov --summary` | 报告首页 + CI 徽章 |
| 函数覆盖率 (Function) | `lcov --summary` | 报告逐文件 |
| 分支覆盖率 (Branch) | `--rc lcov_branch_coverage=1` | 报告逐函数 |

#### 9.2.3 验收标准

1. 每次 CI Push/MR 运行后生成可浏览的 `index.html` 覆盖率报告
2. 报告中包含行覆盖率、函数覆盖率、分支覆盖率三项指标
3. 报告可下载或在 CI 页面直接打开

---

### 9.3 覆盖阈值门禁（fail_under）(CL2-E03)

#### 9.3.1 阈值定义

| CI 阶段 | 行覆盖率阈值 | 阻断行为 |
|:--------|:------------|:---------|
| Commit / Push | ≥ 40% | 低于阈值 → CI FAILED（阻断） |
| Release | ≥ 60% | 低于阈值 → CI FAILED（阻断） |
| 长期目标 | ≥ 80% | 逐步收紧 |

#### 9.3.2 门禁实现

```bash
# CI 脚本 — 覆盖率阈值检查
lcov --summary coverage_filtered.info > coverage_summary.txt
LINE_COV=$(grep 'lines' coverage_summary.txt \
           | awk '{print $2}' | cut -d'%' -f1 | cut -d'.' -f1)

if [ "$LINE_COV" -lt "${FAIL_UNDER:-60}" ]; then
  echo "❌ FAIL: Line coverage ${LINE_COV}% < ${FAIL_UNDER}%"
  exit 1
else
  echo "✅ PASS: Line coverage ${LINE_COV}% ≥ ${FAIL_UNDER}%"
fi
```

阈值通过环境变量 `FAIL_UNDER` 配置，默认 60%（Release 级），Commit 级 CI 可传 `FAIL_UNDER=40`。

#### 9.3.3 豁免机制

覆盖率门禁可通过偏差管理系统豁免（参见 §4 偏差管理流程）：

- 适用场景：紧急修复、代码重构期间过渡
- 额外要求：偏差必须含 `risk_assessment` 和 `mitigation_plan`
- 到期行为：偏差到期后门禁恢复生效

#### 9.3.4 验收标准

1. 覆盖率低于阈值时 CI pipeline 红色失败，MR 无法合入
2. 覆盖率达标时绿色通过
3. 豁免（偏差）记录在 Git 中，完整可审计

---

### 9.4 覆盖趋势追踪与基线 (CL2-E04)

#### 9.4.1 趋势数据采集

每次 CI 运行后自动记录覆盖率摘要到 `.yuleosh/reports/coverage-trend.jsonl`：

```json
{
  "timestamp": "2026-06-18T17:25:00",
  "build_id": "build-20260618-001",
  "line_cov_pct": 72.3,
  "function_cov_pct": 85.1,
  "branch_cov_pct": 65.8,
  "commit": "abc1234"
}
```

#### 9.4.2 回归告警

- 单次覆盖率下降 > 5%（相对前一次）→ CI WARNING（不阻断）
- 连续 3 次下降 → Nightly 告警通知

#### 9.4.3 基线发布

| 阶段 | 操作 | 输出 |
|:-----|:-----|:-----|
| 首次采集 | 从现有 CI 提取 KPI | `baseline-v0.1.json`（快照） |
| 4 周积累 | 每日采集，≥20 个有效数据点 | `metrics/` 历史序列 |
| 基线发布 | 统计分析（均值/P50/P90/UCL/LCL） | `docs/metrics/process-performance-baseline-v1.0.md` |
| 持续监控 | 每周自动对比最新数据与基线 | 超限告警 |

#### 9.4.4 CLI 命令

```bash
# 查看覆盖率趋势
$ yuleosh coverage trend --days 90 --format json

# 查看覆盖率基线
$ yuleosh coverage baseline show

# 发布基线
$ yuleosh coverage baseline publish --version v1.0
```

#### 9.4.5 验收标准

1. 至少保存最近 4 周（≥20 个数据点）的历史覆盖率数据
2. 可查看折线趋势图
3. 单次下降 > 5% 时 CI 输出 warning
4. 基线对比记录可追溯

---

## 10. 文档同步门禁流程

> **对应 CL2 审计项**: CL2-E05 ~ CL2-E07
> **ASPICE 映射**: SWE.4 BP2（验证活动输入一致性）、PA 2.1（追溯管理）
> **来源要求**: 老陈 CL2 审计报告 — 文档与代码脱钩为 CL2 关键缺口

### 10.1 文档 YAML Schema 校验 (CL2-E05)

#### 10.1.1 受管文档类型

| 文档类型 | 存放路径 | Schema 文件 | 校验要求 |
|:---------|:---------|:------------|:---------|
| 架构文档 | `docs/architecture/*.yaml` | `docs/__schema__/architecture.schema.yaml` | 模块名、版本号、最后更新日期、对应代码路径 |
| 接口文档 | `docs/interfaces/*.yaml` | `docs/__schema__/interface.schema.yaml` | 接口名、参数列表、返回值、变更记录 |
| 需求文档 | `specs/*.md` | `docs/__schema__/requirement.schema.yaml` | 需求 ID、描述、状态、关联代码模块 |

#### 10.1.2 Schema 校验流程

```bash
# 本地校验
$ make docs-validate
# → 运行 yamllint + schema 校验
# → 输出校验结果（通过/错误行号+字段名+预期格式）

# CI 自动校验（L2 层）
# → code-docs-schema-validate step handler
# → 耗时 < 10s
# → 失败时输出详细校验错误
```

#### 10.1.3 验收标准

1. 所有受管文档通过 YAML Schema 验证无报错
2. Schema 验证在 CI 中自动运行，耗时 < 10s
3. 文档作者可在本地运行 `make docs-validate` 提前验证

---

### 10.2 代码-文档映射表 (CL2-E06)

#### 10.2.1 映射表定义

映射表存储在 `scripts/docs_map.yaml`，定义代码路径到文档路径的关联关系：

```yaml
# scripts/docs_map.yaml
mappings:
  - code_path: "src/modules/brake_control/"
    doc_paths:
      - "docs/architecture/brake_control.yaml"
      - "docs/interfaces/brake_if.yaml"
    critical: true        # 关键模块 → 文档未更新则硬阻塞
  - code_path: "src/modules/sensor_fusion/"
    doc_paths:
      - "docs/architecture/sensor_fusion.yaml"
    critical: false       # 非关键模块 → 仅 warning
  - code_path: "src/hal/"
    doc_paths:
      - "docs/architecture/hal_layer.yaml"
    critical: true
```

#### 10.2.2 映射表维护责任

| 责任 | 执行者 | 频率 |
|:-----|:-------|:-----|
| 新增模块时创建/更新映射 | 小克 👨‍💻（开发者） | 模块创建时 |
| 映射表完整性审查 | 小马 🐴（质量架构师） | Sprint 交替点 |
| 映射表 schema 版本管理 | CI Pipeline | 自动 |

---

### 10.3 MR 阻断规则 (CL2-E06)

#### 10.3.1 检查流程

```
[MR 创建/更新] → 提取 MR 变更文件列表（src/ 下）
                ↓
        查找 docs_map.yaml 匹配的模块
                ↓
        检查对应文档是否在 MR 变更列表中
                ↓
      ┌────────┴────────┐
      ↓                 ↓
 文档已变更         文档未变更
      ↓                 ↓
    ✅ PASS      ┌──────┴──────┐
                 ↓              ↓
             critical=true   critical=false
                 ↓              ↓
            ❌ FAIL         ⚠️ WARNING
                 ↓              ↓
            MR 无法合入     MR 可合入 + 自动评论提醒
```

#### 10.3.2 阻断规则

| 场景 | 阻断等级 | CI 状态 | 操作 |
|:-----|:---------|:--------|:-----|
| 关键模块代码变更 + 文档未更新 | 硬阻断 | FAILED | MR 阻塞 |
| 非关键模块代码变更 + 文档未更新 | 软阻断 | WARNING | 自动评论 + 提醒 |
| 有有效豁免偏差 | 不阻断 | SUCCESS | 偏差 ID 记录到 CI 日志 |
| 文档同步 + Schema 校验通过 | 通过 | SUCCESS | 正常合并 |

#### 10.3.3 验收标准

1. 关键模块代码变更但文档未更新时，MR 无法合入
2. 非关键模块代码变更但文档未更新时，MR 可合入但留下提醒记录
3. 豁免机制可绕过门禁并留下审计跟踪

---

### 10.4 文档差异自动检测 (CL2-E07)

#### 10.4.1 代码-文档指纹对比

对每个公共 API / 接口函数生成"代码指纹"（函数签名 + 参数 + 返回值类型），同时在文档中记录对应的"文档指纹"（接口名 + 参数描述 + 返回值描述）：

| 指纹类型 | 来源 | 内容 | 用途 |
|:---------|:-----|:-----|:-----|
| 代码指纹 | `src/` 头文件解析 | 函数签名、参数列表、返回值类型 | 对比文档是否过时 |
| 文档指纹 | `docs/interfaces/` YAML | 接口名、参数描述、返回值描述 | 对比代码是否缺文档 |

#### 10.4.2 CI 差异检测

```bash
# CI 脚本 — 文档差异检测
generate_code_fingerprints()    # 从头文件提取函数签名
generate_doc_fingerprints()     # 从文档中提取接口描述
compare_fingerprints()          # 对比差异

# 输出差异报告
# - 新增但文档未记录的 API → WARNING
# - 删除但文档仍保留的 API → WARNING
# - 签名已修改但文档未更新 → WARNING
```

差异报告自动评论在 MR 中，@对应文档负责人。

#### 10.4.3 验收标准

1. 每次 MR 自动执行指纹对比，15s 内完成
2. 差异报告可读性强，指出具体行号和差异内容
3. 每周自动汇总未解决差异项发送给项目组长

---

## 11. 附录

### 11.1 配置参考（CL2 级）

```yaml
misra:
  enabled: true
  fail_on_violation: true
  fail_on_advisory: false
  fail_threshold: 10
  violations_per_kloc: 1.5  # CL2 收紧

pipeline:
  profile: embedded  # general | embedded | automotive

traceability:
  enabled: true
  fail_on_gap: true  # CL2: 追溯到 gap 则阻断
  require_req_tags: true  # CL2: 代码必须标注 REQ-ID

coverage:
  c_threshold_commit: 40  # % CL2: commit 级门禁
  c_threshold_release: 60 # % CL2: release 级门禁
  trend_days: 90           # CL2: 趋势 90 天
  fail_under: 60           # CL2-E03: 覆盖阈值门禁
  branch_coverage: true    # CL2-E02: 分支覆盖统计

docs_sync:
  enabled: true            # CL2-E05: 文档同步门禁
  schema_path: "docs/__schema__/"
  mapping_file: "scripts/docs_map.yaml"
  fail_on_critical: true   # CL2-E06: 关键模块硬阻断
  fingerprint_check: true  # CL2-E07: 指纹差异检测

tools:
  lockfile: tools-version.yaml

cl2_evidence:
  enabled: true
  auto_pack: true  # Release 构建自动打包证据
  pack_dir: CL2-EVIDENCE-PACK
```

### 11.2 CL1 → CL2 升级检查清单

| # | 升级项 | CL1 | CL2 | 状态 |
|:-:|:-------|:---|:---|:----|
| 1 | 增量 MISRA 检查 | delta 报告 | delta + per-file 趋势 | 🏗️ |
| 2 | C 单元测试 | 框架存在+基础运行 | gcov/lcov 覆盖率 ≥60% + 趋势 | 🏗️ G-45 / CL2-E01~E04 |
| 3 | 嵌入式审查 | Agent 审查存在 | Agent 审查 JSON + commit SHA + build_id + file:line | 🏗️ G-47 |
| 4 | SWE.6 合格性测试 | 1 步 final-report | 三段式：规范→执行→评估 | 🏗️ G-31 |
| 5 | 追溯矩阵 | 无 | 自动化 L2 step handler + 三列矩阵 + 阻断 gap | 🏗️ G-46 |
| 6 | 偏差管理 | 基础 CLI | 风险等级+缓解计划+ALM 关联+过期提醒 | 🏗️ |
| 7 | 构建元数据 | 无 | build-metadata.jsonl + 字段完整性 | 🏗️ G-48 |
| 8 | 过程稳定性 KPI | 无 | 成功率+回归率+逃逸率+修复时效 | 🏗️ G-49 |
| 9 | 证据包 | 无 | CLI 打包+完整性校验+Dry Run | 🏗️ G-50 |
| 10 | 工具资格 | TCL/TI/TD 文档 | 版本锁定+变更审批 | 🏗️ G-48 |
| 11 | Dashboard 可视化 | 无 | 趋势图表+追溯矩阵+偏差状态 | 🗓️ |
| 12 | **gcov 覆盖度量** (新增) | 无 | CMake 集成 + lcov 报告 + fail_under + 趋势基线 | 🏗️ CL2-E01~E04 |
| 13 | **文档同步门禁** (新增) | 无 | Schema 校验 + 代码-文档映射 + MR 阻断 + 指纹检测 | 🏗️ CL2-E05~E07 |

### 11.3 相关文档

- [MISRA C:2023 官方标准](https://www.misra.org.uk)
- [cppcheck MISRA Addon 文档](https://cppcheck.sourceforge.io)
- [MISRA C:2023 Spec 契约层](/specs/misra-c2023-spec.md)
- [MISRA 验收判定矩阵](/specs/misra-acceptance-matrix.md)
- [Pipeline 优化计划 + CL2 过审路径](/docs/pipeline-optimization-plan.md)
- [ISO 26262 工具资格认证](/docs/iso26262-tool-qualification.md)
- [CL2 审计计划](/reports/cl2-audit-plan.md)

---

*生成日期: 2026-06-18 (CL2 级 v2.1)*
*由 yuleOSH CI 框架管理 | 质量架构师: 小马 🐴*



# RTM 追溯矩阵 CI 门禁集成规范

> **版本**: v1.0.0 | **状态**: DRAFT  
> **维护人**: 小马 🐴 (质量架构师)  
> **规范依据**: `docs/rtm-spec.md` (v1.0.0) / ASPICE SWE.4 / ISO 26262-8 §8  
> **最后更新**: 2026-06-14

---

## 1. 概述

### 1.1 目的

本文档定义 **RTM（Requirements Traceability Matrix，需求追溯矩阵）** 在 CI pipeline 中的自动验证方案。核心目标：

1. **自动验证**每个 `SHALL`/`SHOULD` 需求有对应的可执行测试用例。
2. **PR 合并门禁**：合入前 SHALL 追溯覆盖率 ≥ **90%**。
3. **与现有 pytest + coverage 工具链无缝集成**，最小化额外依赖。

### 1.2 前置依赖

本文档的完整实现依赖于：

| 依赖 | 文档/位置 | 状态 |
|:----|:----------|:----|
| RTM 字段定义与映射规则 | `docs/rtm-spec.md` §2-§3 | ✅ APPROVED |
| 测试需求标记方式 | `docs/rtm-spec.md` §3.2 | ✅ APPROVED |
| CI 门禁通用阶梯 | `docs/ci-coverage-gateway.md` | 🔄 本文档配套 |
| 行覆盖率阶梯计划 | `docs/ci-coverage-gateway.md` §2 | 🔄 本文档配套 |
| 测试准入基线 | `docs/test-coverage-standards.md` | ✅ APPROVED |

### 1.3 术语定义

| 术语 | 定义 |
|:----|:-----|
| **SHALL Trace Coverage** | 有 ≥1 个已验证测试用例的 SHALL 数量 / 总 SHALL 数量 × 100% |
| **Rogue Test** | 未关联任何需求的测试用例 |
| **Traceability Lock** | CI 门禁阶段，检查 SHALL 追溯覆盖率是否 ≥ 阈值 |
| **RTM Snapshot** | 每次 CI 运行生成的 RTM 数据快照，固化到 `artifacts/rtm/` |
| **Fully Traced** | SHALL 同时满足正向追溯（需求→测试）和反向追溯（测试→需求） |
| **Gap Set** | 当前未被任何测试覆盖的 SHALL 需求集合 |

---

## 2. 门禁规则定义

### 2.1 门禁等级与阈值

| 门禁指标 | SHALL 阈值 | SHOULD 阈值 | 行为 |
|:---------|:----------:|:-----------:|:-----|
| **PR 合并门禁** | **≥90%** | ≥50% | 未达标 **阻塞** PR |
| **Release 门禁** | ≥95% | ≥70% | 未达标禁用 Release |
| **审计门禁** | **100%** | ≥80% | 例外需明确豁免记录 |
| **Rogue Test** | 0 个 rogue | — | 阻塞，禁止无追溯测试 |
| **Fully Traced** | ≥80% | — | 非阻塞质量指标 |
| **Deep Coverage** | ≥30% | — | 非阻塞质量指标 |

### 2.2 门禁规则

| # | 规则 | 强制等级 |
|:--|:-----|:--------:|
| **RTM-CI-01** | CI SHALL 在 Layer 1（单元测试）之后、Layer 2（集成测试）之前执行 RTM 验证 | SHALL |
| **RTM-CI-02** | PR 合入前 SHALL 追溯覆盖率 SHALL ≥ 90% | SHALL |
| **RTM-CI-03** | Release 前 SHALL 追溯覆盖率 SHALL ≥ 95% | SHALL |
| **RTM-CI-04** | 新增 SHALL SHALL 100% 有对应测试（PR 新增需求） | SHALL |
| **RTM-CI-05** | 每个测试用例 SHOULD 关联至少一个需求 ID | SHOULD |
| **RTM-CI-06** | Rogue 测试（无任何需求关联）SHALL 被检测并标记为警告 | SHALL |
| **RTM-CI-07** | 门禁失败时 CI SHALL 输出详细 Gap 报告（未覆盖 SHALL 列表） | SHALL |
| **RTM-CI-08** | RTM 门禁 SHOULD 作为 Check Run 在 PR 页面显示状态 | SHOULD |
| **RTM-CI-09** | 门禁例外（豁免）SHALL 记录在 `docs/rtm-exceptions.md` | SHALL |
| **RTM-CI-10** | RTM 验证结果 SHALL 归档到 `artifacts/rtm/` 目录 | SHALL |

### 2.3 测试标记格式要求

所有测试文件 SHALL 采用以下方式标记其覆盖的需求 ID：

**方式 A：测试函数命名（推荐）**
```python
# 文件名: test_rs_001_pipeline.py
# 函数名格式: test_{req_id_lower}_{description}
def test_rs_001_ddd_spec_generation():
    """RS-001: DDD→SDD pipeline generates target spec"""
    ...
```

**方式 B：pytest marker（多需求关联）**
```python
@pytest.mark.req("RS-002")
@pytest.mark.req("SWR-002.1")
def test_parse_basic_spec():
    """RS-002/SWR-002.1: OpenSpec format parsing"""
    ...
```

**方式 C：文档字符串（函数名不清楚时）**
```python
def test_i2c_init():
    """SWR-008.2: SHALL support HAL mocking for I2C (master read/write)"""
    ...
```

**GIVEN** 一个测试函数使用方式 A 的命名约定
**WHEN** RTM 引擎扫描该文件
**THEN** 它 SHALL 自动提取函数名中的 `req_id` 映射

**GIVEN** 一个测试函数使用方式 B 的 `@pytest.mark.req("RS-XXX")`
**WHEN** pytest 收集测试项
**THEN** RTM 引擎 SHALL 读取 `item._req_ids` 属性完成映射

---

## 3. 与 pytest + coverage 工具链集成方案

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CI Pipeline (GitHub Actions)                     │
├─────────────────────────────────────────────────────────────────────────┤
│  Stage 1: Lint + Type Check                                              │
│  Stage 2: Smoke Tests                                                    │
│  Stage 3: Layer 1 — Unit Tests + Coverage                                │
│    ├─ pytest --cov=yuleosh --cov-fail-under=60                          │
│    └─ ← 产生: artifacts/coverage/coverage.json                          │
│  Stage 4: RTM Verification (新增) ★                                      │
│    ├─ yuleosh rtm scan → tests/*.py → 提取 req_id 标记                  │
│    ├─ yuleosh rtm trace → docs/spec.md ↔ tests/*.py → RTM 矩阵          │
│    ├─ yuleosh rtm verify → SHALL覆盖率 ≥90% → PASS/FAIL                 │
│    └─ ← 产生: artifacts/rtm/rtm-{commit}.json                           │
│  Stage 5: Layer 2 — Cross-Compile + SIL                                  │
│  Stage 6: Layer 2.5 — HIL (mock mode)                                    │
│  Stage 7: Layer 3 — System Test + Evidence Pack                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 RTM 扫描引擎

RTM 扫描引擎 SHALL 实现以下三个核心步骤：

#### 步骤 1：需求提取 (`yuleosh rtm scan-spec`)

```python
# src/yuleosh/rtm/scanner.py (设计)
import re
from pathlib import Path

class SpecScanner:
    """扫描 docs/spec.md 提取所有 SHALL/SHOULD/MAY 语句。"""
    
    REQ_PATTERN = re.compile(
        r'(?P<req_id>(?:RS|SWR|FEATURE)[-]\d+(?:\.\d+)?):\s*'
        r'(?P<req_type>SHALL|SHOULD|MAY)\s+'
        r'(?P<shall_text>.+?)(?=(?:\n(?:RS|SWR|FEATURE)[-]\d+:)|\Z)',
        re.DOTALL
    )
    
    def scan(self, spec_path: str = "docs/spec.md") -> list[Requirement]:
        requirements = []
        content = Path(spec_path).read_text(encoding="utf-8")
        for match in self.REQ_PATTERN.finditer(content):
            req = Requirement(
                req_id=match.group("req_id"),
                req_type=match.group("req_type"),
                shall_text=match.group("shall_text").strip(),
            )
            requirements.append(req)
        return requirements
```

#### 步骤 2：测试映射 (`yuleosh rtm scan-tests`)

```python
class TestScanner:
    """扫描 tests/ 目录，提取每个测试函数的 req_id 映射。"""
    
    METHODS = [
        "name_marker",    # 函数名含 req_id: test_rs_001_xxx
        "pytest_marker",  # @pytest.mark.req("RS-XXX")
        "docstring",      # 文档字符串含 "RS-XXX:" / "SWR-XXX.Y:"
    ]
    
    def scan(self, test_dir: str = "tests/") -> list[TestMapping]:
        mappings = []
        for py_file in Path(test_dir).rglob("test_*.py"):
            # 收集 pytest 标记信息
            ...
        return mappings
```

#### 步骤 3：门禁验证 (`yuleosh rtm verify`)

```python
class GateVerifier:
    """验证 RTM 覆盖率是否达到门禁阈值。"""
    
    def verify(
        self,
        rtm: RTMReport,
        shall_threshold: float = 90.0,
        should_threshold: float = 50.0,
        fail_on_rogue: bool = True,
    ) -> GateResult:
        violations = []
        
        # 1. 检查 SHALL 覆盖率
        for req in rtm.shalls:
            if req.coverage_count == 0:
                violations.append(Violation(
                    req_id=req.req_id,
                    severity="ERROR",
                    message=f"No test covers {req.req_id}"
                ))
        
        shall_coverage = rtm.shalls_covered / rtm.shalls_total * 100
        if shall_coverage < shall_threshold:
            violations.append(Violation(
                severity="ERROR",
                message=f"SHALL coverage {shall_coverage:.1f}% < {shall_threshold}%"
            ))
        
        # 2. 检查 Rogue 测试
        if fail_on_rogue and rtm.rogue_tests:
            violations.append(...)
        
        # 3. 检查 SHOULD 覆盖率（非阻塞）
        ...
        
        passed = len([v for v in violations if v.severity == "ERROR"]) == 0
        return GateResult(passed=passed, violations=violations, metrics=rtm.metrics)
```

### 3.3 CI 脚本实现

```bash
#!/bin/bash
# ci/rtm-verify.sh — RTM CI 门禁验证

set -euo pipefail

SPEC_FILE="${1:-docs/spec.md}"
TEST_DIR="${2:-tests/}"
SHALL_THRESHOLD="${3:-90}"
SHOULD_THRESHOLD="${4:-50}"
OUTPUT_DIR="artifacts/rtm"

mkdir -p "${OUTPUT_DIR}"

echo "=== yuleOSH RTM Verification ==="
echo "Spec:       ${SPEC_FILE}"
echo "Tests:      ${TEST_DIR}"
echo "SHALL ≥:    ${SHALL_THRESHOLD}%"
echo "SHOULD ≥:   ${SHOULD_THRESHOLD}%"
echo ""

# Step 1: 扫描 spec 中的需求
echo "[1/4] Scanning requirements from spec..."
yuleosh rtm scan-spec \
    --spec "${SPEC_FILE}" \
    --output "${OUTPUT_DIR}/requirements.json"

# Step 2: 扫描测试关联
echo "[2/4] Scanning test mappings..."
yuleosh rtm scan-tests \
    --test-dir "${TEST_DIR}" \
    --output "${OUTPUT_DIR}/test-mappings.json"

# Step 3: 建立 RTM 矩阵
echo "[3/4] Building traceability matrix..."
yuleosh rtm trace \
    --requirements "${OUTPUT_DIR}/requirements.json" \
    --test-mappings "${OUTPUT_DIR}/test-mappings.json" \
    --output "${OUTPUT_DIR}/rtm-report.json"

# Step 4: 验证门禁
echo "[4/4] Verifying coverage gate..."
yuleosh rtm verify \
    --rtm "${OUTPUT_DIR}/rtm-report.json" \
    --shall-threshold "${SHALL_THRESHOLD}" \
    --should-threshold "${SHOULD_THRESHOLD}" \
    --output "${OUTPUT_DIR}/gate-result.json"

RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo ""
    echo "✅ RTM gate: PASSED"
    python -c "
import json
with open('${OUTPUT_DIR}/gate-result.json') as f:
    d = json.load(f)
print(f'  SHALL coverage: {d[\"metrics\"][\"shall_coverage\"]:.1f}%')
print(f'  Rogue tests:    {d[\"metrics\"][\"rogue_tests\"]}')
"
else
    echo ""
    echo "❌ RTM gate: FAILED"
    echo ""
    echo "📋 未覆盖 SHALL 清单:"
    python -c "
import json
with open('${OUTPUT_DIR}/gate-result.json') as f:
    d = json.load(f)
for v in d.get('violations', []):
    if v['severity'] == 'ERROR':
        print(f'  🔴 {v[\"req_id\"]}: {v[\"message\"]}')
    elif v['severity'] == 'WARNING':
        print(f'  🟡 {v[\"req_id\"]}: {v[\"message\"]}')
"
    exit 1
fi
```

### 3.4 GitHub Actions 集成

```yaml
# .github/workflows/rtm-gate.yml
name: RTM Traceability Gate
on:
  pull_request:
    paths:
      - 'docs/spec.md'
      - 'tests/**'
      - 'src/yuleosh/rtm/**'

jobs:
  rtm-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      
      - name: Run unit tests (coverage baseline)
        run: |
          pytest --cov=yuleosh --cov-report=json:artifacts/coverage/coverage.json \
                 --junitxml=artifacts/coverage/junit.xml
      
      - name: Run RTM verification (SHALL ≥ 90%)
        run: |
          bash ci/rtm-verify.sh docs/spec.md tests/ 90 50
      
      - name: Upload RTM artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: rtm-report
          path: artifacts/rtm/
      
      - name: Post RTM gate status to PR
        uses: actions/github-script@v7
        if: always()
        with:
          script: |
            const fs = require('fs');
            const result = JSON.parse(fs.readFileSync('artifacts/rtm/gate-result.json', 'utf8'));
            const passed = result.passed;
            const coverage = result.metrics.shall_coverage;
            
            await github.rest.checks.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              name: 'RTM Traceability Gate',
              head_sha: context.sha,
              status: 'completed',
              conclusion: passed ? 'success' : 'failure',
              output: {
                title: passed 
                  ? `✅ SHALL Coverage: ${coverage.toFixed(1)}% (≥90%)` 
                  : `❌ SHALL Coverage: ${coverage.toFixed(1)}% (<90%)`,
                summary: `SHALL traceability: ${result.metrics.covered_shalls}/${result.metrics.total_shalls} covered`,
                text: JSON.stringify(result, null, 2)
              }
            });
```

### 3.5 输出产物（CI 自动生成）

每次 CI 运行 SHALL 在 `artifacts/rtm/` 生成以下文件：

```
artifacts/rtm/
├── requirements.json          # spec.md 中提取的所有需求
├── test-mappings.json         # 测试文件中的需求关联标记
├── rtm-report.json            # 完整的双向追溯矩阵
├── gate-result.json           # 门禁验证结果
├── rtm-gaps.json              # 未覆盖需求详细分析
└── rtm-summary.md             # 人类可读的摘要报告
```

**rtm-summary.md 格式示例：**

```markdown
# RTM 追溯摘要 — CI Run #1427

| 指标 | 值 | 门禁阈值 | 状态 |
|:----|:--:|:--------:|:----:|
| 总 SHALL | 78 | — | — |
| 已覆盖 SHALL | 72 | — | — |
| SHALL 覆盖 | 92.3% | ≥90% | ✅ PASS |
| 总 SHOULD | 9 | — | — |
| 已覆盖 SHOULD | 6 | — | — |
| SHOULD 覆盖 | 66.7% | ≥50% | ✅ PASS |
| Rogue 测试 | 2 | 0 | ⚠️ WARN |
| Deep Coverage | 62.8% | ≥30% | ✅ PASS |

### 未覆盖 SHALL (6 条)
1. RS-004: The system SHOULD support firmware signing
2. SWR-012.3: SHALL provide factory reset mechanism
...

### Rogue 测试 (2 个)
1. tests/test_migration.py::test_legacy_format — 无需求关联
2. tests/test_benchmark.py::test_perf_compare — 无需求关联
```

---

## 4. 增量验证（仅检查变更）

### 4.1 增量检查策略

为提升 CI 速度，SHALL 增量验证策略：

| # | 策略 | 说明 | 什么时候用 |
|:--|:-----|:-----|:-----------|
| **全量** | 扫描所有 spec + 所有 test | 完整 RTM 门禁 | Release / Audit 检查 |
| **增量** | 仅检查 PR 变更文件的映射 | 快速 PR 验证 | 日常 PR 提交 |
| **增强** | 增量检查 + 变更文件的邻接依赖 | 兼顾速度与准确 | PR 涉及接口变更时 |

**增量策略的触发规则：**

```yaml
# .yuleosh/ci-config.yaml
rtm:
  strategy: incremental  # 可选: full / incremental / enhanced
  incremental:
    enabled: true
    # 增量模式下仅检查 CHANGED 文件的映射
    # 当变更包含以下范围时自动升级为全量:
    auto_upgrade_paths:
      - "docs/spec.md"         # 需求变更 → 全量
      - "src/yuleosh/rtm/"     # RTM 引擎变更 → 全量
      - ".yuleosh/ci-config.yaml"  # 配置变更 → 全量
    enhanced:
      deps: true              # 检查变更模块的接口依赖方
      depth: 1                # 依赖追溯深度
```

**GIVEN** PR 仅修改 `tests/test_store_pg_deep.py`
**WHEN** CI 运行 RTM 检查
**THEN** CI SHOULD 使用增量策略 — 仅检查该文件的测试映射

**GIVEN** PR 修改 `docs/spec.md` 添加了新 SHALL
**WHEN** CI 运行 RTM 检查
**THEN** CI SHALL 自动升级为全量策略 — 确保所有 SHALL 均被覆盖

### 4.2 差分比较

RTM CI SHALL 比较当前提交与目标分支（如 master）的 RTM 快照：

```bash
# 比较当前 RTM 与基线
yuleosh rtm diff \
    --current artifacts/rtm/rtm-report.json \
    --baseline artifacts/rtm/rtm-master.json \
    --output artifacts/rtm/rtm-diff.json
```

输出示例：

```json
{
  "added_requirements": ["RS-101", "SWR-050.1"],
  "removed_requirements": ["RS-099"],
  "coverage_delta": 2.1,
  "new_gaps": ["RS-101"],
  "new_coverage": ["RS-050 (was gap)"],
  "rogue_test_delta": 0
}
```

### 4.3 新 SHALL 的强制覆盖

新增的 SHALL SHALL 在提交该 PR 时就附带测试：

```bash
# CI 中检查新增 SHALL 的覆盖
yuleosh rtm check-new \
    --diff artifacts/rtm/rtm-diff.json \
    --rtm artifacts/rtm/rtm-report.json

# 输出:
# ✅ RS-101: covered by test_rs_101_overtemp_shutdown
# ❌ RS-102: NO TEST — 阻塞合并
```

---

## 5. 例外处理与豁免

### 5.1 豁免申请流程

```
┌──────────────────────────────────────────────────────────┐
│ 开发者发现无法为某 SHALL 编写测试                          │
│ → 填写豁免申请 (PR 注释/issue)                            │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 质量架构师评估                                           │
│ - 是否真正不可测 (硬件依赖、环境限制)?                    │
│ - 是否可改为 SHOULD/MAY?                                │
│ - 是否有计划修复?                                         │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 通过 → 记录到 docs/rtm-exceptions.md                      │
│ 拒绝 → 开发者需补充测试或重构代码                          │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ CI 门禁识别到已批准的例外 → 跳过该 SHALL 的门禁检查         │
│ 例外过期后 → 自动重新阻塞门禁                              │
└──────────────────────────────────────────────────────────┘
```

### 5.2 例外记录格式

```markdown
# docs/rtm-exceptions.md

## EXC-001: RISC-V SIL Runner (SWR-008.1)

- **原因**: QEMU RISC-V virt 机器串口配置未认证
- **状态**: APPROVED
- **过期**: 2026-09-30
- **审批人**: 小马 🐴
- **跟踪链接**: TKT-2026-0614-RISCV-SIL

## EXC-002: 硬件签名验证 (RS-004)

- **原因**: 签名验证需要硬件安全模块（HSM），HSM 模拟器尚未部署
- **状态**: APPROVED
- **过期**: 2026-12-31
- **审批人**: 小马 🐴
- **跟踪链接**: TKT-2026-0614-HSM-SIM
```

### 5.3 CI 中的豁免处理

CI 门禁 SHALL 读取 `docs/rtm-exceptions.md` 中的已批准例外列表，并在计算覆盖率时排除这些 SHALL：

```python
# 门禁验证中的豁免处理
class GateVerifier:
    def _load_exceptions(self) -> set[str]:
        """从 docs/rtm-exceptions.md 加载例外需求 ID。"""
        exceptions = set()
        content = Path("docs/rtm-exceptions.md").read_text()
        for match in re.finditer(r'\(([A-Z]+-\d+(?:\.\d+)?)\)', content):
            exceptions.add(match.group(1))
        return exceptions
```

---

## 6. 质量报告与可视化

### 6.1 自动生成的 PR 评论

RTM 门禁完成后，CI SHOULD 在 PR 上发布自动评论：

> ### 🔍 RTM Traceability Gate
>
> | 指标 | 值 | 阈值 | 状态 |
> |------|:--:|:----:|:----:|
> | SHALL 覆盖率 | **92.3%** (72/78) | ≥90% | ✅ |
> | SHOULD 覆盖率 | **66.7%** (6/9) | ≥50% | ✅ |
> | Rogue 测试 | **2** | 0 | ⚠️ |
> | Deep Coverage | **62.8%** | ≥30% | ✅ |
>
> 📄 [完整报告](artifacts/rtm/rtm-summary.md)

### 6.2 趋势仪表盘

RTM 覆盖率趋势 SHALL 在每次 Release 时记录：

```
artifacts/rtm/trend.json

{
  "trend": [
    {"version": "v0.6.0", "date": "2026-06-01", "shall_coverage": 84.0, "deep_coverage": 52.0},
    {"version": "v1.0.0", "date": "2026-06-14", "shall_coverage": 86.0, "deep_coverage": 63.0},
    {"version": "v1.1.0", "date": "2026-Q3",    "shall_coverage": 90.0, "deep_coverage": 60.0},
    {"version": "v1.2.0", "date": "2026-Q4",    "shall_coverage": 95.0, "deep_coverage": 65.0}
  ]
}
```

---

## 7. 与现有系统的对接

### 7.1 与 pytest.ini 的关系

`pytest.ini` SHALL 扩展以包含 RTM 配置：

```ini
[pytest]
testpaths = tests
pythonpath = src
addopts = --cov=yuleosh --cov-report=term-missing --cov-report=html --cov-fail-under=60

[yuleosh]
rtm_enabled = true
rtm_shall_threshold = 90.0
rtm_should_threshold = 50.0
rtm_fail_on_rogue = true
rtm_strategy = incremental
rtm_output_dir = artifacts/rtm
```

### 7.2 与 coverage.json 的关联

RTM 报告 SHALL 引用行覆盖率数据以丰富分析：

```python
# 在 RTM 报告中嵌入行覆盖数据
class RTMReport:
    def merge_coverage(self, coverage_path: str = "artifacts/coverage/coverage.json"):
        """将行覆盖率数据合并到 RTM 报告。"""
        with open(coverage_path) as f:
            cov_data = json.load(f)
        for entry in self.entries:
            # 找到该测试对应的覆盖文件
            if entry.test_file in cov_data.get("files", {}):
                entry.test_coverage = cov_data["files"][entry.test_file]["summary"]["percent_covered"]
```

### 7.3 与 evidence pack 的集成

现有的 EvidenceCollector SHALL 扩展以包含 RTM 数据：

```python
# evidence/pack.py 扩展
class EvidenceCollector:
    def __init__(self, output_dir, version):
        self.rtm_report = None
    
    def load_rtm_report(self, path: str):
        with open(path) as f:
            self.rtm_report = json.load(f)
    
    def generate_traceability_matrix(self) -> str:
        """生成包含 RTM 的完整追溯矩阵。"""
        if self.rtm_report:
            matrix = "# 需求追溯矩阵\n\n"
            matrix += f"## 项目: yuleOSH v{self.version}\n\n"
            matrix += f"SHALL 覆盖率: {self.rtm_report['metrics']['shall_coverage']:.1f}%\n\n"
            for entry in self.rtm_report['entries']:
                status_icon = "✅" if entry['status'] == 'PASS' else "❌"
                matrix += f"| {entry['req_id']} | {entry['req_type']} | {status_icon} | {entry['test_function']} |\n"
            return matrix
        return "## 追溯矩阵\n\n(无 RTM 数据)"
    
    def pack_compliance_zip(self):
        """打包合规证据包。"""
        if self.rtm_report:
            rtm_path = os.path.join(self.output_dir, f"rtm-{self.version}.json")
            with open(rtm_path, 'w') as f:
                json.dump(self.rtm_report, f, indent=2)
        ...
```

---

## 8. 验收检查清单

### 8.1 PR 提交流程检查清单

- [ ] 新增/修改的需求（SHALL）有对应的测试用例
- [ ] 新增测试文档字符串或函数名中包含 `req_id`
- [ ] 本地运行 `pytest` 全部通过
- [ ] 本地运行 `bash ci/rtm-verify.sh` 通过
- [ ] `coverage debt` 未增加（如有增加需在 PR 备注说明）

### 8.2 Release 准备检查清单

- [ ] SHALL 追溯覆盖率 ≥95%
- [ ] SHOULD 追溯覆盖率 ≥70%
- [ ] 无 Rogue 测试
- [ ] 所有例外已更新 `docs/rtm-exceptions.md`
- [ ] 已过期例外已被清理或重新审批
- [ ] RTM 趋势数据已更新到 `artifacts/rtm/trend.json`
- [ ] Full-scan RTM 验证通过

### 8.3 审计准备检查清单

- [ ] SHALL 追溯覆盖率 **100%**（或所有例外已记录）
- [ ] 完整的双向追溯链（需求→测试 + 测试→需求）
- [ ] 每个 SHALL 的测试状态为 PASS
- [ ] Rogue 测试为 0
- [ ] `artifacts/rtm/` 包含所有历史 RTM 快照
- [ ] RTM 数据已纳入 Evidence Pack

---

## 附录 A: 参考文件

| 文件 | 说明 |
|:----|:-----|
| `docs/rtm-spec.md` | RTM 字段定义、映射规则、CLI 命令设计 |
| `docs/ci-coverage-gateway.md` | 覆盖率阶梯计划 |
| `docs/test-coverage-standards.md` | 测试覆盖准入标准 |
| `docs/rtm-exceptions.md` | 门禁例外豁免记录 |
| `pytest.ini` | pytest 配置（含 RTM 扩展配置） |
| `.yuleosh/ci-config.yaml` | CI 配置（RTM 策略） |

## 附录 B: 版本历史

| 版本 | 日期 | 变更说明 |
|:----|:----|:--------|
| v1.0.0 | 2026-06-14 | 初始版本：门禁规则、集成方案、CI 脚本、例外处理 |

---

*本文档中所有标注 SHALL 的规则为强制性要求，未遵守将导致 CI 门禁阻塞合并。SHOULD 规则为推荐性要求，未遵守将产生警告但不阻塞。MAY 规则为信息性说明。*

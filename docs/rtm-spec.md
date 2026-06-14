# yuleOSH 需求双向追溯矩阵规范 (RTM Spec)

> **版本**: v1.0.0 | **状态**: APPROVED  
> **维护人**: 小马 🐴 (质量架构师)  
> **审核人**: 老陈 (架构评审)  
> **规范依据**: ASPICE SWE.4 / ISO 26262-8 §8 / ISO 26262-6 §6  
> **最后更新**: 2026-06-14

---

## 1. 范围

### 1.1 适用对象

本规范适用于 yuleOSH 项目中所有以 `SHALL`/`SHOULD`/`MAY` 关键词表述的功能性及非功能性需求，及其对应的自动化验收测试用例。

### 1.2 目标

- 每条 `SHALL` 语句 SHALL 映射到至少一个可执行的自动化测试用例。
- 每条 `SHOULD` 语句 SHOULD 映射到至少一个自动化测试用例；未覆盖的 SHALL 被记录为技术债务。
- 每条 `MAY` 语句 MAY 映射到测试用例；未覆盖的 MAY 被记录为可选待办项。
- 测试覆盖 SHALL 可测量、可审计、可追溯，满足 ASPICE SWE.4 和 SWE.5 的合规要求。

### 1.3 术语定义

| 术语 | 定义 |
|:----|:-----|
| **SHALL** | 强制性需求，必须实现且必须有对应测试。等价于 RFC 2119 的 MUST。 |
| **SHOULD** | 推荐性需求，建议实现且优先有测试。等价于 RFC 2119 的 SHOULD。 |
| **MAY** | 可选需求，可能有测试。等价于 RFC 2119 的 MAY。 |
| **RTM** | Requirements Traceability Matrix，需求追溯矩阵。 |
| **SHALL Coverage** | 有测试覆盖的 SHALL 数量 / 总 SHALL 数量 × 100%。 |
| **Deep Coverage** | 有 ≥2 个独立测试覆盖的 SHALL 数量 / 总 SHALL 数量 × 100%。 |
| **Acceptance Gate** | CI 流水线中执行需求覆盖检查的阶段，决定是否通过。 |
| **Traceability Chain** | 需求 → 设计 → 代码 → 测试 → 证据的完整追溯路径。 |

---

## 2. RTM 格式定义

### 2.1 字段定义

每一条追溯记录 SHALL 包含以下字段：

| 字段 | 类型 | 约束 | 说明 |
|:----|:----|:----|:-----|
| `req_id` | 字符串 | 格式 `RS-XXX` / `SWR-XXX.Y` | 规范文档中的需求 ID |
| `req_type` | 枚举 | `SHALL` / `SHOULD` / `MAY` | 需求的强制等级 |
| `req_name` | 字符串 | 非空 | 需求标题 |
| `shall_text` | 字符串 | 非空 | SHALL/SHOULD/MAY 语句的完整文本 |
| `test_file` | 字符串 | 相对路径 | 测试文件路径，相对于项目根目录 |
| `test_function` | 字符串 | 非空 | 测试函数名 |
| `test_type` | 枚举 | `U` / `I` / `S` / `H` / `C` / `E` | 测试类型缩写 |
| `scenario_ref` | 字符串 | 可空 | 关联的场景名称 |
| `status` | 枚举 | `PASS` / `FAIL` / `SKIP` / `UNTESTED` / `DROPPED` | 最近一次运行状态 |
| `verified_by` | 字符串 | 非空 | 验证方式（`pytest` / `manual` / `not_verified`） |
| `last_run` | 日期 | ISO 8601 | 最近一次测试执行日期 |
| `notes` | 字符串 | 可空 | 备注，如技术债务原因 |

### 2.2 测试类型缩写

| 缩写 | 全称 | 说明 |
|:---:|:----|:-----|
| `U` | Unit Test | 单元测试，pytest 直接运行，不依赖外部硬件 |
| `I` | Integration Test | CI Layer 2 集成测试 |
| `S` | SIL Test | QEMU 仿真测试 |
| `H` | HIL Test | 硬件在环测试 |
| `C` | Code Review / Static Check | 静态分析 / 代码审查检查 |
| `E` | E2E Test | 端到端测试 |

### 2.3 覆盖状态定义

| 状态 | 符号 | 含义 | CI 行为 |
|:----|:---:|:-----|:--------|
| **已覆盖** | 🟢 | ≥1 个测试用例通过 | 通过 |
| **部分覆盖** | 🟡 | 测试存在但未覆盖所有分支 | 警告，不阻塞 |
| **未覆盖** | 🔴 | 无对应测试用例 | **阻塞**（SHALL 级），警告（SHOULD 级） |
| **不适用** | ⬜ | SHOULD/MAY 或待弃用需求 | 不检查 |

### 2.4 追溯矩阵的物理存储格式

RTM 数据 SHALL 以两种格式并存：

**格式 A — Markdown（人类可读）：**
- 文件路径：`docs/acceptance-matrix-rtm.md`
- 用途：团队审阅、审计检查
- 格式：Markdown 表格，按模块分组

**格式 B — JSON（机器可消费）：**
- 文件路径：`artifacts/rtm/rtm-{version}.json`
- 用途：CI 消费、差异比较、合规包归档
- 格式：结构化 JSON 数组

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-14T09:00:00+08:00",
  "project": "yuleOSH",
  "spec_version": "0.6.0",
  "entries": [
    {
      "req_id": "RS-001",
      "req_type": "SHALL",
      "req_name": "Agent 驱动的开发流水线",
      "shall_text": "The system SHALL support an SDD → DDD → TDD → CI/CD pipeline orchestrated by AI agents",
      "test_file": "tests/test_pipeline_engine.py",
      "test_function": "test_pipeline_full_flow",
      "test_type": "I",
      "scenario_ref": "SDD → DDD → TDD 全流程",
      "status": "PASS",
      "verified_by": "pytest",
      "last_run": "2026-06-13",
      "notes": ""
    }
  ],
  "summary": {
    "total_entries": 78,
    "covered": 67,
    "partial": 1,
    "untested": 10,
    "coverage_percent": 85.9,
    "deep_coverage_percent": 62.8,
    "pass_gate": true
  }
}
```

---

## 3. SHALL → 测试用例映射规则

### 3.1 映射规则（强制性）

以下规则适用于所有 `SHALL` 语句：

| 规则编号 | 规则 | 类型 |
|:--------|:----|:----|
| **RTM-R01** | 每条 SHALL 语句 SHALL 映射到至少 1 个自动执行的测试用例。 | SHALL |
| **RTM-R02** | 每条 SHALL 语句 SHOULD 映射到至少 2 个测试用例（happy path + 异常路径）。 | SHOULD |
| **RTM-R03** | 测试文件 SHALL 包含可解析的需求关联标记（见 §3.2）。 | SHALL |
| **RTM-R04** | 映射关系 SHALL 在 CI 流水线的 coverage 阶段自动验证。 | SHALL |
| **RTM-R05** | 测试用例 SHALL 至少覆盖 SHALL 语句的正常功能路径（happy path）。 | SHALL |
| **RTM-R06** | 安全关键的 SHALL 语句 SHALL 有正向（期待满足）和反向（期待拒绝测试）。 | SHALL |
| **RTM-R07** | 新模块首次提交时，其所有 SHALL 语句 SHALL 至少有 50% 已覆盖测试。 | SHALL |
| **RTM-R08** | CI 合并前，新增 SHALL 的测试覆盖 SHALL 达到 100%。 | SHALL |

### 3.2 需求关联标记方式

测试文件 SHALL 通过以下方式标记其覆盖的需求 ID。

**方式 A（推荐）：测试函数命名约定**

```python
# 文件名含需求 ID: test_rs_001_pipeline_full_flow.py
# 函数名格式: test_{req_id_lower}_{description}

def test_rs_001_pipeline_full_flow():
    """RS-001: SDD → DDD → TDD pipeline"""
    ...
```

**方式 B：文档字符串标记**

```python
def test_i2c_init():
    """SWR-008.2: SHALL support HAL mocking for I2C (master read/write)"""
    ...
```

**方式 C：pytest marker 标记（推荐用于多需求关联）**

```python
@pytest.mark.req("RS-002")
@pytest.mark.req("SWR-002.1")
def test_parse_basic_spec():
    """RS-002/SWR-002.1: OpenSpec format parsing"""
    ...
```

### 3.3 映射质量等级

| 等级 | 要求 | CI 门禁 |
|:----|:-----|:--------|
| 🔴 **不可接受** | SHALL 无任何测试，或测试持续 FAIL | 阻塞合并 |
| 🟡 **最低可接受** | 每条 SHALL ≥1 个测试，且所有测试 PASS | 允许通过 |
| 🟢 **推荐** | 每条 SHALL ≥1 个测试，30% 的 SHALL 有 ≥2 个测试 | 通过 + 质量徽章 |
| 🏆 **卓越** | 每条 SHALL ≥2 个测试（happy path + error path），且 100% 测试通过 | 通过 + 卓越标记 |

### 3.4 覆盖深度指标

- **SHALL Coverage** = `covered_shalls / total_shalls × 100%`
- **Deep Coverage** = `deep_covered_shalls / total_shalls × 100%` （deep = ≥2 测试用例）
- **Critical Path Coverage** = 关键安全路径的 SHALL 覆盖率（单独跟踪）

---

## 4. 验收门禁标准

### 4.1 CI 门禁配置

yuleOSH 的 CI 流水线 SHALL 在 Layer 1（单元测试）之后执行 RTM 验证。

```
CI L1:  pytest --cov --cov-fail-under=70
        ↓
CI RTM: yuleosh rtm verify --threshold 80  ← 新增门禁
        ↓
CI L2:  cross-compile + SIL + static analysis
        ↓
CI L2.5: HIL (硬件在环，mock 模式也可)
        ↓
CI L3:  system test + evidence pack
```

### 4.2 门禁阈值

| 门禁指标 | SHALL 阈值 | SHOULD 阈值 | 行为 |
|:---------|:----------:|:-----------:|:-----|
| 单条覆盖 | 100%（≥1 测试） | ≥50% | 未达标警告 + 非阻塞 |
| 模块覆盖率 | ≥80% | ≥60% | 未达标阻塞 |
| 全局覆盖率 | ≥85%（v1.0.0 目标） | ≥70% | 未达标阻塞 |
| 无 FAIL 测试 | 100% PASS | — | 阻塞 |
| Deep Coverage | ≥30%（推荐） | — | 非阻塞质量指标 |
| 无 Rogue 测试 | 100% 测试可追溯 | — | 阻塞（测试未关联任何需求者标记为 Rogue） |

### 4.3 门禁触发条件

- **PR/MR 合并前**：SHALL 覆盖率 ≥80%，所有 SHALL ≥1 测试。
- **Release 构建前**：SHALL 覆盖率 ≥85%，所有 SHALL ≥1 测试，Deep Coverage ≥30%。
- **审计构建前**：SHALL 覆盖率 ≥95%，所有 SHALL ≥1 测试，所有 SHOULD ≥1 测试（或记录例外）。

### 4.4 异常流程

当门禁触发失败时：

1. CI SHALL 输出详细的失败报告，列出所有未覆盖的 SHALL 及其预期测试位置。
2. 开发者 SHALL 补充缺失的测试用例或提交特例豁免申请。
3. 特例豁免 SHALL 由质量架构师（小马 🐴）审批，记录在 `docs/rtm-exceptions.md`。
4. 特例豁免 SHALL 设置过期时间，到期后自动重新阻塞。

### 4.5 覆盖率趋势跟踪

每次 Release，RTM 覆盖率 SHALL 被追加到覆盖率趋势记录：

| 版本 | 总 SHALL | 覆盖率 | Deep Coverage | PASS 率 |
|:----|:--------:|:------:|:-------------:|:-------:|
| v0.4.0 | 48 | 81% | 45% | 100% |
| v0.6.0 | 62 | 84% | 52% | 100% |
| v1.0.0 | 78 | 86% | 63% | 100% |
| v1.1.0 | — | ≥95% (目标) | ≥60% (目标) | 100% |

---

## 5. 与 OpenSpec 引擎的集成

### 5.1 数据流架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     OpenSpec 引擎 (spec/validate.py)                │
│  parse_spec() → SpecDocument { requirements, scenarios }            │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ SpecDocument.requirements[].shall[]
                          │ SpecDocument.scenarios[].given/when/then
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  RTM 引擎（本规范实现）                              │
│                                                                     │
│  ① extract_tests()       扫描 tests/ 目录，提取需求ID标记         │
│  ② build_rtm()           建立 shall ↔ test 双向映射                 │
│  ③ verify_coverage()     验证覆盖率门禁                             │
│  ④ generate_report()     输出 JSON + Markdown                       │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ RTM 数据
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Evidence Pack (evidence/pack.py)                                    │
│  → compliance-evidence.zip 包含 rtm-{version}.json                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 RTM 引擎接口定义

RTM 引擎 SHALL 提供以下编程接口：

```python
# src/yuleosh/rtm/__init__.py  (计划实现)

def extract_tests(test_dir: str = "tests/") -> list[TestMapping]:
    """扫描测试目录，提取需求关联标记。
    
    返回每个测试函数的 req_id 映射列表。
    支持的标记方式：
      - 函数名包含 req_id（如 test_rs_001_xxx）
      - 文档字符串包含 "RS-XXX:" 或 "SWR-XXX.Y:"
      - pytest marker: @pytest.mark.req("RS-XXX")
    """

def build_rtm(spec_path: str = "docs/spec.md",
              test_dir: str = "tests/") -> RTMReport:
    """构建完整的需求追溯矩阵。
    
    1. 解析 spec 获取所有 SHALL/SHOULD/MAY
    2. 扫描 tests/ 获取 req_id 标记
    3. 建立 shall ↔ test 双向映射
    4. 返回 RTMReport
    """

def verify_coverage(rtm: RTMReport,
                    shall_threshold: float = 80.0,
                    should_threshold: float = 50.0) -> GateResult:
    """验证覆盖率门禁。
    
    Returns GateResult(passed=True/False, violations=[...])
    """

def generate_report(rtm: RTMReport,
                    format: str = "json",
                    output_path: str = "artifacts/rtm/") -> str:
    """生成追溯矩阵报告（JSON / Markdown / HTML）。"""
```

### 5.3 与现有 EvidenceCollector 的集成

现有的 `EvidenceCollector` 在 `evidence/pack.py` 中 SHALL 扩展以包含 RTM 数据：

```python
# 在 generate_traceability_matrix() 中加入 RTM 数据
class EvidenceCollector:
    def __init__(self, output_dir, version):
        self.rtm_data = None   # ← 新增字段
    
    def set_rtm_data(self, rtm_report: dict):
        """注入 RTM 追溯矩阵数据。"""
        self.rtm_data = rtm_report
    
    def generate_traceability_matrix(self) -> str:
        """生成包含 RTM 的追溯矩阵。"""
        if self.rtm_data:
            # 在矩阵中嵌入 RTM 数据和 SHALL 覆盖率
            ...
    
    def pack_compliance_zip(self) -> str:
        """打包合规证据包，包含 rtm-{version}.json。"""
        ...
```

### 5.4 SpecDocument 的 RTM 扩展

`SpecDocument` 的 `to_dict()` SHALL 扩展以包含 RTM 数据：

```python
class SpecDocument:
    def __init__(self, path: str):
        ...
        self.rtm: RTMReport | None = None  # ← 新增
    
    def to_dict(self):
        base = {...}  # 原有字段
        if self.rtm:
            base["rtm"] = self.rtm.to_dict()
        return base
```

---

## 6. 与 pytest + coverage 工具的对接方案

### 6.1 CI 流水线集成步骤

RTM 验证 SHALL 作为独立的 CI 步骤执行：

```yaml
# .yuleosh/ci-config.yaml 扩展
rtm:
  enabled: true
  shall_threshold: 80.0
  should_threshold: 50.0
  deep_coverage_target: 30.0
  fail_on_rogue_tests: true
  report_format: json
  output_path: "artifacts/rtm/"
```

### 6.2 CLI 命令设计

```bash
# 验证需求覆盖率门禁
yuleosh rtm verify --spec docs/spec.md --test-dir tests/ --shall 80 --should 50
# 输出示例:
# ✅ RTM: 67/78 SHALLs covered (85.9%) — PASS (threshold: 80%)
# ⚠️ SHOULDs: 5/9 covered (55.6%) — PASS (threshold: 50%)

# 查看未覆盖 SHALL
yuleosh rtm gap --spec docs/spec.md
# 输出示例:
# 🔴 未覆盖 SHALL:
#   1. RS-004: The system SHOULD support firmware signing (SHOULD)
#   2. RS-006: The system SHOULD provide a mobile-responsive interface (SHOULD)
#   ...

# 生成完整 RTM 报告
yuleosh rtm report --spec docs/spec.md --test-dir tests/ --format json --output artifacts/rtm/

# 查看单个需求的追溯链
yuleosh rtm trace --req-id RS-001
# 输出示例:
# RS-001 → The system SHALL support SDD → DDD → TDD → CI/CD
#   ✅ tests/test_pipeline_engine.py::test_pipeline_full_flow (I)
#   ✅ tests/test_pipeline_engine.py::test_superpowers_rules (I)
```

### 6.3 pytest 插件集成

yuleOSH SHALL 提供可选的 pytest 插件，用于在测试执行时自动采集需求关联数据：

```python
# src/yuleosh/rtm/pytest_plugin.py (示例设计)

def pytest_configure(config):
    """注册 rtm 标记。"""
    config.addinivalue_line(
        "markers",
        "req(req_id): mark test with requirement ID for RTM traceability"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """在测试收集阶段提取 req_id 标记。"""
    for item in items:
        req_ids = []
        # 方法1: marker
        for marker in item.iter_markers(name="req"):
            req_ids.extend(marker.args)
        # 方法2: 函数名解析
        name_match = re.search(r"(RS|SWR|FEATURE)[_-](\d+)", item.nodeid, re.I)
        if name_match:
            req_ids.append(f"{name_match.group(1)}-{name_match.group(2)}")
        # 方法3: 文档字符串
        docstr = item.function.__doc__ or ""
        doc_matches = re.findall(r"(?:RS|SWR|FEATURE)[-]\d+", docstr, re.I)
        req_ids.extend(doc_matches)
        
        item._req_ids = list(set(req_ids))
```

### 6.4 Coverage 报告对接

```bash
# 步骤 1: 运行 pytest 采集测试结果
pytest tests/ --junitxml=artifacts/rtm/junit.xml --json-report=artifacts/rtm/test-results.json

# 步骤 2: 运行行覆盖率
pytest tests/ --cov=src/yuleosh/ --cov-report=json:artifacts/rtm/coverage.json

# 步骤 3: 运行 RTM 验证
yuleosh rtm verify --spec docs/spec.md \
                   --test-dir tests/ \
                   --junit artifacts/rtm/junit.xml \
                   --shall 80
```

### 6.5 行覆盖与需求覆盖的关系

```
┌──────────────────────────────────────────┐
│  测试充分性的二维度量                     │
├────────────────┬─────────────────────────┤
│                │   需求覆盖 (RTM)         │
│                ├──────────┬──────────────┤
│                │  不足     │  充足        │
├───────┬────────┼──────────┼──────────────┤
│ 行覆  │ 不足   │ ❌ 危险   │ ⚠️ 关注      │
│ 盖率  ├────────┼──────────┼──────────────┤
│       │ 充足   │ ⚠️ 预警   │ ✅ 健康      │
└───────┴────────┴──────────┴──────────────┘

行覆盖率充足但需求覆盖不足 = 测试了很多"无关紧要"的代码（噪音）
需求覆盖充足但行覆盖不足 = 核心功能有测试，但边界情况可能遗漏
两者均充足 = 理想的测试状态
```

---

## 7. 完整追溯链示例

### 7.1 需求 → 设计 → 测试 → 证据

以 `SWR-009.1: Flash Abstraction Layer` 为例展示完整追溯链：

```
┌─────────────────────────────────────────────────────────────────────┐
│ ① 需求定义 (docs/spec.md)                                           │
│                                                                     │
│ SWR-009.1: Flash Abstraction Layer (FAL)                            │
│   - The system SHALL provide abstract FlashTool base class          │
│   - The system SHALL provide concrete implementations:              │
│     OpenOCDRunner, JLinkRunner, PyOCDRunner                         │
│   - The system SHALL provide FlashRunner facade                     │
│   - FlashRunner SHALL support preferred-tool override               │
│   - FlashRunner SHALL attempt fallback tools                        │
│   - Each runner SHALL return FlashResult dataclass                  │
│   Status: APPROVED                                                  │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ② 设计实现 (src/yuleosh/cross/flash.py)                             │
│                                                                     │
│ class FlashTool(ABC):               # SWR-009.1.1                  │
│     @abstractmethod                 # 抽象基类                      │
│     def write(self, ...)             # write() 方法                 │
│     @abstractmethod                                                  │
│     def erase(self, ...)             # erase() 方法                 │
│     @abstractmethod                                                  │
│     def verify(self, ...)            # verify() 方法                │
│                                                                     │
│ class OpenOCDRunner(FlashTool):      # SWR-009.1.2                  │
│     def write(self, ...)             # OpenOCD 烧录实现              │
│     ...                                                              │
│                                                                     │
│ class FlashRunner:                   # SWR-009.1.3                  │
│     def flash(self, firmware):       # 外观模式                      │
│         # auto-detect + fallback                                    │
│         ...                                                          │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ③ 测试实现 (tests/test_flash.py)                                    │
│                                                                     │
│ @pytest.mark.req("SWR-009.1")                                       │
│ def test_flash_tool_abc_interface():         ← 覆盖抽象基类         │
│     """SWR-009.1: FlashTool ABC write/erase/verify methods"""       │
│                                                                     │
│ @pytest.mark.req("SWR-009.1")                                       │
│ def test_openocd_runner_write():             ← 覆盖具体实现         │
│     """SWR-009.1: OpenOCDRunner write method"""                     │
│                                                                     │
│ @pytest.mark.req("SWR-009.1")                                       │
│ def test_flash_runner_auto_detect():         ← 覆盖 facade          │
│     """SWR-009.1: FlashRunner auto-detect"""                        │
│                                                                     │
│ @pytest.mark.req("SWR-009.1")                                       │
│ def test_flash_runner_fallback():            ← 覆盖 fallback        │
│     """SWR-009.1: FlashRunner fallback chain"""                     │
│                                                                     │
│ @pytest.mark.req("SWR-009.1")                                       │
│ def test_flash_result_dataclass():           ← 覆盖 dataclass       │
│     """SWR-009.1: FlashResult dataclass fields"""                   │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ④ 追溯验证 (CI RTM step)                                            │
│                                                                     │
│ $ yuleosh rtm trace --req-id SWR-009.1                               │
│                                                                     │
│ SWR-009.1: Flash Abstraction Layer                                   │
│   SHALL: provide abstract FlashTool base class                      │
│     ✅ tests/test_flash.py::test_flash_tool_abc_interface           │
│   SHALL: provide concrete implementations (OpenOCD/JLink/pyOCD)     │
│     ✅ tests/test_flash.py::test_openocd_runner_write               │
│     ✅ tests/test_flash.py::test_jlink_runner_write (planned)       │
│     ✅ tests/test_flash.py::test_pyocd_runner_write (planned)       │
│   SHALL: provide FlashRunner facade                                 │
│     ✅ tests/test_flash.py::test_flash_runner_auto_detect           │
│   SHALL: support preferred-tool override                            │
│     ✅ tests/test_flash.py::test_flash_runner_tool_override         │
│   SHALL: attempt fallback chain                                     │
│     ✅ tests/test_flash.py::test_flash_runner_fallback              │
│   SHALL: return FlashResult dataclass                               │
│     ✅ tests/test_flash.py::test_flash_result_dataclass             │
│                                                                     │
│  Coverage: 6/6 SHALLs ✅ 100%                                       │
│  Deep Coverage: ✅ (2+ tests on concrete implementations)           │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ⑤ 证据归档 (artifacts/evidence/)                                    │
│                                                                     │
│ compliance-evidence-v1.0.0.zip:                                     │
│   ├── spec.md                              ← 需求定义              │
│   ├── spec-validate-report.json            ← 规范验证报告          │
│   ├── code-review-archive.json             ← 代码审查存档          │
│   ├── rtm-v1.0.0.json                      ← 追溯矩阵（本规范）   │
│   ├── sil-test-report.json                 ← SIL 测试报告          │
│   ├── hil-report.json                      ← HIL 测试报告          │
│   └── coverage.json                        ← 行覆盖率报告          │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 双向追溯验证

正向追溯（需求 → 测试）：
```
RS-004: "The system SHALL support cross-compilation for ARM targets"
  → test_ci_engine.py::test_cross_compile_arm() 覆盖确认
```

反向追溯（测试 → 需求）：
```
test_ci_engine.py::test_cross_compile_arm()
  → 文档字符串内部标记: "RS-004: SHALL cross-compilation for ARM"
  → 追溯成功确认
```

当正向和反向追溯均能匹配时，该 SHALL 被视为 **fully traceable**。

---

## 8. 质量门禁的 CI 实现规范

### 8.1 流水线阶段

```
┌─────────────────┐
│ 触发 (PR/Commit)│
└────────┬────────┘
         ▼
┌─────────────────┐
│ ① L0: lint +   │  ← 快速失败 (5 min)
│    basic check  │
└────────┬────────┘
         ▼
┌─────────────────────────────────┐
│ ② L1: Unit tests + Coverage    │  ← pytest + pytest-cov
│                                │
│   ├ 2a: pytest --cov --cov-    │
│   │    fail-under=70           │  (行覆盖率 ≥70%)
│   │                            │
│   ├ 2b: yuleosh rtm verify     │  ← 新增门禁
│   │    --shall 80              │  (需求覆盖率 ≥80%)
│   │                            │
│   └ 2c: Rogue test detection   │  (所有测试需关联需求)
└─────────────────────────────────┘
         ▼
┌─────────────────┐
│ ③ L2: Cross-   │  ← 交叉编译 + SIL + MISRA
│    compile +    │
│    SIL + ASA    │
└────────┬────────┘
         ▼
┌─────────────────┐
│ ④ L2.5: HIL    │  ← 硬件在环（可选mock）
└────────┬────────┘
         ▼
┌─────────────────┐
│ ⑤ L3: System   │  ← 系统测试 + 证据包
│    Test + Eve   │
└─────────────────┘
```

### 8.2 CI 脚本规范

```bash
#!/bin/bash
# ci/rtm-verify.sh — RTM 门禁检查

set -euo pipefail

SHALL_THRESHOLD=${1:-80}
SPEC_FILE=${2:-"docs/spec.md"}
TEST_DIR=${3:-"tests/"}

echo "🔍 Running RTM verification..."
echo "   SHALL threshold: ≥${SHALL_THRESHOLD}%"
echo "   Spec: ${SPEC_FILE}"

# 执行 RTM 验证
yuleosh rtm verify \
  --spec "${SPEC_FILE}" \
  --test-dir "${TEST_DIR}" \
  --shall "${SHALL_THRESHOLD}" \
  --output "artifacts/rtm/verify-result.json"

RESULT=$?

if [ $RESULT -eq 0 ]; then
  echo "✅ RTM gate PASSED"
else
  echo "❌ RTM gate FAILED"
  echo ""
  echo "📋 未覆盖需求清单:"
  yuleosh rtm gap --spec "${SPEC_FILE}"
  exit 1
fi
```

### 8.3 门禁结果格式

```json
{
  "gate": "rtm-verify",
  "passed": true,
  "timestamp": "2026-06-14T09:00:00+08:00",
  "spec_file": "docs/spec.md",
  "threshold": {
    "shall": 80.0,
    "should": 50.0
  },
  "metrics": {
    "total_shalls": 78,
    "covered_shalls": 67,
    "shall_coverage": 85.9,
    "total_shoulds": 9,
    "covered_shoulds": 5,
    "should_coverage": 55.6,
    "deep_coverage": 62.8,
    "rogue_tests": 0
  },
  "violations": [
    {
      "req_id": "DEMO-UART-001.1",
      "type": "SHALL",
      "text": "yuleosh demo uart CLI",
      "severity": "ERROR",
      "action": "需在 tests/ 添加对应测试"
    }
  ],
  "enforce": true
}
```

---

## 9. 例外处理与豁免流程

### 9.1 何时可豁免

以下情况可申请 SHALL 覆盖豁免：

1. **SHOULD / MAY 需求**：非强制，自动豁免。
2. **技术暂不可测**：如需真实硬件但未到货（HIL）。
3. **弃用标记**：需求标记为 `DROPPED` 或 `DEPRECATED`。
4. **测试环境限制**：CI 环境中不可达的测试路径。

### 9.2 豁免流程

```
开发者提交豁免申请 → 维护人评估 → 记录例外文件 → 设定过期时间
```

例外记录格式：

```markdown
# docs/rtm-exceptions.md (示例)

## EXC-001: RISC-V SIL Runner (SWR-008.1)

- **原因**: QEMU RISC-V virt 机器的串口配置尚未认证
- **状态**: APPROVED
- **过期**: 2026-09-30 (90天窗口)
- **审批人**: 小马 🐴
- **跟踪**: TKT-2026-0614-RISCV-SIL
```

---

## 10. 合规审计清单

本规范定义了以下 ASPICE 相关的合规检查点：

| ASPICE 领域 | 相关 RTM 规则 | 审计证据 |
|:-----------|:-------------|:---------|
| SYS.3 (系统需求) | RS-002 需求树层级 | spec.md 的需求 ID |
| SWE.1 (软件需求) | RS-001.2 → SHALL 映射 | rtm-{version}.json |
| SWE.4 (软件测试) | RTM-R01~RTM-R08 | 追溯矩阵 + 覆盖率报告 |
| SWE.5 (软件集成) | SWR-008.3 SIL 测试规范 | sil-test-report.json |
| SYS.5 (系统集成) | RS-009 HIL 测试 | hil-report.json |
| SUP.9 (变更管理) | SWR-002.2 变更追踪 | spec-delta 记录 |

---

## 附录 A: 参考文件

| 文件 | 说明 |
|:----|:-----|
| `docs/spec.md` | yuleOSH 主规范文档，所有 SHALL/SHOULD/MAY 的源 |
| `docs/spec-contract.md` | 外包合同级别的 spec 子集 |
| `docs/requirements-coverage-traceability.md` | 现有需求覆盖率追踪表 |
| `docs/acceptance-matrix-rtm.md` | 本规范定义的验收矩阵实例 |
| `docs/design/requirements-coverage-tool.md` | 需求覆盖率工具设计草案 |
| `src/yuleosh/spec/validate.py` | OpenSpec 引擎实现 |
| `src/yuleosh/evidence/pack.py` | 证据包收集器 |
| `pytest.ini` | pytest 配置 |
| `.yuleosh/ci-config.yaml` | CI 配置（含 RTM 设置） |

## 附录 B: 规范版本历史

| 版本 | 日期 | 变更说明 |
|:----|:----|:--------|
| v1.0.0 | 2026-06-14 | 初始版本：RTM 字段定义、映射规则、门禁标准、OpenSpec/Pytest 集成 |

---

*本规范以 SHALL/SHOULD/MAY 术语定义强制性、推荐性和可选性要求。所有标注 SHALL 的规则为强制性要求，未遵守将导致 CI 门禁阻塞。*

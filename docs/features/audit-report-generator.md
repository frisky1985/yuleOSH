# 自动审计报告生成器 (Audit Report Generator)

对标客户 ASPICE 审核需求，一键生成 ASPICE 维度的审计报告，从证据数据自动填充，支持 PDF/HTML/JSON/Text 多种输出格式。

---

## 1. 概述

| 项目 | 内容 |
|:-----|:------|
| 对标需求 | dSPACE/Vector 审计包生成能力 |
| 实现位置 | `src/yuleosh/report/audit_report.py` |
| 支持格式 | HTML（自包含）、PDF（通过 weasyprint）、JSON、Text |
| 核心功类 | `AuditReportGenerator` |

### 1.1 解决的问题

- 客户 ASPICE 审核前需要大量手工整理证据
- 证据分散在 CI 流水线、测试报告、评审记录中
- 传统方式需 3-5 人天准备审计材料 → yuleOSH 一键生成 < 30 秒

---

## 2. 架构

```
  证据数据源                                   报告输出
  ──────────                                  ──────────
  .osh/evidence/*.json           ──→  HTML (自包含)
  data/requirements/                →  PDF (weasyprint)
    requirements.json               →  JSON (机器可读)
  data/tests/                       →  Text (CLI)
    test-cases.json
  (pipeline 运行结果)
         │
         ▼
  EvidenceScanner
    - 按 ASPICE 维度分类证据
    - 自动推断 process_id
    - 去重
         │
         ▼
  AuditReportGenerator
    - 计算每个维度覆盖率
    - 评分 (NI/AL1/AL2/AL3)
    - 生成 findings/recommendations
         │
         ▼
  Exporters (HTML/PDF/JSON/Text)
```

---

## 3. 覆盖的 ASPICE 维度

| 过程 | 标题 | 证据来源 | 默认评分标准 |
|:-----|:-----|:---------|:------------|
| SWE.1 | 软件需求分析 | `requirements.json` / evidence spec 文件 | ≥90% → AL3, ≥70% → AL2, ≥30% → AL1 |
| SWE.2 | 软件架构设计 | evidence architecture 文件 / arch review 结果 | 同上 |
| SWE.3 | 软件详细设计/单元构建 | evidence code 文件 / 代码评审 | 同上 |
| SWE.4 | 软件单元验证 | evidence unit_test / coverage 文件 | 同上 |
| SWE.5 | 软件集成/集成测试 | `test-cases.json` (SWE.5) / integration test 结果 | 同上 |
| SWE.6 | 软件资格测试 | `test-cases.json` (SWE.6) / qualification test | 同上 |
| SYS.1-5 | 系统级过程 | evidence system 文件 | 同上 |
| MAN.3 | 项目管理 | evidence plan 文件 | 同上 |
| SUP.1 | 质量保证 | evidence audit 文件 | 同上 |
| SUP.9 | 问题解决 | evidence issue 文件 | 同上 |
| SUP.10 | 变更管理 | evidence change 文件 | 同上 |

### 3.1 评分标准

| 级别 | 含义 | 条件 |
|:-----|:-----|:------|
| AL3 | Fully Achieved | ≥90% 证据覆盖 + 零失败 |
| AL2 | Largely Achieved | ≥70% 证据覆盖 + 失败项 < 20% |
| AL1 | Partially Achieved | ≥30% 证据覆盖 |
| NI | Not Achieved | <30% 或无证据 |

---

## 4. 数据模型

### 4.1 AspiceReport

| 字段 | 类型 | 描述 |
|:-----|:-----|:------|
| `project_name` | string | 项目名称 |
| `version` | string | 报告版本 |
| `generated_at` | string (ISO datetime) | 生成时间 |
| `report_id` | string | 报告唯一 ID |
| `overall_score` | string | 总体评分: `AL1` / `AL2` / `AL3` / `NI` |
| `overall_coverage_pct` | float | 所有维度平均覆盖率 |
| `total_evidences` | int | 证据条目总数 |
| `total_gaps` | int | 总缺口数 |
| `dimensions` | ProcessDimension[] | 各维度评估详情 |
| `summary_by_process` | dict | 各维度摘要 |
| `recommendations` | string[] | 改进建议 |

### 4.2 ProcessDimension

| 字段 | 类型 | 描述 |
|:-----|:-----|:------|
| `process_id` | string | ASPICE 过程 ID |
| `title` | string | 过程名称 |
| `score` | string | 评级 |
| `coverage_pct` | float | 证据覆盖率 |
| `evidence_count` | int | 证据条目数量 |
| `gap_count` | int | 缺口计数 |
| `findings` | list[dict] | 具体发现 |
| `evidences` | EvidenceItem[] | 该维度所有证据 |

### 4.3 EvidenceItem

| 字段 | 类型 | 描述 |
|:-----|:-----|:------|
| `process` | string | 所属 ASPICE 过程 |
| `category` | string | 证据类别 (requirement/test/review) |
| `title` | string | 证据标题 |
| `ref_id` | string | 源数据 ID |
| `path` | string | 文件路径 |
| `status` | string | 通过/失败/待审 |
| `details` | string | 额外详情 |
| `timestamp` | string | 时间戳 |
| `evidence_type` | string | 证据类型 (test/review/analysis/document) |

---

## 5. 证据自动分类

### 5.1 显式分类

证据 JSON 文件中的 `process` 字段直接指定 ASPICE 维度：

```json
{
  "process": "SWE.1",
  "type": "requirement",
  "title": "Door lock timing requirement"
}
```

### 5.2 隐式推断

如果没有显式指定 `process`，系统按 `type` 自动推断：

| evidence `type` | 推断为 |
|:----------------|:-------|
| `requirement`, `spec`, `shall` | SWE.1 |
| `architecture`, `design`, `arch_review` | SWE.2 |
| `code`, `source`, `implementation` | SWE.3 |
| `unit_test`, `code_review`, `misra`, `coverage` | SWE.4 |
| `integration_test`, `integration` | SWE.5 |
| `qualification_test`, `system_test`, `acceptance` | SWE.6 |
| `audit`, `quality`, `compliance` | SUP.1 |
| `issue`, `defect`, `problem` | SUP.9 |
| `change`, `change_request` | SUP.10 |

### 5.3 文件名推断

如果 type 也无法判断，按文件路径中的关键词匹配：
- 路径包含 `swe.1` / `swe1` → SWE.1
- 路径包含 `integration` → SWE.5 (integration_test)
- etc.

---

## 6. 使用方式

### 6.1 CLI 命令

```bash
# 一键生成全部格式报告
yuleosh audit-report \
  --evidence-dir .osh/evidence \
  --requirements data/requirements/requirements.json \
  --tests data/tests/test-cases.json \
  --project "BCM Project" \
  --version "v1.5.0" \
  --output ./reports/audit/

# 仅生成 HTML
yuleosh audit-report \
  --format html \
  --project "BCM Project" \
  --output ./reports/audit/

# 仅生成 PDF（需要 weasyprint）
yuleosh audit-report \
  --format pdf \
  --project "BCM Project" \
  --output ./reports/audit/

# 仅预览文本（CLI 友好）
yuleosh audit-report \
  --format text
```

### 6.2 Python API

```python
from yuleosh.report.audit_report import AuditReportGenerator

gen = AuditReportGenerator(
    evidence_dir=".osh/evidence",
    requirements_file="data/requirements/requirements.json",
    tests_file="data/tests/test-cases.json",
)

report = gen.generate_aspice_report(
    project_name="BCM Project",
    version="v1.5.0",
)

# 输出
gen.export_html(report, "aspice-report.html")
gen.export_pdf(report, "aspice-report.pdf")   # 需 weasyprint
gen.export_json(report, "aspice-report.json")
gen.export_text(report, "aspice-report.txt")

# 或获取文本字符串
text_report = gen.export_text(report)
print(text_report)
```

### 6.3 Pipeline 集成

在 CI pipeline 的最终 stage 自动生成审计报告：

```yaml
# .yuleosh/pipeline.yaml
stages:
  - name: audit-report
    type: analysis
    script: |
      yuleosh audit-report \
        --project "${YULEOSH_PROJECT}" \
        --version "${CI_PIPELINE_ID}" \
        --output .yuleosh/reports/audit/
    artifacts:
      - .yuleosh/reports/audit/aspice-report.html
      - .yuleosh/reports/audit/aspice-report.json
```

---

## 7. 输出格式说明

### 7.1 HTML

自包含的 HTML 报告，无外部依赖，可直接发给审核员。

```
aspice-report.html
├── 标题 + 元信息 (项目名/版本/报告ID/生成时间)
├── 总体评分卡片 (NI/AL1/AL2/AL3 + 总体覆盖率)
├── 过程维度表格
│   ├── 过程ID / 标题 / 评分 / 覆盖率 / 证据数 / 缺口数
│   └── 每个维度的 findings 详表
├── 改进建议列表
└── 评分等级图例
```

**效果预览：**
```
┌─────────────────────────────────────────────────────────────────┐
│  🔍 ASPICE Audit Report                                         │
│  Project: BCM Project | Version: v1.5.0                         │
│  Report ID: ASPICE-AUDIT-20260727-010000                       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     AL2                                 │   │
│  │            Largely Achieved                              │   │
│  │    Overall Coverage: 75.3%  |  Total Evidence: 28       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Process Dimension Coverage                                     │
│  ┌────────┬──────────────────────┬───────┬─────────┬──────┬───┐ │
│  │ Process│ Title                │ Score│Coverage │ Evid.│Gaps│ │
│  ├────────┼──────────────────────┼───────┼─────────┼──────┼───┤ │
│  │ SWE.1  │ Requirements Analysis│ AL2  │ 85.7%   │ 7    │ 0  │ │
│  │ SWE.5  │ Integration Test    │ AL2  │ 80.0%   │ 5    │ 0  │ │
│  │ SWE.6  │ Qualification Test  │ AL1  │ 50.0%   │ 2    │ 0  │ │
│  │ MAN.3  │ Project Management  │ NI   │ 0.0%    │ 0    │ 1  │ │
│  └────────┴──────────────────────┴───────┴─────────┴──────┴───┘ │
│                                                                 │
│  Recommendations                                                │
│  • [SWE.6] ⚠️ 部分证据缺失 — 建议补充资格测试证据               │
│  • [MAN.3] ❌ 无可用证据 — 请提供项目管理计划/进度证据          │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 PDF

通过 weasyprint 将 HTML 转换为 PDF：

```bash
pip install weasyprint
yuleosh audit-report --format pdf
```

> **注意**: weasyprint 需要系统级依赖 (libpango, libffi)，在 macOS 上通过 `brew install pango` 安装，在 Linux 上通过 `apt-get install libpango-1.0-0`。

### 7.3 JSON

机器可读格式，可被其他工具消费：

```bash
yuleosh audit-report --format json
```

### 7.4 Text

CLI 友好的文本报告，可直接在终端查看：

```bash
yuleosh audit-report --format text
```

---

## 8. 扩展：自定义模板

如果需要定制报告内容/样式，可以继承 `AuditReportGenerator` 覆盖渲染方法：

```python
from yuleosh.report.audit_report import AuditReportGenerator

class CustomReportGenerator(AuditReportGenerator):
    """Custom audit report with OEM-specific branding."""
    
    def _render_html(self, report):
        # 自定义 HTML 模板
        return f"""<html>...{self._render_dimensions(report)}...</html>"""
    
    def export_pdf(self, report, output_path):
        # 使用自己的 PDF 渲染引擎
        ...
```

---

## 9. 与已有模块的集成

- **evidence collection** (`src/yuleosh/evidence/`): 生成器的证据来源
- **traceability** (`src/yuleosh/alm/traceability.py`): LRM/LRT 矩阵可作为 SWE.1 的补充证据
- **report** (`src/yuleosh/report/`): 与现有 exporter/card_generator 并列
- **CLI** (`src/yuleosh/cli/main.py`): 注册 `audit-report` 子命令
- **pipeline**: 在 CI 最终 stage 自动生成

---

## 10. 对标差异

| 功能 | Vector/dSPACE | yuleOSH (当前) |
|:-----|:-------------|:--------------|
| ASPICE 维度报告 | ✅ | ✅ (15 个过程维度) |
| 证据自动填充 | ✅ | ✅ (扫描 JSON + 推断) |
| PDF 输出 | ✅ | ✅ (需 weasyprint) |
| HTML 输出 | ✅ | ✅ (自包含) |
| JSON 输出 | ❌ | ✅ |
| 自定义模板 | ✅ | ⚠️ (可扩展继承) |
| 审核员协作 | ✅ | ❌ (计划 P3) |
| 审计历史对比 | ✅ | ❌ (计划 P3) |
| 一键上传到 Polarion | ✅ | ⚠️ (需手工导入) |

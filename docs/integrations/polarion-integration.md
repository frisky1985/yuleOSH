# Polarion 集成设计

支持 yuleOSH ↔ Polarion ALM 的双向追溯同步，导出证据链为 Polarion 可导入格式，使客户能在 Polarion 中直接查看 yuleOSH 的 ASPICE 证据。

---

## 1. 概述

| 项目 | 内容 |
|:-----|:------|
| 集成方式 | REST API + XML 导出 + 标签追溯 |
| 认证方式 | Bearer Token / Basic Auth |
| 已有代码 | `src/yuleosh/alm/polarion.py` — `PolarionBackend` 适配器 |
| 输出格式 | Polarion XML WorkItem 导入格式 / REST API v3 |

---

## 2. 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                     yuleOSH 平台                              │
│                                                              │
│  Evidence Packager                                           │
│    ↓                                                         │
│  Polarion Integrator                                        │
│    ├── REST API 同步 (双向)  →  Polarion Cloud               │
│    └── XML 导出 (离线)      →  Polarion 导入向导             │
│                                                              │
│  PolarionBackend (alm/polarion.py)                           │
│    ↓ REST API / SOAP API                                     │
│  Polarion (Siemens ALM)                                      │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 认证配置

### 3.1 Bearer Token (推荐)

```yaml
# .yuleosh/integrations/polarion.yaml
polarion:
  url: "https://polarion.example.com/polarion"
  auth_type: bearer
  token: "${YULEOSH_POLARION_TOKEN}"
  project_id: "BCM_Project"
```

### 3.2 Basic Auth (for on-premise)

```yaml
polarion:
  url: "https://polarion.internal.com/polarion"
  auth_type: basic
  username: "${YULEOSH_POLARION_USER}"
  password: "${YULEOSH_POLARION_PASSWORD}"
  project_id: "BCM_Project"
```

### 3.3 环境变量

```bash
export YULEOSH_POLARION_URL="https://polarion.example.com/polarion"
export YULEOSH_POLARION_TOKEN="your-api-token"
export YULEOSH_POLARION_PROJECT="BCM_Project"
```

---

## 4. 双向追溯同步

### 4.1 同步模型

同步以 **标签 (tag/label)** 为基础范围，支持增量同步。

```
yuleOSH (证据数据)                         Polarion (WorkItem)
─────────────────                         ──────────────────
REQ-BCM-001  ──tag:yuleosh-swe1──→  WorkItem: REQ-BCM-001
  status: approved                         status: approved
  version: 1.2                             custom: yuleosh_version
  
TC-BCM-001  ──tag:yuleosh-test──→  TestRun: TC-BCM-001
  last_run: passed                         result: passed
  history: [...]                           history: [...]
```

### 4.2 正向同步 (yuleOSH → Polarion)

```python
from yuleosh.alm.polarion import PolarionBackend

polarion = PolarionBackend()

# 同步所有 yuleosh 标签的 evidence
polarion.bulk_sync(label="yuleosh")

# 按维度同步
for process in ["SWE.1", "SWE.5", "SWE.6"]:
    polarion.bulk_sync(label=f"yuleosh-{process.lower()}")
```

**同步内容：**

| yuleOSH 数据 | Polarion 目标 | 同步方向 |
|:------------|:-------------|:---------|
| 需求条目 (requirements.json) | WorkItem (type: requirement) | 正向 |
| 测试用例 (test-cases.json) | TestCase / TestRun | 正向 |
| 测试运行结果 (last_run → history) | TestRecord | 正向 |
| MISRA 违规报告 | WorkItem (type: issue) | 正向 |
| ASPICE 审计报告 | Linked Document | 正向 |
| CI Pipeline 状态 | 自定义字段 + 评论 | 正向 |

### 4.3 反向同步 (Polarion → yuleOSH)

```python
# 获取 Polarion WorkItem 状态变更
evidence = polarion.sync_ticket_to_evidence("WI-12345")
# → 返回 {status, comments, tags, ...}
```

**同步内容：**

| Polarion 数据 | yuleOSH 接收 | 用途 |
|:-------------|:------------|:------|
| WorkItem status 变更 | 需求状态同步 | 保持 yuleOSH 需求与 Polarion 一致 |
| 评审意见 (comments) | 评审记录 | 可纳入 evidence chain |
| 附件/链接 | 可追溯 | — |

---

## 5. 离线导出：XML 格式

适用于无法直接 REST 访问 Polarion 的场景（如客户隔离网络）。

### 5.1 导出命令

```bash
# 导出所有证据为 Polarion 可导入 XML
yuleosh alm export --provider polarion \
  --format xml \
  --output ./polarion-export.xml

# 仅导出特定维度
yuleosh alm export --provider polarion \
  --label swe1 \
  --format xml \
  --output ./polarion-export-swe1.xml
```

### 5.2 XML 格式 (Polarion Import)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<polarion-import>
  <workitems>
    <workitem type="requirement" id="REQ-BCM-001">
      <title>Door lock shall respond within 10ms</title>
      <description>SHALL_DOOR_LOCK_RESPONSE: The door lock actuator SHALL...</description>
      <status>approved</status>
      <severity>critical</severity>
      <tags>
        <tag>yuleosh</tag>
        <tag>yuleosh-swe1</tag>
        <tag>asil-b</tag>
      </tags>
      <custom-fields>
        <custom-field id="yuleosh_version">1.2</custom-field>
        <custom-field id="yuleosh_priority">P0</custom-field>
        <custom-field id="yuleosh_asil">ASIL_B</custom-field>
      </custom-fields>
      <linked-workitems>
        <linked-workitem role="parent">REQ-BCM-002</linked-workitem>
        <linked-workitem role="parent">REQ-SAF-001</linked-workitem>
        <linked-workitem role="verifies">TC-BCM-001</linked-workitem>
      </linked-workitems>
    </workitem>

    <workitem type="testcase" id="TC-BCM-001">
      <title>Door lock response time — nominal condition</title>
      <description>Verify that the door lock actuator reaches...</description>
      <tags>
        <tag>yuleosh</tag>
        <tag>yuleosh-test</tag>
      </tags>
      <test-steps>
        <step>Send authenticated unlock command via CAN</step>
        <step>Start timer on CAN Tx confirmation</step>
        <step>Monitor actuator feedback pin via ADC</step>
        <step>Stop timer when feedback pin transitions above 2.5 V</step>
        <step>Record measured response time</step>
      </test-steps>
      <linked-workitems>
        <linked-workitem role="verifies">REQ-BCM-001</linked-workitem>
      </linked-workitems>
    </workitem>
  </workitems>

  <testruns>
    <testrun id="TR-BCM-001" testcase="TC-BCM-001">
      <result>passed</result>
      <duration>7.2 ms</duration>
      <executed-by>yuleosh CI</executed-by>
      <executed-at>2026-07-24T14:00:00Z</executed-at>
      <pipeline-id>ci-run-bcm-20260724-001</pipeline-id>
    </testrun>
  </testruns>
</polarion-import>
```

### 5.3 导出流程

```
data/requirements/requirements.json
data/tests/test-cases.json
.stack/evidence/*.json
        │
        ▼
  PolarionXmlExporter
        │
        ▼
  polarion-export.xml
        │
        ▼
  → Polarion Admin → Import WorkItems
  → 或 REST API POST /import
```

---

## 6. 证据链导出

### 6.1 证据链 → Polarion Linked Document

yuleOSH 的 ASPICE 证据链可以打包成 Polarion 可附加的 Linked Document：

```bash
# 生成 Polarion 兼容的证据链包
yuleosh evidence pack --format polarion --output ./evidence-pack.zip

# 一步式: 打包 + 上传到 Polarion WorkItem
yuleosh evidence sync --provider polarion --target WI-12345
```

### 6.2 证据链包内容

```
evidence-pack.zip
├── polarion-manifest.xml          # Polarion Linked Document manifest
├── aspice-report.html             # 审计报告 (HTML 可内嵌)
├── requirements.json              # 需求数据
├── test-cases.json                # 测试用例数据
├── misra-report.json              # MISRA 检查结果
├── coverage-report.json           # 覆盖率报告
└── evidence-chain.json            # 完整证据链索引
```

---

## 7. ASPICE 证据维度 → Polarion 映射

| ASPICE 维度 | yuleOSH 证据 | Polarion WorkItem Type | 标签 |
|:-----------|:------------|:-----------------------|:-----|
| SWE.1 | 需求条目 | `requirement` | `yuleosh-swe1` |
| SWE.2 | 架构文档/评审 | `document` | `yuleosh-swe2` |
| SWE.3 | 代码/设计评审 | `code_review` | `yuleosh-swe3` |
| SWE.4 | 单元测试结果 | `testcase` | `yuleosh-swe4` |
| SWE.5 | 集成测试结果 | `testcase` | `yuleosh-swe5` |
| SWE.6 | 资格测试结果 | `testcase` | `yuleosh-swe6` |
| SUP.1 | 质量审计报告 | `audit` | `yuleosh-sup1` |
| SUP.9 | 缺陷/问题 | `issue` | `yuleosh-sup9` |

---

## 8. CLI 命令

```bash
# 测试连接
yuleosh alm test --provider polarion

# 同步所有标签
yuleosh alm sync --provider polarion --label yuleosh

# 仅预览要同步的内容 (dry-run)
yuleosh alm sync --provider polarion --dry-run

# 导出离线 XML
yuleosh alm export --provider polarion --format xml -o export.xml

# 查看集成状态
yuleosh alm status --provider polarion
```

---

## 9. 现有代码集成

`src/yuleosh/alm/polarion.py` 已提供完整的：
- `PolarionBackend.create_ticket()` — 创建 WorkItem
- `PolarionBackend.update_status()` — 更新 WorkItem 状态
- `PolarionBackend.sync_evidence_to_ticket()` — 正向证据同步
- `PolarionBackend.sync_ticket_to_evidence()` — 反向状态同步
- `PolarionBackend.bulk_sync()` — 批量同步
- `PolarionBackend._add_tag()` — 标签管理

需要补充的：
- `PolarionXmlExporter` — XML 离线导出工具
- `EvidencePacker` — 证据链打包工具

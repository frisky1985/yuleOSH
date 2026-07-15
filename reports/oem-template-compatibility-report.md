# OEM 追溯矩阵模板兼容性分析报告

> **项目**: yuleOSH — OEM Template Adapter  
> **生成时间**: 2026-07-15  
> **分析范围**: `src/yuleosh/evidence/oem_templates.py`  
> **测试覆盖**: `tests/test_oem_templates.py` (31 个测试用例)

---

## 1. 背景

老陈在行业评审中指出：**yuleOSH 输出的追溯矩阵格式可能不匹配 OEM（VW/Audi/BMW/Mercedes）要求的标准格式**。在 ASPICE CL2/CL3 审计现场，被客户退回追溯矩阵意味着整次审计失败。

当前 yuleOSH 的追溯输出格式（来自 `trace_by_req_id()`, `get_aspice_coverage()`, `get_confirmation_trace()`）是内部 KG 原生格式（`Node.to_dict()`/`Edge.to_dict()`），缺少：

- OEM 特定的列命名规范（德语/英语混合）
- 审计要求的额外字段（ASIL 等级、签审人、安全完整性等级）
- 标准化的输出格式（CSV / 固定列宽 Markdown / JSON schema）
- 排序规则（按需求 ID 排序）
- layer 过滤（unit/integration/sil/hil）

## 2. 实现方案

### 2.1 新增文件

**`src/yuleosh/evidence/oem_templates.py`** — OEM Template Adapter

核心 API：
```python
export_traceability_matrix(
    store,                    # KGStore 实例
    template="generic",       # OEM 模板名
    output_format="markdown", # markdown | csv | json
    filter_layer=None,        # unit / integration / sil / hil
    include_test_evidence=True,
) -> str
```

### 2.2 支持的 OEM 模板

| 模板名 | display_name | 列数 | 语种 | 适用场景 |
|--------|-------------|------|------|---------|
| `generic` | Generic ASPICE Traceability Matrix | 13 | 英文 | 通用 ASPICE 审计 |
| `vw` | Volkswagen Traceability Matrix | 18 | 德语 | VW 80000 / VDA ASPICE |
| `bmw` | BMW Traceability Matrix | 16 | 德语 | BMW Group ASPICE |
| `mercedes` | Mercedes-Benz Traceability Matrix | 18 | 德语 | MB.ASIL 审计 |
| `oem_common` | OEM Common Minimum Traceability Matrix | 9 | 英文 | 跨 OEM 最小公共集 |

### 2.3 模板定义结构

每个模板定义包含：

```python
{
    "display_name":        str,      # 模板显示名称
    "description":         str,      # 中文描述
    "column_map":          dict,     # yuleOSH内部字段 → OEM列名
    "required_columns":    list,     # 有序输出列名
    "sort_key":            str,      # 排序依据列
    "sort_reverse":        bool,     # 是否降序
    "extra_columns":       dict,     # 额外字段及默认值
    "header_style":        str,      # 表头样式
}
```

### 2.4 数据流

```
KGStore
  ├─ list_nodes("requirement")        → 需求节点
  ├─ list_edges("implements")         → 需求→代码 追溯
  ├─ list_edges("covers")            → 需求→测试 追溯
  └─ list_edges("verifies")          → 测试→代码 确认
         │
         ▼
  _build_trace_rows()                → _TraceRow[]
         │
         ▼
  _map_and_sort_rows()               → dict[] (OEM列名映射 + 排序)
         │
         ├─ _format_markdown()        → str (Markdown表格)
         ├─ _format_csv()              → str (CSV格式)
         └─ _format_json()             → str (JSON格式)
```

### 2.5 CLI 集成

新增命令：
```bash
yuleosh traceability export --template generic --format markdown
yuleosh traceability export --template vw --format csv
yuleosh traceability export --template mercedes --format json
yuleosh traceability export --template bmw --format markdown --layer unit
```

输出文件保存至 `.yuleosh/reports/traceability-{template}-matrix.{ext}`。

## 3. 各 OEM 模板列映射

### 3.1 Generic（通用 ASPICE）

| yuleosh 内部字段 | OEM 列名 |
|:--------------------|:----------------|
| req_id | Requirement ID |
| req_title | Requirement Title |
| req_statement | Requirement Statement |
| test_id | Test Case ID |
| test_name | Test Case Name |
| test_file | Test File |
| test_type | Test Level |
| test_verdict | Test Verdict |
| test_evidence | Test Evidence |
| code_file | Implementation File |
| code_function | Implementation Function |
| layer | Layer |
| trace_type | Trace Type |
| build_id | Build ID |

### 3.2 VW（Volkswagen）

| OEM 列名 | 来源 | 说明 |
|:----------------------------|:------------------------------|:----|
| VW-Anforderungs-ID | req_id | 需求ID（VW格式前缀） |
| Bezeichnung | req_title | 需求标题 |
| Anforderungstext | req_statement | 需求正文 |
| Quelle | req_source | 文档来源 |
| ASIL | req_asil | 安全完整性等级 |
| Ebene | req_layer | 系统/软件层级 |
| Testfall-ID | test_id | 测试用例ID |
| Testfallbezeichnung | test_name | 测试名称 |
| Testdatei | test_file | 测试文件路径 |
| Teststufe | test_type | 测试阶段 |
| Testergebnis | test_verdict | 测试结果 |
| Testnachweis | test_evidence | 测试证据链接 |
| Implementierungsdatei | code_file | 实现文件 |
| Funktion | code_function | 函数名 |
| Prüfer | reviewer | 评审人（额外字段） |
| Geprüft am | reviewed_at | 评审日期（额外字段） |
| ASPICE-Schicht | layer | ASPICE层级 |
| Verbindungstyp | trace_type | 追溯关系类型 |
| Build-ID | build_id | CI Build编号 |

### 3.3 BMW

| OEM 列名 | 来源 | 说明 |
|:-------------------------------|:------------------------|:----|
| BMW-Anforderungs-ID | req_id | 需求ID |
| Titel | req_title | 标题 |
| Beschreibung | req_statement | 描述 |
| ASIL / Safety Level | req_asil | ASIL安全等级 |
| Quelle / Dokument | req_source | 来源文档 |
| Test-Fall-ID | test_id | 测试用例ID |
| Test-Name | test_name | 测试名称 |
| Test-Level | test_type | 测试层级 |
| Testergebnis | test_verdict | 测试结果 |
| Nachweis-Dokument | test_evidence | 证据文档 |
| SW-Komponente | code_file | 软件组件 |
| SW-Funktion | code_function | 软件函数 |
| Reviewer | reviewer | 评审人（额外字段） |
| Review-Datum | reviewed_at | 评审日期（额外字段） |
| SW-Schicht | layer | 软件层级 |
| Mapping-Typ | trace_type | 映射类型 |

### 3.4 Mercedes-Benz

| OEM 列名 | 来源 | 说明 |
|:-----------------------------------------|:-----------------------|:----|
| MBN-Anforderungs-ID | req_id | MBN格式需求ID |
| Titel / Kurzbeschreibung | req_title | 标题 |
| Anforderungsbeschreibung | req_statement | 需求描述 |
| Sicherheitsintegritätsstufe (ASIL) | req_asil | 安全完整性等级 |
| Quelle (ASPICE PA / System) | req_source | 来源 |
| Prüfspezifikations-ID | test_id | 测试规范ID |
| Prüfbezeichnung | test_name | 测试名称 |
| Prüfstufe | test_type | 测试阶段 |
| Prüfergebnis | test_verdict | 测试结果 |
| Prüfnachweis | test_evidence | 测试证据 |
| Implementierung (Datei) | code_file | 实现文件 |
| Implementierung (Funktion) | code_function | 实现函数 |
| Verantwortlicher Prüfer | reviewer | 负责评审人（额外字段） |
| Prüfdatum | reviewed_at | 评审日期（额外字段） |
| Abdeckungsgrad (%) | coverage_pct | 覆盖率百分比（额外字段） |
| Build-Nummer | build_id | 构建编号 |
| ASPICE-Ebene | layer | ASPICE层级 |
| Verbindungsart | trace_type | 连接类型 |

### 3.5 OEM Common（最小公共集）

| OEM 列名 | 来源 |
|:----------------|:---------------|
| Requirement ID | req_id |
| Requirement Title | req_title |
| Test Case ID | test_id |
| Test Name | test_name |
| Test Level | test_type |
| Verdict | test_verdict |
| Evidence Link | test_evidence |
| Implementation | code_file |
| Relation | trace_type |

## 4. 测试结果

全部 **31 个测试用例通过**。

| 测试类 | 测试数 | 说明 |
|:---------------------------|:------|:-----|
| `TestTemplates` | 7 | 模板结构完整性检查 |
| `TestExportMarkdownFormat` | 5 | Markdown输出格式 |
| `TestExportCsvFormat` | 4 | CSV输出格式 |
| `TestExportJsonFormat` | 4 | JSON输出格式 |
| `TestExportWithLayerFilter` | 3 | layer过滤功能 |
| `TestExportEmptyStore` | 3 | 空KG优雅降级 |
| `TestExportUnknownTemplate` | 2 | 未知模板降级到generic |
| `TestExportInvalidFormat` | 1 | 非法格式参数异常 |
| `TestGetTemplate` | 2 | 模板解析逻辑 |

### 4.1 手动验证示例

以下为 MockKGStore 输出的 Generic Markdown 矩阵片段：

```markdown
# Generic ASPICE Traceability Matrix

> Generated: 2026-07-15T18:54:00
> Template: Generic ASPICE Traceability Matrix
> Rows: 3

| Requirement ID | Requirement Title | Requirement Statement | Test Case ID | Test Name | ... |
|---|---|---|---|---|---|
| RS-BRAKE-001 | 刹车灯控制 | 系统应在刹车踏板被踩下时点亮刹车灯 | tests/test_brake_control.py | Test Brake Control | ... |
| RS-INDICATOR-001 | 转向灯控制 | 系统应在转向拨杆被操作时点亮相应转向灯 | tests/test_indicator_control.py | Test Indicator Control | ... |
| RS-TEMP-001 | 温度监控 | 系统应持续监控环境温度并报告异常 |  |  | ... |
```

## 5. 约束检查

| 约束 | 状态 |
|:-----|:-----|
| 不修改现有 KV 查询 API | ✅ `queries.py` 未修改 |
| 不修改 `trace_by_req_id()` 等函数 | ✅ 使用 `list_nodes()`/`list_edges()` 底层 API |
| 全量回归通过 | ✅ 45 个测试通过 |
| 空 store 优雅降级 | ✅ 返回 "（无追溯数据）" |
| 未知模板降级 | ✅ 降级到 `generic` |
| 非法 format 参数 | ✅ 抛出 ValueError |

## 6. 后续建议

1. **OEM 模板扩展** — 可继续添加 Audi / Stellantis / Bosch 等客户自定义模板
2. **Excel 输出** — 基于已存在的 `excel_writer.py`，可扩展.xlsx 输出
3. **模板版本化** — 当 OEM 更新审计格式时，可通过模板版本兼容
4. **CSV 编码处理** — 德语特殊字符 (ä/ö/ü/ß) 在当前标准库处理中已兼容
5. **签名/水印** — 可利用已有的 `signer.py` 为导出矩阵添加数字签名

---

*Report generated by yuleOSH OEM Template Adapter analysis*

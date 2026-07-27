# 需求管理看板 (Requirements Dashboard)

对标 Vector PREEvision 的需求管理功能，提供需求条目的全生命周期管理、版本追溯、状态看板。

---

## 1. 概述

需求管理看板是 yuleOSH 的质量入口，所有开发工作从需求出发。

| 对标对象 | 能力 | yuleOSH 实现 |
|:---------|:-----|:-------------|
| Vector PREEvision | 需求条目/版本/状态/变更历史 | 需求看板 Web UI + JSON 数据层 |
| Polarion ALM | 需求追溯矩阵 (SWE.1) | 内置 LRM/LRT 生成 |
| IBM DOORS | 需求链接分析 | 跨条目链接 + 影响分析 |

---

## 2. 数据模型

### 2.1 需求条目结构

每条需求存储在 `data/requirements/requirements.json` 中，结构如下：

| 字段 | 类型 | 描述 | 示例 |
|:-----|:-----|:-----|:-----|
| `id` | string | 需求唯一 ID | `REQ-BCM-001` |
| `title` | string | 需求标题 | `Door lock shall respond within 10ms` |
| `description` | string | 完整 SHALL 定义 | `SHALL_DOOR_LOCK_RESPONSE: ...` |
| `priority` | string | 优先级 | `P0` / `P1` / `P2` |
| `status` | string | 当前状态 | `draft` → `review` → `approved` → `implemented` → `verified` |
| `version` | string | 当前版本 | `1.2` |
| `asil` | string | ASIL 等级 | `QM` / `ASIL_A` / `ASIL_B` / `ASIL_C` / `ASIL_D` |
| `source` | string | 来源 | `customer` / `safety` / `internal` |
| `tags` | string[] | 标签 | `["door", "lock", "timing"]` |
| `category` | string | 分类 | `functional` / `safety` / `technical` / `non-functional` |
| `created_at` | string | 创建时间 | `2026-07-01T08:00:00Z` |
| `updated_at` | string | 最后更新时间 | `2026-07-20T14:30:00Z` |
| `approved_by` | string | 批准人 ID | `ou_manager_mock` |
| `owner` | string | 负责人 ID | `ou_swe_mock` |
| `history` | VersionChange[] | 版本变更历史 | 见 2.2 |
| `linked_req_ids` | string[] | 关联需求 ID | `["REQ-BCM-002", "REQ-SAF-001"]` |
| `linked_test_ids` | string[] | 关联测试用例 ID | `["TC-BCM-001", "TC-BCM-002"]` |
| `linked_risk_ids` | string[] | 关联风险 ID | `["HAZ-DOOR-001"]` |

### 2.2 版本变更历史

```json
{
  "version": "1.2",
  "status": "approved",
  "timestamp": "2026-07-20T14:30:00Z",
  "author": "ou_manager_mock",
  "change": "Approved for ASIL_B implementation"
}
```

### 2.3 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "title", "description", "priority", "status", "version"],
    "properties": {
      "id":         { "type": "string", "pattern": "^REQ-[A-Z]+-\\d{3}$" },
      "title":      { "type": "string", "minLength": 1 },
      "description":{ "type": "string", "minLength": 1 },
      "priority":   { "type": "string", "enum": ["P0", "P1", "P2", "P3"] },
      "status":     { "type": "string", "enum": ["draft", "review", "approved", "implemented", "verified", "rejected"] },
      "version":    { "type": "string", "pattern": "^\\d+\\.\\d+$" },
      "asil":       { "type": "string", "enum": ["QM", "ASIL_A", "ASIL_B", "ASIL_C", "ASIL_D", ""] },
      "source":     { "type": "string", "enum": ["customer", "safety", "internal", "system"] },
      "created_at": { "type": "string", "format": "date-time" },
      "updated_at": { "type": "string", "format": "date-time" },
      "history": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["version", "status", "timestamp", "change"],
          "properties": {
            "version":   { "type": "string" },
            "status":    { "type": "string" },
            "timestamp": { "type": "string", "format": "date-time" },
            "author":    { "type": "string" },
            "change":    { "type": "string" }
          }
        }
      }
    }
  }
}
```

---

## 3. 需求生命周期 / 状态看板

### 3.1 状态流

```
  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌───────────┐    ┌─────────┐
  │ draft   │ →  │ review  │ →  │ approved│ →  │implemented│ →  │verified │
  │ 草稿    │    │ 评审中  │    │ 已批准  │    │ 已实现    │    │ 已验证   │
  └─────────┘    └─────────┘    └─────────┘    └───────────┘    └─────────┘
       │              │              │
       ↓              ↓              ↓
  ┌─────────┐    ┌─────────┐    ┌─────────┐
  │rejected │    │ rejected│    │rejected │
  │ 退回    │    │ 退回    │    │ 退回    │
  └─────────┘    └─────────┘    └─────────┘
```

### 3.2 看板列

| 列 | 含义 | 用户操作 | 自动操作 |
|:---|:-----|:---------|:---------|
| 📝 草稿 | 需求初始创建 | 起草/编辑需求 | 无 |
| 🔍 评审中 | 提交给 Reviewer 审查 | 添加评审意见/批准/退回 | 发送 Feishu 通知 |
| ✅ 已批准 | Review 通过 | — | 标记可进入开发 |
| ⚙️ 已实现 | 开发完成提交 | 关联代码/测试 | pipeline RTE stage 完成后自动标记 |
| 🎯 已验证 | 测试通过 | — | pipeline 测试 stage 全部通过后自动标记 |
| ❌ 已退回 | 评审/验证不通过 | 修改后重新提交 | 清空状态流转 |

### 3.3 优先级定义

| 等级 | 定义 | SLA | 颜色 |
|:-----|:-----|:----|:-----|
| P0 | 安全关键或阻塞性 | 24h 内响应 | 🔴 |
| P1 | 核心功能 | 3d 内进入开发 | 🟡 |
| P2 | 增强/舒适功能 | 按 Sprint 排期 | 🔵 |
| P3 | 远期/低优先级 | 排入 Backlog | ⚪ |

---

## 4. Dashboard 页面 Mockup

### 4.1 布局

```
┌─────────────────────────────────────────────────────────────────────┐
│  📋 需求看板  ·  BCM Project  v1.5.0                                │
│  [全部: 10]  [P0: 3]  [P1: 3]  [P2: 2]  [草稿: 1] [评审中: 2] ...  │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ Filter: [ID/关键词] [状态:∨] [优先级:∨] [ASIL:∨] [           ] │ │
│  ├──────┬──────────────────────┬──────────┬──────┬──────┬─────────┤ │
│  │ ID   │ 标题                  │ 优先级   │ ASIL │ 状态  │ 版本    │ │
│  ├──────┼──────────────────────┼──────────┼──────┼──────┼─────────┤ │
│  │001   │ Door lock response   │ P0 🔴   │ B    │ ✅已批│ v1.2   │ │
│  │002   │ No unlock while moving│ P0 🔴   │ B    │ ⚙️已实│ v1.1   │ │
│  │003   │ Lighting PWM freq    │ P1 🟡   │ QM   │ ✅已批│ v1.0   │ │
│  │004   │ Diagnostic fault     │ P1 🟡   │ B    │ 🔍评审│ v1.1   │ │
│  │005   │ Wiper intermittent   │ P2 🔵   │ QM   │ 📝草稿│ v1.0   │ │
│  │006   │ OTA via UDS          │ P1 🟡   │ B    │ 🎯已验证│v1.0   │ │
│  │007   │ Power brownout       │ P0 🔴   │ B    │ 🔍评审│ v1.2   │ │
│  └──────┴──────────────────────┴──────────┴──────┴──────┴─────────┘ │
│  [新建需求]  [批量导入]  [导出 CSV]  [生成 RTM]                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 详情面板（点击条目展开）

```
┌──────────────────────────────────────────────────────────────────────┐
│  REQ-BCM-001: Door lock shall respond within 10ms                    │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ 描述: SHALL_DOOR_LOCK_RESPONSE: The door lock actuator SHALL... ││
│  │ 优先级: P0  |  ASIL: ASIL_B  |  来源: customer  |  版本: v1.2  ││
│  │ 负责人: ou_swe_mock  |  批准人: ou_manager_mock                 ││
│  ├──────────────────────────────────────────────────────────────────┤│
│  │ 变更历史:                                                        ││
│  │  v1.2 ✅ 2026-07-20 Approved for ASIL_B implementation          ││
│  │  v1.1 🔍 2026-07-10 Clarified measurement point                 ││
│  │  v1.0 📝 2026-07-01 Initial creation                            ││
│  ├──────────────────────────────────────────────────────────────────┤│
│  │ 关联物件                                                         ││
│  │  需求: REQ-BCM-002 · REQ-SAF-001                                ││
│  │  测试: TC-BCM-001 ✅ · TC-BCM-002 ⏳                             ││
│  │  风险: HAZ-DOOR-001                                             ││
│  └──────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. API Endpoints

需求看板对应的 REST API：

| 方法 | 路径 | 描述 |
|:-----|:-----|:-----|
| `GET` | `/api/v1/requirements?project={id}` | 获取需求列表（支持 filter/sort/paginate） |
| `GET` | `/api/v1/requirements/{req_id}` | 获取单条需求详情（含 History） |
| `POST` | `/api/v1/requirements` | 创建新需求 |
| `PUT` | `/api/v1/requirements/{req_id}` | 更新需求 |
| `PATCH` | `/api/v1/requirements/{req_id}/status` | 变更需求状态 |
| `POST` | `/api/v1/requirements/{req_id}/version` | 创建新版本快照 |
| `GET` | `/api/v1/requirements/{req_id}/history` | 获取版本变更历史 |
| `GET` | `/api/v1/requirements/dashboard?status=review` | 获取看板视图数据 |
| `GET` | `/api/v1/requirements/report/rtm` | 导出 RTM 追溯矩阵 |

---

## 6. 与已有模块的集成

- **pipeline stages**: MISRA 违规、Build 失败自动更新关联需求状态为 review
- **Loop Engineering Loop 1**: 缺陷自动创建新需求/修订
- **Traceability (alm/traceability.py)**: 直接从 `requirements.json` 生成 LRM/LRT 矩阵
- **审计报告**: `report/audit_report.py` 将需求作为 SWE.1 证据输入

## 7. 对标差异

| 功能 | Vector PREEvision | yuleOSH (当前) |
|:-----|:-----------------|:--------------|
| 需求条目 CRUD | ✅ | ✅ |
| 状态工作流 | ✅ | ✅ (5 states) |
| 版本历史 | ✅ | ✅ |
| 需求链接分析 | ✅ | ✅ (双向关联) |
| 可执行需求 | ✅ (SysML) | ❌ (plain text SHALL) |
| 需求模拟验证 | ✅ | ❌ (计划 P3) |
| 变更影响分析 | ✅ | ⚠️ (通过 KG 影响图部分实现) |
| 多人实时协作 | ✅ | ⚠️ (需要多租户 P2-4) |

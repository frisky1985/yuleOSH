# 测试用例管理库 (Test Case Library)

对标 dSPACE AutomationDesk / Vector CAST 的测试用例管理能力，提供结构化测试用例存储、自动运行、历史追踪和回归选择。

---

## 1. 概述

测试用例库是 yuleOSH 质量闭环的关键环节，支持从需求自动到测试的追溯、CI 集成运行、回归集裁剪。

| 对标对象 | 能力 | yuleOSH 实现 |
|:---------|:-----|:-------------|
| dSPACE AutomationDesk | 测试用例结构化 + 参数化 | JSON schema + 参数化 steps |
| Vector CAST | 测试与需求双向追溯 | `requirement_ids` 字段 + LRM 集成 |
| Polarion Test Management | 历史结果 + 回归选择 | `history` 数组 + `regression_priority` |

---

## 2. 数据模型

测试用例库主文件：`data/tests/test-cases.json`

### 2.1 顶层结构

```json
{
  "_meta": {
    "version": "1.0",
    "description": "yuleOSH Test Case Library",
    "generated_at": "2026-07-27T01:00:00Z",
    "total_cases": 16,
    "schema_url": "https://yuleosh.dev/schemas/test-case/v1"
  },
  "test_cases": [ ... ],
  "test_categories": {
    "functional":  { "description": "Functional verification (SWE.5)", "count": 7 },
    "robustness":  { "description": "Robustness testing (SWE.6)",      "count": 5 },
    "safety":      { "description": "Safety mechanism verification",   "count": 4 }
  },
  "regression_sets": {
    "always":    { "description": "Run every CI",  "case_ids": ["TC-BCM-001", ...] },
    "on_change": { "description": "Run on module change", "case_ids": [...] },
    "on_demand": { "description": "Manual trigger", "case_ids": [...] }
  }
}
```

### 2.2 测试用例条目结构

| 字段 | 类型 | 描述 | 示例 |
|:-----|:-----|:-----|:-----|
| `id` | string | 用例唯一 ID | `TC-BCM-001` |
| `title` | string | 用例标题 | `Door lock response time — nominal` |
| `description` | string | 详细描述 | `Verify that the door lock actuator reaches...` |
| `requirement_ids` | string[] | 关联需求 ID 列表 | `["REQ-BCM-001"]` |
| `preconditions` | string[] | 前置条件 | `["BCM powered at 13.5V", "HSM session active"]` |
| `steps` | string[] | 测试步骤 | `["Send unlock command", "Start timer", ...]` |
| `expected_results` | string | 期望结果 | `Response time ≤ 10 ms` |
| `verification_method` | string | 验证方法 | `test` / `analysis` / `review` / `inspection` |
| `tags` | string[] | 标签 | `["door", "lock", "timing"]` |
| `category` | string | 分类 | `functional` / `safety` / `robustness` / `regression` |
| `test_level` | string | ASPICE 测试级别 | `SWE.4` / `SWE.5` / `SWE.6` / `SYS.4` / `SYS.5` |
| `asil` | string | ASIL 等级 | `QM` / `ASIL_B` |
| `automation` | string | 自动化程度 | `automated` / `semi-automated` / `manual` |
| `last_run` | RunResult | 最近一次运行结果 | 见 2.3 |
| `history` | RunResult[] | 历史运行记录 | 过去所有运行记录 |
| `regression_priority` | string | 回归优先级 | `always` / `on_change` / `on_demand` |

### 2.3 运行结果结构

```json
{
  "run_id": "ci-run-bcm-20260724-001",
  "status": "passed",
  "timestamp": "2026-07-24T14:00:00Z",
  "measured_value": "7.2 ms",
  "runner": "yuleosh.testgen.runner",
  "error": "Exceeded 10 ms threshold — actuator driver optimization needed"
}
```

### 2.4 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["_meta", "test_cases"],
  "properties": {
    "_meta": {
      "type": "object",
      "required": ["version", "total_cases"],
      "properties": {
        "version": {"type": "string"},
        "description": {"type": "string"},
        "generated_at": {"type": "string", "format": "date-time"},
        "total_cases": {"type": "integer", "minimum": 0},
        "schema_url": {"type": "string", "format": "uri"}
      }
    },
    "test_cases": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "title", "steps", "expected_results"],
        "properties": {
          "id": {"type": "string", "pattern": "^TC-[A-Z]+-\\d{3}$"},
          "title": {"type": "string", "minLength": 1},
          "description": {"type": "string"},
          "requirement_ids": {
            "type": "array",
            "items": {"type": "string", "pattern": "^REQ-"}
          },
          "preconditions": {
            "type": "array",
            "items": {"type": "string"}
          },
          "steps": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1
          },
          "expected_results": {"type": "string", "minLength": 1},
          "verification_method": {
            "type": "string",
            "enum": ["test", "analysis", "review", "inspection"]
          },
          "test_level": {
            "type": "string",
            "enum": ["SWE.4", "SWE.5", "SWE.6", "SYS.4", "SYS.5"]
          },
          "asil": {
            "type": "string",
            "enum": ["QM", "ASIL_A", "ASIL_B", "ASIL_C", "ASIL_D"]
          },
          "automation": {
            "type": "string",
            "enum": ["automated", "semi-automated", "manual"]
          },
          "last_run": {
            "type": "object",
            "properties": {
              "run_id": {"type": "string"},
              "status": {"type": "string", "enum": ["passed", "failed", "skipped", "error"]},
              "timestamp": {"type": "string", "format": "date-time"},
              "measured_value": {"type": "string"},
              "runner": {"type": "string"},
              "error": {"type": "string"}
            }
          },
          "history": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["run_id", "status", "timestamp"],
              "properties": {
                "run_id": {"type": "string"},
                "status": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "measured": {"type": "string"},
                "error": {"type": "string"}
              }
            }
          },
          "regression_priority": {
            "type": "string",
            "enum": ["always", "on_change", "on_demand"]
          }
        }
      }
    },
    "test_categories": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "description": {"type": "string"},
          "count": {"type": "integer"}
        }
      }
    },
    "regression_sets": {
      "type": "object",
      "patternProperties": {
        "^[a-z_]+$": {
          "type": "object",
          "required": ["description", "case_ids"],
          "properties": {
            "description": {"type": "string"},
            "case_ids": {
              "type": "array",
              "items": {"type": "string"}
            }
          }
        }
      }
    }
  }
}
```

---

## 3. 测试分类/标签体系

### 3.1 类别 (Categories)

| 类别 | 描述 | ASPICE 映射 | 占比建议 |
|:-----|:-----|:-----------|:---------|
| `functional` | 功能需求验证 | SWE.5 | 40–50% |
| `robustness` | 鲁棒性/边界测试 | SWE.6 | 20–30% |
| `safety` | 安全机制验证 | SWE.6 + ISO 26262 | 15–20% |
| `regression` | 回归测试 | — | 10% |
| `performance` | 性能/时序验证 | Non-functional | 5% |

### 3.2 标签 (Tags)

标签用于灵活筛选和分组，例如：
- `door`, `lock`, `lighting`, `wiper` — 按功能域
- `can`, `lin`, `uds` — 按通信协议
- `timing`, `power`, `memory` — 按质量属性
- `ota`, `diagnostics`, `dem` — 按子系统
- `fail-safe`, `signal-loss`, `fault-injection` — 按测试手法

---

## 4. 回归选择策略

### 4.1 三级回归集

| 优先级 | 触发条件 | 用例数量 | 运行时间 |
|:-------|:---------|:---------|:---------|
| `always` | 每次 CI 运行 | 核心 + 安全 (12/16) | ~5 min |
| `on_change` | 相关模块文件发生变更 | 影响域 (3/16) | ~2 min |
| `on_demand` | 手动触发或 Nightly 构建 | 全部含耗时环境 (1/16) | ~30 min * |

\* 环境依赖较重的测试（如极端温度箱测试）仅在 On-Demand 模式运行。

### 4.2 智能回归集选择（计划 P3）

通过变更影响分析自动计算需要运行的回归集：
1. 检测 git diff 涉及的模块
2. 查询 KG 影响图确定受影响的 SWC/功能
3. 查找关联测试用例
4. 自动组装 `on_change` 回归集

---

## 5. Dashboard 页面 Mockup

```
┌──────────────────────────────────────────────────────────────────────┐
│  🧪 测试用例库 · BCM Project · 16 cases                              │
│  [全部]  [功能性: 7]  [鲁棒性: 5]  [安全: 4]  [回归集: always▶]      │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ 🔍 [搜索用例/ID]  [分类:∨] [ASIL:∨] [自动化:∨] [运行状态:∨]   ││
│  ├───────┬────────────────────────┬──────────┬──────┬──────┬───────┤│
│  │ ID    │ 标题                    │ 需求     │ ASIL │ 结果 │ 回归  ││
│  ├───────┼────────────────────────┼──────────┼──────┼──────┼───────┤│
│  │001    │ Door lock response     │ BCM-001  │ B    │ ✅ 7.2ms│ ★   ││
│  │002    │ Lock response - temp   │ BCM-001  │ B    │ ⏳    │ ○   ││
│  │003    │ No unlock >5km/h       │ BCM-002  │ B    │ ✅  │ ★   ││
│  │004    │ Speed signal loss      │ BCM-002  │ B    │ ✅  │ ★   ││
│  │005    │ PWM frequency          │ BCM-003  │ QM   │ ✅  │ ◇  ││
│  │006    │ DEM open-load          │ BCM-004  │ B    │ ⏳ 未跑│ ★   ││
│  └───────┴────────────────────────┴──────────┴──────┴──────┴───────┘│
│                                                                      │
│  回归集: ★ = always   ◇ = on_change   ○ = on_demand                  │
│  [新建用例]  [导入/导出]  [运行回归]  [查看历史趋势]                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 用例详情面板

```
┌──────────────────────────────────────────────────────────────────────┐
│  TC-BCM-001: Door lock response time — nominal condition             │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ 需求: REQ-BCM-001 · ASIL_B · 测试级别: SWE.5 · 自动化: 自动    ││
│  ├──────────────────────────────────────────────────────────────────┤│
│  │ 前置条件:                                                        ││
│  │ ① BCM powered at 13.5 V ± 0.1 V                                ││
│  │ ② HSM session active with valid auth token                      ││
│  ├──────────────────────────────────────────────────────────────────┤│
│  │ 步骤:                                                            ││
│  │ ① Send authenticated unlock command via CAN (UDS 0x2F)          ││
│  │ ② Start timer on CAN Tx confirmation                            ││
│  │ ③ Monitor actuator feedback pin via ADC                         ││
│  │ ④ Stop timer when feedback pin transitions above 2.5 V          ││
│  │ ⑤ Record measured response time                                 ││
│  ├──────────────────────────────────────────────────────────────────┤│
│  │ 期望: Response time ≤ 10 ms from CAN Tx to feedback pin trans.  ││
│  ├──────────────────────────────────────────────────────────────────┤│
│  │ 历史运行:                                                        ││
│  │  ✅ 2026-07-24  7.2 ms  (passed)                                ││
│  │  ✅ 2026-07-23  8.1 ms  (passed)                                ││
│  │  ❌ 2026-07-22  11.4 ms (failed — exceeded 10ms threshold)      ││
│  └──────────────────────────────────────────────────────────────────┘│
|  [编辑] [重新运行] [关联需求] [克隆] [删除]                           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 6. API Endpoints

| 方法 | 路径 | 描述 |
|:-----|:-----|:-----|
| `GET` | `/api/v1/testcases?project={id}` | 获取测试用例列表（支持 filter/sort） |
| `GET` | `/api/v1/testcases/{tc_id}` | 获取单个用例详情 |
| `POST` | `/api/v1/testcases` | 创建新测试用例 |
| `PUT` | `/api/v1/testcases/{tc_id}` | 更新用例定义 |
| `POST` | `/api/v1/testcases/{tc_id}/run` | 触发单个用例运行 |
| `POST` | `/api/v1/testcases/regression` | 按回归集运行 |
| `GET` | `/api/v1/testcases/regression/sets` | 获取回归集定义 |
| `GET` | `/api/v1/testcases/{tc_id}/history` | 获取历史运行记录 |
| `GET` | `/api/v1/testcases/stats?period=week` | 测试统计（趋势/通过率） |

---

## 7. 与已有模块的集成

- **testgen**: `src/yuleosh/testgen/runner.py` 读取 `test-cases.json` 执行自动化用例
- **pipeline CI**: CI Layer 2/3 stage 自动调度 `regression_priority: always` 的用例
- **traceability**: `alm/traceability.py` 的 LRM 矩阵将测试用例映射回需求
- **audit report**: `report/audit_report.py` 将测试用例作为 SWE.5/SWE.6 证据
- **dSPACE adapter**: `adapter/dspace_adapter.py` 可将用例导出为 AutomationDesk XML
- **Dashboard**: 历史运行趋势图表

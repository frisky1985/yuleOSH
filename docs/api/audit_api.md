# 审计 (`audit`) API 参考

> 代码根:`src/yuleosh/audit/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`audit` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/audit.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .audit import handle_audit` |
| `# projects).  ``/api/v1/audit`` is served ONLY by api.audit.handle_audit` |
| `"audit": handle_audit,` |
| `logging.getLogger("yuleosh.audit").warning(` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_canonical_json` | `(data: dict)` | Canonical JSON for hash computation (stable key order). | `audit/model.py:99` |
| `compute_event_hash` | `(event_dict: dict, prev_hash: str)` | Compute the SHA-256 hash of an event payload plus its predecessor. | `audit/model.py:104` |
| `compute_prompt_hash` | `(prompt: str)` | SHA-256 of the exact prompt text sent to the model. | `audit/model.py:116` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `AuditEvent` | `()` | An immutable audit event record. | `audit/model.py:125` |
| `AuditLog` | `()` | File-system-backed append-only audit log. | `audit/model.py:201` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `AuditEvent.__init__` | `(self, actor: str, action: str, target: str, timestamp: str, tenant: str, detail: Optional[dict], model: Optional[str], prompt_hash: Optional[str], reviewed_by: Optional[str], reviewed_at: Optional[str], event_hash: str, prev_hash: str)` | — | `audit/model.py:132` |
| `AuditEvent.to_dict` | `(self)` | — | `audit/model.py:154` |
| `AuditEvent.from_dict` | `(cls, data: dict)` | — | `audit/model.py:178` |
| `AuditLog.__init__` | `(self, data_root: Optional[str])` | — | `audit/model.py:212` |
| `AuditLog.record` | `(self, actor: str, action: str, target: str, timestamp: str, tenant: str, detail: Optional[dict], model: Optional[str], prompt_hash: Optional[str], reviewed_by: Optional[str], reviewed_at: Optional[str])` | Record an audit event. Returns the AuditEvent. | `audit/model.py:231` |
| `AuditLog.record_ai_generation` | `(self, actor: str, target: str, model: str, prompt: str, prompt_hash: str, tenant: str, reviewed_by: str, reviewed_at: str, detail: Optional[dict])` | Record an AI-generated artifact (draft) into the SHA-256 audit chain. | `audit/model.py:334` |
| `AuditLog.sign_ai_generation` | `(self, reviewer: str, target: str, prompt_hash: Optional[str], tenant: str, note: str, actor: str)` | Append a human review sign-off for a previously recorded AI draft. | `audit/model.py:383` |
| `AuditLog.verify` | `(self, tenant: str, from_date: str, to_date: str)` | Verify the integrity of the audit hash chain. | `audit/model.py:470` |
| `AuditLog.query` | `(self, tenant: str, from_date: str, to_date: str, action: str, actor: str, limit: int)` | Query audit events with optional filters. | `audit/model.py:558` |
| `AuditLog.get_summary` | `(self, tenant: str, from_date: str, to_date: str)` | Get a summary of audit events grouped by action type. | `audit/model.py:625` |

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.audit import <公共符号>
# 详见 docs/modules/audit.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 12 处生产引用(Grep `yuleosh.audit` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/audit/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

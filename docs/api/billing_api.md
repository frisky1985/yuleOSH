# 计费 (`billing`) API 参考

> 代码根:`src/yuleosh/billing/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`billing` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/billing.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `"billing": ("yuleosh.ui.routes.billing_routes", "handle_billing"),` |
| `from yuleosh.billing.metering import (` |
| `def handle_billing(method: str, path_tail: str, body: dict, query: dict,` |
| `if not check_role(user, "billing", "view"):` |
| `if not check_role(user, "billing", "view"):` |
| `if not check_role(user, "billing", "upgrade"):` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

_(无模块级函数或均在子模块内)_

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `UsageEntry` | `()` | A single usage metric entry. | `billing/metering.py:86` |
| `UsageMeter` | `()` | File-system-backed usage metering. | `billing/metering.py:98` |
| `MockStripeSession` | `()` | Mock Stripe Checkout Session for testing without real API key. | `billing/metering.py:208` |
| `BillingManager` | `()` | Billing and subscription management. | `billing/metering.py:222` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `UsageMeter.__init__` | `(self, data_root: Optional[str])` | — | `billing/metering.py:107` |
| `UsageMeter.increment` | `(self, tenant: str, resource: str, amount: int)` | Record a usage event. | `billing/metering.py:126` |
| `UsageMeter.increment_ci_run` | `(self, tenant: str)` | Convenience: record a CI run. | `billing/metering.py:137` |
| `UsageMeter.get_monthly_usage` | `(self, tenant: str, month: str)` | Get aggregated usage for a given month. | `billing/metering.py:141` |
| `UsageMeter.get_usage_summary` | `(self, tenant: str, plan: str)` | Get usage summary with limits comparison. | `billing/metering.py:168` |
| `UsageMeter.is_within_limits` | `(self, tenant: str, plan: str)` | Check if tenant is within plan limits. Returns check results. | `billing/metering.py:189` |
| `MockStripeSession.__init__` | `(self, customer_id: str, price_id: str, tenant: str, plan: str)` | — | `billing/metering.py:211` |
| `BillingManager.__init__` | `(self, data_root: Optional[str])` | — | `billing/metering.py:228` |
| `BillingManager.create_checkout_session` | `(self, tenant: str, plan: str, customer_id: str, success_url: str, cancel_url: str)` | Create a Stripe Checkout Session for upgrading. | `billing/metering.py:251` |
| `BillingManager.handle_webhook` | `(self, payload: dict)` | Handle Stripe webhook events (mock mode). | `billing/metering.py:302` |
| `BillingManager.get_subscription` | `(self, tenant: str)` | Get current subscription for a tenant. | `billing/metering.py:364` |
| `BillingManager.cancel_subscription` | `(self, tenant: str)` | Cancel (downgrade to free). | `billing/metering.py:378` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `STRIPE_SECRET_KEY` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.billing`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/ui/routes/billing_routes.py:19
from yuleosh.billing.metering import (

```

> 共 1 个文件引用本子系统；完整调用图见 `docs/modules/billing.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 2 处生产引用(Grep `yuleosh.billing` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/billing/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

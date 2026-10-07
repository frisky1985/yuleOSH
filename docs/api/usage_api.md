# 用量计量 (`usage`) API 参考

> 代码根:`src/yuleosh/usage/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`usage` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/usage.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `if sub == "usage":` |
| `return handle_usage_check(method, path_tail, body, query, handler)` |
| `def handle_usage_check(method: str, path_tail: str, body: dict, query: dict,` |
| `"usage": {` |
| `handle_usage,` |
| `path_tail: "usage" | "plan" | "upgrade"` |
| `if method == "GET" and sub == "usage":` |
| `usage_data = usage.get("usage", {})` |
| `from yuleosh.usage.metering import TIERS` |
| `"usage": {` |
| `def handle_usage(handler: BaseHTTPRequestHandler) -> dict:` |
| `from yuleosh.usage.metering import get_usage_summary` |
| `from yuleosh.usage.metering import get_usage_summary` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `get_org_tier` | `(store, org_id: int)` | Get the current subscription tier for an org. | `usage/metering.py:70` |
| `get_trial_status` | `(store, org_id: int)` | Get trial status for an org. | `usage/metering.py:78` |
| `check_tier_limit` | `(store, org_id: int, resource: str)` | Check if an org has exceeded a resource limit. Returns {allowed, limit, used, message}. | `usage/metering.py:108` |
| `record_pipeline_run` | `(store, org_id: int, project_id: int, llm_tokens: int, user_id: int | None, run_id: str | None, user_email: str | None)` | Record a pipeline run for usage metering. | `usage/metering.py:134` |
| `get_usage_summary` | `(store, org_id: int)` | Get usage summary with tier limits. | `usage/metering.py:153` |
| `is_stripe_configured` | `()` | Check if Stripe is configured. | `usage/stripe_gateway.py:22` |
| `create_checkout_session` | `(org_id: int, tier: str, email: str, org_slug: str)` | Create a Stripe Checkout session for subscription. | `usage/stripe_gateway.py:27` |
| `handle_stripe_webhook` | `(payload: bytes, signature: str)` | Process Stripe webhook events. | `usage/stripe_gateway.py:59` |

### 3.2 公共类

_(无顶层类)_

### 3.3 类关键公共方法(节选)

_(无)_

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.usage import <公共符号>
# 详见 docs/modules/usage.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 6 处生产引用(Grep `yuleosh.usage` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/usage/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

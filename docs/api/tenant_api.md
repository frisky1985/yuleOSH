# 多租户 (`tenant`) API 参考

> 代码根:`src/yuleosh/tenant/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`tenant` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/tenant.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `"tenant": ("yuleosh.ui.routes.tenant_routes", "handle_tenant"),` |
| `"tenants": ("yuleosh.ui.routes.tenant_routes", "handle_tenant_list"),` |
| `from yuleosh.tenant.model import TenantStore` |
| `def handle_tenant(method: str, path_tail: str, body: dict, query: dict,` |
| `return handle_tenant_info(method, path_tail, body, query, handler)` |
| `return handle_tenant_projects(method, path_tail, body, query, handler)` |
| `return handle_tenant_update(method, path_tail, body, query, handler)` |
| `return handle_tenant_project_create(method, path_tail, body, query,` |
| `def handle_tenant_info(method: str, path_tail: str, body: dict, query: dict,` |
| `def handle_tenant_update(method: str, path_tail: str, body: dict, query: dict,` |
| `def handle_tenant_list(method: str, path_tail: str, body: dict, query: dict,` |
| `def handle_tenant_projects(method: str, path_tail: str, body: dict, query: dict,` |
| `def handle_tenant_project_create(method: str, path_tail: str, body: dict,` |
| `"tenant": tenant.id,` |
| `Security (P0): requires a valid Bearer session (tenant_routes._require_auth);` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `"tenant": usage.get("tenant", tenant_slug),` |
| `"tenant": tenant_slug,` |
| `from yuleosh.tenant.model import TenantStore` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

_(无模块级函数或均在子模块内)_

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `Tenant` | `()` | A multi-tenant organization in the yuleOSH platform. | `tenant/model.py:68` |
| `TenantStore` | `()` | File-system-backed tenant persistence layer. | `tenant/model.py:109` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `Tenant.limits` | `(self)` | — | `tenant/model.py:89` |
| `Tenant.has_feature` | `(self, feature: str)` | — | `tenant/model.py:92` |
| `Tenant.to_dict` | `(self)` | — | `tenant/model.py:96` |
| `Tenant.from_dict` | `(cls, data: dict)` | — | `tenant/model.py:100` |
| `TenantStore.__init__` | `(self, data_root: Optional[str])` | — | `tenant/model.py:120` |
| `TenantStore.get` | `(self, slug: str)` | Get tenant by slug. Returns None if not found. | `tenant/model.py:133` |
| `TenantStore.get_or_create` | `(self, slug: str, name: str, plan: str)` | Get existing tenant or create a new one. | `tenant/model.py:141` |
| `TenantStore.create` | `(self, slug: str, name: str, plan: str)` | Create a new tenant with the given slug. | `tenant/model.py:148` |
| `TenantStore.update` | `(self, slug: str, **kwargs)` | Update tenant fields in-place. | `tenant/model.py:170` |
| `TenantStore.delete` | `(self, slug: str)` | Remove tenant metadata and data directory. | `tenant/model.py:182` |
| `TenantStore.list_tenants` | `(self)` | List all tenants. | `tenant/model.py:194` |
| `TenantStore.save_project` | `(self, slug: str, project_data: dict)` | Save a project definition under the tenant's projects directory. | `tenant/model.py:208` |
| `TenantStore.get_project` | `(self, slug: str, project_slug: str)` | Get a project by slug within a tenant. | `tenant/model.py:219` |
| `TenantStore.list_projects` | `(self, slug: str)` | List all projects for a tenant. | `tenant/model.py:226` |
| `TenantStore.delete_project` | `(self, slug: str, project_slug: str)` | Delete a project by slug. | `tenant/model.py:236` |
| `TenantStore.get_config` | `(self, slug: str, key: str, default)` | Get a tenant config value. | `tenant/model.py:246` |
| `TenantStore.set_config` | `(self, slug: str, key: str, value)` | Set a tenant config value. | `tenant/model.py:253` |

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.tenant import <公共符号>
# 详见 docs/modules/tenant.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 3 处生产引用(Grep `yuleosh.tenant` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/tenant/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

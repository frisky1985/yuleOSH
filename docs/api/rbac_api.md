# 角色权限 (`rbac`) API 参考

> 代码根:`src/yuleosh/rbac/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`rbac` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/rbac.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from yuleosh.rbac import check_role` |
| `from yuleosh.rbac import check_role` |
| `from yuleosh.rbac import check_role` |
| `from yuleosh.rbac import check_role` |
| `from yuleosh.rbac import check_role` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `get_role_from_user_info` | `(user_info: Optional[dict])` | Extract the permission-tier string from decoded user info. | `rbac/model.py:214` |
| `check_role` | `(user_info: Optional[dict], required_resource: str, required_action: str)` | Check if the user's role has permission for the given resource/action. | `rbac/model.py:229` |
| `require_role` | `(required_resource: str, required_action: str)` | Decorator: require permission to access a route handler. | `rbac/model.py:253` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `Role` | `()` | Represents a role with its permissions. | `rbac/model.py:162` |
| `PermissionSet` | `()` | Holds all permissions for a given role. | `rbac/model.py:183` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `Role.__init__` | `(self, name: str)` | — | `rbac/model.py:165` |
| `Role.can` | `(self, resource: str, action: str)` | Check if this role has permission for (resource, action). | `rbac/model.py:171` |
| `PermissionSet.__init__` | `(self, role_name: str)` | — | `rbac/model.py:186` |
| `PermissionSet.can` | `(self, resource: str, action: str)` | — | `rbac/model.py:189` |
| `PermissionSet.resources` | `(self)` | List all resources this role can access. | `rbac/model.py:192` |
| `PermissionSet.to_dict` | `(self)` | Return a human-readable permission dict. | `rbac/model.py:202` |

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.rbac`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/ui/routes/billing_routes.py:82
from yuleosh.rbac import check_role

# src/yuleosh/ui/routes/project_routes.py:165
from yuleosh.rbac import check_role

# src/yuleosh/api/audit.py:72
from yuleosh.rbac import check_role

# src/yuleosh/api/members.py:29
from yuleosh.rbac.role_contract import INVITABLE_ROLES

```

> 共 4 个文件引用本子系统；完整调用图见 `docs/modules/rbac.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 6 处生产引用(Grep `yuleosh.rbac` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/rbac/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

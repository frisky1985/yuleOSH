# 合规检查 (`compliance`) API 参考

> 代码根:`src/yuleosh/compliance/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`compliance` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/compliance.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .compliance import handle_compliance` |
| `"compliance": handle_compliance,` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_extract_req_ids` | `(text: str)` | Extract unique requirement identifiers matching any known ID form. | `compliance/compliance_checker.py:38` |
| `_profile_search_paths` | `(name: str, profile_dir: Optional[Path])` | — | `compliance/profile.py:213` |
| `_find_profile_file` | `(name: str, profile_dir: Optional[Path])` | — | `compliance/profile.py:222` |
| `_require` | `(cond: bool, field_path: str, message: str)` | — | `compliance/profile.py:234` |
| `_validate` | `(data: dict, name: str)` | 校验 yaml 结构：缺字段与未知字段两类错误均带路径与修复提示。 | `compliance/profile.py:239` |
| `_yaml_to_profile` | `(data: dict)` | 把已校验的 yaml dict 无损映射到 StandardProfile。 | `compliance/profile.py:291` |
| `load_profile` | `(name: str, profile_dir: Optional[Path])` | 加载并校验一个合规标准 profile (A1-03)。 | `compliance/profile.py:336` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `ComplianceChecker` | `()` | Check a project directory for ASPICE v3.1 compliance. | `compliance/compliance_checker.py:46` |
| `EvidenceSpec` | `()` | 单条产出证据描述 (yaml: ``base_practices[].output_evidence[]``)。 | `compliance/profile.py:24` |
| `BasePractice` | `()` | 基础实践 (yaml: ``base_practices[]``)。 | `compliance/profile.py:33` |
| `ProcessArea` | `()` | 过程域 (yaml 顶层键 ``swe.1``~``swe.6`` 等)。 | `compliance/profile.py:43` |
| `ProfileMeta` | `()` | 标准元信息 (yaml: ``meta``)。 | `compliance/profile.py:55` |
| `StandardProfile` | `()` | 一个完整合规标准的强类型表示 (yaml 顶层)。 | `compliance/profile.py:64` |
| `ProfileError` | `(Exception)` | profile 校验错误，携带字段路径与修复提示。 | `compliance/profile.py:188` |
| `ProfileNotFoundError` | `(FileNotFoundError)` | profile 文件不存在；携带可用清单作为修复提示。 | `compliance/profile.py:196` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `ComplianceChecker.__init__` | `(self, project_dir: str, template_path: Optional[Path], profile: Optional['StandardProfile'])` | — | `compliance/compliance_checker.py:49` |
| `ComplianceChecker.run` | `(self)` | Run the full compliance check and return the report. | `compliance/compliance_checker.py:1250` |
| `ComplianceChecker.generate_report_markdown` | `(self, report: dict)` | Format the compliance check report as markdown. | `compliance/compliance_checker.py:1310` |
| `ComplianceChecker.run_and_save` | `(self, output_path: Optional[str])` | Run compliance check, save markdown report, return file path. | `compliance/compliance_checker.py:1389` |
| `StandardProfile.standard` | `(self)` | 标准名 (mirror of ``meta.standard``)。 | `compliance/profile.py:94` |
| `StandardProfile.version` | `(self)` | 标准版本 (mirror of ``meta.version``)。 | `compliance/profile.py:99` |
| `StandardProfile.area_by_id` | `(self, area_id: str)` | 按过程域 id 检索（如 ``swe.1``）。 | `compliance/profile.py:103` |
| `StandardProfile.all_base_practice_ids` | `(self)` | 返回所有 base_practice id（扁平、保序）。 | `compliance/profile.py:110` |
| `StandardProfile.to_template_dict` | `(self)` | 把 ``StandardProfile`` 还原为 ``ComplianceChecker`` 消费的 template dict。 | `compliance/profile.py:117` |
| `ProfileError.__init__` | `(self, field_path: str, message: str)` | — | `compliance/profile.py:191` |
| `ProfileNotFoundError.__init__` | `(self, name: str, searched: List[Path], available: List[str])` | — | `compliance/profile.py:199` |

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.compliance`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/evidence/aspice_check.py:25
from yuleosh.compliance.compliance_checker import ComplianceChecker

# src/yuleosh/cli/onboard.py:318
from yuleosh.compliance.compliance_checker import ComplianceChecker

# src/yuleosh/cli/stats.py:193
from yuleosh.compliance.compliance_checker import _extract_req_ids

# src/yuleosh/cli/commands/compliance.py:24
from yuleosh.compliance.compliance_checker import ComplianceChecker

# src/yuleosh/api/router.py:38
from .compliance import handle_compliance

```

> 共 5 个文件引用本子系统；完整调用图见 `docs/modules/compliance.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 6 处生产引用(Grep `yuleosh.compliance` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/compliance/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

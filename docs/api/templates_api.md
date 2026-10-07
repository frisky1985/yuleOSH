# 模板 (`templates`) API 参考

> 代码根:`src/yuleosh/templates/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`templates` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/templates.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_discover_builtin_templates` | `()` | Discover all built-in templates from the templates/ directory. | `templates/__init__.py:30` |
| `_discover_user_templates` | `(base_dir: str | Path)` | Discover templates from a user/project-local directory. | `templates/__init__.py:52` |
| `list_templates` | `(project_root: Optional[str | Path])` | List all discoverable templates, deduplicated by name. | `templates/__init__.py:74` |
| `resolve_template` | `(name: str, project_root: Optional[str | Path])` | Resolve a template by name with search priority (TG-REQ-002). | `templates/__init__.py:108` |
| `get_template_dir` | `(template: dict)` | Get the resolved filesystem path for a template. | `templates/__init__.py:117` |
| `_sha256_file` | `(path: Path)` | — | `templates/golden.py:35` |
| `load_golden` | `(template_dir: Path)` | Load golden sample metadata from *template_dir*. | `templates/golden.py:41` |
| `compare_to_golden` | `(generated_dir: Path, golden: GoldenSample)` | Compare *generated_dir* against the golden sample. | `templates/golden.py:71` |
| `generate_golden` | `(template_dir: Path, output_dir: Path)` | Capture *output_dir* as the new golden sample for *template_dir*. | `templates/golden.py:135` |
| `discover_templates` | `()` | Scan ecus/ subdirectories for template.yaml and build a registry. | `templates/ecus/__init__.py:26` |
| `get_template` | `(name: str)` | Get a template by name. | `templates/ecus/__init__.py:48` |
| `list_ecu_templates` | `()` | List all available ECU templates with summary info. | `templates/ecus/__init__.py:54` |
| `_build_default_context` | `(template_name: str, project_name: str, mcu: str, asil: str, template_meta: dict[str, Any])` | Build the default Jinja2 rendering context from CLI args + template metadata. | `templates/ecus/__init__.py:86` |
| `_j2_env` | `(tpl_dir: Path)` | Create a Jinja2 environment rooted at the template directory. | `templates/ecus/__init__.py:121` |
| `init_project` | `(template_name: str, project_name: str, mcu: str, asil: str, output_dir: str, extra_context: Optional[dict[str, Any]])` | Render a Jinja2 ECU template into a new project directory. | `templates/ecus/__init__.py:136` |
| `_strip_j2_suffix` | `(filename: str)` | Remove .j2 suffix if present (handles nested suffixes like .c.j2 → .c). | `templates/ecus/__init__.py:266` |
| `main` | `()` | — | `templates/generic-python/src/main.py:5` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `GoldenSample` | `()` | — | `templates/golden.py:28` |

### 3.3 类关键公共方法(节选)

_(无)_

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.templates`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/project_detection.py:143
from yuleosh.templates import resolve_template

# src/yuleosh/cli/commands/misc.py:55
from yuleosh.templates import list_templates

# src/yuleosh/cli/commands/methodology.py:38
from yuleosh.templates import get_template_dir, resolve_template

# src/yuleosh/cli/main.py:573
from yuleosh.templates.ecus import get_template

```

> 共 4 个文件引用本子系统；完整调用图见 `docs/modules/templates.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 4 处生产引用(Grep `yuleosh.templates` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/templates/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

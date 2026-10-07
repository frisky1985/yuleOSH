# 模块设计速写：plugins（插件系统）

> 包：`src/yuleosh/plugins/` ｜ 规模：3 .py ≈ 819 行
> 定位：**已实现但未被接入（ORPHAN）**——非运行期扩展点

## 职责
插件系统：本地管理器（发现/加载/安装/卸载）、远程注册表（插件市场）、沙箱（安全执行）。证据：`plugins/__init__.py:4-9`、`registry.py:4-9`、`sandbox.py:4-12`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `plugins/__init__.py` (293) | 管理器 | `PluginManifest` `:29`；`PluginInfo` `:90`；`PluginManager` `:106`；`Plugin` `:267` |
| `plugins/registry.py` (276) | 远程注册表 | `RegistrySource` `:30`；`PluginRegistry` `:82`；`DEFAULT_SOURCES` `:69`（硬编码 GitHub index.json `:72`）；`search` `:130`；`download` `:183`（SHA256 校验） |
| `plugins/sandbox.py` (250) | 沙箱 | `SAFE_BUILTINS` `:34`；`SandboxViolation` `:59`；`PluginSandbox` `:68`；`execute` `:95`；`_restricted_import` `:215` |

## 公共 API / 入口点
- `PluginManager` / `PluginManifest` / `PluginInfo` / `Plugin`
- `PluginRegistry` / `RegistrySource` / `RegistryPluginEntry` / `PluginVersionEntry` / `DEFAULT_SOURCES`
- `PluginSandbox` / `SandboxViolation` / `SAFE_BUILTINS`

## 生产接线
- **唯一导入方** `skills/plugin_skills.py:19` `from yuleosh.plugins import PluginManifest, PluginManager`；而 `skills` CLI（`skills/cli.py`）只用 `get_registry()`，**完全不用** `PluginManager`/`PluginRegistry`/`PluginSandbox`。
- 构造函数调用 grep 仅命中各自 `__init__` 定义，**生产代码无任何实例化**。
- **结论：`PluginRegistry` 全仓零调用方（ORPHAN）；`PluginManager`/`PluginSandbox` 仅被从未实例化的 `SkillManager` 引用。整个插件市场 + 沙箱运行路径是死代码——仅模块被导入（执行类定义），不执行任何逻辑。**

## 运行时触发方式
- **不被调用**。无 `plugin` CLI 子命令（grep `build_plugin_subparser`/`add_parser("plugin")` 无结果；CLI 仅 `hook`/`skills`）。
- 唯一路径：进程导入 `yuleosh.skills` → `plugin_skills` → `yuleosh.plugins`（仅执行模块级类定义，无实例化/无执行）。

## 扩展机制（设计如此，但当前无入口）
- 本地：`PluginManager.discover` 扫 `plugins_dir` 下 `manifest.json`（`__init__.py:115-132`）；支持目录 /.yuleosh-plugin tar.gz / URL 安装（`install` `:146-222`）。
- 远程：`PluginRegistry._load_indexes` 拉 `index.json`（`registry.py:95-126`，SHA256 校验 `:183-223`）。
- 沙箱：`PluginSandbox.execute` 受限全局编译入口（`sandbox.py:95-133`），受限 `open`（`:159`）、受限 `import`（标准库白名单 `:215`）、超时（`:127`）。

## 环境变量 / 配置
- **模块本身不读环境变量**。注册表 URL + User-Agent（`registry.py:249,256` 硬编码 `yuleOSH/0.4.0`）均硬编码。

## 偏差 / 死代码（设计文档必记）
- **D1：`PluginRegistry` 完全孤立（零调用方）**；`PluginManager`/`PluginSandbox` 仅被未实例化的 `SkillManager` 引用。插件安装/搜索/下载/执行链路当前无入口。
- **D2：`PluginManifest.validate` 有 no-op 分支**（`:80-82`，相对 `entry` 路径直接 `pass`，注释「保留作为记录」）。
- **D3：`PluginSandbox.block_subprocess`（`sandbox.py:241`）从未被调用**、也未注入 `safe_globals`；子进程限制靠 `_restricted_import` 标准库白名单实现（文档字符串「限制系统调用」主要靠导入白名单）。

## 规模
3 .py ≈ 819 行。

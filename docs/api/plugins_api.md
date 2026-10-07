# 插件 (`plugins`) API 参考

> 代码根:`src/yuleosh/plugins/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`plugins` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/plugins.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

_(无模块级函数或均在子模块内)_

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `PluginManifest` | `()` | Plugin 元数据，对应 manifest.json 的 Python 表示。 | `plugins/__init__.py:30` |
| `PluginInfo` | `()` | 已安装插件的摘要信息。 | `plugins/__init__.py:91` |
| `PluginManager` | `()` | 插件管理器 — 发现、加载、安装、卸载本地插件。 | `plugins/__init__.py:106` |
| `Plugin` | `()` | 已加载的插件运行时包装。 | `plugins/__init__.py:267` |
| `RegistrySource` | `()` | 注册表源配置。 | `plugins/registry.py:31` |
| `PluginVersionEntry` | `()` | 插件版本条目（来源于注册表索引）。 | `plugins/registry.py:50` |
| `RegistryPluginEntry` | `()` | 插件在注册表中的条目。 | `plugins/registry.py:59` |
| `PluginRegistry` | `()` | Plugin 市场注册表 — 从远程源发现和下载插件。 | `plugins/registry.py:82` |
| `SandboxViolation` | `(Exception)` | 沙箱违规执行异常。 | `plugins/sandbox.py:59` |
| `PluginSandbox` | `()` | 插件沙箱 — 安全执行 Plugin 代码。 | `plugins/sandbox.py:68` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `PluginManifest.from_dict` | `(cls, data: dict)` | 从字典构建，忽略未知字段。 | `plugins/__init__.py:49` |
| `PluginManifest.from_file` | `(cls, path: str | Path)` | 从 manifest.json 文件加载。 | `plugins/__init__.py:56` |
| `PluginManifest.to_dict` | `(self)` | — | `plugins/__init__.py:62` |
| `PluginManifest.validate` | `(self)` | 返回验证错误列表，空列表表示通过。 | `plugins/__init__.py:65` |
| `PluginManager.__init__` | `(self, plugins_dir: str | Path)` | — | `plugins/__init__.py:109` |
| `PluginManager.discover` | `(self)` | 扫描 plugins_dir 下所有子目录，加载合法的 manifest.json。 | `plugins/__init__.py:115` |
| `PluginManager.load` | `(self, name: str)` | 加载指定名称的插件（返回 Plugin 包装对象）。 | `plugins/__init__.py:136` |
| `PluginManager.install` | `(self, source: str)` | 从本地路径或 URL 安装插件。 | `plugins/__init__.py:146` |
| `PluginManager.uninstall` | `(self, name: str)` | 卸载指定名称的插件。 | `plugins/__init__.py:226` |
| `PluginManager.list_installed` | `(self)` | 列出所有已安装插件的信息。 | `plugins/__init__.py:236` |
| `PluginManager.get_manifest` | `(self, name: str)` | 获取指定插件的 Manifest。 | `plugins/__init__.py:252` |
| `Plugin.__init__` | `(self, manifest: PluginManifest, directory: Path)` | — | `plugins/__init__.py:270` |
| `Plugin.name` | `(self)` | — | `plugins/__init__.py:275` |
| `Plugin.entry_path` | `(self)` | — | `plugins/__init__.py:279` |
| `RegistrySource.to_dict` | `(self)` | — | `plugins/registry.py:37` |
| `RegistrySource.from_dict` | `(cls, data: dict)` | — | `plugins/registry.py:41` |
| `PluginRegistry.__init__` | `(self, sources: Optional[list[RegistrySource]])` | — | `plugins/registry.py:85` |
| `PluginRegistry.search` | `(self, query: str)` | 搜索插件。 | `plugins/registry.py:130` |
| `PluginRegistry.get_details` | `(self, name: str)` | 获取指定插件的最新版本 Manifest。 | `plugins/registry.py:171` |
| `PluginRegistry.download` | `(self, name: str, version: str)` | 下载插件包到临时文件，返回本地路径。 | `plugins/registry.py:183` |
| `PluginRegistry.add_source` | `(self, source: RegistrySource)` | 添加自定义注册表源。 | `plugins/registry.py:227` |
| `PluginRegistry.remove_source` | `(self, name: str)` | 移除注册表源。 | `plugins/registry.py:232` |
| `PluginRegistry.clear_cache` | `(self)` | 清除索引缓存，下次搜索时重新加载。 | `plugins/registry.py:239` |
| `PluginSandbox.__init__` | `(self, plugin_dir: Path | str, manifest: PluginManifest | None, extra_read_dirs: Optional[list])` | 初始化沙箱。 | `plugins/sandbox.py:71` |
| `PluginSandbox.execute` | `(self, plugin: Plugin, args: dict[str, Any])` | 在沙箱中执行插件入口函数。 | `plugins/sandbox.py:95` |
| `PluginSandbox.block_subprocess` | `()` | 阻塞子进程创建（通过替换 os.system / os.popen / subprocess）。 | `plugins/sandbox.py:241` |

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.plugins import <公共符号>
# 详见 docs/modules/plugins.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 1 处生产引用(Grep `yuleosh.plugins` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/plugins/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

# skills API 参考
> 代码根:`src/yuleosh/skills/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述
`skills` 子系统提供**两套并存 API**:(1) **提示拼接技能库(v3.4.0)**——以 markdown `Skill` 为单位,经 `SkillRegistry` 注册并由 `render_skills` 注入 LLM 提示词(`src/yuleosh/skills/__init__.py:7-18`);(2) **插件编排技能存储(原始 API)**——`SkillManager`/`SkillManifest`/`Workflow`/`WorkflowStep` 把 Skill 视为插件工作流(`src/yuleosh/skills/__init__.py:20-26`,`src/yuleosh/skills/plugin_skills.py:4-10`)。内置 3 个技能(`autosar-coding`/`misra-fix`/`python-testing`)随 registry 首次访问自动注册(`src/yuleosh/skills/builtin.py:119`)。

## 2. HTTP 端点
本子系统**不对外暴露任何 REST 端点**。它以库形式被 `codegen/prompts.py`、`pipeline/knowledge_injection.py` 与 CLI(`cli/main.py:919` → `skills/cli.py`)使用。CLI 子命令 `yuleosh skills list|show` 经 `handle_skills_command` 分派(`src/yuleosh/skills/cli.py:17`)。

## 3. Python 公共 API

### 3.1 模块级函数
| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `get_registry` | `get_registry() -> SkillRegistry` | 返回进程级单例 registry(首次调用自动注册内置技能并尝试加载持久化技能) | `registry.py:163` |
| `set_registry` | `set_registry(registry) -> SkillRegistry` | 替换单例(测试/嵌入用);**无生产调用方,见 §6** | `registry.py:181` |
| `reset_registry` | `reset_registry() -> None` | 清空单例,下次 `get_registry` 重建;**无生产调用方,见 §6** | `registry.py:188` |
| `render_skills` | `render_skills(names, registry=None, max_chars_per_skill=4000) -> str` | 将给定技能渲染为 markdown 块以拼接进提示词;未知名跳过 | `prompt.py:27` |
| `resolve_skill_names` | `resolve_skill_names(names, registry=None) -> list[str]` | 规范化技能名输入并剔除未知名;**无生产调用方,见 §6** | `prompt.py:65` |
| `builtin_skills` | `builtin_skills() -> list[Skill]` | 返回内置技能的全新实例 | `builtin.py:119` |

### 3.2 公共类
| 类 | 关键方法(签名) | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `Skill` | `to_dict() -> dict`、`from_dict(data) -> Skill`、`render_header() -> str`、`render() -> str` | 可复用技能单元:name/title/description/content/tags/version/created_at | `model.py:20` |
| `SkillRegistry` | `register(skill, overwrite=False) -> bool`、`register_many(skills, overwrite=False) -> int`、`unregister(name) -> bool`、`get(name) -> Skill|None`、`list(tag=None) -> list[Skill]`、`names() -> list[str]`、`save(path=None) -> Path`、`load(path=None) -> int`、`load_default() -> int`、`save_default() -> Path`、`default_persist_path() -> Path` | 内存技能存储 + 可选 JSON 持久化(默认 `.osh/skills/skills.json`);注册时经 `knowledge.indexer` 非致命钩子沉淀 | `registry.py:38` |
| `SkillManager` | `__init__(skills_dir, plugin_manager)`、`discover_skills() -> list[SkillManifest]`、`get_skill(name) -> SkillManifest|None`、`run_skill(name, inputs) -> dict` | 插件编排:加载并拓扑执行 Skill 工作流;**无生产调用方,见 §6** | `plugin_skills.py:91` |
| `SkillManifest` | `from_dict(data) -> SkillManifest`、`from_file(path) -> SkillManifest` | 扩展 `PluginManifest`,增加 `workflow` 字段;**无生产调用方,见 §6** | `plugin_skills.py:65` |
| `Workflow` | `from_dict(data) -> Workflow` | 技能工作流定义(steps/outputs) | `plugin_skills.py:36` |
| `WorkflowStep` | — (dataclass:`id/plugin/inputs/depends_on/condition`) | 工作流步骤 | `plugin_skills.py:26` |

### 3.3 关键数据结构
| 结构 | 说明 | 文件:行 |
| --- | --- | --- |
| `@dataclass Skill` | 技能单元(name/title/description/content/tags/version/created_at,`created_at` 构造时自动设) | `model.py:20` |
| `@dataclass WorkflowStep` | 工作流步骤(id/plugin/inputs/depends_on/condition) | `plugin_skills.py:26` |
| `@dataclass Workflow` | 工作流(version/steps/outputs),含 `from_dict` | `plugin_skills.py:36` |
| `@dataclass SkillManifest`(继承 `PluginManifest`) | 技能清单(扩展 `workflow`) | `plugin_skills.py:65` |
| 常量 `HEADER` | `render_skills` 输出块头("## 📚 技能参考") | `prompt.py:21` |
| 常量 `BUILTIN_SKILL_NAMES` | `["autosar-coding","misra-fix","python-testing"]`;**无生产调用方,见 §6** | `builtin.py:149` |
| 常量 `DEFAULT_PERSIST_REL` | `".osh/skills/skills.json"`(持久化相对路径) | `registry.py:33` |

## 4. 配置 / 环境变量
| 变量 | 用途 | 文件:行 |
| --- | --- | --- |
| `OSH_HOME` | registry 持久化根目录;`SkillRegistry.default_persist_path()` 取 `OSH_HOME/skills/skills.json`,缺省 `.` | `registry.py:152` |

> 注:技能库本身不读取任何 LLM/密钥类环境变量;`render_skills` 仅消费 `SkillRegistry` 内存数据。

## 5. 调用示例

**示例 1 — 在 codegen/提示词中注入技能(基于 `prompt.py:27`,真实用法见 `codegen/prompts.py:16,147`)**
```python
from yuleosh.skills.prompt import render_skills

block = render_skills(["autosar-coding", "misra-fix"])
# 将 block 拼接到 system prompt 即可让模型遵循规范生成代码
```

**示例 2 — 注册并持久化自定义技能(基于 `model.py:20`、`registry.py:38,113`)**
```python
from yuleosh.skills.model import Skill
from yuleosh.skills.registry import get_registry

reg = get_registry()
reg.register(Skill(
    name="my-coding", title="我的编码规范",
    description="示例技能", content="## 规则\n- 禁止裸 int",
    tags=["c"],
))
reg.save_default()  # 写入 OSH_HOME/.osh/skills/skills.json
```

**示例 3 — CLI 查看技能(基于 `cli.py:17`)**
```bash
yuleosh skills list
yuleosh skills show misra-fix
```

## 6. 偏差 / 备注
- **`skills` 不是 ORPHAN**(整体):被 `codegen/prompts.py:16`、`cli/main.py:919`、`pipeline/knowledge_injection.py:214` 三处 import 使用,核心用途是提示词拼接。
- **`plugin_skills` 整套 API 为 ORPHAN(经 Grep `src/yuleosh/` 验证)**:
  `SkillManager` / `SkillManifest` / `Workflow` / `WorkflowStep`(`plugin_skills.py`)**仅在 `skills/__init__.py` 内部被 re-export 与同模块自引用**,全仓无任何生产模块 import 它们来执行技能工作流(既不是 `codegen`、`cli/main.py` 也不是 `pipeline/*` 的调用方)。属 v3.4.0 引入提示拼接库后保留的**遗留编排 API 死代码**(`__init__.py:20-26` 自述 "original API, preserved")。其中 `SkillManager.run_skill` 还依赖 `plugins.sandbox.PluginSandbox`(`plugin_skills.py:158`),若该依赖路径变动将直接失效。
- **包内其他无生产调用方符号(疑似 ORPHAN / 测试专用)**:
  - `registry.set_registry` / `reset_registry`(`registry.py:181,188`):仅 re-export,无生产 import(测试隔离用途)。
  - `prompt.resolve_skill_names`(`prompt.py:65`):无生产 import;`pipeline/knowledge_injection.py:107` 用的是同模块内独立的 `_resolve_skill_names`(下划线私有版),二者并非同一函数。
  - `builtin.BUILTIN_SKILL_NAMES`(`builtin.py:149`):定义并 re-export,但无生产 import(内置技能经由 `get_registry()` → `builtin_skills()` 自动注册,不依赖该常量列表)。
- **与直觉相悖**:
  - 同一包内"技能"有两个互斥语义——`Skill`(markdown 提示片段)与 `SkillManifest`(插件工作流),命名易混淆;实际生产只用前者(`render_skills` 路径),后者已无人调用。
  - `SkillRegistry.register` 在注册时会**非致命地**写知识索引(`registry.py:66-75`),即注册技能会产生跨子系统副作用(依赖 `yuleosh.knowledge.indexer`),异常仅 warning 不影响注册——属隐式耦合。

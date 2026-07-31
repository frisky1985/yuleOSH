# Skills 技能库 — 扩展指南

> yuleOSH v3.4.0 · `src/yuleosh/skills/` 从空模块升级为真实技能库

## 1. 概念

Skill = 一段可复用的**规范/模式文本**（Markdown），通过
`render_skills(names)` 拼接到 LLM prompt，让模型在生成代码、修复违规时
遵循团队约定。

```
Skill（name / title / description / content / tags）
   │
   ├─ SkillRegistry（内存注册表，可选 JSON 持久化）
   │
   ├─ render_skills(names) → Markdown → LLM prompt
   │
   └─ CLI: yuleosh skills list | show <name>
```

## 2. 内置技能（≥3）

| name | 用途 |
|---|---|
| `autosar-coding` | AUTOSAR C 编码规范要点（头文件/命名/标准类型/接口纪律） |
| `misra-fix` | MISRA 违规修复模式（类型转换/指针/switch 穿透/返回值） |
| `python-testing` | pytest 最佳实践（fixtures/mock/参数化/覆盖率） |

## 3. 添加新技能

### 3.1 代码内置（推荐，随版本分发）

在 `src/yuleosh/skills/builtin.py` 中：

```python
from yuleosh.skills.model import Skill

def builtin_skills() -> list[Skill]:
    return [
        # ... 已有技能 ...
        Skill(
            name="my-team-c",                        # 唯一标识（kebab-case）
            title="团队 C 编码约定",                  # 人类可读标题
            description="xxx 的编码要点。",           # 列表页一句话
            content="""### 要点
1. 规则一…
2. 规则二…
""",
            tags=["c", "team", "coding-standard"],
            version="1.0.0",
        ),
    ]
```

同时把新名字加进 `BUILTIN_SKILL_NAMES` 列表。

### 3.2 运行时注册（无需改代码）

```python
from yuleosh.skills import Skill, get_registry

registry = get_registry()
registry.register(Skill(name="my-skill", title="T", description="D", content="…"))
registry.save_default()   # 持久化到 .osh/skills/skills.json
```

重启后 `registry.load_default()` 会合并加载（已存在的条目不会被覆盖）。

### 3.3 在 prompt 中使用

```python
from yuleosh.skills import render_skills, resolve_skill_names

names = resolve_skill_names("autosar-coding, misra-fix")  # 过滤未知技能
skills_block = render_skills(names)
prompt = f"{system_prompt}\n\n{skills_block}"
```

- 未知技能名会被跳过（仅 warning），不会破坏调用方。
- 默认 codegen prompt 自动注入 `autosar-coding`，可通过
  `session.config["codegen"]["skills"]` 覆盖。

## 4. API 速查

| 接口 | 说明 |
|---|---|
| `Skill(name, title, description, content, tags=…)` | 数据模型 |
| `get_registry()` | 单例注册表（自动注册内置技能） |
| `registry.register(skill, overwrite=False) → bool` | 注册（重名拒绝） |
| `registry.register_many(skills) → int` | 批量注册 |
| `registry.get(name) → Skill\|None` | 查询 |
| `registry.list(tag=None) → list[Skill]` | 列表（可按 tag 过滤） |
| `registry.unregister(name) → bool` | 注销 |
| `registry.save(path=None) / load(path=None)` | JSON 持久化 |
| `render_skills(names, registry=None) → str` | 拼接为 prompt 块 |
| `resolve_skill_names(names) → list[str]` | 规范化+过滤未知 |

## 5. CLI

```bash
yuleosh skills list            # 列出全部技能
yuleosh skills list --json     # JSON 输出
yuleosh skills show misra-fix  # 查看技能全文
```

## 6. 测试

新技能请补充 `tests/test_skills_module.py` 用例（注册/查询/render/持久化），
覆盖要求 ≥60%。

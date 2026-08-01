# Code Generation (D3 编码生成闭环) — 使用说明

> yuleOSH v3.4.4 · Harness Coding 能力补全

## 1. 是什么

D3 编码生成闭环让 pipeline 的 `development` 步骤（`DevelopmentStep` / `step_claude_dev`）
从「只输出开发计划（development-plan.md）」升级为**直接产出可编译的目标语言代码**：

```
spec / 架构 / PRD + skills
        │
        ▼
   LLM 生成代码（### FILE: 标记格式）
        │
        ▼
   落盘 artifacts/generated-code/<session>/
        │
        ▼
   编译验证（py_compile / gcc -fsyntax-only / 项目构建命令）
        │
     失败? ──┐（带编译错误反馈重试，最多 3 次）
        │    │
      成功   └──► 记录失败原因到报告
        │
        ▼
   codegen-report.md（文件清单 / 验证结果 / 修复轮次）
```

**默认行为不变**：`generate-code` 是新增模式，未启用时 `development` 步骤仍输出
规划文档，与旧版完全一致。

## 2. 启用方式

### 2.1 通过 session 配置（pipeline 内推荐）

```python
from yuleosh.pipeline.session import PipelineSession

session = PipelineSession(
    name="my-run",
    spec_path="spec/brake-light.md",
    development_mode="generate-code",          # ← 开启 D3
    config={
        "codegen": {
            "skills": ["autosar-coding", "misra-fix"],  # 注入技能库（可选）
            "target_language": "C",                      # 目标语言提示（可选）
            "max_retries": 3,                            # 修复轮次上限（默认 3）
            "language": "c",                             # 强制验证语言（可选）
            "build_cmd": ["make", "-C", "build"],        # 项目构建命令（可选）
            "output_dir": "/path/to/custom",             # 自定义输出目录（可选）
        }
    },
)
```

### 2.2 通过步骤参数（类方式）

```python
from yuleosh.pipeline.step_classes import DevelopmentStep

step = DevelopmentStep(mode="generate-code", max_retries=3)
report_path = step(session)
```

优先级：`session.development_mode` 显式设置时以 session 为准，否则用构造参数。

### 2.3 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `OSH_CODEGEN_DIR` | 生成代码根目录（相对/绝对） | `<project>/artifacts/generated-code` |

## 3. 产物结构

```
artifacts/generated-code/<session-name>/
├── codegen-report.md        ← 生成报告（文件清单/验证结果/修复轮次）
├── src/…                    ← 生成的源代码文件（相对项目根路径）
└── …
```

`codegen-report.md` 包含：

- **Status**：`verified`（编译通过）/ `failed`（重试耗尽）/ `no-files`（LLM 未产出文件）
- **Generated Files**：全部落盘文件清单
- **Verification**：语言、验证命令、返回码、编译输出
- **Repair Rounds**：尝试轮次与最后一次错误

## 4. 验证方式

按生成文件的扩展名自动选择验证器：

| 语言 | 命令 |
|---|---|
| Python (`.py`) | `python3 -m py_compile <files>` |
| C/C++ (`.c/.h/.cpp/…`) | `gcc -fsyntax-only -std=c11 -Wall <files>`（无 gcc 时退回 `cc`） |
| 其他 | 需在 `codegen.build_cmd` 提供项目构建命令，否则验证失败 |

编译失败时，引擎把错误输出拼进下一次 LLM 请求（"🔧 编译验证失败 — 请修复后重新输出全部文件"），
最多重试 `max_retries`（默认 3）次。

## 5. LLM 输出格式

引擎解析两种格式（都支持）：

1. **标记格式**（推荐）：

   ```
   ### FILE: src/brake_light.c
   ```c
   /* ...完整代码... */
   ```
   ```

2. **JSON 格式**：

   ```json
   {"files": [{"path": "src/a.py", "content": "print(1)", "language": "python"}]}
   ```

路径会做安全清洗（剥离 `../`、前导 `/`），防止逃逸输出目录。

## 6. 程序化使用

```python
from yuleosh.codegen import CodegenEngine, parse_generated_files, build_codegen_prompt

sys_prompt, user_prompt = build_codegen_prompt(
    spec_content=spec_text, spec_name="x.md",
    architecture_content=arch_text, prd_content=prd_text,
    skills=["autosar-coding"],          # skills → prompt 拼接
    target_language="C",
)
engine = CodegenEngine(max_retries=3, llm_client=my_client)
result = engine.generate(session, sys_prompt, user_prompt)
print(result.status, result.files, result.report_path)
```

## 7. 范围外

- 不改动 pipeline 其他步骤行为（默认模式仍输出 planning）
- 不做多语言编译器沙箱（仅本机工具链）
- 不接入外部 agent 框架

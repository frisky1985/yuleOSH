# OpenSpec 规范管理改造 — 需求总体架构

> **日期**: 2026-08-18
> **状态**: 已评审（老板拍板 A+C）
> **关联**: `.yuleosh/agents/RULES.md §11 需求原子化`

## 1. 目标

让 yuleOSH 平台原生支持 OpenSpec 规范管理：项目规范按
`.osh/specs/<capability>/spec.md` 结构化组织（每 capability 独立目录、
独立演进），平台所有 spec 消费方（validate / spec-check / spec_contracts /
pipeline 主链路 / methodology_gate）统一识别该结构；新项目 init 即生成
OpenSpec 骨架；规则固化要求新项目用 OpenSpec。

## 2. 边界

- **范围内**: `spec validate` CLI、`spec_contracts`、pipeline spec-check
  步骤、init 模板、RULES.md 规则、window-anti-pinch 项目示范拆分
- **范围外**: 不改变单文件 `spec.md` 的兼容支持（向后兼容）；
  不改 spec 语法解析器本身（parse_spec 已支持 OpenSpec 格式）
- **验收底线**: 构建 + 单测 + coverage 全绿；全量回归不引入契约漂移

## 3. 核心模块划分（按领域职责命名）

| 模块 | 职责 | 现有基础 |
|:--|:--|:--|
| `spec/validate.py` | 目录聚合校验入口（新增 `validate_spec_dir` / CLI 目录参数） | parse_spec 单文件 |
| `spec_contracts.py` | 目录聚合契约抽取（新增 `contracts_check_dir`） | extract_contracts 单文件 |
| `pipeline/step_handlers/spec.py` | spec-check 自动发现 OpenSpec 目录 | 单文件 spec_path |
| `pipeline/session.py` | spec_path 支持目录解析 | 单文件 resolve |
| `templates/methodology/` | init 生成 OpenSpec 骨架（`.osh/specs/README.md` + 示例 capability） | specs/spec.md 单文件 |
| `.yuleosh/agents/RULES.md` | §12 OpenSpec 规范管理规则 | — |

## 4. 模块间依赖

```
validate_spec_dir ──→ parse_spec (复用, 逐文件)
contracts_check_dir ──→ extract_contracts (复用, 逐文件)
step_spec_check ──→ validate_spec_dir / contracts_check_dir (优先目录)
session.spec_path ──→ 目录时聚合
init 模板 ──→ 生成 .osh/specs/ 骨架
RULES.md §12 ──→ 约束新项目
```

## 5. 验收标准总览

- A-01: `spec validate .osh/specs/`（目录）聚合校验所有 capability
- A-02: `spec validate` 单文件仍兼容（回归）
- A-03: pipeline spec-check 自动发现 `.osh/specs/`（存在时优先）
- A-04: contracts_check 目录聚合（多 capability 契约合并校验）
- A-05: init 生成 OpenSpec 骨架（.osh/specs/README + 示例）
- A-06: RULES.md §12 固化（新项目 SHALL 用 OpenSpec 结构）
- A-07: 全量回归绿（无契约漂移）

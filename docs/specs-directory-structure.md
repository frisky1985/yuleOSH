# 需求规格目录结构规范

> **版本**: v1.0.0  
> **日期**: 2026-10-11  
> **状态**: 已实施

---

## 目录结构

```
specs/
├── modules/          # 大型模块规格说明
│   ├── spec-fta.md
│   ├── spec-fault-injection.md
│   ├── spec-knowledge-management.md
│   ├── tech-fta.md
│   ├── tech-fault-injection.md
│   └── tech-knowledge-management.md
│
└── submodules/       # 轻量级子模块需求列表
    ├── compliance-engine.md
    ├── evidence-module.md
    └── pipeline-module.md
```

---

## 设计 rationale

### 为什么合并 spec/ 和 specs/？

**问题**：项目根目录同时存在 `spec/` 和 `specs/` 两个目录，命名相似但用途不同，造成混淆：
- `spec/` — 存放大型模块规格（FTA、故障注入、知识管理等）
- `specs/` — 存放轻量级子模块需求列表（合规引擎、证据模块等）

**解决方案**：统一为 `specs/` 目录，通过子目录区分文件类型：
- `specs/modules/` — 大型模块规格
- `specs/submodules/` — 轻量级子模块需求

**优势**：
1. 消除命名歧义
2. 按文件规模分类，便于查找
3. 符合单一职责原则

---

## 目录职责

### specs/modules/

**存放内容**：大型模块的完整规格说明文档

**特征**：
- 文件体积大（40KB - 105KB）
- 采用 RFC 2119 文体（SHALL/SHOULD/MAY）
- 包含完整的需求规格结构：
  - 核心数据结构定义
  - 功能需求（按功能区域分组）
  - 非功能需求
  - 接口规范
  - 行业约束
  - 实现指引
  - 术语表

**示例文件**：
- `spec-fta.md` (44KB) — 故障树分析模块规格
- `spec-fault-injection.md` (40KB) — 故障注入模块规格
- `tech-fta.md` (83KB) — FTA 技术实现文档
- `tech-fault-injection.md` (106KB) — 故障注入技术文档

**适用场景**：
- 独立的功能模块
- 需要详细设计的数据结构
- 涉及多个接口的复杂功能
- 需要行业合规约束的功能

---

### specs/submodules/

**存放内容**：轻量级子模块的需求列表

**特征**：
- 文件体积小（1KB - 2KB）
- 采用简单的 REQ-xxx 格式
- 结构扁平：
  - 功能区域分组
  - 需求编号 + 描述
  - 优先级 + 状态
  - 追溯关系

**示例文件**：
- `compliance-engine.md` (1.4KB) — 合规引擎需求
- `evidence-module.md` (1.6KB) — 证据模块需求
- `pipeline-module.md` (1KB) — 流水线模块需求

**典型格式**：
```markdown
## 功能区域: Compliance Engine

### REQ-CE-001: Profile 加载
- **SHALL** 从 yaml 文件加载合规标准 profile
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-001, SYS-REQ-003
```

**适用场景**：
- 核心流水线组件
- 工具型模块
- 需求数量少（< 20 条）
- 不需要复杂数据结构定义

---

## 代码兼容性

### 已更新的代码

**文件**: `src/yuleosh/ci/stages/methodology_gate.py` (lines 71-78)

**变更**：更新 spec 文件发现逻辑，扫描新目录结构

```python
# 退路：specs/ 下文件名含 'spec' 的（排除 misra/requirements/matrix）
for pattern in ["specs/modules/*.md", "specs/submodules/*.md", "specs/*.md"]:
    for p in _find_files(project_dir, [pattern]):
        name = p.name.lower()
        if "spec" in name and "matrix" not in name and "requirement" not in name and "misra" not in name:
            found.append(p)
if found:
    return found
```

**扫描优先级**：
1. `docs/spec.md` — 项目主规格
2. `docs/software-requirements.md` — SRS 文档
3. `specs/modules/*.md` — 大型模块规格
4. `specs/submodules/*.md` — 子模块需求
5. `specs/*.md` — 兼容旧结构

---

## 迁移指南

### 从旧结构迁移

**旧结构**：
```
spec/
├── spec-fta.md
└── tech-fta.md

specs/
├── compliance-engine.md
└── evidence-module.md
```

**迁移步骤**：

1. **创建新目录**：
   ```bash
   mkdir -p specs/modules specs/submodules
   ```

2. **移动大型模块规格**：
   ```bash
   mv spec/*.md specs/modules/
   ```

3. **移动子模块需求**：
   ```bash
   mv specs/*.md specs/submodules/
   ```

4. **删除旧目录**：
   ```bash
   rmdir spec/
   ```

5. **验证**：
   ```bash
   .venv/bin/yuleosh pipeline run --project <project-id>
   ```

---

## 新增文件指南

### 何时放入 specs/modules/？

- 文件预计 > 10KB
- 需要定义复杂数据结构
- 包含多个功能区域
- 涉及外部接口或行业标准
- 需要详细的实现指引

**模板**：参考 `specs/modules/spec-fta.md`

---

### 何时放入 specs/submodules/？

- 文件预计 < 5KB
- 需求数量 < 20 条
- 不需要复杂数据结构
- 主要是功能需求列表
- 追溯关系简单

**模板**：参考 `specs/submodules/compliance-engine.md`

---

## 最佳实践

1. **命名规范**：
   - 模块规格：`spec-<module-name>.md`
   - 技术文档：`tech-<module-name>.md`
   - 子模块需求：`<module-name>-module.md` 或 `<module-name>-engine.md`

2. **版本管理**：
   - 每个文件顶部标注版本号
   - 重大变更时递增主版本号

3. **追溯关系**：
   - 所有需求必须追溯到 SYS-REQ
   - 使用 `**追溯**: SYS-REQ-xxx` 格式

4. **状态标记**：
   - 未实现：`**状态**: 待实现`
   - 已实现：`**状态**: 已实现`
   - 已验证：`**状态**: 已验证`

---

## 相关文档

- [系统需求规范](../docs/system-requirements.md) — SYS.1 系统需求
- [软件需求规范](../docs/spec.md) — SWE.1 软件需求
- [V 模型支持](./planning/product-vmodel-support-v3-10-09.md) — V 模型实施计划

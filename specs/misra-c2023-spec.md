# MISRA C:2023 静态检查集成 — Spec 契约层

> **版本**: 1.0.0-draft
> **作者**: 小马 🐴（质量架构师）
> **格式**: RFC 2119 (SHALL / SHOULD / MAY) + OpenSpec
> **依赖**: `ci/stages.py`, `ci/config.py`, `misra-rules.yaml`

---

## 1. 范围与目的

本文档定义 yuleOSH 将 **MISRA C:2023** 静态检查集成到 CI 流水线中的契约要求。

MISRA C:2023 是汽车/工业嵌入式 C 代码的事实编码标准。本集成通过 `cppcheck`（优先）或 `clang-tidy`（后备）在 CI Layer 2 中执行自动检查，配合 `misra-rules.yaml` 规则配置文件管理违规。

### 背景

| 维度 | 当前状态 | 目标 |
|:-----|:---------|:-----|
| 静态检查 | `cppcheck --enable=all` 无规则过滤 | MISRA C:2023 分级规则检查 |
| 违规管理 | 无规则配置，无违规数据库 | `misra-rules.yaml` 驱动的违规分级与自动判决 |
| MISRA_FAIL_FAST | 存在但仅用于 clang-tidy | 扩展至 cppcheck MISRA 规则 |
| 合规性证据 | 无 MISRA 专用证据 | `.osh/ci/misra-report-*.json` 作为 ASPICE SWE.4 证据 |

---

## 2. 术语表

| 术语 | 定义 |
|:-----|:-----|
| **MISRA C:2023** | Motor Industry Software Reliability Association C 编码标准 (2023 版) |
| **Required 规则** | MUST 遵守；违规需偏差申请 |
| **Advisory 规则** | SHOULD 遵守；违规应记录 |
| **Project-specific 规则** | MAY 按项目上下文启用/禁用的附加规则 |
| **偏差许可 (Deviation)** | 对 Required 规则违规的有文件记录的豁免 |
| **cppcheck** | 开源 C/C++ 静态分析工具，内建 MISRA 规则 |
| **TOP 20** | 嵌入式安全中最关键的 20 条 MISRA 规则子集（SWE.4 关注） |

---

## 3. 契约要求

### 3.1 MISRA 检查阶段

**SWE-MISRA-S1**: MISRA 静态检查阶段 SHALL 在 CI Layer 2 的 `static_analysis_stage` 中执行。
  - traceability: "misra-rules.yaml → ci/stages.py:run_misra_check() → ci/misra_report.py:parse_cppcheck_output()"

- 检查工具优先级：`cppcheck --misra=` > `cppcheck --enable=all --suppress=*` 降级回退 > `clang-tidy` 后备
- [REQ-MISRA-S1.1] SHALL 在 `src/` 下所有 `.c` / `.h` 文件上执行
- [REQ-MISRA-S1.2] SHALL 读取 `misra-rules.yaml` 确定启用规则集和严重度

**SWE-MISRA-S2**: MISRA 违规报告 SHALL 以结构化 JSON 格式保存到 `.osh/ci/misra-report-{commit}.json`。
  - traceability: "ci/misra_report.py:generate_json_report() → .yuleosh/reports/misra-report.json → ASPICE SWE.4"

- [REQ-MISRA-S2.1] SHALL 包含规则编号、描述、文件路径、行号、严重度
- [REQ-MISRA-S2.2] SHALL 包含统计摘要（total / required / advisory / project-specific）
- SHOULD 包含时间戳和工具版本

**SWE-MISRA-S3**: MISRA_FAIL_FAST 环境变量 SHALL 控制违规是否阻断流水线。
  - traceability: "ci/stages.py:is_misra_fail_fast() → ci/config.py:MISRA_FAIL_FAST → run_misra_check() 阻断逻辑"

- [REQ-MISRA-S3.1] `MISRA_FAIL_FAST=1`：任何 Required 违规 SHALL 导致 stage 标记为 "failed"
- [REQ-MISRA-S3.2] `MISRA_FAIL_FAST=0`（默认）：违规 SHALL 被记录但 stage 标记为 "warning"

### 3.2 规则配置文件

**SWE-MISRA-CFG1**: `misra-rules.yaml` SHALL 定义所有启用的 MISRA 规则。
  - traceability: "misra-rules.yaml → ci/misra_report.py:load_rule_definitions() → run_misra_check() 规则过滤"

```
格式：
rules:
  - rule: "Rule 1.1"
    category: "Required" | "Advisory" | "Project-specific"
    description: "..."
    severity: "critical" | "major" | "minor" | "info"
    enabled: true | false
    check: "cppcheck" | "clang-tidy" | "manual"
    rationale: "..."
```

**SWE-MISRA-CFG2**: TOP 20 规则 SHALL 默认全部启用且不可禁用（除非偏差申请）。
  - traceability: "misra-rules.yaml TOP 20 spec_ref → ci/misra_report.py:enrich_with_definitions()"

### 3.3 违规处理

**SWE-MISRA-DEV1**: 偏差申请 SHALL 记录在 `docs/misra-deviations.md` 中。
  - traceability: "docs/misra-deviations.md → ci/stages.py:suppress_rules → misra_report.py 偏差排除"

- [REQ-MISRA-DEV1.1] SHALL 包含规则编号、被豁免的文件/行、理由、审批时间
- [REQ-MISRA-DEV1.2] SHALL 在 CI 报告中排除已豁免的违规

**SWE-MISRA-DEV2**: MISRA 违规报告 SHOULD 在每个 CI 运行后自动更新到 `.osh/evidence/`。

### 3.4 配置集成

**SWE-MISRA-CONF1**: CI 配置（`ci/config.py`）SHALL 包含 MISRA 配置节：
  - traceability: ".yuleosh/ci-config.yaml → ci/config.py → ci/stages.py:run_misra_check()"

```yaml
# .yuleosh/ci-config.yaml 扩展示例
misra:
  enabled: true
  ruleset: "misra-rules.yaml"   # 相对于 project_dir
  fail_on_required: true        # MISRA_FAIL_FAST 等价
  max_warnings: 100             # Advisory 警告上限，超出后 stage warning
  deviation_file: "docs/misra-deviations.md"
```

---

## 4. 规则分级目录

MISRA C:2023 包含约 180 条规则。本集成按三级分类。

### 4.1 Required 规则（30 条核心）

| 编号 | 简要描述 | 严重度 |
|:-----|:---------|:------|
| Rule 1.1 | 实现不得包含未定义行为 | critical |
| Rule 1.2 | 实现不得包含未指定/实现定义行为 | major |
| Rule 2.1 | 项目不得包含不可达代码 | major |
| Rule 2.2 | 不得包含死码 | major |
| Rule 2.3 | 不得包含空汇编写法 | major |
| Rule 3.1 | #include 指令语法正确 | major |
| Rule 4.1 | 八进制/十六进制常量无歧义 | minor |
| Rule 5.1 | 标识符不得遮蔽外部链接 | major |
| Rule 5.3 | 标识符内部链接唯一 | minor |
| Rule 5.6 | typedef 名称在同一命名空间唯一 | minor |
| Rule 5.7 | 标签唯一 | minor |
| Rule 5.9 | 标识符字符数限制 | info |
| Rule 6.1 | 位域仅使用适当类型 | major |
| Rule 6.2 | 单比特位域使用布尔类型 | major |
| Rule 7.1 | 不能对一元 & 运算符用于 register | minor |
| Rule 7.2 | 所有源代码字符集须在基本字符集 | major |
| Rule 8.1 | 类型须显式声明 | major |
| Rule 8.2 | 函数须有声明原型 | major |
| Rule 8.3 | 声明与定义参数一致 | major |
| Rule 8.4 | 外部定义须可达 | major |
| Rule 8.5 | 外部对象/函数仅一次声明 | major |
| Rule 8.6 | 标识符须有同一作用域与链接 | major |
| Rule 8.9 | 对象应定义于合适作用域 | minor |
| Rule 8.10 | 静态存储期对象须初始化 | major |
| Rule 8.11 | 局部变量不遮蔽外部变量 | minor |
| Rule 8.13 | 指针应指向 const 数据 | major |
| Rule 9.1 | 聚合初始化完整 | major |
| Rule 9.2 | 设计器初始化无重复项 | minor |
| Rule 9.3 | 数组初始化使用大括号 | minor |
| Rule 10.1 | 不得在位字段上执行算术 | major |
| Rule 10.2 | 移位操作不溢出 | major |
| Rule 10.3 | 复合表达式的值不转换到更宽类型 | major |
| Rule 10.4 | 复合表达式类型不转换为窄类型 | major |
| Rule 11.1 | 指针转换为整型 | major |
| Rule 11.2 | 指针转换为更严格对齐类型 | major |
| Rule 11.3 | void * 转换到函数指针 | major |
| Rule 11.4 | 指向对象的指针转换到字符类型 | info |
| Rule 12.1 | 缺少括号导致歧义 | major |
| Rule 12.2 | 移位计数不越界 | major |
| Rule 13.1 | 赋值运算符的结果不得用于另一表达式 | major |
| Rule 13.2 | 副作用不得依赖于求值顺序 | major |
| Rule 13.3 | 逗号运算符不用于函数参数 | minor |
| Rule 14.1 | 循环计数器不修改 | major |
| Rule 14.3 | 条件语句须为布尔表达式 | major |
| Rule 15.1 | 非 goto 跳转（break/continue） | minor |
| Rule 15.2 | goto 前向跳转 | major |
| Rule 15.3 | return 路径一致 | major |
| Rule 16.1 | switch 有 default 分支 | major |
| Rule 16.2 | switch 每个 case 有 break | major |
| Rule 17.1 | 函数参数不修改 | major |
| Rule 17.2 | 函数递归应避免 | major |
| Rule 17.3 | printf 系列格式字符串与参数匹配 | major |
| Rule 18.1 | 指针运算限于数组内 | major |
| Rule 18.2 | 两指针减法限于同一数组 | major |
| Rule 18.3 | 关系运算限于指向同一对象 | major |
| Rule 18.4 | 不得使用 +、-、+=、-= 和 void * | major |
| Rule 19.1 | malloc/free 应避免 | major |
| Rule 19.2 | 仅使用 free 后的 null 赋值 | major |
| Rule 20.1 | #include 仅用于头文件 | minor |
| Rule 20.2 | 引号头文件搜寻符合标准 | minor |
| Rule 20.6 | #if/#elif 控制表达式为整型常量 | minor |
| Rule 21.1 | 仅使用标准库保留宏 | minor |
| Rule 21.2 | 不应使用保留标识符 | minor |
| Rule 21.3 | 不得使用 realloc 和 free(s) | major |
| Rule 22.1 | 资源应正确获取并释放 | major |
| Rule 22.2 | 资源释放后被清除 | major |

### 4.2 Advisory 规则（15 条）

| 编号 | 简要描述 | 严重度 |
|:-----|:---------|:------|
| Rule 0.1 | 项目使用合适的语言子集 | info |
| Rule 0.2 | 不中断的复合语句使用大括号 | minor |
| Rule 0.3 | 文件内容应符合标准 | info |
| Rule 0.4 | 不得使用汇编 | info |
| Rule 2.4 | 注释不得嵌套 | info |
| Rule 2.5 | /* 和 // 的使用正确 | info |
| Rule 3.2 | #include 路径唯一 | info |
| Rule 4.2 | 不应使用 setjmp/longjmp | info |
| Rule 7.3 | #include 文件名符合规范 | info |
| Rule 8.12 | 枚举类型定义后使用 | minor |
| Rule 9.5 | 结构体成员列表无重复 | minor |
| Rule 14.4 | goto 语句向后跳转 | info |
| Rule 15.4 | break 只用于 switch/loop | minor |
| Rule 16.3 | switch 表达式为整型 | minor |
| Rule 17.4 | 函数参数数量不超限 | info |

### 4.3 Project-specific 规则（按需启用）

| 编号 | 简要描述 | 典型场景 |
|:-----|:---------|:---------|
| Rule 1.3 | 不得使用 C 标准库中运行时边界检查的函数 | 安全认证项目 |
| Rule 1.4 | 不得使用变长数组 | ASIL-D 项目 |
| Rule 15.5 | 不得使用 continue | 极端安全项目 |
| Rule 19.3 | 不使用动态内存分配 | 医疗/航空 |

---

## 5. ASPICE SWE.4/SWE.5 映射

### SWE.4 — 软件单元验证

| MISRA Spec ID | SWE.4 BP | 覆盖要求 |
|:--------------|:---------|:---------|
| SWE-MISRA-S1 | SWE.4.BP1 | MISRA 检查作为单元验证的一部分执行 |
| SWE-MISRA-S2 | SWE.4.BP1 | 检查结果作为验证证据存档 |
| SWE-MISRA-CFG1 | SWE.4.BP1 | 规则集定义检查范围 |
| SWE-MISRA-DEV1 | SWE.4.BP2 | 偏差申请提供合规性轨迹 |
| SWE-MISRA-CONF1 | SWE.4.BP1 | 配置确定检查严格度 |

### SWE.5 — 软件集成与集成测试

| MISRA Spec ID | SWE.5 BP | 覆盖要求 |
|:--------------|:---------|:---------|
| SWE-MISRA-S1 | SWE.5.BP2 | 集成构建前执行 MISRA 检查 |
| SWE-MISRA-S2 | SWE.5.BP3 | MISRA 报告作为集成测试证据 |
| SWE-MISRA-DEV1 | SWE.5.BP2 | 偏差申请确保集成阶段合规 |

### SWE.6 — 软件合格性测试

| MISRA Spec ID | SWE.6 BP | 覆盖要求 |
|:--------------|:---------|:---------|
| SWE-MISRA-S3 | SWE.6.BP2 | MISRA_FAIL_FAST 确保发布前合规 |
| SWE-MISRA-DEV2 | SWE.6.BP3 | 自动证据存档支持合格性评审 |

---

## 6. 验收判据

| Spec ID | 验收项 | 方法 | 通过标准 |
|:--------|:-------|:-----|:---------|
| SWE-MISRA-S1 | MISRA 检查阶段 | CI 运行 + 日志 | cppcheck 输出 MISRA 规则违规 |
| SWE-MISRA-S2 | 结构化报告 | 检查 `.osh/ci/` | JSON 包含规则/文件/行/严重度 |
| SWE-MISRA-CFG1 | 规则配置文件 | 解析 `misra-rules.yaml` | TOP 20 全部启用 |
| SWE-MISRA-DEV1 | 偏差排除 | 在 CI 中排除 | 偏差文件中规则不被报告 |
| SWE-MISRA-CONF1 | CI 配置集成 | 测试 `load_ci_config` | MISRA 配置段正确解析 |

---

## 7. 风险与假设

| 风险 | 影响 | 缓解 |
|:-----|:-----|:-----|
| cppcheck MISRA 支持不完全 | 部分 C:2023 规则可能无法检测 | 配置 `clang-tidy` 作为后备；标记未覆盖规则供手动检查 |
| 误报过多 | 开发抗拒使用 | Required 级规则列表经人工审核；Advisory 级不阻断 |
| 模板项目 C 代码非 MISRA 合规 | 新项目首次 CI 运行会大量违规 | 模板项目逐步适配；偏差文件吸收已知违规 |
| 无 `misra-rules.yaml` | CI 降级为通用 cppcheck | 小克 👨‍💻 需在 Sprint 内创建该文件 |

---

*本文档由 yuleOSH 质量架构师生成，基于 MISRA C:2023 标准与 ASPICE v3.1 SWE 过程参考模型。*

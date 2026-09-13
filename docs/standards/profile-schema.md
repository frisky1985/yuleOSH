# yuleOSH 合规标准 Profile Schema 规范

> **本文档是编写新合规标准 profile 的唯一权威输入。** 外部工程师（例如 A-M2 的
> ISO 26262 作者）**仅凭本文档即可新增一个标准**，无需阅读任何 Python 代码。
> 检查引擎（`ComplianceChecker`）对所有标准零代码改动地消费同一份 schema。

---

## 1. 它是什么

`StandardProfile` 是 yuleOSH 多标准合规检查的**统一数据模型**。每个合规标准
（如 ASPICE v3.1、未来的 ISO 26262、车厂定制标准）对应**一个** `<name>.yaml` 文件。

检查引擎读取该 yaml 定义的「过程域 → 基础实践(BP) → 产出证据/检查要点」层级，
对项目实际产出物逐条比对，给出 ✅ / ⚠️ / ❌ 三项判定。

**核心不变量**：yaml 到内存对象再到 checker 消费 dict 的映射是**无损**的
（见 §7）。因此同一份 schema 既能被人读懂，也能被引擎精确消费，且新标准接入
不需要改动任何业务代码。

---

## 2. 文件位置与命名

| 项 | 规则 |
|----|------|
| 文件名 | `<standard_name>.yaml`（**不含** 目录与 `.yaml` 后缀；loader 自动补后缀） |
| 标准示例 | `aspice_v3.1.yaml`、`iso26262.yaml` |
| 放置目录 | `src/yuleosh/compliance/profiles/`（优先）；也兼容 `src/yuleosh/compliance/` 根目录 |
| 加载 API | `load_profile("<standard_name>")` —— 只需传 `<standard_name>`，不要带 `.yaml` |
| 搜索顺序 | 先在 `compliance/profiles/` 找，再到 `compliance/` 根目录找 |
| 列出已注册 | `list_profiles()`（返回可用 profile 名列表，用于 CLI 报错时的可用清单） |

> 注意：CLI / 代码里传的是 `aspice_v3.1`（无后缀）。带后缀传参会被当作文件名拼
> 接成 `aspice_v3.1.yaml.yaml`，导致 `ProfileNotFoundError`。

---

## 3. 顶层结构与最小可运行示例

一个 profile 文件由 **1 个 `meta` 块 + N 个过程域顶层键** 组成：

```yaml
# 最小可运行 profile（结构合法，可直接 load_profile 通过）
meta:
  standard: "DEMO"
  version: "1.0"
  description: "最小演示标准"

area1:                       # ← 过程域顶层键（任意命名，见 §4 备注）
  id: "AREA1"
  title: "示例过程域"
  description: |
    过程域的块文本描述，原样保留（不折叠）。
  base_practices:
    - id: "AREA1.BP1"
      title: "完成第一项基础实践"
      output_evidence:
        - type: "document"
          path: "docs/area1-spec.md"
          description: "AREA1 规范文档"
      check:
        - "规范文档包含唯一标识的需求条目"
```

---

## 4. 字段规范表

校验采用**字段白名单 + 必填校验**两类规则。下表即白名单全量；出现白名单外字段
会触发 `ProfileError`（带字段路径与修复提示）。

### 4.1 `meta`（必填块，至少 `standard`）

| YAML 路径 | 含义 | 类型 | 必填 | 约束 |
|-----------|------|------|------|------|
| `meta.standard` | 标准名（如 `ASPICE` / `ISO26262`） | string | **是** | 非空 |
| `meta.version` | 标准版本 | string | 否 | 缺省 `"3.1"` |
| `meta.description` | 标准一句话描述 | string | 否 | — |

### 4.2 过程域顶层键（如 `swe.1`、`area1`、`part6`）

> **键名自由 + 推荐前缀约定（A1-04 决策3）**：loader **不强制** `swe.N`，键名原样保留为
> `ProcessArea.key` 并用于还原 checker 消费的 dict 键。新标准（如 ISO 26262）可用
> `part6` / `part8` 等自有命名。**为避免多标准并存键碰撞，推荐使用 `标准名.过程域` 约定**，
> 例如 `iso26262.part6`、`iso26262.part8`（仅约定，非强制；引擎对键名不做前缀校验）。
>
> ⚠️ **消费端已标准化（A1-04 阻断修复）**：`ComplianceChecker.run()` 遍历**除 `meta` 外的所有
> 顶层键**，不再仅识别 `swe.*`。因此任意命名的过程域（含 `iso26262.part6`）都能被正常消费，
> 不会出现旧版「非 SWE 标准生成空报告」的 bug。

| YAML 路径 | 含义 | 类型 | 必填 | 约束 |
|-----------|------|------|------|------|
| `<area>.id` | 过程域 ID（展示用） | string | **是** | 非空 |
| `<area>.title` | 过程域标题 | string | 否 | — |
| `<area>.description` | 过程域描述 | string（块文本 `|`） | 否 | 块文本原样保留 |
| `<area>.order` | 章节排序权重（A1-04 决策2，可选） | int | 否 | 升序排列；**缺失则保持 yaml 文档书写顺序**（推荐用文档序，仅在需显式重排时加 `order`） |
| `<area>.base_practices` | 该域下的基础实践列表 | list | 否（可空） | 元素见 §4.3 |

### 4.3 `base_practices[]` 元素

| YAML 路径 | 含义 | 类型 | 必填 | 约束 |
|-----------|------|------|------|------|
| `<bp>.id` | 基础实践 ID（如 `SWE.1.BP1`） | string | **是** | 非空，建议在标准内唯一 |
| `<bp>.title` | BP 标题 | string | 否 | — |
| `<bp>.output_evidence` | 该 BP 的产出证据清单 | list | 否 | 元素见 §4.4 |
| `<bp>.check` | 检查要点（人工/自动核查提示文本） | list[str] | 否 | 纯文本，用于报告「缺失项」展示 |

### 4.4 `output_evidence[]` 元素

| YAML 路径 | 含义 | 类型 | 必填 | 约束 |
|-----------|------|------|------|------|
| `<ev>.type` | 证据类型 | string | **是** | **推荐枚举**：`document` / `source` / `test` / `ci` / `evidence` / `sil`（见 §10） |
| `<ev>.path` | 证据路径（相对项目根） | string | **是** | 非空；文件或目录均可 |
| `<ev>.description` | 证据说明 | string | 否 | — |

---

## 5. 加载与校验行为

调用 `load_profile(name)` 时依次执行：

1. **文件定位**：按 §2 搜索目录拼 `<name>.yaml`。
   - 找不到 → 抛 `ProfileNotFoundError`，异常携带 `searched`（搜索路径列表）与
     `available`（可用 profile 名清单），供 CLI 提示。
2. **YAML 解析**：解析失败 → 透传 `yaml.YAMLError`（错误路径即文件名）。
3. **结构校验**（`ProfileError`，每条带 `字段路径` 与 `修复提示`）：
   - 顶层必须是 mapping；
   - 必须有 `meta`；`meta.standard` 必填非空；
   - 任何 mapping 出现白名单外字段 → 报错（如 `meta.foo` 未知字段）；
   - `area` / `bp` / `ev` 缺必填字段（`id` / `type` / `path`）→ 报错。
4. **映射**：校验通过后，无损映射为 `StandardProfile` 对象返回。

> 设计意图：**缺字段与未知字段都会被捕获并定位**，避免静默错误配置流入检查引擎。

---

## 6. 与代码模型的映射（仅供理解，编写 profile 不需要）

内存对象 `StandardProfile` 由以下强类型结构承载（字段一一对应 yaml）：

| yaml 结构 | 代码类 | 关键字段 |
|-----------|--------|----------|
| 顶层 `meta` | `ProfileMeta` | `standard` / `version` / `description` |
| 顶层过程域键 | `ProcessArea` | `id` / `title` / `description` / `order`(可选) / `base_practices` / `key`（= 原 yaml 顶层键） |
| `base_practices[]` | `BasePractice` | `id` / `title` / `output_evidence` / `check` |
| `output_evidence[]` | `EvidenceSpec` | `type` / `path` / `description` |
| 整体 | `StandardProfile` | `meta` + `areas`（保序 list） |

便捷访问：`profile.standard` / `profile.version`（镜像 meta）、
`profile.area_by_id("SWE.1")` / `profile.all_base_practice_ids()`。

---

## 7. 反向序列化语义（对 checker 透明，编写者需知道）

`StandardProfile.to_template_dict()` 把内存对象**还原**为 checker 消费的 template dict。
关键点：

- 顶层 `meta` 映射为 `meta` 子块；
- 每个 `ProcessArea` 还原为 dict 键 **`area.key`**（即 yaml 原顶层键）；
  若 `key` 缺失则回退 `area.id.lower()`；
- `base_practices` / `output_evidence` / `check` 逐字段还原。

**推论**：若你改变了 yaml 过程域的**顶层键名**，还原后的 dict 键随之改变；
`id` 仅用于展示，不影响 dict 键。保持「顶层键名 = 期望 dict 键」即可。

---

## 8. 完整示例

### 8.1 ASPICE v3.1 风格（摘录，来自内置 `aspice_v3.1.yaml`）

```yaml
meta:
  standard: "ASPICE"
  version: "3.1"
  description: "Software Engineering Process Group — SWE.1~SWE.6"

swe.1:
  id: "SWE.1"
  title: "Software Requirements Analysis"
  description: |
    Transform system requirements into a structured set of software requirements.
  base_practices:
    - id: "SWE.1.BP1"
      title: "Specify software requirements"
      output_evidence:
        - type: "document"
          path: "docs/software-requirements.md"
          description: "Software Requirements Specification (SRS)"
        - type: "document"
          path: "docs/requirements.md"
          description: "Alternative requirements document"
      check:
        - "Each requirement has a unique identifier (REQ-xxx)"
        - "Each requirement contains SHALL statements"
        - "Requirements are traced to system requirements"
    - id: "SWE.1.BP2"
      title: "Structure software requirements"
      output_evidence:
        - type: "document"
          path: "specs/"
          description: "Structured specs directory"
      check:
        - "Requirements are organized by functional area"
        - "Requirements have defined attributes (priority, status)"
```

### 8.2 ISO 26262 风格新标准（展示 A-M2 接入，无需改代码）

```yaml
# iso26262.yaml —— 仅提供同结构 yaml 即可被引擎消费
meta:
  standard: "ISO26262"
  version: "2018"
  description: "Road vehicles — Functional Safety (Part 6/8 摘录)"

# 顶层键采用「标准名.过程域」推荐约定（A1-04 决策3），避免多标准键碰撞
iso26262.part6:                       # 顶层键自由命名，对应字典键；此处用推荐前缀
  id: "ISO26262-6"
  order: 1                            # 可选：显式章节排序（缺失则按文档序）
  title: "Product development at the software level"
  description: |
    Specifies the software development process for functional safety.
  base_practices:
    - id: "ISO26262-6.BP1"
      title: "Software architectural design"
      output_evidence:
        - type: "document"            # 强制白名单枚举（A1-04 决策1）
          path: "docs/sw-architecture.md"
          description: "Software architectural design specification"
        - type: "source"
          path: "src/"
          description: "Software units implementing the design"
      check:
        - "Architecture satisfies ASIL-appropriate freedom-from-interference"
        - "Software units are traceable to architectural elements"
    - id: "ISO26262-6.BP2"
      title: "Software unit implementation and verification"
      output_evidence:
        - type: "test"
          path: "tests/unit/"
          description: "Unit test results"
        - type: "ci"
          path: ".osh/ci/"
          description: "CI verification records"
      check:
        - "Unit tests achieve required statement/branch coverage for ASIL"
        - "Verification results are archived with coverage evidence"

iso26262.part8:
  id: "ISO26262-8"
  title: "Supporting processes"
  base_practices:
    - id: "ISO26262-8.BP1"
      title: "Confidence from use / proven in use"
      output_evidence:
        - type: "evidence"
          path: ".osh/evidence/proven-in-use.md"
          description: "Proven-in-use justification"
      check:
        - "Field data supports the claimed confidence level"
```

---

## 9. 新增一个标准的操作步骤（A-M2 操作手册）

1. **复制基线**：`cp src/yuleosh/compliance/profiles/aspice_v3.1.yaml \
   src/yuleosh/compliance/profiles/<new>.yaml`
2. **改名与元信息**：改 `meta.standard` / `meta.version` / `meta.description`。
3. **设计过程域**：按你的标准改写顶层键（如 `part6`）、`id`、`title`、`description`、
   `base_practices`。
4. **填 BP 证据与检查点**：每个 `bp` 至少给出 `output_evidence`（含 `type`/`path`）
   与 `check`（核查提示文本）。
5. **放置**：确保文件在 `profiles/` 目录，文件名即 `<new>.yaml`。
6. **本地校验（无引擎依赖）**：
   ```bash
   python -c "from yuleosh.compliance.profile import load_profile; \
              p = load_profile('<new>'); print(p.standard, [a.id for a in p.areas])"
   ```
   无异常即结构合法。
7. **端到端跑检查**：
   ```bash
   yuleosh compliance check --profile <new> <project_dir>
   ```
8. **（可选）注册到 OEM/标准模板注册表**：若还需自定义追溯矩阵模板，调用
   `register_oem_template(name, template)`（要求 `column_map` 与
   `required_columns` 字段），消费方仅按 `name` 检索，无需改其它代码。

---

## 10. 常见错误与排查

| 现象 | 原因 | 修复 |
|------|------|------|
| `ProfileNotFoundError: 找不到 ... 可用 profile: ...` | 文件名/目录错，或传参带 `.yaml` | 确认放在 `profiles/`，传参不带后缀 |
| `ProfileError: 未知字段 'foo'（meta 仅允许 [...])` | yaml 拼错字段名 | 按白名单 §4 修正字段名 |
| `ProfileError: 缺少必填字段 meta.standard` | `meta.standard` 缺失或空 | 补非空 `standard` |
| `ProfileError: base_practices[N] 缺少必填字段 id` | 某 BP 漏 `id` | 补 `id` |
| `ProfileError: output_evidence[M].type 缺少必填字段 type` | 证据漏 `type`/`path` | 补 `type` 与 `path` |
| `ProfileError: evidence.type 取值 'foo' 不在允许集合 [...]` | `type` 拼写漂移（如 `documnt`） | 改用下方白名单枚举值（A1-04 决策1 强制校验） |
| 还原后 dict 键与预期不符 | 改了过程域顶层键名 | 顶层键即 dict 键（§7），对齐命名 |

**`evidence.type` 强制白名单（A1-04 决策1：Option B）**：loader 对 `type` 取值做**强制枚举校验**
（不再仅校验键名）。允许集合固定为：

```text
document  (文档)      source    (源码)      test      (测试)
ci        (CI 记录)   evidence  (证据包)    sil       (SIL/HIL 结果)
```

> ⚠️ 拼写漂移（如 `documnt`）**过去会静默报「缺证据」假阴性**；自本决策起会**在加载阶段即报
> `ProfileError` 并带字段路径**，把错误挡在作者侧。新标准需新类型时，在 loader 的
> `_EVIDENCE_TYPE_ENUM` 一处增删即可（同文件、一行）。

---

## 11. 版本与向后兼容

- 本 schema 自 A1-02 设计、A1-03 加载/校验、A1-05 接入 checker，当前已稳定。
- 新增字段需同步更新本文档与 loader 白名单（`_ALLOWED_*` 集合）及对应 dataclass 字段，
  并保持 `to_template_dict` 还原一致。
- 既有 `aspice_v3.1.yaml` 是 schema 的「黄金参照」——任何新标准的结构合法性
  都以能通过 `load_profile` 为最低门槛（即 §9 第 6 步）。

---

*本文档即 A1-09 交付物。评审见 `docs/standards/profile-schema-review.md`（ISO 26262
作者视角走查，待全员评审会确认）。*

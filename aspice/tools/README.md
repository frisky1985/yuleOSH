# 需求追踪表机械校验工具（trace_check.py）

面向 ASPICE 4.0 CL2 评估准备，对供应商《亚远景_ENG_TP_需求追踪表_V1.0.xlsx》的
9 张清单（涉众需求 → 网络安全需求 → 系统需求 → 系统架构元素 → 硬件需求 →
硬件设计元素 → 软件需求 → 软件架构元素 → 软件详设）做只读校验，输出 Markdown
报告与机器可读 JSON，供 CI 门禁自动执行。

- 单文件 Python 3（实测 3.14），仅依赖标准库 + `openpyxl`，不依赖 pytest。
- 对输入文件**只读**，不修改任何源模板 / 覆盖矩阵。
- 所有结论均基于表内 ID 与引用文本，不做语义猜测。

## 1. 快速开始

```bash
# 1) 内置自测（无需外部文件）
python3 /workspace/aspice/tools/trace_check.py --selftest

# 2) 用内置默认路径跑源追踪表（控制台输出概览 + 前 20 条明细）
python3 /workspace/aspice/tools/trace_check.py

# 3) 源追踪表 + 源测试规范，生成 Markdown + JSON
python3 /workspace/aspice/tools/trace_check.py \
  --trace "/workspace/aspice/_source_templates/工程域模版/ASPICE 4.0 -工程V左/亚远景_ENG_TP_需求追踪表_V1.0.xlsx" \
  --cases "/workspace/aspice/_source_templates/工程域模版/ASPICE 4.0 -工程V右/亚远景_ENG_TP_测试规范_V1.0.xlsx" \
  --out "/workspace/aspice/tools/reports/trace_report_sample.md" \
  --json

# 4) 严格模式：WARN 也返回失败
python3 /workspace/aspice/tools/trace_check.py --trace <xlsx> --strict
```

## 2. CLI 参数

| 参数 | 说明 |
| --- | --- |
| `--trace <xlsx>` | 必填（省略时使用仓库内默认源追踪表路径）。文件不存在或不是有效 `.xlsx` 时输出明确错误并返回 2。 |
| `--cases <xlsx>` | 可选。读取《测试规范》的「2.测试用例」页，校验用例引用存在性与覆盖率。 |
| `--out <report.md>` | Markdown 报告路径；目录不存在会自动创建。 |
| `--json` | 输出 JSON。指定 `--out` 时写入同名 `.json`；未指定 `--out` 时向 stdout 输出**纯 JSON**，人读摘要改到 stderr，便于 CI 管道直接解析。 |
| `--strict` | WARN 也视为失败（退出码 1）。 |
| `--id-pattern <regex>` | ID 命名规范，默认 `^[A-Za-z][A-Za-z0-9_.\-]{2,}$`。 |
| `--selftest` | 现场构造 3 张清单的小工作簿，跑完整分析并断言，退出码 0 表示通过。 |

退出码：`0` 通过；`1` 存在 ERROR（`--strict` 时为存在 WARN）；`2` 输入缺失 / 文件损坏 / 写入失败。
异常路径统一输出 `[ERROR] ...`，不打印 traceback。

## 3. 校验口径

### 3.1 列名识别与归一化
表头定位在前 20 行内按关键词命中数自动选择。匹配前将表头统一去空白（含换行）、小写化，
然后模糊匹配：
- ID 列：`ID / 标识 / 编号 / 编码 / Identifier`（排除上游、来源、下游、测试用例列）；
- 下游列：`下游 / Downstream`；
- 测试用例列：`测试用例 / Test Case / TestCase / 动态测试`；
- 上游列：`上游 / Upstream`；来源列：`来源 / Source`（仅作为来源说明，不默认当作上游 ID）。

识别结果会完整打印在报告第 2 节。未识别到表头、未识别到 ID 列、未识别到下游列分别给 WARN，
并说明该 sheet 是“跳过”还是“按链尾处理”。

### 3.2 ID 非空与唯一性
- 整行全空的数据行视为占位行，直接忽略。
- ID 为空但整行并非全空 → 每张清单聚合为 1 条 WARN（给出数量与前 5 个行号），避免刷屏。
- 同一清单内 ID 重复 → ERROR（每个重复 ID 组记 1 条，列出全部行号）。
- 同一 ID 跨清单重复 → WARN（列出涉及的清单），通常意味着编号空间未隔离或误用。

### 3.3 ID 命名规范
默认正则 `^[A-Za-z][A-Za-z0-9_.\-]{2,}$`，可用 `--id-pattern` 覆盖。
每张清单聚合为 1 条 WARN，给出不合规数量与最多 3 个样本。

### 3.4 下游引用可解析（断链）
「下游元素」按 `, ; ， ； / 、 换行` 拆成多值，逐个在全库 ID 索引中查找。
- 找不到 → ERROR（每处断链 1 条），统计为“断链”。
- 空引用、`NA / N/A / 无 / 待定 / TBD / -` 等占位值不算引用，也不报错。
- 引用区分大小写，按去首尾空白后的原文精确匹配。

### 3.5 反向闭合与孤儿检测
仅凭下游列也可建立反向索引（谁被谁引用）：
- 叶子节点（本行无下游引用）且入度为 0、且该清单不是链尾（`详设 / 详细设计 / 测试用例`
  或没有下游列）→ WARN“可能未被上游引用”，每张清单聚合 1 条并给样本。
- 若清单存在明确的「上游元素 / Upstream」列：逐一校验上游引用是否存在（ERROR），
  非链首行缺少上游引用给 WARN，构成双向闭环。
- 仅有「来源 / Source」列时：只对“看起来像 ID”的来源值做存在性校验（WARN），
  自由文本来源（如“客户”“市场”）不参与闭环；同时仍给一条 INFO，建议补“上游元素”列。
- 缺少上游列的清单各给 1 条 INFO，明确“建议补上游元素列以支持严格双向校验”。

### 3.6 测试用例 ID 规范
对每个非空「测试用例」单元格按同一组分隔符拆值，要求每个值满足
`^<本行需求ID>-TC-\d{2}$`。不合规单元格按清单聚合为 1 条 WARN，附比例与最多 3 个样本。
- 若提供 `--cases`，再从「2.测试用例」页读取“测试用例ID”列：
  - 被追踪表引用的用例 ID / 用例表去重 ID 数 = 用例引用覆盖率；
  - 追踪表引用了但用例表中不存在的 ID → 聚合 WARN；
  - 用例表内 ID 为 0 时覆盖率显示 N/A，不伪造 100%。

### 3.7 覆盖率
- 清单覆盖率 = 有下游引用行 / 有效行（有效行 = ID 非空）。
- 外链覆盖率见 3.6；用例列不合规比例 = 不合规非空单元格 / 全部非空单元格。
- 分母为 0 时统一输出 `N/A`，不输出 0% 或 100%。

## 4. 报告结构

`--out` 生成的 Markdown 固定包含：
1. **概览**：文件、清单数/分析数/跳过数、有效行、断链、孤儿、问题计数、是否通过。
2. **列映射**：每张清单的表头行、ID/下游/用例/上游/来源列及状态。
3. **问题明细**：严重度 / 清单 / 行号 / 单元格 / ID / 问题 / 建议（超过 300 条截断并注明）。
4. **覆盖率**：逐清单与合计；测试用例单元格合规率、用例引用覆盖率。
5. **结论与建议**：自动指出断链、空表、缺少上游列、被跳过清单等。

控制台始终打印概览 + 前 20 条明细；`--json` 的 stdout 模式为纯 JSON，摘要改走 stderr。
JSON 字段包含 `passed`、`counts.{error,warn,info}`、`broken_links`、`orphans`、
`testcase.noncompliance_ratio`、`case_stats`、`sheets[]`、`issues[]`，足够直接做门禁判断。

## 5. CI 集成片段

### GitHub Actions

```yaml
name: aspice-trace-check
on: [push, pull_request]

jobs:
  trace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python3 -m pip install openpyxl
      - name: Selftest
        run: python3 aspice/tools/trace_check.py --selftest
      - name: Trace check (strict)
        run: |
          python3 aspice/tools/trace_check.py \
            --trace "aspice/_source_templates/工程域模版/ASPICE 4.0 -工程V左/亚远景_ENG_TP_需求追踪表_V1.0.xlsx" \
            --cases "aspice/_source_templates/工程域模版/ASPICE 4.0 -工程V右/亚远景_ENG_TP_测试规范_V1.0.xlsx" \
            --out aspice/tools/reports/trace_report.md \
            --json --strict
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trace-report
          path: |
            aspice/tools/reports/trace_report.md
            aspice/tools/reports/trace_report.json
```

### GitLab CI

```yaml
aspice-trace:
  image: python:3.12-slim
  script:
    - pip install openpyxl
    - python3 aspice/tools/trace_check.py --selftest
    - python3 aspice/tools/trace_check.py
        --trace "aspice/_source_templates/工程域模版/ASPICE 4.0 -工程V左/亚远景_ENG_TP_需求追踪表_V1.0.xlsx"
        --cases "aspice/_source_templates/工程域模版/ASPICE 4.0 -工程V右/亚远景_ENG_TP_测试规范_V1.0.xlsx"
        --out aspice/tools/reports/trace_report.md --json --strict
  artifacts:
    when: always
    paths:
      - aspice/tools/reports/trace_report.md
      - aspice/tools/reports/trace_report.json
```

仅需退出码时，可去掉 `--out`，用 `--json` 从 stdout 读取
`passed` / `counts`；也可保留 `--out` 并读取同名 `.json`。

## 6. 样例结论（真实源模板）

执行命令：

```bash
python3 trace_check.py \
  --trace ".../ASPICE 4.0 -工程V左/亚远景_ENG_TP_需求追踪表_V1.0.xlsx" \
  --cases ".../ASPICE 4.0 -工程V右/亚远景_ENG_TP_测试规范_V1.0.xlsx" \
  --out reports/trace_report_sample.md --json
```

产物：
- `/workspace/aspice/tools/reports/trace_report_sample.md`
- `/workspace/aspice/tools/reports/trace_report_sample.json`

实测结果（基线模式，退出码 0）：

| 指标 | 数值 |
| --- | --- |
| 清单数 | 9（已分析 8 / 跳过 1） |
| 数据行（非空） | 26 |
| 有效行（ID 非空） | **0** |
| 下游引用 / 断链 | 0 / **0** |
| ERROR / WARN / INFO | **0 / 8 / 8** |
| 测试用例列非空 / 不合规 | **0 / 0（比例 N/A）** |
| 用例表 ID 数 / 被引用 | 0 / 0（覆盖率 N/A） |

关键发现（如实反映）：

1. **源追踪表并不是已填写的 BCM/LIN 案例，而是空白模板。** 9 张清单只有表头、
   下拉与占位示例值（如 `Functional`、`A Sample`、`软件模块`），没有任何有效 ID；
   26 个非空数据行全部是“ID 为空但整行非空”的示例残留，所以出现 8 条对应 WARN。
2. **BCM/LIN 示例实际在 V 左的 SYS2/SYS3/SWE1 文档中**：`亚远景_SYS2_TP_系统需求
   规格说明书_V1.0.xlsx` 的「3.系统需求」B4 为 `ProjectID_SYS_Feature001`，
   `SWE1_TP_软件需求规格说明书_V1.0.xlsx` 的「3.软件需求」B4 为
   `ProjectID_SWE_Feature001`，SYS3 的「5.系统动态架构设计」也以 BCM 状态机为例。
   但追踪表里没有出现任何一条相关 ID，也没有任何下游引用。也就是说，模板没有承接
   这组示例数据，“追溯无法机械举证”在源文件层面就是事实。
3. **0 断链是“无数据可检”，不是“链路健康”。** 报告第 5 节已明确这一点；
   用例列不合规比例同样为 N/A，因为用例列 0 个非空格、用例表 0 个用例 ID。
4. **网络安全需求页无 ID 列**（表头只有“网络安全目标 / 网络安全需求”文本列），
   无法建立索引，已按 WARN 跳过；这是 1 张被跳过的清单。
5. **软件详设页无“下游元素”列**，按链尾处理并给出 WARN；其余 8 张已分析清单
   全部没有“上游元素”列，各给出 1 条 INFO。
6. 加 `--strict` 时因 8 条 WARN 返回退出码 1；基线模式返回 0。CI 若要把“模板未填写”
   也拦住，应使用 `--strict`。

自测回归结果（`--selftest`，退出码 0）：

```text
ERROR=2 WARN=6 INFO=3 broken=1 orphans=2 valid=9
PASS: 列映射/表头偏移识别
PASS: 空 ID、重复 ID、跨清单重复、非法命名
PASS: 断链、孤儿节点、缺少上游列 INFO
PASS: 测试用例自由文本不合规计数
PASS: 报告渲染
SELFTEST OK
```

自测构造了 3 张清单（含表头偏移、空 ID、同表重复、跨表重复、非法 ID、断链、
自由文本用例、链尾页），断言各类问题均被检出，用于防止改动后规则退化。

## 7. 已知限制

- `openpyxl` 以 `data_only=True` 读取，公式单元格依赖 Excel 保存的缓存值；
  若工作簿由程序生成且从未被 Excel 打开/保存，公式结果可能读为 `None`。
- 合并单元格只取左上角值；跨行合并的层级 ID 需要先拆分成独立行。
- 用例 ID 默认要求前缀等于**本行需求 ID**；一个用例覆盖多条需求的场景会判为不合规，
  如需放宽可修改 `CASE_SUFFIX_PATTERN` / 校验逻辑。
- “来源 / Source”列按来源说明处理，不强制当作上游 ID；仅表头明确含
  “上游 / Upstream”时才执行完整双向闭环。
- 报告问题明细最多 300 条；全量数据仍在 JSON `issues[]` 中。

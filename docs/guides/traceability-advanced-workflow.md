# 追溯链进阶工作流 — 悬空 ID 对齐 / 需求编号化 / HTML 矩阵

> 适用：yuleASR 等 C 项目在完成基础 @req/@tests 标注后，进一步打通
> "需求 ↔ 代码 ↔ 测试" 一一对应（ID 级追溯）。
> 实证：2026-08-25 yuleASR（悬空 608→0，覆盖率 61.7%→97.9%，HTML 矩阵 47 需求）。

## 背景：三类悬空引用

基础标注后，测试文件的 @req 可能引用**不存在的需求 ID**：

1. **测试自创编号段**（`SWS_Adc_00201`）：design 文档只有 000xx 段，测试自编号 002xx
2. **伪 ID**（`MCU_CLOCK_001`）：非 SWS/SWR 格式
3. **裸模块名**（`SWS_Adc`）：文件级归属声明，无文档定义

## 一、对齐悬空 ID（改测试）

工具：`tools/align_req_ids.py`（yuleASR 仓库）

匹配链（测试函数名 → API → 真实 SWS ID）：
1. `@coverage ApiName, ...` 注释（最可靠，直接列 API）
2. `TEST_CASE(name)` / `void test_xxx(void)` / `void Test_Xxx(void)`（Unity 三种命名）
3. 组合名分词：`test_init_deinit` → {init, deinit} → Adc_Init
4. 词→后缀子串：`notification` → enablegroupnotification

关键坑（全部实证）：
- **必须模块限定匹配**（从悬空 ID 提取模块：`SWS_Adc_00201`→Adc，过滤 api_map）—— 否则 `init` 误配到 Xcp_Init
- `func[5:]` 仅当函数名以 test_/Test_ 开头；@coverage 提取的 API 名**不能**截断（`Mcu_Init` → `_init` bug）
- 真实 ID 集合要含编号 ID **和**裸模块名（正则 `SWS_\w+_\d+` 漏裸名，需加 `SWS_[A-Za-z]+`）
- design API 表正则要接受反引号包裹（`| \`BswM_RequestMode\` |`）
- **dry-run 必须不写盘**（模块级 APPLY_MODE 标志；曾出现 dry-run 误写盘污染工作区，`git checkout -- tests/` 恢复）

## 二、需求编号化补全（补文档）

工具：`tools/backfill_req_ids.py`（yuleASR 仓库）

对齐后剩余悬空 = 测试引用存在但 design 文档无编号定义（380 ID / 60 模块）。
测试反映真实功能 → **补文档，不改测试**。

- 从测试文件收集 {模块: {SWS ID: 测试函数名}}（跳过 mock 目录）
- 有 design 文档的模块：追加 `## 需求追溯表`（`| SWS_X | API | 测试覆盖场景 |`；API 从函数名剥离 test_ 前缀和场景后缀 `_(Valid|Invalid|After|Should|...)`）
- 无 design 文档的模块：创建最小 `<mod>-design.md`（从测试路径推断层：tests/bsw/<layer>/...）再追加表
- 裸模块名：在模块文档补模块级需求行
- 幂等：已有 `## 需求追溯表` 则跳过

## 三、HTML 需求×测试矩阵

工具：`tools/gen_trace_matrix.py`（yuleASR 仓库）→ `docs/traceability-matrix.html`

- 每个需求一行：需求 ID | 状态徽章 | 需求描述 | 对应测试用例（文件+函数徽章内联）| 实现代码
- 数据源：traceability-report.json（LRM）+ requirements.md + 测试 @req 注释
- 追溯变更后重新生成：`python3 tools/gen_trace_matrix.py`

## 四、requirements.md 追溯字段消费（yuleOSH 侧）

`docs/requirements.md` 可能有 `- 测试追溯: <files>` 字段，而 LRM 主源
software-requirements.md 没有 → 覆盖率虚低。yuleOSH `generate_lrm` 现已
通过 `_parse_req_trace_links()` 消费（解析 docs/*requirements*.md 块）。
实证：yuleASR 覆盖率 61.7% → 97.9%。

## 五、验证闭环

1. `make test`（ctest 54/54）— 抓注释插入破坏编译
2. 悬空审计脚本 → 非 mock 测试期望 0
3. `yuleosh traceability report` → test_coverage_pct 上升
4. `python3 tools/gen_trace_matrix.py` → 重新生成 HTML

## 六、mock 文件约定

tests/mock/ 是测试替身，其 @req 引用**不计入追溯**（审计/对齐/补文档时一律排除）。

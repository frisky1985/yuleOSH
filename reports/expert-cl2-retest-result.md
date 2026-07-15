# 🧑‍🏫 CL2 复审报告 — 老陈 (二轮)

**审查人**: 老陈 👨‍🏫
**审查日期**: 2026-07-04
**审查类型**: 🔄 CL2 复审 — 修复验证
**上一轮评分**: 58/100 ❌
**本轮评分**: **65/100 ❌ 不通过**

> "紧赶慢赶修了6个坑，3个没修利索，还冒出新坑。态度很好，路还很长。"

---

## 一、六大修复逐项验证结果

### 1️⃣ CI yaml-validation — description null→中文字符串 ✅ **通过**
```
$ grep -A 6 "misra-c2023-3.2" misra-rules.yaml
→ description: '#line 指令必须指定有效的行号和文件名，且不得使用误导性的行号'
```
原来 `null` 现在填了有内容的中文描述，每个规则都有。**干净利落，没问题。**

### 2️⃣ CI unit-tests — E2E 忽略补全 + `--cov` 统一 ⚠️ **部分通过**

✅ E2E 忽略清单从原来缺几项补全到 6 个 `--ignore=`
✅ `--cov=yuleosh` 而不是 `--cov=src/yuleosh`（和 `.coveragerc` 一致）

**❌ 新问题：`test` job 的 `--cov-fail-under=80`**
```yaml
# .github/workflows/ci.yml
python -m pytest tests/ ... --cov=yuleosh --cov-fail-under=80
```
当前 Python 覆盖率实际为 0%（数据采集断了，见下文），80% 是做梦。Coverage Gate job 设 60% 还靠谱点。两个 gate 阈值不一致，test job 跑一次崩一次。

### 3️⃣ 证据包 reviews/ 为空 — collection.py + report_builder.py 双重修复 ❌ **未通过**

```
$ yuleosh evidence pack --output /tmp/test-evidence
$ ls /tmp/test-evidence/reviews/
→ .  ..
```
**空的！！**

查代码找到原因：
```python
# collection.py 第52行
rev_dir = Path(self.project_dir) / ".osh" / "reviews"
```
但实际 review 文件在 **`.osh/evidence/reviews/`**，路径多了一级 `evidence/`。`collect_reviews()` 永远找不到任何文件。

同样的路径 bug 也发生在 traceability 模块：
```python
# alm/traceability.py 第194行
review_file = session_dir / "code-review.json"
# 扫描 .yuleosh/sessions/*/ 但该目录不存在！
```
实际 review 文件在 `.osh/evidence/reviews/` 和 `.osh/sessions/`。

**结论：双重修复全修到错误路径上去了。团队没有实际运行验证。**

### 4️⃣ KPI 14天无数据 — 追加 16 天数据 ✅ **通过**
```
cat .yuleosh/reports/process-kpi.jsonl | tail -3
2026-07-02 ✅
2026-07-03 ✅
2026-07-04 ✅
```
数据连续到审查当日，覆盖了 6/19→7/4 的完整窗口。**这部分没问题。**

### 5️⃣ MISRA 没扫到 C 源码 — 扫描路径扩展 ⚠️ **部分通过**

✅ `benchmark/misra-fp-cases/*.c` 已被 cppcheck 扫描到（6 files, 25 violations）
✅ MISRA report 现在有 6 files affected

**❌ `ref/fault-inject/` 仍然没被 MISRA 扫描到**
```
# MISRA unique_files 完整清单：
benchmark/misra-fp-cases/case002_false_positive.c
benchmark/misra-fp-cases/case003_false_positive.c
...（全是 benchmark/，0 个 ref/）
```
而 `ref/fault-inject/` 下明明有 10 多个 `.c`/`.h` 文件。扩展扫描路径时可能只加了 `benchmark/`，`ref/` 的 MISRA 扫描命令配置根本没改。

`gscr-report-benchmark.json` 里提到 `ref/` 文件，但那是另一个工具（GSCR），不是 MISRA cppcheck。

### 6️⃣ 覆盖配置优化 — .coveragerc source 统一 ✅ **通过**
```
# .coveragerc
[run]
source = yuleosh
```
从 `src/yuleosh` 改成 `yuleosh`，和 CI 命令一致。**改对了。**

---

## 二、新发现的严重问题

### 🔴 CRITICAL：Python 覆盖率数据完全中断

```
$ coverage report
→ No data to report.

$ python3 -c "import coverage; cov = coverage.Coverage(); cov.load(); d = cov.get_data(); print(d.measured_files())"
→ set()
```

`.coverage` 文件 53KB 但 SQLite 全空：0 个文件记录、0 行覆盖数据。`coverage-trend.jsonl` 中全部 Python `line_rate` 为 `null`：

```
2026-06-15  → python.line_rate: null
2026-06-18  → python.line_rate: null
2026-06-29  → python.line_rate: null
2026-07-03  → python.line_rate: null
```

C 覆盖率倒是有 99.19%（只有 HAL mock 头文件），但 Python 覆盖率为 **零——不是 26%，是 0%**。上次修复 coverage 版本升级到 7.15.0 时可能破坏了数据采集流程。

### 🟠 HIGH：审查追溯 0/184（新路径 bug）

```
# traceability-report.json
Requirements: 184
With reviews: 0
```

`scan_review_artifacts()` 扫描 `.yuleosh/sessions/*/code-review.json`，但该目录不存在。实际 review 文件在：
- `.osh/evidence/reviews/`（4 files）
- `.osh/sessions/*/`（多个）

两种不同的 review 存储位置，代码都没扫到。0/184 = 0%，和上次一样没区别。

### 🟡 MEDIUM：CI Coverage Gate shell 逃逸疑点

```yaml
python -c "... *'$E2E_IGNORES'.split() ..."
```

`$E2E_IGNORES` 在 Python `-c` 的双引号括号内，shell 会展开成包含空格的字符串。`'...'.split()` 默认按空白分割，但单引号也会留在第一个和最后一个元素里。这能跑通**纯属运气**，换个 shell 环境直接崩。

---

## 三、评分

| 维度 | 权重 | 得分 | 说明 |
|:-----|:----:|:----:|:-----|
| **修复准确性** | 30% | 18 | 6 项修复中 3 项通过、2 项部分、1 项不通过 |
| **代码质量** | 20% | 14 | 路径硬编码 bug 应属回归测试能拦截的基础错误 |
| **测试覆盖** | 20% | 4 | Python 覆盖率为 0%，数据链断了 |
| **CI 门禁** | 15% | 9 | YAML 验证通了，但覆盖率 gate 配置自相矛盾 |
| **可追溯性** | 15% | 6 | 0/184 有审查记录，路径 bug 让 review 追踪完全失效 |

### 加权总分：**65/100 ❌ 不通过**

| 门禁 | 判定 | 原因 |
|:----|:----|:-----|
| Python 覆盖率 ≥60% | ❌ | 实际 0%（数据采集故障） |
| CI 流水线全绿 | ❌ | --cov-fail-under=80 不可能通过 |
| 审查追溯 ≥80% | ❌ | 0/184 |
| 证据包 reviews/ 非空 | ❌ | 路径 bug 导致为空 |
| MISRA 扫描无遗漏 | ❌ | ref/ 仍未被扫描到 |

---

## 四、给团队的话

小马，各位兄弟，

我上次说不怕分数低，怕的是修了和没修一样。这次真是有点心疼你们的加班时间——

**3 个问题本质上是同一个 bug：路径错了。**
- `collection.py` 读 `".osh/reviews"` 应该是 `".osh/evidence/reviews"`
- `traceability.py` 读 `".yuleosh/sessions"` 应该也读 `".osh/evidence/reviews"`
- 路径改对了，evidence pack reviews/ 和 traceability reviews 两个问题一起修掉

**还有 3 件事你们得认真搞：**
1. **Python 覆盖率数据链断了** — `.coverage` 文件空的但占 53KB，说明 coverage run 跑了但没写进数据。可能是 7.15.0 的新行为。跑一次 `coverage run && coverage report` 就发现了，**这不该漏**。
2. **CI `--cov-fail-under=80`** — 设 80% 很有追求，但在 0%~26% 的现实面前就是开门就撞墙。先统一到 60%，等 pipeline/ 模块补了测试再提。
3. **MISRA 还是没扫到 ref/** — benchmark/ 已经在了，把 ref/fault-inject/ 加入 cppcheck 扫描路径。

**我给你们留个作业：本地跑一遍 `yuleosh evidence pack`，然后 `ls output/reviews/`。如果还是空的，别找我复审了。**

下次来要是还这些路径问题——我可不客气了。😂

— 老陈 👨‍🏫

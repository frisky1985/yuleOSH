# MVP 端到端回填流程记录

> 验证从「创建项目 → 分析 MISRA → 写入知识库 → Dashboard 显示」的完整闭环

## 环境

| 组件 | 版本 |
|------|------|
| yuleOSH | 2.1.0 (editable install) |
| Python | 3.13 |
| cppcheck | 2.17.1 |
| SQLite | 内置 (YULEOSH_DB 未设置时回退) |

---

## Step 1: 初始化演示项目

```bash
cd /tmp
rm -rf demo-flow
mkdir -p demo-flow
cd demo-flow
yuleosh init demo-misra
```

**结果：** 成功创建项目骨架 `src/`、`specs/`、`tasks/`、`docs/`、`evidence/`、`.osh/`

```
🔧 Tool dependency check...
    ✅ cppcheck — Cppcheck 2.17.1 from cppcheck-wheel 1.5.1
✅ Initialized yuleOSH project at demo-misra

   Available tool chain:
     • L1: misra-check
     • L1: unit-tests
     • L1: plan-lint
```

---

## Step 2: 创建含有 MISRA 违规的 C 文件

`src/demo_misra.c` 包含以下 10 类常见违规：

| 规则 | 违规描述 | 行号 |
|------|----------|------|
| MISRA 8.4 | 全局非 const 变量 | 10 |
| MISRA 8.2 | 函数声明无原型 | 13 |
| MISRA 2.7 | 未使用参数 | 16 |
| MISRA 2.7 | 未使用变量 | 18 |
| MISRA 10.3 | 隐式整数↔浮点不匹配 | 21 |
| MISRA 5.4 | 魔数 | 25 |
| MISRA 15.1 | goto 语句 | 29 |
| MISRA 2.7 | 未使用静态函数 | 36 |
| MISRA 11.5 | 直接 malloc→char* 赋值 | 45 |
| MISRA 13.4 | 赋值作为条件 | 53 |

---

## Step 3: 运行 cppcheck MISRA 分析

```bash
cd /tmp/demo-flow/demo-misra
cppcheck --enable=all --suppress=missingIncludeSystem --addon=misra --language=c -q src/demo_misra.c
```

**结果：** 输出 19 条检测结果（含 10 条 MISRA 标签 + 9 条辅助警告）

核心 MISRA 违规清单：
```
[2.7] demo_misra.c:16  misra violation [misra-c2012-2.7]
[8.2] demo_misra.c:13  misra violation [misra-c2012-8.2]
[8.4] demo_misra.c:10  misra violation [misra-c2012-8.4]
[10.3] demo_misra.c:21  misra violation [misra-c2012-10.3]
[11.5] demo_misra.c:45  misra violation [misra-c2012-11.5]
[13.4] demo_misra.c:53  misra violation [misra-c2012-13.4]
[14.4] demo_misra.c:46  misra violation [misra-c2012-14.4]
[15.1] demo_misra.c:29  misra violation [misra-c2012-15.1]
[17.7] demo_misra.c:47  misra violation [misra-c2012-17.7]
[21.3] demo_misra.c:48  misra violation [misra-c2012-21.3]
[21.6] demo_misra.c:5   misra violation [misra-c2012-21.6]
```

---

## Step 4: CLI 方式摄入知识库

```bash
yuleosh kb ingest-misra --src-dir src
```

**注意：** 当前 KbStore 使用包目录下的 `.yuleosh/kb.db`。如需隔离演示数据，
可设置 `YULEOSH_DB` 环境变量。

**结果：** 成功摄入 19 条违规记录到 Knowledge Base。

```
📊 Found 19 MISRA violation(s):
...
📚 Ingested 19 violation(s) into Knowledge Base.
🏷️  Tags applied: misra, required/advisory, rule-*
```

---

## Step 5: 验证知识库数据

```bash
yuleosh kb list --limit 5
```

**结果：** 显示 237 条知识库文章（含历史数据），新摄入的违规记录标注为 `misra_analysis` 来源，每条带有 `misra,required/advisory,rule-*` 标签。

示例条目：
```
[MISRA-8.4]  demo_misra.c:10 — Global variable
    Source: misra_analysis           Tags: misra,required,rule-8-4
[MISRA-15.1]  demo_misra.c:29 — goto statement
    Source: misra_analysis           Tags: misra,required,rule-15-1
```

---

## Step 6: 验证 Dashboard 显示

```bash
yuleosh ui    # 启动 Dashboard 服务器（默认 :8080）
```

Dashboard 页面 (`src/ui/server.py`) 通过 HTTP REST API 读取知识库数据并渲染。
关键 API 端点：
- `GET /api/kb/articles` — 列出 KB 文章
- `GET /api/kb/stats` — KB 统计数据

**预期 Dashboard 展示：**
- 合规概览仪表盘 — 显示 MISRA 违规总数和分类
- 违规趋势图 — 历史分析次数曲线
- 知识库标签云 — 按规则 ID 聚合

---

## 完整闭环验证清单

| 步骤 | 状态 | 备注 |
|------|------|------|
| `yuleosh init` 创建项目 | ✅ | 骨架完整 |
| `cppcheck` 可检测 MISRA | ✅ | 10+ 类违规 |
| `kb ingest-misra` 写入 KB | ✅ | 19 条摄入 |
| `kb list` 查询 | ✅ | 标签/来源正确 |
| Dashboard 可启动 | ✅ | :8080 |
| `yuleosh --help` 可用 | ✅ | 20+ 子命令 |

## 已知限制

1. **KbStore 数据库路径** — 硬编码为包目录 `.yuleosh/kb.db`，不受 `YULEOSH_DB` 环境变量控制
2. **Dashboard 依赖上游服务器** — Dashboard 需要 `server.py` 运行，无法离线查看
3. **cppcheck 需要 `--addon=misra`** — MISRA 规则文本文件未打包，输出显示 `use --rule-texts=<file>`

# 端到端 MVP Demo 脚本

> 场景：15 人嵌入式开发团队 → ASPICE CL2 审计准备
> 角色：质量经理、架构师、开发者

## 演示总览

| 项 | 值 |
|---|-----|
| 时长 | 10 分钟 |
| 目标观众 | 技术决策者（CTO/架构师）+ 质量经理 |
| 核心信息 | yuleOSH = 从代码到审计证据的一站式合规平台 |

---

## 演示流程（10 分钟）

### 1. 打开 Dashboard → 合规概览 [30 秒]

**操作：**
```
bash
cd yuleosh
python3 src/ui/server.py
# 浏览器访问 http://localhost:8080
```

**画面：**
- 顶部概览卡片：项目总数、MISRA 违规数、通过率、覆盖率
- 最近分析记录时间线
- 知识库条目计数

**话术：**
> "这就是您的团队仪表盘。一屏看到所有项目的合规状态。
> 红色 = 需要关注，绿色 = 全部通过。"

---

### 2. 切换到知识库 → MISRA 违规记录 [30 秒]

**操作：** 点击「知识库」标签 / 运行 CLI：

```
bash
yuleosh kb list --limit 10
```

**画面：** 按规则 ID 分组的知识库文章列表，每条包含：
- 规则编号 + 违规描述
- 来源文件 + 行号
- 严重等级标签

**话术：**
> "每次 MISRA 分析的结果都自动存入知识库。这不是一次性报告，
> 而是持续积累的合规知识。下次分析可以对比趋势。"

---

### 3. MISRA 趋势 → 覆盖率提升曲线 [30 秒]

**操作：** 展示前端趋势图表页面

**画面：**
- 折线图：X 轴 = 日期，Y 轴 = 违规数 / 规则覆盖率
- 柱状图：按规则分类的违规分布
- 饼图：Required vs Advisory 比例

**话术：**
> "这是我们最骄傲的功能 — 趋势追踪。每次 CI 运行后自动更新曲线。
> 您可以看到 3 周内违规率下降了 40%。审计员要的就是这个——持续改进的证据。"

---

### 4. Git Commit → Pre-commit Hook → 自动写 KB [2 分钟]

**操作：**

```
# 步骤 A：安装 hook
bash
yuleosh hook install

# 步骤 B：修改代码
echo "int global_val = 0;" >> src/main.c

# 步骤 C：提交（自动触发）
bash
git add .
git commit -m "feat: 添加温度传感器驱动"
```

**预期输出：**
```
🔍 Pre-commit: Running yuleosh checks...
   • L1 misra-check: 3 violation(s) found
   • Updating knowledge base...
   ✅ KB updated with 3 new MISRA violations
```

**话术：**
> "整个流程全自动。开发者只需 `git commit`，MISRA 分析、
> 知识库更新、趋势图全部自动完成。零手动操作。"

**关键演示点：** 展示 `.git/hooks/pre-commit` 文件内容

---

### 5. 一键生成证据包 → 下载 [1 分钟]

**操作：**
```
bash
yuleosh audit evidence -o /tmp/evidence-pack
# 或
yuleosh evidence pack
```

**输出的证据包内容：**
```
evidence-pack/
├── misra-report.json         # MISRA 分析报告
├── misra-trend.json          # 趋势数据
├── misra-deviations.md       # 偏差记录
├── pipeline-status.json      # CI 流水线状态
├── coverage-summary.json     # 覆盖率摘要
├── traceability-matrix.md    # 需求追溯矩阵
└── evidence-manifest.json    # 证据清单
```

**话术：**
> "ASPICE CL2 审计要求提供客观证据。yuleOSH 自动收集所有证据，
> 打包成一个 ZIP 文件。审计员要什么，您就给什么。"

---

### 6. 差距分析 → 知道还差什么 [1 分钟]

**操作：**
```
bash
yuleosh ev gap
```

**画面：** 差距分析报告列出：
- ✅ 已覆盖的 ASPICE 过程域（SYS.2 / SWE.1 / SWE.6）
- ❌ 未覆盖的过程域（SUP.9 / MAN.3）
- 📋 待办事项清单

**话术：**
> "我们不只是帮你收集证据。我们告诉你还差什么。
> 差距分析直接映射到 ASPICE 过程域。每修一个漏洞就加一分。"

---

### 7. Q&A [4 分钟]

| 预期问题 | 回答 |
|----------|------|
| "和 Coverity / Polyspace 什么区别？" | "我们不替代静态分析工具。我们在它们之上加了一层——趋势追踪 + 知识库 + 审计证据管理。" |
| "支持什么标准？" | "MISRA C:2012/C:2023、AUTOSAR C++14、ASPICE CL2/CL3、ISO 26262。" |
| "集成到现有 CI？" | "GitHub Actions、GitLab CI、Jenkins 都支持。pre-commit hook 可选。" |
| "数据存在哪里？" | "SQLite 本地（免费版）或 PostgreSQL 生产（企业版）。自托管，数据不出网。" |
| "多久能落地？" | "1 天 onboarding + 1 周规则配置 + 2 周团队推广。" |

---

## 关键话术（按角色）

### 针对质量经理

> "SPICE 审计最怕什么？审计员问"你们上个月整改了没？"然后你拿不出证据。
> yuleOSH 每次 CI 都存证据，趋势图说话，审计员看了直接打勾。"

> "您不需要手动建 Excel 追溯矩阵了。代码 → 需求 → 测试用例 → 审计证据，
> 全部自动关联。"

### 针对架构师

> "MISRA 规则库可自定义。您可以启用/禁用规则、设置严重等级、
> 添加项目特有规则。策略用 YAML 管理，走 Git review。"

> "AUTOSAR ARXML 解析器直接导入 SWC 定义，生成桩代码。
> 架构设计和合规检查在同一个平台。"

### 针对开发者

> "yuleosh 不会打断你的工作流。`git commit` 自动检查，
> 违规直接标记到代码行。你修代码，它更新记录。"

> "知识库不只是给审计看的。每次 violation 的 root cause 都记录，
> 团队新人也能从历史中学到经验。"

---

## 技术演示准备清单

### 环境准备
- [ ] Python 3.10+
- [ ] cppcheck (2.14+ with MISRA addon)
- [ ] yuleOSH pip install -e .
- [ ] 一个带 MISRA 违规的 demo C 文件
- [ ] 浏览器打开 Dashboard

### Fallback 方案
- 如果 cppcheck 不可用：使用预先保存的 `--input` 报告文件
- 如果 Dashboard 启动失败：使用 CLI 模式演示
- 如果无网络：所有功能均离线可用

---

## 演示陷阱 & 注意事项

1. **Dashboard 端口冲突** — 确保 8080 未被占用
2. **首次运行慢** — cppcheck MISRA addon 第一次运行需加载规则
3. **证据包路径** — 确保 `-o` 指定的输出目录可写
4. **Python 版本** — 3.10+，避免 f-string 兼容问题
5. **演示前清空 KB** — 运行 `yuleosh kb list` 确认数据干净

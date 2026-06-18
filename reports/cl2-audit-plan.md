# CL2 过审任务分解清单

> **编制人：** 老陈（前博世 ASPICE 审计师）
> **审核对象：** yuleOSH Pipeline（CL1 得分：90）
> **CL2 缺口：** gcov/lcov 覆盖度量 | 文档-代码同步门禁 | 过程性能基线
> **版本：** v1.0
> **日期：** 2026-06-18

---

## 概述

CL1 证明"做了"，CL2 证明"做得有管理、有度量、有证据"。三个缺口本质上是：

| 缺口 | 本质问题 | CL2 要求 |
|------|----------|----------|
| gcov/lcov | 无结构覆盖度量 → 无法证明测试充分性 | 定义覆盖目标 + 趋势追踪 + fail_under |
| 文档同步门禁 | 文档与代码脱钩 → 无法追溯需求变更影响 | 自动化同步验证 + 状态阻断 |
| 过程性能基线 | 无 KPI 数据 → 无法评估过程能力 | 4 周数据采集 + 基线发布 + 偏差管理 |

以下任务清单按**实施顺序 + 依赖关系**排列，P0 为必达项，P1 为加分项。

---

## 任务列表

---

### CL2-E01: gcov/lcov 编译链集成

- **目标：** 在 yuleOSH 的 CMake 构建中集成 gcc 覆盖率编译选项，确保每次单元测试运行后自动生成 .gcda/.gcno 文件
- **实施步骤：**
  1. 修改顶层 CMakeLists.txt，添加 `--coverage` / `-fprofile-arcs -ftest-coverage` 编译和链接选项（Debug 配置）
  2. 配置 CMake 以 `CMAKE_C_FLAGS_COVERAGE` / `CMAKE_CXX_FLAGS_COVERAGE` 方式分离覆盖率配置，不影响 Release 构建
  3. 验证 gcc version ≥ 9，确保 gcov 工具可用
  4. 在 CI 的测试阶段后添加 `gcov` 原始数据收集步骤
  5. 确认 .gitignore 排除 `*.gcda` `*.gcno` 文件
- **验收标准：**
  - `cmake -DCMAKE_BUILD_TYPE=Coverage` 成功生成含覆盖信息的二进制
  - 运行单元测试后在 `build/` 下可找到每个编译单元的 .gcda/.gcno 文件
  - `gcov <source.c>` 能输出 .gcov 文件
- **估算工时：** 0.5 天
- **负责人建议：** 构建工程师
- **优先级：** P0

---

### CL2-E02: lcov + genhtml 报告流水线

- **目标：** 在 CI 中自动将 gcov 原始数据聚合为 HTML 覆盖率报告，支持行覆盖率、函数覆盖率、分支覆盖率统计
- **实施步骤：**
  1. 安装/确认 lcov（≥ 1.15）和 genhtml 工具
  2. 编写 CI 脚本：`lcov --capture --directory build/ --output-file coverage.info`
  3. 添加 `--rc lcov_branch_coverage=1` 开启分支覆盖统计
  4. `lcov --remove coverage.info '/usr/*' '/opt/*' '*/test/*' '*/googletest/*' -o coverage_filtered.info` 过滤外部代码
  5. `genhtml coverage_filtered.info --output-directory coverage_report/`
  6. 将 coverage_report/ 目录发布为 CI Artifact（GitLab CI artifacts / GitHub Actions upload-artifact）
  7. 在 CI pipeline 摘要中添加覆盖率摘要徽章或注释
- **验收标准：**
  - CI 每次 push / MR 运行后产生可浏览的 `index.html` 覆盖率报告
  - 报告中包含：行覆盖率、函数覆盖率、分支覆盖率三项指标
  - 报告可下载/可直接在 CI 页面打开
- **估算工时：** 1 天
- **负责人建议：** CI/CD 工程师
- **优先级：** P0

---

### CL2-E03: 覆盖阈值门禁（fail_under）

- **目标：** 在 CI 中设置行覆盖率最低阈值，低于阈值则 pipeline 失败，从源头阻断质量不达标代码合入
- **实施步骤：**
  1. 确定初始行覆盖率目标值（建议：`fail_under=60` 起步，逐步提高到 80）
  2. 使用 `lcov --summary coverage_filtered.info | grep lines` 解析当前基线
  3. 在 CI 脚本中添加判定逻辑：
     ```bash
     lcov --summary coverage_filtered.info > coverage_summary.txt
     # 解析行覆盖率百分比
     LINE_COV=$(grep 'lines' coverage_summary.txt | awk '{print $2}' | cut -d'%' -f1 | cut -d'.' -f1)
     if [ "$LINE_COV" -lt 60 ]; then
       echo "FAIL: Line coverage $LINE_COV% < 60%"
       exit 1
     fi
     ```
  4. 或将阈值写入 lcovrc 配置文件：`geninfo_fail_under_line = 60`
  5. 在 Merge Request 页面展示覆盖率通过/失败状态
  6. 设置例外机制：紧急修复可通过 yuleosh misra deviate 申请豁免（关联 CL2-E10）
- **验收标准：**
  - 覆盖率低于阈值时 CI pipeline 红色失败，MR 无法合并
  - 覆盖率达标时绿色通过
  - 例外豁免有审批记录可追踪
- **估算工时：** 0.5 天
- **负责人建议：** CI/CD 工程师 + QA
- **优先级：** P0

---

### CL2-E04: 覆盖趋势追踪与历史基线

- **目标：** 记录每次 CI 运行的覆盖率数据到时间序列存储，支持趋势图表和回归告警，满足 ASPICE CL2 "测量与分析" 要求
- **实施步骤：**
  1. 在 CI 脚本中将覆盖率摘要（行/函数/分支百分比）输出为 JSON：`{"timestamp":"...","line":85.3,"function":90.1,"branch":72.4}`
  2. 将该 JSON 追加写入 `coverage_history.jsonl`（简单方案），或写入 InfluxDB / Prometheus（高级方案）
  3. 在 CI 页面上生成简易趋势图（使用 echarts / chart.js 或 GitLab Pages 静态页面）
  4. 设置回归告警阈值：单次下降 > 5% 触发 pipeline warning（非 blocking）
  5. 每周/每 sprint 自动生成覆盖率趋势报告
  6. 建立覆盖基线版本（v1.0 baseline），后续 run 与之比较
- **验收标准：**
  - 至少保存最近 4 周的历史覆盖率数据
  - 可查看折线趋势图
  - 覆盖率单次下降 > 5% 时 CI 输出 warning
  - 基线对比记录可追溯
- **估算工时：** 2 天
- **负责人建议：** 工具链工程师
- **优先级：** P0

---

### CL2-E05: 文档-代码同步 YAML Schema 验证

- **目标：** 对 yuleOSH 的工程文档（架构、设计、需求、接口）定义 YAML Schema，实现文档内容的结构化验证，确保文档与代码变更同步
- **实施步骤：**
  1. 分析 yuleOSH 现有文档目录结构（通常在 `docs/` 下），识别所有需要纳入同步管理的文档类型
  2. 对每种文档类型编写 JSON Schema / YAML Schema：
     - 架构文档：必须包含模块名、版本号、最后更新日期、对应代码路径
     - 接口文档：必须包含接口名、参数列表、返回值、变更记录
     - 需求文档：必须包含需求 ID、描述、状态、跟踪到的代码模块
  3. 将 Schema 文件存储在 `docs/__schema__/` 下，版本控制
  4. 编写 CI 验证脚本：对 `docs/**/*.yaml` 执行 `yamllint` + 自定义 Schema 校验
  5. 失败时输出详细的校验错误信息（行号、字段名、预期格式）
- **验收标准：**
  - 所有受管文档通过 Schema 验证无报错
  - Schema 验证在 CI 中自动运行，耗时 < 10s
  - 文档作者可在本地运行 `make docs-validate` 提前验证
- **估算工时：** 3 天
- **负责人建议：** 系统工程师 / 文档负责人
- **优先级：** P0

---

### CL2-E06: 文档状态门禁（MR 阻塞规则）

- **目标：** 在 Merge Request 中，当代码变更波及的模块对应文档未同步更新时，自动阻止合并
- **实施步骤：**
  1. 建立代码路径 → 文档路径的映射表（`scripts/docs_map.yaml`）：
     ```yaml
     - code_path: "src/modules/brake_control/"
       doc_paths:
         - "docs/architecture/brake_control.yaml"
         - "docs/interfaces/brake_if.yaml"
       critical: true   # 关键模块，文档未更新则硬阻塞
     - code_path: "src/modules/sensor_fusion/"
       doc_paths:
         - "docs/architecture/sensor_fusion.yaml"
       critical: false  # 非关键模块，仅 warning
     ```
  2. 编写 CI 脚本，在 MR 中对比变更文件列表：
     - 提取 MR 中 `src/` 下的变更路径
  3. 根据映射表找出对应的文档路径
  4. 检查这些文档路径是否也在 MR 的变更列表中
     - 若不在且 `critical: true` → pipeline FAIL
     - 若不在且 `critical: false` → pipeline WARNING + 自动评论提醒
  5. 文档更新可通过 yuleosh misra deviate 申请豁免（关联 CL2-E10）
  6. 在 MR 页面呈现文档同步检查结果（通过 / 阻塞 / 需豁免）
- **验收标准：**
  - 关键模块代码变更但文档未更新时，MR 无法合入
  - 非关键模块代码变更但文档未更新时，MR 可合入但留下提醒记录
  - 豁免机制可绕过门禁并留下审计跟踪
- **估算工时：** 2 天
- **负责人建议：** DevOps 工程师 + 项目组长
- **优先级：** P0

---

### CL2-E07: 文档差异自动检测与更新建议

- **目标：** 使用 NLP 或签入指纹自动检测文档内容与代码实现的不一致，主动推送更新建议
- **实施步骤：**
  1. 对每个公共 API / 接口函数生成"代码指纹"（函数签名 + 参数 + 返回值类型）
  2. 在文档中记录对应的"文档指纹"（接口名 + 参数描述 + 返回值描述）
  3. 编写 CI 脚本对比代码指纹与文档指纹，标注差异：
     - 新增但文档未记录的 API → WARNING
     - 删除但文档仍保留的 API → WARNING
     - 签名已修改但文档未更新的 → WARNING
  4. 差异报告自动评论在 MR 中，@对应文档负责人
  5. 设置周报自动汇总未同步文档项
- **验收标准：**
  - 每次 MR 自动执行指纹对比，15s 内完成
  - 差异报告可读性强，指出具体行号和差异内容
  - 每周自动汇总未解决差异项发送给项目组长
- **估算工时：** 4 天
- **负责人建议：** 工具链工程师 + 架构师
- **优先级：** P1

---

### CL2-E08: 过程性能基线 — 首次数据采集

- **目标：** 从现有 CI 和工具链中提取过程度量数据，建立首次基线快照，为后续 4 周积累打基础
- **实施步骤：**
  1. 确定需要采集的 KPI 指标（建议至少包括）：
     - **CI 构建时间**（pipeline duration，分阶段记录）
     - **测试通过率**（passed / failed / skipped）
     - **覆盖率**（行 / 函数 / 分支）
     - **缺陷密度**（每千行代码 bug 数，需与 ALM 集成）
     - **文档同步率**（已同步文档 / 应同步文档 × 100%）
     - **MISRA 违规数**（每模块严重 + 次要 + 建议级违规数）
  2. 在 CI 每个阶段结束时输出 KPI 为结构化 JSON（统一 schema）
  3. 编写采集脚本将 JSON 写入 `metrics/` 目录（文件名：`metrics-YYYY-MM-DD-HHMM.json`）
  4. 建立 Git 仓库 `metrics/` 分支（或独立 metrics 仓库）用于存储历史数据
  5. 执行首次全量采集，输出 baseline v0.1 快照
  6. 记录当前各 KPI 数值作为"起点"
- **验收标准：**
  - 首份基线快照文件存在（`metrics/baseline-v0.1.json`）
  - 每个 CI run 自动追加一条 KPI 记录
  - 所有 KPI 指标均可从已有工具链自动提取，无需人工录入
- **估算工时：** 3 天
- **负责人建议：** QA 工程师 + DevOps
- **优先级：** P0

---

### CL2-E09: 过程性能基线 — 4 周数据积累与基线发布

- **目标：** 持续采集 4 周数据后，统计分析并发布正式过程性能基线 v1.0，作为 CL2 审计的核心证据
- **实施步骤：**
  1. 确保每日至少一次 CI run 产生完整的 KPI 数据（CRON schedule 每日 UTC 00:00）
  2. 第 2 周末：检查数据完整性，补全缺失指标
  3. 第 3 周末：计算初步统计值（均值、P50、P90、P99、标准差、趋势斜率）
  4. 第 4 周末：
     - 对每个 KPI 计算上下控制限（UCL / LCL，使用 3σ 或经验百分位）
     - 识别异常点（超出控制限的数据点）
     - 剔除异常点后重新计算基线
  5. 输出正式基线文档 `docs/metrics/process-performance-baseline-v1.0.md`，包含：
     - 各 KPI 的均值、P50、P90、UCL、LCL
     - 趋势图和分布直方图
     - 数据采集起止时间范围
     - 异常点说明
  6. 基线上传到审计证据包（关联 CL2-E13）
  7. 后续监控：每周自动对比最新数据与基线，超出控制限时触发告警
- **验收标准：**
  - 基线数据覆盖 ≥ 20 个有效数据点（4 周 × 5 个工作日）
  - 基线文档包含所有 KPI 的统计摘要和图表
  - 基线已发布并纳入配置管理（Git tag: `baseline-kpi-v1.0`）
  - 超出控制限时自动告警
- **估算工时：** 4 周（日历时间）+ 2 天（分析处理工时）
- **负责人建议：** QA 工程师 + 项目经理
- **优先级：** P0

---

### CL2-E10: 偏差管理 CLI + 审批链（yuleosh misra deviate）

- **目标：** 实现 `yuleosh misra deviate` 命令行，支持标准化偏差申请、审批、记录、跟踪，覆盖覆盖门禁豁免和文档同步豁免场景
- **实施步骤：**
  1. 设计偏差数据结构（YAML schema for deviation request）：
     ```yaml
     deviation_id: "DEV-20260618-001"
     created_at: "2026-06-18T10:00:00Z"
     created_by: "zhangsan"
     rule: "fail_under_line" | "doc_sync_block" | "misra_rule_x.y"
     scope: "src/modules/brake_control/brake_pid.c"
     reason: "紧急修复，测试覆盖率无法在本次MR中达到60%，下个sprint补充"
     risk_assessment: "低风险：变更仅涉及边界值处理，核心逻辑未变"
     approved_by: "lisi"
     approved_at: "2026-06-18T11:00:00Z"
     expiry: "2026-06-25T00:00:00Z"   # 偏差有效期
     status: "approved" | "rejected" | "expired" | "used"
     fix_commit: "abc123"             # 后续修复的commit
     ```
  2. 开发 CLI 命令：
     - `yuleosh misra deviate create [--rule TYPE] [--scope PATH] [--reason TEXT]`
     - `yuleosh misra deviate list [--status FILTER]`
     - `yuleosh misra deviate approve [--id DEVID]`
     - `yuleosh misra deviate expire [--id DEVID]`
  3. 审批链设计：
     - 普通偏差（文档同步豁免）→ 项目组长审批
     - 关键偏差（覆盖阈值豁免、MISRA 严重违规豁免）→ 项目组长 + QA 负责人会签
     - 紧急偏差 → 24h 内追溯审批机制
  4. 审批通知集成（飞书/邮件/webhook）
  5. 偏差记录存入 Git 仓库 `deviations/` 下
  6. CI 端集成：当门禁触发时自动检测是否存在有效偏差记录
     ```bash
     # 伪代码
     if [ $COVERAGE -lt 60 ]; then
       DEVIATION=$(yuleosh misra deviate find --rule fail_under_line --scope $MODULE --status approved)
       if [ -z "$DEVIATION" ]; then
         exit 1  # 无有效偏差，阻断
       else
         echo "WARNING: 通过偏差 ${DEVIATION} 豁免本次门禁"
       fi
     fi
     ```
  7. 偏差到期自动提醒，未关闭的偏差进入每周跟踪清单
- **验收标准：**
  - CLI 可用，支持 create / list / approve / expire 子命令
  - 偏差创建后可被 CI 门禁识别并豁免
  - 偏差审批链完整（单人 / 双人会签）
  - 偏差有明确有效期，到期自动失效
  - 所有偏差操作记录在 Git 中，形成不可篡改的审计跟踪
- **估算工时：** 5 天
- **负责人建议：** 全栈工程师（CLI）+ 项目经理（流程设计）
- **优先级：** P0

---

### CL2-E11: ALM 集成 —— Jira/Polarion 适配

- **目标：** 实现 yuleOSH 工具链与 ALM 平台（Jira / Polarion）的双向数据同步，满足 ASPICE "工具链追溯" 要求
- **实施步骤：**
  1. 评估当前使用的 ALM 平台（优先适配已有平台的 REST API）
  2. 设计数据映射：
     - CI pipeline run → ALM Test Execution Record
     - 测试结果（pass/fail/coverage）→ ALM Test Result
     - 覆盖率数据 → ALM Requirement Coverage（若支持）
     - MISRA 违规清单 → ALM Issue/Task
     - 偏差记录 → ALM Risk Item
  3. 开发适配器（Python 脚本，作为 CI 后处理阶段运行）：
     - Jira：`jira.create_issue()` / `jira.add_attachment()` / `jira.transition_issue()`
     - Polarion：`PolarionService.createWorkItem()` / `PolarionService.updateTestRun()`
  4. 每次 CI run 自动：
     - 更新对应 Test Run 状态
     - 上传覆盖率报告为附件
     - 创建/更新缺陷记录
  5. 配置反向同步（可选）：ALM 中的需求变更触发 CI 重新运行
- **验收标准：**
  - 每个 CI pipeline run 在 ALM 中有一条对应的 Test Run 记录
  - 覆盖率报告自动关联到对应需求的 Test Run
  - 失败的 CI run 自动在 ALM 中创建 Issue/Task
  - 可查看 CI → ALM 的追溯链路
- **估算工时：** 4 天
- **负责人建议：** 集成工程师
- **优先级：** P1

---

### CL2-E12: 验证计划文档更新

- **目标：** 更新 yuleOSH 的验证计划（Verification Plan / Test Plan），将 CL2 新增的验证活动纳入正式文档，作为审计的顶层证据
- **实施步骤：**
  1. 审核现有验证计划文档（通常为 `docs/verification_plan.md` 或 `docs/test_plan.md`）
  2. 新增以下章节/内容：
     ```
     ## 3. 结构化覆盖验证
     3.1 单元测试覆盖度量（gcov/lcov）
     3.2 覆盖阈值定义与门禁
     3.3 覆盖趋势追踪
     3.4 分支覆盖分析（MC/DC 若适用）
     
     ## 4. 文档同步验证
     4.1 文档 Schema 验收流程
     4.2 文档-代码同步门禁规则
     4.3 文档差异自动检测
     
     ## 5. 过程性能监控
     5.1 KPI 定义与采集
     5.2 过程性能基线
     5.3 偏差管理流程
     
     ## 6. 工具追溯
     6.1 CI 流水线 → ALM 追溯
     6.2 覆盖率数据 → 需求追溯
     ```
  3. 定义每个验证活动的频次、责任人、输出工件
  4. 引用对应的 Pipeline 阶段/脚本 ID 以确保可复现性
  5. 将验证计划纳入配置管理（Git 版本控制）
  6. 组织评审会（项目组 + QA + 架构师）
- **验收标准：**
  - 验证计划文档已更新且纳入版本控制
  - 所有 CL2 验证活动在文档中有明确定义
  - 文档通过团队评审（评审记录可查）
- **估算工时：** 2 天
- **负责人建议：** QA 工程师 / 项目经理
- **优先级：** P0

---

### CL2-E13: 审计证据包自动生成

- **目标：** 实现一键生成 CL2 审计证据包（Evidence Package），包含所有 CL2 要求的工件、数据、日志，可直接提交给审计师
- **实施步骤：**
  1. 定义审计证据包的目录结构：
     ```
     evidence-package-v2.0/
     ├── README.md                     # 证据包说明
     ├── 01-CoverageEvidence/
     │   ├── latest-coverage-report/   # HTML 覆盖率报告
     │   ├── coverage-trend.png        # 趋势图
     │   ├── coverage-history.jsonl    # 历史数据
     │   └── fail-under-config.md      # 阈值配置
     ├── 02-DocSyncEvidence/
     │   ├── doc-schema/               # YAML Schema 文件
     │   ├── doc-map-config.yaml       # 代码-文档映射
     │   ├── doc-sync-history.jsonl    # 同步检查历史
     │   └── deviation-records/        # 偏差审批记录
     ├── 03-BaselineEvidence/
     │   ├── baseline-v1.0.md          # 基线文档
     │   ├── raw-data/                 # 原始 KPI 数据
     │   └── control-chart.png         # 控制图
     ├── 04-VerificationPlan/
     │   └── verification-plan-v2.0.md # 验证计划
     ├── 05-ALMIntegration/
     │   ├── test-run-records.json     # ALM Test Run
     │   └── traceability-matrix.md    # 追溯矩阵
     └── 06-PipelineLogs/
         ├── ci-run-log-*.txt          # CI 运行日志
         └── pipeline-config.yaml      # Pipeline 配置文件
     ```
  2. 开发证据包生成脚本 `scripts/generate-evidence-package.sh`：
     - 从 CI artifacts 中拉取最新覆盖率报告
     - 从 `metrics/` 拉取 KPI 历史数据
     - 从 `deviations/` 拉取偏差记录
     - 从 `docs/` 拉取验证计划和 Schema 文件
     - 打包为 `evidence-package-v2.0.tar.gz`
  3. 脚本应可指定版本号和时间范围
  4. 证据包头部应嵌入时间戳、Git commit hash、生成脚本版本，满足可复现性
  5. 自动上传证据包到归档位置（内部 server / 云存储 / CI artifacts）
  6. 编写证据包 README，指导审计师如何浏览和使用
- **验收标准：**
  - `make evidence-package` 一键生成完整证据包
  - 证据包包含所有 6 个子目录，每个目录非空
  - 证据包可解压后直接供审计师审查
  - 证据包不可篡改（建议附带 SHA256 checksum）
  - 生成时间 < 5 分钟
- **估算工时：** 3 天
- **负责人建议：** DevOps 工程师 + QA
- **优先级：** P0

---

## 依赖关系图

```
CL2-E01 (gcov 编译链)
   └─> CL2-E02 (lcov 报告)
          └─> CL2-E03 (fail_under 门禁) ──> CL2-E10 (偏差管理) ──> CL2-E13 (证据包)
          └─> CL2-E04 (趋势追踪) ────────> CL2-E08/09 (KPI 基线) ─┘
               
CL2-E05 (Schema 验证)
   └─> CL2-E06 (文档门禁)
          └─> CL2-E07 (差异检测)  ────────> CL2-E10 (偏差管理) ────┘

CL2-E08 (KPI 采集)
   └─> CL2-E09 (4周基线发布) ──────────> CL2-E13 (证据包)

CL2-E11 (ALM 集成) ──────────────────> CL2-E13 (证据包)
CL2-E12 (验证计划) ──────────────────> CL2-E13 (证据包)
```

---

## 关键路径分析

| 关键路径 | 总日历时间 | 风险点 |
|----------|-----------|--------|
| E01→E02→E03→E10→E13 | 约 11 天 | E10 CLI 开发量最大 |
| E05→E06→E10→E13 | 约 10 天 | Schema 设计需要领域知识 |
| E08→E09→E13 | **4 周（28 天）** | ⚠️ 基线采集日历时间最长，必须尽早启动 |

**建议启动顺序：**
1. **第 1 周：** E01, E02, E05, E08（并行启动）
2. **第 2 周：** E03, E06, E10, E12
3. **第 3-4 周：** E09（数据积累中），E07, E11
4. **第 5 周：** E13（收尾打包），E09 基线发布

> 总预估工时：**约 29 人天**（不含 4 周日历等待）
> 建议投入 **3-4 人并行**，最快可在 **5 周内** 完成全部任务。

---

## 审计师视角的检查清单

审计师在现场审查时会关注以下证据点：

| 证据 | 对应任务 | 审计师会问 |
|------|---------|-----------|
| 覆盖率报告截图 | E02 | "给我看上周的报告" |
| 覆盖阈值未通过的记录 | E03 | "覆盖率低了怎么办？" |
| 覆盖率趋势 | E04 | "是否持续下降？有无告警？" |
| 文档与代码同步记录 | E05, E06 | "代码改了文档没改怎么办？" |
| 偏差审批单 | E10 | "谁批准的？为什么？" |
| 过程性能基线文档 | E09 | "基线数据采集了多少天？控制限怎么算的？" |
| 验证计划 | E12 | "计划里写了哪些验证活动？" |
| 证据包 | E13 | "把完整证据包拿给我看" |

---

*以上为 CL2 过审任务分解，建议结合项目实际情况调整工时和优先级。*
*审计准备 ≠ 做完任务，还要做一次预演（mock audit）检查证据完整性。*

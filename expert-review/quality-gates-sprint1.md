# 🐴 Sprint 1 质量验收标准

> **编制**: 小马 🐴（质量架构师） | **日期**: 2026-07-05
> **版本**: v1.0.0 GA | **关联计划**: Sprint 1 (Week 1-2), sprint-optimization-plan.md
> **验收原则**: 每项交付必须有明确的【验收标准】+【测试方法】+【通过/不通过】判定

---

## 0. 通用质量规则（适用于所有交付项）

| 规则 | 说明 |
|:-----|:------|
| QR-1 | 不得引入新的 P0/P1 技术债务 |
| QR-2 | 所有产出物需通过小马审查 |
| QR-3 | 交付前运行全量回归测试，0 新增失败 |
| QR-4 | 证据包保持 `valid: True` |

---

## 1. 交付项验收矩阵

### 1.1 建议1：重新产品定位

| 交付项 | 验收标准 | 测试方法 | 通过/不通过 |
|:-------|:---------|:---------|:-----------:|
| 1.1 定位语文案终审 | 定位语文案经小马在 positioning-review.md 中终审通过，签字确认 | 人工审查 positioning-review.md §1 | □ 通过 □ 不通过 |
| 1.2 官网首页更新 (index.html) | Hero 区不再出现"一站式 ASPICE 合规开发平台"；第一屏明确标注"覆盖 SWE.1~SWE.6 辅助"；无"全自动"表述 | 人工审查 index.html render 结果 | □ 通过 □ 不通过 |
| 1.3 官网首页更新 (frontend/out/index.html) | 同上，Next.js 构建产物同步更新 | 审查构建后的 frontend/out/index.html | □ 通过 □ 不通过 |
| 1.4 竞品对标重写 | 竞品对比表不再出现 Vector/dSPACE 直接对比，改为"手工三件套 vs yuleOSH" | 审查 positioning.md 和首页竞品区 | □ 通过 □ 不通过 |
| 1.5 ISO 26262 删除 | `grep -rn "ISO 26262\|功能安全\|ASIL" README.md index.html frontend/out/` 返回 0 条匹配 | CLI 执行上述 grep 命令 | □ 通过 □ 不通过 |
| 1.6 定价页文案更新 | Pro 描述中无"全自动"表述；Enterprise 描述中无 ASPICE 咨询包提及 | 审查 pricing.html + frontend/out/pricing/index.html | □ 通过 □ 不通过 |
| 1.7 docs/pricing.md 更新 | 价格数字正确（Pro ¥599/月，Enterprise ¥98,000/年）；无"全自动"表述 | 审查 docs/pricing.md | □ 通过 □ 不通过 |
| 1.8 docs/positioning.md 更新 | 核心定位变更为新定位，竞品对标更新 | 审查 docs/positioning.md | □ 通过 □ 不通过 |
| 1.9 docs/positioning-unified.md 更新 | 记录本次定位变更；旧定位更新为最新版本 | 审查 docs/positioning-unified.md | □ 通过 □ 不通过 |
| 1.10 docs/user-personas.md 更新 | 无"零人工干预"、"全自动"等过度承诺表述 | 审查 docs/user-personas.md | □ 通过 □ 不通过 |
| 1.11 README.md 更新 | Compliance 段删除"/ ISO 26262"；H1 和首段定位为新定位 | 审查 README.md | □ 通过 □ 不通过 |
| 1.12 全体对外物料一致性 | 所有对外页面的定位语、措辞、价格信息一致 | 交叉对比所有文件 | □ 通过 □ 不通过 |

### 1.2 建议2：证据包修复（evidence check → valid: True）

| 交付项 | 验收标准 | 测试方法 | 通过/不通过 |
|:-------|:---------|:---------|:-----------:|
| 2.1 audit-manifest.json 生成 | `yuleosh ev pack` 生成的 ZIP 包中包含 `audit-manifest.json`，文件格式为 JSON，包含必要字段（文件名、版本、时间戳、SHA256 校验和） | `unzip -l <ev-pack>.zip \| grep audit-manifest.json` | □ 通过 □ 不通过 |
| 2.2 evidence check → valid: True | 在任何一个已初始化的项目中运行 `yuleosh ev check`，返回 JSON 格式输出包含 `"valid": true` | `yuleosh ev check \| python3 -c "import sys,json; d=json.load(sys.stdin); assert d['valid']==True"` | □ 通过 □ 不通过 |
| 2.3 证据包结构标准化 | 输出 `docs/evidence-pack-structure.md`，定义了标准目录结构。文档经小马审查通过 | 人工审查文档 | □ 通过 □ 不通过 |
| 2.4 字段完整性校验 | `yuleosh ev check --strict` 模式下，如果 JSON 缺少必需字段则报错并提示缺失字段名 | 构造一个缺少字段的证据文件运行 `ev check --strict` | □ 通过 □ 不通过 |
| 2.5 数值合理性校验 | 覆盖率 <5% 时证据包输出 WARNING；覆盖率 <1% 时输出 CRITICAL | 构造覆盖率为 0.5% 和 3% 的 mock 数据运行 ev check | □ 通过 □ 不通过 |
| 2.6 SHA-256 签名 | 证据包 ZIP 文件同级存在 `.sig` 签名文件；提供 `yuleosh ev verify <pack.zip>` 命令可验证签名 | `yuleosh ev verify <pack.zip>` 返回 verified: True | □ 通过 □ 不通过 |

### 1.3 建议3：C 覆盖率攻坚（1.4% → ≥15%）

| 交付项 | 验收标准 | 测试方法 | 通过/不通过 |
|:-------|:---------|:---------|:-----------:|
| 3.1 核心模块覆盖率目标清单 | 输出书面清单，涵盖模块名、当前覆盖率、目标值（≥60% 行覆盖/≥50% 分支覆盖） | 审查输出文档 | □ 通过 □ 不通过 |
| 3.2 CI/misra_report 模块 | `ci/misra_report/` 行覆盖率 ≥60% | `pytest --cov=ci/misra_report --cov-report=term` | □ 通过 □ 不通过 |
| 3.3 CI/kpi 模块 | `ci/kpi/` 行覆盖率 ≥60% | `pytest --cov=ci/kpi --cov-report=term` | □ 通过 □ 不通过 |
| 3.4 evidence 模块 | `evidence/` 行覆盖率 ≥60% (从 ~0-15% 提升) | `pytest --cov=evidence --cov-report=term` | □ 通过 □ 不通过 |
| 3.5 flash + hil 模块 | `flash/` + `hil/` 行覆盖率 ≥50% | `pytest --cov=flash --cov=hil --cov-report=term` | □ 通过 □ 不通过 |
| 3.6 ci/pipeline 模块 | `ci/pipeline/` 行覆盖率 ≥60% | `pytest --cov=ci/pipeline --cov-report=term` | □ 通过 □ 不通过 |
| 3.7 全局覆盖率 | `coverage report` 全项目行覆盖率 ≥15% | `pytest --cov --cov-report=term` | □ 通过 □ 不通过 |
| 3.8 覆盖率门禁 CI 配置 | `.coveragerc` 或 pytest config 中设定了 `fail_under_line` 和 `fail_under_condition` 阈值 | 审查 CI 配置文件 | □ 通过 □ 不通过 |
| 3.9 全局回归测试 | 运行 `pytest` 全量测试，0 新增失败 (new fails) | `pytest -x --tb=short` | □ 通过 □ 不通过 |
| 3.10 覆盖攻坚不破坏现有逻辑 | 运行 `yuleosh ev check` 仍返回 valid: True | 验证 3.9 + 3.10 联合运行 | □ 通过 □ 不通过 |

### 1.4 建议4：AI Benchmark 框架搭建

| 交付项 | 验收标准 | 测试方法 | 通过/不通过 |
|:-------|:---------|:---------|:-----------:|
| 4.1 Benchmark 任务集定义 | 输出 `docs/ai-benchmark-tasks.md`（即本报告任务 C 的产出物），包含 30 个典型嵌入式任务，按简单/中等/困难分层 | 人工审查文档 | □ 通过 □ 不通过 |
| 4.2 Benchmark Runner 框架 | `python3 -m bench run` 能执行所有 benchmark 任务并输出 JSON 格式结果 | 执行 `python3 -m bench run --dry-run` 返回任务清单 | □ 通过 □ 不通过 |
| 4.3 第一次数据采集 | 每个 benchmark 任务至少跑 5 次，输出 CSV 数据集，含每次运行的成功/失败、耗时、代码接受率 | 审查输出的 CSV 文件 | □ 通过 □ 不通过 |
| 4.4 Benchmark Runner 稳定性 | 框架执行过程中无 Python 异常中断；3 次重复运行结果一致 | `python3 -m bench run` 连续运行 3 次 | □ 通过 □ 不通过 |

### 1.5 建议5：LLM 策略文档 + RAG 原型

| 交付项 | 验收标准 | 测试方法 | 通过/不通过 |
|:-------|:---------|:---------|:-----------:|
| 5.1 LLM 策略文档 | 输出 `docs/llm-strategy.md`，包含：模型选型(Citation)、成本模型、多模型切换策略 | 人工审查文档 | □ 通过 □ 不通过 |
| 5.2 MISRA RAG 索引 | RAG 查询"规则 10.1"返回完整规则说明 + 正反面代码示例 | 调用 RAG query 接口测试 | □ 通过 □ 不通过 |
| 5.3 嵌入式最佳实践 RAG 索引 | RAG 查询"UART 环形缓冲区实现"返回代码示例 + 最佳实践 | 调用 RAG query 接口测试 | □ 通过 □ 不通过 |
| 5.4 Token 预算预检 | 存在 `estimate_cost(prompt)` 函数，输入 prompt 返回预估 Token 数和成本 | Python 调用该函数测试 | □ 通过 □ 不通过 |
| 5.5 LLM 调用审计日志 | 证据包中包含 `llm-call-log.json`，每条含 prompt_hash, model, token_count, cost, duration | `yuleosh ev pack` 后检查 ZIP 内容 | □ 通过 □ 不通过 |
| 5.6 _call_llm 解耦 | `grep -r "_call_llm" src/ \| wc -l` 结果为 0（不再被外部模块直接调用）；存在统一的 `LLMClient` 类 | CLI 执行上述 grep | □ 通过 □ 不通过 |

---

## 2. 门禁检查清单（CI 集成用）

```yaml
# Sprint 1 门禁配置 — 建议纳入 CI pipeline
gates:
  # 证据包
  evidence_valid:
    command: "yuleosh ev check"
    expected: '"valid": true'
    severity: BLOCKER

  # 覆盖率
  global_coverage:
    command: "pytest --cov --cov-report=term-missing | tail -3 | grep TOTAL"
    expected: ">= 15%"
    severity: BLOCKER

  # ISO 26262 删除验证
  no_iso26262_public:
    command: "grep -rn 'ISO 26262\\|功能安全\\|ASIL' README.md index.html pricing.html frontend/out/"
    expected: empty
    severity: BLOCKER

  # 定位一致性
  positioning_consistency:
    command: "grep '一站式 ASPICE 合规开发平台' README.md index.html pricing.html frontend/out/index.html"
    expected: empty
    severity: BLOCKER

  # 全自动表述
  no_quanzidong:
    command: "grep -rn '全自动' README.md docs/pricing.md docs/positioning.md"
    expected: empty
    severity: WARNING

  # 全量回归
  full_regression:
    command: "pytest -x --tb=short -q"
    expected: "0 failed"
    severity: BLOCKER

  # _call_llm 解耦
  call_llm_decoupled:
    command: "! grep -r '_call_llm' src/ --include='*.py' | grep -v 'LLMClient'"
    expected: true
    severity: WARNING
```

---

## 3. 质量红线（不可妥协）

| # | 红线 | 破坏后果 |
|:-:|:-----|:---------|
| R-1 | 证据包 `valid: False` 上线 | 即刻回滚，不允许进入 Sprint 2 |
| R-2 | 全局覆盖率 < 10% 就提交 Sprint 1 结束 | 延期至达标，不可带病进入 Sprint 2 |
| R-3 | ISO 26262 仍在对外页面出现 | 即刻关闭页面，修复后才允许上线 |
| R-4 | 定位语仍然出现"一站式 ASPICE 合规开发平台" | 同上 |
| R-5 | 新引入 P0 技术债务且未记录 | 审查不通过，要求先修复再交付 |

---

## 4. Sprint 1 结束检查清单

□ 1.1~1.12 定位修改全部完成且一致
□ 2.1~2.6 证据包修复全部完成
□ 3.1~3.10 覆盖率 ≥15%，门禁生效
□ 4.1~4.4 AI Benchmark 框架搭建完成
□ 5.1~5.6 LLM 策略就绪，RAG 可用
□ 全量回归测试 0 新增失败
□ 证据包检测 valid: True
□ 全局覆盖率 ≥15%
□ ISO 26262 从对外页面全部删除
□ 无 P0 技术债务未记录

---

## 5. 异常处理流程

| 场景 | 处理方式 | 决策者 |
|:-----|:---------|:-------|
| 某模块覆盖攻坚遇到不可测试代码 | 改为集成测试覆盖，模块目标降低至 40% | 小克 + 小马合议 |
| evidence check 修复后仍有 false 返回 | 标记为 BLOCKER，加班修复 | 小克 |
| MISRA RAG 索引遇到版权限制 | 改用 few-shot prompt 替代 RAG | 小克 + 小明合议 |
| Benchmark 框架搭建超 Sprint 1 时间 | 框架可用+数据产出延迟至 Sprint 2 | 小明决策 |
| 定位修改截止 W2 未完成 | 推迟至 W2 加班完成，不影响 Sprint 2 启动 | 小明 |

---

*小马 🐴 — Sprint 1 质量验收标准制定完成*

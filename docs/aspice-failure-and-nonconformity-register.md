# yuleOSH 满足 ASPICE 自动化的失败项与不符合项清单

- 文档编号：AUD-ASPICE-001
- 版本：v1.1（B1–B5 修复已落地，待额度恢复后补 3/3 连跑）
- 日期：2026-11-16
- 对照基线：《ASPICE 智能研发与合规审计平台 — 系统架构与详细设计说明书》v1.0（DOC-ASPICE-AI-SDD-001）
- 判定口径
  - **F（Failure）**：运行时实际发生的失败，有日志/产物证据。
  - **NC（Non-Conformity）**：实现与 SDD 条款或 ASPICE 过程要求不符。
  - **D（Defect）**：产品实现缺陷，导致门禁或统计结果失真。
- 等级
  - **P0**：阻断「自动跑绿 ASPICE」，不修无法产出可审核证据包。
  - **P1**：证据包不完整，评估员会开不符合项。
  - **P2**：工程质量/效率问题，不影响合规判定。

---

## 0. 证据基线（三次真实运行）

| 编号 | 工程 / 会话 | 输入 | 结果 | 关键数据 |
|---|---|---|---|---|
| RUN-A | `62e87b875c79` / `90dc720be61c` | 一句话需求，全流程 102 步，深链模型 `deepseek-chat` | **failed（RED）**，第 24 步中断 | 23/102 步完成，118.0s，6 次 LLM，52,124 tokens |
| RUN-B | `f415e3739900` / `55891d3dae05` | 同一句话需求，复跑 | **failed**，第 10 步 | 18.1s，`HTTP 402 Payment Required` 重试后硬失败 |
| RUN-C | 8 步子集（同工程体系） | 同一句话需求 | completed，但汇总标记 **UNVERIFIED** | 5 次 LLM，35,979+16,978 tokens，代码 1 文件 `verified` |

产物路径：`/workspace/demos/desktop-workspace/62e87b875c79/`
关键证据：`.osh/sessions/90dc720be61c/{gate-summary,prd-review,arch-review,codegen-deploy,c-coverage-gate}.json`、`.yuleosh/reports/codegen-deploy.json`、`artifacts/generated-code/aspice-led-1hz/codegen-report.md`

---

## 1. 失败项（F）

### F-01 · P0 · 无代码部署时覆盖率门禁硬失败，拖垮整条流水线

- **现象**：第 24 步 `qemu-verify` 中，QEMU 子步明确「未找到二进制 → 跳过」，但同一步的 `c-coverage-gate` 子步在工程根目录执行 CMake，报
  `CMake Error: The source directory ... does not appear to contain CMakeLists.txt`，随后 `hard-failed (no fallback)`，整条流水线中断。
- **证据**：`.osh/sessions/90dc720be61c/c-coverage-gate.json` → `phases.build.success=false`；运行日志 `Step [qemu-verify] hard-failed`。
- **影响**：SWE.5 门禁 G7 直接 failed；后续 78 步全部 pending，SUP/MAN/ACQ/SPL 等过程零证据。
- **期望行为**：无部署代码时应 skip 并标注「证据不足（no code deployed）」，而不是 hard fail。
- **修复落点**：`src/yuleosh/pipeline/step_handlers/c_coverage_gate.py`（build 前置检查：无 `src/`、无 `CMakeLists.txt`、无 `codegen-deploy.json=deployed` 时返回 skipped）。
- **验收**：构造「codegen 失败」场景重跑，`qemu-verify` 状态为 `skipped`，流水线继续执行后续步骤，最终汇总为 `UNVERIFIED` 而非 `failed`。

### F-02 · P0 · 生成代码 POSIX 编译失败，4 轮自愈未收敛，导致部署被拦

- **现象**：生成 `SchM.c` 直接调用 `clock_gettime(CLOCK_MONOTONIC, ...)`；自检命令为 `gcc -fsyntax-only -std=c11`（无 `-D_POSIX_C_SOURCE`），glibc 严格 C11 下不暴露 POSIX 声明 → `error: 'CLOCK_MONOTONIC' undeclared`。重试 4 轮（上限 3）仍失败。
- **证据**：`artifacts/generated-code/aspice-led-1hz/codegen-report.md` → `Status: ❌ failed`、`Rounds: 4 (max retries: 3)`、`Return code: 1`。
- **连锁后果**：`codegen-deploy.json` = `skipped_codegen_failed`（护栏正确）→ 下游 `internal-code-review`/`c-unit-test`/`code-review-unified`/`misra-review`/`integration-test` 全部 skipped → 追溯矩阵实现覆盖率 0%。
- **违背**：SDD §1.2「接口生成、语法编译必须由确定性工具链完成」；§6.1「沙箱内消化重试，绝不污染基线」——前半句已做到，后半句的「消化」未做到。
- **修复落点**：`src/yuleosh/codegen/`（自检命令按平台注入 `-D_POSIX_C_SOURCE=200809L`；或 prompt 明确禁止无 HAL 的 POSIX 直接调用）+ 修复提示中加入编译错误原文。
- **验收**：同一 spec 连续 3 次生成，3/3 编译通过；生成代码中不出现绕过 HAL 的时间/IO 系统调用。

### F-03 · P2 · LLM 4xx 错误无短路，重试链空转

- **现象**：`HTTP 402 Payment Required` 触发同一请求 3 次重试 + SSE 降级 + 本地 Ollama 降级，18s 后在第 10 步硬失败。
- **证据**：RUN-B 日志 `chat_completion stream attempt 1/3 ... 3/3`、`本地 Ollama 降级也失败`。
- **修复落点**：`src/yuleosh/llm/`（401/402/403/404 直接抛出，不重试不降级；仅 429/5xx 重试）。
- **验收**：注入 402 后 <1s 失败，错误信息包含「余额/额度不足」。

### F-04 · P0 · 5 个系统层步骤「完成但无产物」，G0 永不闭环

- **现象**：`sys-requirements / sys-architecture / sys-verification / sys-integration / sys-validation` 均报 completed，但审计器将其降级为 `not-run`。
- **证据**：运行日志 `claimed 'completed' but produced no artifact — recorded as not-run`；`gate-summary.json` → `G0 status=not-run`。
- **根因**：sys 层 handler 写入 `<project>/docs/system-*.md`（文件确实存在），而门禁产物查找只扫 `<project>/.osh/sessions/<id>/`，且 `_ARTIFACT_CANDIDATES` 表中无 `sys-*` 条目（`src/yuleosh/pipeline/gates.py:473` 起）。
- **影响**：SYS.1–SYS.5 的全部证据无法入账，V 模型左半部分在审计上等于没做。
- **修复落点**：`src/yuleosh/pipeline/gates.py` 增加 sys-* 的项目级路径规则，或 sys handler 同时落一份 session 内副本并返回路径。
- **验收**：G0 状态为 `passed` 且 `artifact_hashes` 包含 5 个 system 文档哈希。

---

## 2. 不符合项（NC）

### NC-01 · P0 · 无多智能体协同闭环（评审意见不回灌，失败即中断）

- **现象**：评审产生的 findings 无任何回灌路径；一旦步骤失败直接中断整条流水线。
- **证据**：`src/yuleosh/pipeline/orchestrator.py:733`（`Step failed — pipeline interrupted`）、`:1471`（`hard-failed (no fallback)`）；全仓库无 rework/bounce/retry_from 逻辑。
- **违背**：SDD §4.2（MISRA 失败 → 精确报错回灌编码 Agent，上限 3 次）；§2.1「多智能体流水线」。
- **影响**：架构评审即使给了 major findings，也只能让流水线停住，不会让架构 agent 重做。这是「流水线」和「协同」的分界线。
- **修复落点**：`orchestrator.py` 新增返工路由表（review step → producer step + findings 注入），上限 2 轮后升级为需要人工。
- **验收**：注入「架构缺少 HAL 分层」缺陷，架构 agent 被实际重跑一次并在产物中修正；`session.json` 记录 `rework_rounds=1`。

### NC-02 · P0 · OpenSpec 不是强类型 SSOT，无拓扑闭环校验

- **现象**：需求为 Markdown + 正则解析，全仓库无 Pydantic；无悬空引用拦截、无孤儿需求计算。
- **证据**：`grep -ri pydantic src/yuleosh` → 0 命中；`src/yuleosh/spec/validate.py` 为文本级校验。
- **违背**：SDD §1.2（SSOT）、§3.2（Pydantic v2 强类型）、§3.3（门禁 0：悬空引用/孤儿需求拦截）。
- **影响**：RUN-A 的 `requirements` 契约只有 4 个 ID 且 `SWR-001` 重复 3 次、系统层实际 6 条需求，无任何校验报警。
- **修复落点**：`src/yuleosh/spec/` 新增 Pydantic 模型层 + `validate_topology()`；生成 spec 后强制实例化，失败即 Gate 0 拦红。
- **验收**：故意构造「DesignUnit 引用不存在 REQ」「存在未分配 REQ」两种输入，均在 Gate 0 被阻断并给出精确 ID 列表。

### NC-03 · P0 · 无物理隔离验证通道

- **现象**：编码、测试、评审由同一模型在同一上下文串行执行；无 Docker/容器隔离；外部 agent 缺失时静默跳过。
- **证据**：`external_agents.py:549-552`（`claude CLI not installed` → `write_mock_skip`）；`codex-verify.json` → `{"status":"skipped","reason":"codex CLI not installed"}`；`tests/` 目录为空。
- **违背**：SDD §1.2（物理隔离验证、验证独立性）、§4.2（双通道：A 编码只见 Spec+Header，B 测试物理屏蔽 C 源码）。
- **影响**：RUN-A 中 `c-unit-test` / `integration-test` / `internal-code-review` 全部 skipped，却未阻断流程；不具备独立性声明资格。
- **修复落点**：`test_*` handlers 改为「测试上下文仅注入 spec + interface header」；执行放进子进程/容器；CLI 缺失时使用第二模型或同模型新上下文，并标注 `independence=degraded`。
- **验收**：测试产物中不含源码函数体信息；`session.json` 记录独立级别；P0 步骤不允许 `skipped`。

### NC-04 · P0 · 交接契约校验空转

- **现象**：`contracts.json` 判 `validation.passed=true`，但 `interfaces.found=0`、`guardrails.want=0`、`params.want=0`。
- **证据**：`.osh/sessions/90dc720be61c/contracts.json`。
- **违背**：SDD §3.2（InterfaceDef 强类型）、§4.1（确定性接口生成）。
- **影响**：契约门禁形同虚设，「架构与实现一致」这一 ASPICE 核心证据无法成立。
- **修复落点**：`src/yuleosh/spec_contracts.py`（契约非空判定；从 spec 抽取 IF/参数/安全等级，为空则 fail 而非 pass）。
- **验收**：LED demo 的契约应至少含 1 个 HAL 接口、1 个周期参数；若抽取为 0 则 Gate 拦红。

### NC-05 · P0 · 评审在空输入上自证通过

- **现象**：`arch-review` 判 `status=passed`、`finding_count=0`，同时 `static_summary` 为 `No source directory found`。
- **证据**：`.osh/sessions/90dc720be61c/arch-review.json`。
- **影响**：评审员看不到代码/设计实体，仍给通过；这与 SDD「不信任 LLM 自述」直接冲突。
- **修复落点**：`src/yuleosh/pipeline/step_handlers/review_arch.py`（静态检查无输入时不得判 passed，应为 `insufficient-evidence` 并阻断 G2）。
- **验收**：删除源码后重跑，G2 不得为 passed。

### NC-06 · P1 · 覆盖率门禁不区分 ASIL，无 MC/DC

- **现象**：全局阈值 `c_fail_under=70`，与 ASIL 无关。
- **证据**：`src/yuleosh/pipeline/step_handlers/c_coverage_gate.py:604`、`:679`。
- **违背**：SDD §4.2(3)：QM 80/70、ASIL-A 100/90、ASIL-B/C/D 100/100 + MC/DC。
- **修复落点**：同上文件，阈值由 `ProjectMeta.asil_level` 决定；新增 MC/DC 报告解析。
- **验收**：切换 ASIL 等级，阈值与报告同步变化；ASIL-B 下分支未覆盖 100% 必须拦红。

### NC-07 · P1 · 追溯依赖注释标签，无 AST 提取与图查询

- **现象**：追溯矩阵基于 spec 文本与 `@trace_req` 标签；无 AST 解析、无图数据库、无变更影响分析。
- **证据**：`.osh/evidence/traceability-matrix.json`（10 条 SHALL，实现覆盖率 0%）；全仓库 `neo4j` 0 命中（现为 SQLite KG）。
- **违背**：SDD §4.3（不信任自述、AST 提取、四层节点拓扑）、§6.2（SUP.10 变更影响分析图查询）。
- **修复落点**：`src/yuleosh/knowledge_graph/` 新增 C AST 提取器（函数 ↔ 注释标签绑定校验）+ 下游影响查询接口。
- **验收**：伪造 `@trace_req`（函数实际未实现该需求）能被 AST 校验识别；修改一条需求能列出受影响设计单元与测试用例。

### NC-08 · P1 · 无 ReqIF 导出

- **现象**：`ReqIF` 全仓库 0 命中；仅有 XLSX/HTML 导出。
- **证据**：`grep -ri reqif src/yuleosh` → 0；XLSX 导出存在于 `src/yuleosh/evidence/excel_writer.py`。
- **违背**：SDD §2.2、§5.2（`Requirements_Baseline.reqif`，对接 DOORS/Polarion）。
- **修复落点**：`src/yuleosh/evidence/exporters.py` 新增 ReqIF 1.2 序列化。
- **验收**：导出的 reqif 可被至少一个标准工具导入且需求条目/层级无损。

### NC-09 · P1 · 无电子签批与基线固化

- **现象**：无 `AUDIT_SIGNOFF_LOG`、无 `git tag SIGNED_*`；仅有门禁级 `artifact_hashes`。
- **证据**：`grep -ri "SIGNED_|AUDIT_SIGNOFF" src/yuleosh` → 0；`gate-summary.json` 已有 SHA-256 哈希（可复用）。
- **违背**：SDD §4.4（角色权限分离、联合哈希、git tag 固化）。
- **修复落点**：`src/yuleosh/evidence/` 新增 signoff 模块；`api` 增加签批端点；复用现有哈希计算。
- **验收**：Gate 2 未签批时禁止判定为「可发布」；签批后生成 tag 且日志可校验哈希一致。

### NC-10 · P1 · MISRA 无自愈循环，缺失即跳过

- **现象**：`misra-review` 因 `misra-report.json` 不存在而 skipped；无 cppcheck 报错回灌。
- **证据**：`misra-review.json` → `status: skipped`，`message: MISRA report not found`。
- **违背**：SDD §4.2(2)（cppcheck `--addon=misra --error-exitcode=1`，报错行号回灌，上限 3 次）。
- **修复落点**：`src/yuleosh/ci/` + `orchestrator.py` 返工路由（依赖 NC-01）。
- **验收**：注入 MISRA 违规后编码 agent 被重跑且违规数下降；3 轮未收敛转人工并标红。

### NC-11 · P1 · 平台模式未由元数据驱动，出现过度设计漂移

- **现象**：spec 要求 HAL 与主机可验证，产出为 AUTOSAR 全栈（`LedSwc`/`Rte_Led`/`SchM`）并直接调用 POSIX 时间 API。
- **证据**：`artifacts/generated-code/aspice-led-1hz/src/` 目录结构；`SchM.c` 中 `clock_gettime`。
- **违背**：SDD §3.2（`ProjectMeta.platform` 决定 HAL 生成策略）、§4.1（AUTOSAR / 裸机双模式）。
- **修复落点**：`ProjectMeta` 增加 `platform`/`asil_level` 并注入 codegen prompt 与接口生成器。
- **验收**：`platform=BARE_METAL_MCU` 时不得出现 RTE/SchM 文件；`AUTOSAR_CP` 时必须生成 arxml。

### NC-12 · P1 · 门禁 skipped/not-run 不阻断后续步骤

- **现象**：`gates.py` 已将 skipped/stale/not-run 归为 `unverified`（这一点做得好），但仍继续执行后续步骤，且个别 review 自身返回 passed。
- **证据**：`src/yuleosh/pipeline/gates.py:274-286`（状态分类）、`:731`（降级逻辑）；RUN-A 中 18 个 skipped 步骤后仍继续。
- **影响**：最终报告可能是 `UNVERIFIED` 而非 `failed`，容易被误读为「基本通过」。
- **修复落点**：区分「可降级步骤」与「P0 阻断步骤」；P0 集合内 skipped 直接 fail。
- **验收**：P0 步骤（需求/架构/代码/单测/追溯/签批）任一 skipped 时，最终状态为 failed。

### NC-13 · P2 · 缺少 CL3 量化过程数据

- **现象**：无连续运行成功率、门禁稳定性、缺陷密度等度量。
- **违背**：ASPICE CL3 过程量化管理要求。
- **修复落点**：`src/yuleosh/api/` 增加 run 历史聚合；脚本化连续 N 次运行。
- **验收**：能输出最近 10 次运行的成功率、各门禁失败分布。

---

## 3. 缺陷（D，导致结果失真或统计错误）

### D-01 · P1 · 覆盖率统计依赖单一阈值，缺失报告时回退 0 并可能 PASS
- 证据：`src/yuleosh/pipeline/step_handlers/measurement.py:88` 注释自述「缺失数据时会回退到 0 并给出 PASS」。
- 修复：缺失数据必须判 `insufficient-evidence`，不得 PASS。

### D-02 · P2 · 系统层需求从 spec 反推，漂移检测被结构性关闭
- 证据：`.osh/evidence/sys-spec-alignment.json` → `{"status":"spec-derived","note":"SYS 需求由 spec 反推（V 模型方向倒置），不做 SYS→spec 引用校验"}`。
- 修复：SYS 从干系人需求独立推导，再做 SYS↔spec 双向比对，冲突 BLOCK。

### D-03 · P2 · `sys_layer.py` 关键词回退推断
- 证据：`src/yuleosh/pipeline/step_handlers/sys_layer.py:395`（无法推断时回退到「测试」）。
- 修复：回退必须显式标注 `inferred=true` 并在评审中重点核查。

---

## 4. 需要保留的现有优势（改造中不得回退）

1. `gate-summary.json` 的 SHA-256 `artifact_hashes` 入账。
2. `codegen-deploy` 的「编译失败不部署」护栏（`execution.py:628-636`）。
3. 门禁审计器对「声称完成但无产物」的降级（`gates.py:731`）。
4. `context_guard` 的 50%/80% 上下文分级策略。
5. 本地模型（Ollama / OpenAI 兼容端点）支持，符合内网要求。
6. 102 步 / 25 门禁的过程域覆盖度。

---

## 5. 修复批次建议

| 批次 | 内容 | 依赖 | 完成后可验证的信号 |
|---|---|---|---|
| **B1（阻断项）** | F-04、F-01、NC-04、NC-05 | 无 | 门禁不再空放行；G0 可闭环；契约非空 |
| **B2（协同内核）** | NC-01、NC-02、NC-10 | B1 | 评审可打回生产者；Spec 拓扑校验拦红；MISRA 自愈 |
| **B3（独立验证与合规门禁）** | NC-03、NC-06、NC-11 | B2 | 测试上下文隔离；ASIL 阈值生效；双平台模式 |
| **B4（证据包）** | NC-07、NC-08、NC-09、D-01/02 | B3 | 四层追溯 + ReqIF + 签批；缺失证据不 PASS |
| **B5（量化与健壮性）** | F-02、F-03、NC-12、NC-13、D-03 | B4 | 3/3 连续跑绿；4xx 短路；CL3 度量 |

### 整体验收（DoD）

1. 同一句话需求连续 3 次全流程运行，**3/3 GREEN**。
2. G0–G7 全部 `passed`，且 `not-run`/`skipped` 数为 0（显式 N/A 需登记理由）。
3. 产物齐全：spec、prd、architecture、design、code、tests、coverage、traceability 全部存在并哈希入账。
4. 追溯四层（Requirement → DesignUnit → CodeFunction → TestCase）双向 100%，0 orphan。
5. 证据包（XLSX + ReqIF + signoff log）可被第三方独立审核。
6. 反例验证：注入「漏 SHALL 映射」「接口不符」「覆盖率不足」三类缺陷，必须全部被拦红。

---

## 6. 待决策事项

1. **LLM 额度**：DeepSeek 账户已 402，验证需要可用额度（或切换其他 provider）。
2. **外部 CLI**：本机是否可用 `claude` / `codex` CLI？不可用则采用「第二模型」或「同模型独立上下文」方案，并标注独立性降级。
3. **SSOT 迁移策略**：引入 Pydantic 是替换现有 Markdown OpenSpec，还是「Markdown 仍为人类可读视图、JSON 为唯一事实来源」的双向同步？
4. **图谱方案**：沿用 SQLite KG 并补齐等价图查询，还是引入 Neo4j？
5. **范围**：按 B1→B5 分批推进，还是一次性以「全 102 步跑绿」为目标？

---

## 7. v1.1 修复状态（2026-11-16）

修复原则：**代码由 yuleOSH 自身产出，本清单只记录缺陷与验收证据**；不手写工程交付物。
所有条目均以确定性单测/真实 CLI 运行取证，未使用 mock 冒充绿。

| 条目 | 状态 | 修复落点 | 验收证据 |
|---|---|---|---|
| F-01 覆盖门禁硬失败 | ✅ 已修 | `step_handlers/c_coverage_gate.py`（排除 `artifacts/`；无 `CMakeLists.txt` → `skipped` + `gate_passed=False`） | `tests/test_aspice_gate_strictness.py`、RUN 实测跳过不再中断 |
| F-02 POSIX 编译 4 轮未收敛 | ✅ 已修 | `codegen/compilers.py`（按平台注入 `-D_POSIX_C_SOURCE=200809L`，裸机不加） | `tests/test_b5_quantification.py::TestF02PosixMacro` |
| F-03 LLM 4xx 无短路 | ✅ 已修（含两条路径） | `llm/providers/deepseek.py`、`llm/streaming.py`、`llm/client.py`（legacy 重试循环 + 流式降级分支） | 单测 `TestF03FatalHttpErrors` / `TestF03LegacyClientShortCircuit`；真实 402 运行由 7.3s/「after 3 retries」降为 2.5s/「non-retryable HTTP 402」 |
| F-04 sys-* 无产物致 G0 不闭环 | ✅ 已修 | `pipeline/gates.py`（`_PROJECT_ARTIFACT_CANDIDATES` + project 产物哈希入账） | `tests/test_gate_artifact_coverage.py` |
| NC-01 无评审返工闭环 | ✅ 已修 | `pipeline/rework.py` + `orchestrator._maybe_rework` + `prompts._rework_suffix` | `tests/test_rework_routing.py` |
| NC-02 SSOT 无拓扑校验 | ✅ 已修 | `spec/ssot.py`（数据类 SSOT + `validate_topology`） | `tests/test_spec_ssot.py` |
| NC-03 无物理隔离验证 | ✅ 已修（分级） | `pipeline/verification_independence.py`（`isolated`/`degraded`/`none`） | `tests/test_verification_independence.py` |
| NC-04 契约校验空转 | ✅ 已修 | `spec_contracts.validate_contracts`（声明接口但 0 抽取、重复需求 ID） | `tests/test_spec_contracts.py`、`tests/test_aspice_negative_injection.py` |
| NC-05 评审空输入自证通过 | ✅ 已修 | `review_arch.py`、`sys_layer.py` 结构门禁 | `tests/test_aspice_gate_strictness.py` |
| NC-06 覆盖率不分 ASIL | ✅ 已修 | `c_coverage_gate._ASIL_POLICY`（QM 80/70，ASIL-A 100/90，B+ 100/100；无证据不 PASS） | `tests/test_aspice_gate_strictness.py::TestAsilCoveragePolicy` |
| NC-07 追溯仅靠注释 | ✅ 已修 | `evidence/ast_trace.py`（AST 函数级追溯 + 需求文本实质匹配） | `tests/test_b4_evidence_pack.py::TestAstTrace` |
| NC-08 无 ReqIF | ✅ 已修 | `evidence/reqif.py`（ReqIF 1.2 导出并回读自检） | `TestReqIF`；`human_report` 产出 `requirements.reqif` |
| NC-09 无电子签批 | ✅ 已修 | `evidence/signoff.py`（G1/G2 人工签批，绑定产物 SHA-256 + git tag；未签 → `awaiting-signoff`） | `TestSignoff` / `TestGateAwaitingSignoff` |
| NC-10 MISRA 无自愈 | ✅ 已修 | `rework.plan_rework`（misra-review → development，≤2 轮） | `tests/test_rework_routing.py` |
| NC-11 平台模式漂移 | ✅ 已修 | `project_meta.py` + `codegen/prompts.py` + `engine._check_platform_layout` | `tests/test_project_meta.py` |
| NC-12 skipped 不阻断 | ✅ 已修 | `pipeline/p0.py` + orchestrator P0 检查；**并修** LLM 降级产物 status=skipped 时步骤不再停留 completed | `tests/test_b5_quantification.py::TestNC12P0Blocking` |
| NC-13 无 CL3 量化 | ✅ 已修 | `ci/kpi/history.py::summarize`（近 N 次成功率 / 门禁失败分布） | `TestNC13RunHistory` |
| D-01 缺报告回退 0 可能 PASS | ✅ 已修 | `ci/kpi/report.py`（`INSUFFICIENT-EVIDENCE`） | `tests/test_b4_evidence_pack.py::TestD01MeasurementEvidence` |
| D-02 SYS 从 spec 反推、漂移关闭 | ✅ 已修 | `sys_layer._write_sys_spec_alignment`（双向比对落盘）+ spec 解析器 ID 修复 | `TestD02SysSpecAlignment` |
| D-03 关键词推断无标注 | ✅ 已修 | `sys_layer._infer_verification_method` 返回 `(method, inferred)` + 文档「⚠️ 推断 / 待确认」 | `TestD03InferenceLabelling` |

### DoD 对照

| DoD | 状态 | 说明 |
|---|---|---|
| 1. 同一需求连续 3 次 3/3 GREEN | ⛔ **外部阻塞** | DeepSeek 账户返回 `HTTP 402 Insufficient Balance`（实测 2026-11-16）。需充值或切换 provider 后执行；流水线已在 402 下正确判 RED 且 4xx 立即短路，不产生假绿。 |
| 2. G0–G7 全 passed，0 skipped | ⏳ 依赖 DoD-1 | 门禁严格化已完成，待真实跑绿取证。 |
| 3. 产物齐全并哈希入账 | ✅ | `artifact_hashes` 覆盖 session + project 产物（F-04）。 |
| 4. 四层追溯 100% / 0 orphan | ✅（确定性可验） | `ast_trace` + `spec/ssot.validate_topology` 提供 0 orphan 判定。 |
| 5. 证据包可独立审核 | ✅（未签批时为 `awaiting-signoff`） | ReqIF + signoff + XLSX 导出器。 |
| 6. 三类反例必须拦红 | ✅ | `tests/test_aspice_negative_injection.py`（8 passed；每类含正向对照）。 |

### 本轮验证记录

- 专项回归：`378 passed`（门禁/契约/追溯/KPI/orchestrator/评审 20 个文件）。
- 反例注入：`8 passed`（漏 SHALL 映射 / 接口不符 / 覆盖率不足，各含对照组）。
- 真实 402 运行：`architecture` 2.5s 判 failed，`prd`/`super-analysis` 如实标 `skipped`，整条 run 判 RED，exit=1。
- 未执行：前端 `tsc`/`jest`/`build`（仓库无 `node_modules`，需 `npm ci`）。

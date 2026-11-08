# 语义抽检清单（注解 ↔ 需求正文）

> 自动生成：按 `sha256(req_id)` 排序取前 20 条，样本可复现。
> 抽检目的：覆盖率只能证明链接存在，不能证明链接正确。
> 逐条核对：代码文件中的 `@req` 是否指向该需求，实现内容是否与需求正文一致。

| # | 需求 ID | 需求正文（截断） | 关联实现文件 | 注解核对 | 语义匹配 | 备注 |
|--:|:--------|:----------------|:-------------|:--------|:--------|:-----|
| 1 | SHALL-151 | Each SIL test SHALL have a configurable timeout with a default of 30 seconds | `src/yuleosh/pipeline/orchestrator.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 2 | SHALL-135 | The CLI command `yuleosh kg report rtm` SHALL trigger RTM generation | `src/yuleosh/knowledge_graph/reporter.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 3 | SHALL-124 | The system SHALL support graph snapshots for baseline comparison | `src/yuleosh/kb/codegen_failures.py` —<br>`src/yuleosh/kb/store.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 4 | SHALL-202 | The system SHALL enforce timeout-based termination (default 30s) for all SIL tes | `src/ci/fi_cmd.py` —<br>`src/yuleosh/__main__.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 5 | SHALL-132 | RTM generation SHALL support Markdown, HTML, and CSV output formats | `src/yuleosh/knowledge_graph/reporter.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 6 | SHALL-214 | The system SHALL encrypt all database connections using TLS (minimum TLS 1.2) | `src/yuleosh/engine/tenant_security.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 7 | SHALL-13 | The system SHALL provide a requirements tree hierarchy (SYS → SW → Feature → Sce | `src/yuleosh/alm/traceability.py` —<br>`src/yuleosh/api/requirements.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 8 | SHALL-120 | After successful payment the system SHALL update the user's subscription status | `src/yuleosh/billing/metering.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 9 | SHALL-110 | Unauthenticated users SHALL be limited to 3 preview assessments per 24 hours per | `src/yuleosh/api/ratelimit.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 10 | SHALL-26 | The system SHALL support MISRA-C/C++ static analysis gates | `src/yuleosh/api/ci.py` —<br>`src/yuleosh/ci/config.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 11 | SHALL-123 | The system SHALL support incremental graph build for CI integration | `src/yuleosh/kb/codegen_failures.py` —<br>`src/yuleosh/kb/store.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 12 | SHALL-119 | The system SHALL use Stripe Checkout for paid upgrade processing | `src/yuleosh/billing/metering.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 13 | SHALL-20 | The system SHALL support auto-reviewer routing based on task type | `src/yuleosh/pipeline/step_handlers/review.py` —<br>`src/yuleosh/pipeline/step_handlers/review_code.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 14 | SHALL-98 | Mock steps SHALL include: Spec Parsing, Requirements Analysis, SDD, Code Generat | `src/yuleosh/api/demo.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 15 | SHALL-54 | The system SHALL support HAL mocking for at least: UART, GPIO, Timer, I2C, SPI | `src/yuleosh/cross/sil_assert.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 16 | SWARCH-006 | **SWARCH-006**: 软件架构 SHALL 提供 SaaS 平台服务，实现租户上下文、配额校验、订阅状态与审计日志写入。 | `src/yuleosh/__init__.py` —<br>`src/yuleosh/adapter/__init__.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 17 | SHALL-147 | The pipeline SHALL include a `merge-gate` step in the PIPELINE_STEPS registry | `src/yuleosh/knowledge_graph/merge_gate.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 18 | SHALL-216 | The system SHALL encrypt sensitive configuration (API keys, tokens) at rest | `src/yuleosh/engine/tenant_security.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 19 | SHALL-112 | Rate limit exceeded SHALL return HTTP 429 | `src/yuleosh/api/ratelimit.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |
| 20 | SHALL-35 | The system SHALL support configurable layer dependency chain | `src/yuleosh/ci/config.py` — | [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |

## 处置约定

- **注解核对不一致**：代码缺少或错标 `@req` → 记为评审发现，修正注解。
- **语义不匹配**：实现与需求正文不符 → 记为评审发现，回到需求或代码修复。
- 抽检结果写入独立评审记录的 `findings`，不要直接修改本清单。

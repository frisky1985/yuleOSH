# `yuleosh.audit` 模块设计文档

> 子系统定位：不可篡改审计日志（Event Sourcing + SHA-256 哈希链）
> 代码根：`src/yuleosh/audit/`
> 文档性质：详细设计（SWE.3），基于源码实地盘点。标注 `@req CR-003 @req NFR-002`（`model.py:1`）。

---

## 0. 命名澄清

仓库内存在**两套“audit”**，彼此独立、无 import 关系：

1. **本模块 `yuleosh.audit`**：通用操作审计日志，SHA-256 哈希链，JSONL append-only。
2. `yuleosh.engine.tenant_security.py` 的 `containers.jsonl` 容器审计：独立 JSONL，**无哈希链**，无 import 关系（`tenant_security.py:52-181`）。

本文档仅描述 `yuleosh.audit`。

---

## 1. 职责边界

事件溯源（Event Sourcing）式不可变审计日志（`__init__.py:4` 标注 `SAAS-4`）：每条状态变更记录为一个不可变审计事件；**SHA-256 哈希链**保证防篡改（任何编辑/删除/重排都被 `AuditLog.verify()` 检测，`model.py:14-19`）。按日文件锚定（每日首条 `prev_hash=""`，`:19,29-30`）。AI 生成溯源：通过 `prompt_hash` + `sign_ai_generation()` 把“草稿”升级为可采信证据（`:21-26,91-93`）。

---

## 2. 目录结构与规模

| 文件 | 行数 | 职责 |
|---|---|---|
| `__init__.py` | 27 | 包导出（`AuditLog`、`AuditEvent`、`compute_event_hash`、`compute_prompt_hash` 等 `:20-27`） |
| `model.py` | 602 | 核心实现（`AuditEvent` / `AuditLog` / 哈希链 / verify） |

---

## 3. 数据模型（使用 `__slots__` 普通类，非 dataclass / 非 pydantic）

**`AuditEvent`**（`model.py:124`，`__slots__` `:127-151`）：
`actor`（执行者，`"user:42"` / `"system"`）、`action`、`target`、`timestamp`、`tenant`、`detail: dict`、`model`（可选 AI 溯源）、`prompt_hash`（可选）、`reviewed_by`（可选）、`reviewed_at`（可选）、`hash`（本事件 SHA-256，`""`=legacy）、`prev_hash`（上一条 SHA-256，`""`=链锚）。

**`AuditLog`**（`model.py:200`）：
- `record(actor, action, target="", ...)` → 追加记录（`:230`）
- `record_ai_generation(...)`（`:297`）、`sign_ai_generation(reviewer, ...)`（`:346`）
- `_last_hash(tenant)` — 链尾哈希锚点（`:385`）
- `verify(tenant="", from_date="", to_date="")` → 校验（`:433`）
- `query(...)` / `get_summary(...)`（`:521,588`）
- 事件类型常量：`EVENT_AI_GENERATION`、`EVENT_AI_SIGN`、`EVENT_EVIDENCE_UPLOAD/DELETE/EXPORT`（`:87-89`）

---

## 4. 哈希链机制

- `compute_event_hash(event_dict, prev_hash="")`（`model.py:103`）：取除 `hash`/`prev_hash` 外所有字段（`_HASH_EXCLUDED`，`:45`）的规范 JSON（`sort_keys` 稳定序，`:98-100`），拼接 `"|" + prev_hash`，再 SHA-256（`:110-112`）。
- 链接：`record()` 调 `_last_hash(tenant)` 取链尾哈希作 `prev_hash`，新事件 `hash = compute_event_hash(event_dict, prev_hash)`（`:270-273`）。
- 每日首条 `prev_hash=""`（链锚，`:19,149`）；跨日经 `_last_hash` 扫描最新日期文件续链（`:385-431`）。

---

## 5. 存储（**文件系统 JSONL，非 SQLite / 非 DB**）

- 全局：`data/audit/YYYY-MM-DD.jsonl`（`model.py:29,207`）
- 租户隔离：`data/{tenant}/audit/YYYY-MM-DD.jsonl`（`:30,208,227`）
- 写入：`open(file_path, "a")` 追加，每行一个 JSON（`:281-282`）；每次 `record` 同时写租户日志 + 全局日志（`:284-289`）；目录自动创建（`:220,278,287`）。

> **偏差（已如实标注）**：`model.py:203` 注释称“原子写（临时文件再 rename）”，但 `model.py:281` 实际为直接 `open(...,"a")` 追加，未用临时文件+rename。多进程并发追加存在行交错风险，文档据实记录。

---

## 6. verify 协议

- `AuditLog.verify(tenant="", from_date="", to_date="")`（`model.py:433`）：默认范围过去 30 天到今天（`:450-453`）。逐日逐行重放，对每条算 `expected = compute_event_hash(data, prev_hash)` 与存储 `hash` 比对；不匹配返回 `valid=False` + `broken_at` + `reason`（`:488-495`）；检测 malformed JSON（`:475-479`）。legacy 事件（无 `hash`）计入 `legacy` 用推算锚点（`:481-486`）。返回 `{"valid","checked","legacy","broken_at","reason","files"}`（`:442-443,512-519`）。
- **CLI**：`yuleosh audit verify`（`cli/main.py:480-488` → `cli/commands/misc.py:1391` `cmd_audit_verify`，内部调 `log.verify()` `:1402`）。
- 证据打包时自动调用 verify：`_collect_audit_log_verification()` 写 `audit-log-verification.json`（`misc.py:911-959`），由 `cmd_audit_evidence` 触发（`:1208-1213`）。

---

## 7. 与“签名 / 证据包”的关系（澄清）

- `sign_ai_generation()`（`model.py:346`）**不是加密签名**——它追加一条 `ai.generation.sign` 事件（含 `reviewed_by` / `reviewed_at`）。本模块**不实现公私钥签名算法**。
- 真正的加密签名在 `yuleosh.evidence.signer.py:225` 的 `public_key.verify(...)`，与本模块无 import 耦合。
- 概念关联：AI 草稿经 `sign_ai_generation` 追加事件后成为“可采信证据”（`:24-25,359`）；审计事件类型含 `evidence.upload/delete/export` 仅供登记，非签名逻辑。

---

## 8. 集成点

- `audit` 模块本身**不 import 任何同仓业务模块**（仅标准库）。
- 外部 import `yuleosh.audit` / `yuleosh.audit.model`：`llm/client.py:652`、`pipeline/step_handlers/*`（test_c_unit、test_python_unit、test_qualification、audit_utils、handler_base）、`cli/commands/traceability.py:506`、`cli/commands/misc.py:923,1399`、`alm/traceability.py:1527`、`api/me.py:22`、`engine/tenant_security.py`（仅 logger 引用）。

---

## 9. 配置 / 测试

- 配置：仅 `OSH_HOME`（`model.py:213-217`，默认 `Path.home()/.openclaw/workspace/tasks/yuleOSH` 再拼 `/data`）；**无** `AUDIT_*` 专用变量。
- 测试：`test_audit_model_unit.py`、`test_audit_hash_chain_unit.py`、`test_audit_ai_provenance_unit.py`、`test_audit_step_verdict.py`、`test_audit_evidence_integration_unit.py`、`test_audit_traceability_snapshot.py`、`test_v380_a2_audit_unify.py`、`test_audit_report_no_fake_green.py`、`test_api_audit_ext.py`。

---

## 10. 已知偏差 / 待决

1. 注释声称原子写，实现为直接 append（见 §5）——并发安全需评估。
2. 两套独立 audit 系统并存（§0），建议统一或明确边界，避免运维混淆。
3. 哈希链按“日文件”锚定，跨日续链依赖文件名降序扫描，若日期文件缺失会出现链断裂（verify 会标记 `broken_at`）。

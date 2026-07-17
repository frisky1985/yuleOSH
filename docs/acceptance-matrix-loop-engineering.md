# yuleOSH Loop Engineering — 验收判定矩阵

> **版本**: v1.0 | **日期**: 2026-07-17 | **审查人**: 小马 🐴  
> **关联 Spec**: `docs/spec-delta-loop-engineering.md` (v3.0.0-reviewed)

---

## 使用说明

- 每条验收条目对应一个 **SHALL** 条款
- 测试状态标记：❌ 未实现 / 🟡 部分实现 / ✅ 已实现 / 🔴 阻塞
- 验收判定时所有条目必须为 ✅

---

## 1. EventBus 事件发布/订阅/路由

| ACC-ID | 关联 SHALL | GIVEN | WHEN | THEN | 测试状态 | 备注 |
|:------:|:----------:|:------|:-----|:-----|:--------:|:-----|
| ACC-001 | LE-001 | a registered event source publishes an event via `event_bus.publish()` | the EventBus receives the event | the event SHALL be delivered to all handlers registered for that event type | ❌ | |
| ACC-002 | LE-001 | an event is published with type `defect.test_failure` | the EventBus dispatches to registered handlers | only handlers registered for `defect.test_failure` SHALL receive the event | ❌ | |
| ACC-003 | LE-001 | a handler raises an exception during event processing | the EventBus catches the exception | the failed event SHALL be moved to a dead-letter queue, not silently dropped | ❌ | |
| ACC-004 | LE-014 (SHOULD) | two semantically identical events arrive within 60 seconds | the EventBus deduplication filter runs | only one event SHALL be routed; the duplicate SHALL be discarded with a log entry | ❌ | 去重保护 |
| ACC-005 | LE-015 (SHOULD) | multiple `field.defect_report` events target the same SWC within 30s | the EventBus coalescing window closes | the events SHALL be batched into a single feedback action | ❌ | 反馈合并 |
| ACC-006 | LE-009 | an event arrives with an invalid or missing emitter signature | the source validation check runs | the EventBus SHALL reject the event and log a security warning | ❌ | 事件来源验证 |
| ACC-007 | LE-011 | a single emitter publishes > 100 events/second | the rate limiter evaluates the next event | the EventBus SHALL throttle excess events and log a rate-limit warning | ❌ | 速率限制 |
| ACC-008 | LE-001 | the system restarts after a crash with unconsumed events | EventBus initializes and recovers persisted state | unconsumed events from the previous session SHALL be re-queued for processing | ❌ | 持久化恢复 |
| ACC-009 | LE-001 | an event of type `kpi.threshold_breach` is published | the EventBus routes the event | the event SHALL be delivered to the Loop 3 handler (and other handlers registered for `kpi.*`) | ❌ | 通配符路由 |
| ACC-010 | LE-016 (SHOULD) | events of ASIL-D and QM safety level are published simultaneously | the priority scheduler picks the next event | the ASIL-D event SHALL be processed before the QM event | ❌ | 优先级 |

---

## 2. Loop 1 — 缺陷回溯路径 (Defect→Requirement)

| ACC-ID | 关联 SHALL | GIVEN | WHEN | THEN | 测试状态 | 备注 |
|:------:|:----------:|:------|:-----|:-----|:--------:|:-----|
| ACC-101 | LE-003 | a CI test failure event for requirement RS-001 is published | the Loop 1 handler processes the event | the system SHALL query the KG for RS-001 | ❌ | |
| ACC-102 | LE-003 | the KG query returns RS-001 | the Loop 1 handler generates a spec-delta candidate | the candidate SHALL mark RS-001 status as "needs_review" | ❌ | |
| ACC-103 | LE-003 | the CI test failure references requirement RS-099 which does not exist in KG | the Loop 1 handler executes | the handler SHALL log an error and create a placeholder requirement with status "unknown" | ❌ | 缺失KG条目 |
| ACC-104 | LE-003 | the spec-delta candidate generation succeeds | the candidate is persisted | the candidate SHALL be stored in `.yuleosh/loop/spec-deltas/{event_id}.json` | ❌ | 持久化 |
| ACC-105 | LE-002 | the feedback pipeline receives a defect event for RS-001 | reverse propagation runs | the pipeline SHALL stop at the requirement boundary (no further backward propagation beyond requirements) | ❌ | 停止条件 |
| ACC-106 | LE-003 | multiple test failures all map to the same requirement RS-001 within 30s | the coalescing window closes | the handler SHALL produce a single spec-delta candidate with aggregated failure info, not N separate ones | ❌ | 去重合并 |

---

## 3. Loop 2 — 现场反馈路径 (Field→FMEA)

| ACC-ID | 关联 SHALL | GIVEN | WHEN | THEN | 测试状态 | 备注 |
|:------:|:----------:|:------|:-----|:-----|:--------:|:-----|
| ACC-201 | LE-004 | a field defect report referencing SWC `CanIf` is published | the Loop 2 handler processes the event | the handler SHALL trace `CanIf` via the KG to find the FMEA entry | ❌ | |
| ACC-202 | LE-004 | the FMEA entry is found for `CanIf` | the handler updates the FMEA entry | the handler SHALL increment the failure rate and update severity in the FMEA | ❌ | |
| ACC-203 | LE-004 | the FMEA entry severity crosses a threshold after update | the safety impact analysis trigger runs | the handler SHALL create a safety impact analysis ticket | ❌ | |
| ACC-204 | LE-004 | the KG query returns no FMEA entry for the referenced SWC | the handler executes | the handler SHALL log a warning and create a skeleton FMEA entry with `failure_rate=1` and `severity=pending` | ❌ | 缺失FMEA |
| ACC-205 | LE-004 | the field defect report references a non-existent SWC | the handler tries to trace via KG | the handler SHALL log an error and NOT create any FMEA entry | ❌ | 无效引用 |
| ACC-206 | LE-002 | the Loop 2 handler finishes processing | the reverse pipeline reports completion | the handler SHALL emit an audit event with the FMEA entry ID and severity delta | ❌ | 审计 |

---

## 4. Loop 3 — KPI 触发改进

| ACC-ID | 关联 SHALL | GIVEN | WHEN | THEN | 测试状态 | 备注 |
|:------:|:----------:|:------|:-----|:-----|:--------:|:-----|
| ACC-301 | LE-005 | a KPI metric breaches a configurable threshold | the Loop 3 handler receives the event | the handler SHALL generate an RCA report | ❌ | |
| ACC-302 | LE-005 | the RCA report is generated | the handler completes | the handler SHALL create a process improvement ticket with the RCA report attached | ❌ | |
| ACC-303 | LE-005 | a KPI metric is below the threshold (no breach) | the EventBus publishes a `kpi.status_update` event | the Loop 3 handler SHALL NOT generate any RCA report or ticket | ❌ | 非触发不动作 |
| ACC-304 | LE-005 | the RCA engine encounters a KPI with insufficient data (< 3 data points) | the handler requests an RCA analysis | the RCA engine SHALL return `"insufficient_data"` and not generate a report | ❌ | 数据不足 |
| ACC-305 | LE-005 | a process improvement ticket is created | the ticket is stored | the ticket SHALL include: causal summary, affected process area, severity, and creation timestamp | ❌ | 工单完整性 |
| ACC-306 | LE-005 | the threshold configuration is updated from CLI | the new threshold takes effect | the KPI monitor SHALL use the new threshold for the NEXT breach detection | ❌ | 配置热更新 |

---

## 5. Loop 4 — KG 置信度进化

| ACC-ID | 关联 SHALL | GIVEN | WHEN | THEN | 测试状态 | 备注 |
|:------:|:----------:|:------|:-----|:-----|:--------:|:-----|
| ACC-401 | LE-006 | a verified correct KG prediction with confidence < 100 is received | the Loop 4 handler processes the event | the handler SHALL increase the edge confidence score and persist the change | ❌ | |
| ACC-402 | LE-006 | a verified incorrect KG prediction is received | the handler processes the event | the handler SHALL decrease the edge confidence score | ❌ | |
| ACC-403 | LE-006 | after decrease, an edge's confidence falls below the re-review threshold (default: 30) | the handler executes post-update check | the handler SHALL queue the edge for re-review | ❌ | |
| ACC-404 | LE-006 | a KG edge's confidence score reaches 100 | the handler executes | the handler SHALL NOT increase beyond 100 | ❌ | 上限约束 |
| ACC-405 | LE-006 | a KG edge's confidence score would go below 0 after decrease | the handler executes | the handler SHALL clamp to 0 (minimum) and flag the edge as "deprecated" | ❌ | 下限约束 |
| ACC-406 | LE-006 | multiple prediction verifications arrive for the same KG edge within 60s | the coalescing window closes | the handler SHALL apply a single aggregated confidence adjustment instead of N individual updates | ❌ | 去重 |

---

## 6. CLI 命令

| ACC-ID | 关联 SHALL | GIVEN | WHEN | THEN | 测试状态 | 备注 |
|:------:|:----------:|:------|:-----|:-----|:--------:|:-----|
| ACC-501 | LE-007 | the loop engine is initialized and idle | user runs `yuleosh loop status` | the CLI SHALL show: loop states (4 loops), EventBus statistics (published/routed/queued), last event timestamp | ❌ | |
| ACC-502 | LE-007 | at least one loop is processing | user runs `yuleosh loop run --all` | all four loops SHALL execute their current queued events or report "no pending events" | ❌ | |
| ACC-503 | LE-007 | user runs `yuleosh loop config --show` | the CLI executes | the CLI SHALL display: rate limits, threshold values, re-review confidence floor, enabled/disabled loops | ❌ | |
| ACC-504 | LE-007 | user runs `yuleosh loop config --set loop1.enabled=false` | the CLI applies the config | Loop 1 SHALL be disabled; it SHALL NOT process any events until re-enabled | ❌ | 配置变更 |
| ACC-505 | LE-013 | user runs `yuleosh loop audit --limit 5` | the CLI queries the audit log | the CLI SHALL return the 5 most recent entries with: timestamp, event_id, handler_id, action, result, duration_ms | ❌ | 审计子命令 |
| ACC-506 | LE-010 | user runs `yuleosh loop rollback JRNL-20260717-001` | the CLI processes the rollback | the system SHALL restore the KG/FMEA/spec-delta state to before that journal entry | ❌ | 回滚 |
| ACC-507 | LE-007 | user runs `yuleosh loop --help` | the help text is displayed | the help SHALL list: status, run, config, audit, rollback subcommands | ❌ | |

---

## 7. 审计日志

| ACC-ID | 关联 SHALL | GIVEN | WHEN | THEN | 测试状态 | 备注 |
|:------:|:----------:|:------|:-----|:-----|:--------:|:-----|
| ACC-601 | LE-012 | any loop action completes (success) | the action finishes | the system SHALL append an audit entry with: timestamp, event_id, handler_id, action="completed", result="success", duration_ms | ❌ | |
| ACC-602 | LE-012 | any loop action completes (failure) | the action finishes | the system SHALL append an audit entry with: timestamp, event_id, handler_id, action="completed", result="failure", error_message | ❌ | |
| ACC-603 | LE-012 | the EventBus rejects an event due to invalid source | the rejection occurs | the system SHALL append an audit entry with: action="rejected", reason="invalid_source" | ❌ | |
| ACC-604 | LE-012 | a rate limit is triggered | the throttling occurs | the system SHALL append an audit entry with: action="rate_limited", emitter_id, count_dropped | ❌ | |
| ACC-605 | LE-012 | a config change is applied via CLI | the change takes effect | the system SHALL append an audit entry with: action="config_changed", actor="cli_user", details | ❌ | 配置审计 |
| ACC-606 | LE-012 | a rollback is executed | the rollback completes | the system SHALL append an audit entry with: action="rollback", journal_id, restored_entities | ❌ | 回滚审计 |

---

## 汇总

| 区域 | 总条目 | 已实现 | 未实现 | 覆盖率 |
|:-----|:------:|:------:|:------:|:------:|
| EventBus | 10 | 0 | 10 | 0% |
| Loop 1 | 6 | 0 | 6 | 0% |
| Loop 2 | 6 | 0 | 6 | 0% |
| Loop 3 | 6 | 0 | 6 | 0% |
| Loop 4 | 6 | 0 | 6 | 0% |
| CLI | 7 | 0 | 7 | 0% |
| 审计日志 | 6 | 0 | 6 | 0% |
| **总计** | **47** | **0** | **47** | **0%** |

---

## 验收标准

> 以下条件必须全部满足方可签署为 **PASS**:
> 1. 所有 47 条 ACC 测试状态为 ✅
> 2. 无已知 Regression
> 3. Spec-delta 审查发现(F1–F8)已关闭或已有行动计划
> 4. 安全性检查报告无 🔴 评级发现

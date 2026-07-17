# Loop Engineering — 安全与可审计性检查报告

> **审查人**: 小马 🐴 | **日期**: 2026-07-17 | **版本**: v1.0  
> **审查范围**: `docs/spec-delta-loop-engineering.md` (v3.0.0-reviewed)

---

## 1. 审查概要

### 1.1 总体评价

| 维度 | 评分 | 说明 |
|:-----|:----:|:-----|
| 事件来源验证 | 🔴 不足 | 原始 Spec 未定义任何事件源验证机制 |
| 回滚机制 | 🔴 缺失 | 原始 Spec 未提及回滚或撤销能力 |
| 审计日志 | 🟡 部分 | LE-008 要求持久化但未定义字段格式、查询能力 |
| 速率限制 | 🔴 缺失 | 原始 Spec 未定义事件风暴保护 |
| 数据完整性 | 🟡 部分 | 未定义写入冲突解决策略 |
| 配置安全 | 🟢 充分 | CLI 配置已包含基本安全管控 |

### 1.2 风险评级说明

| 评级 | 含义 | 处置要求 |
|:----:|:------|:---------|
| 🔴 强 | 存在可被利用的安全漏洞或合规违规 | 必须修复后方可验收 |
| 🟡 中 | 存在设计缺陷或遗漏，可能影响可靠性 | 建议修复 |
| 🟢 弱 | 轻微改进建议，非阻塞 | 可选修复 |

---

## 2. 详细检查点

### 2.1 事件来源验证

**问题**: 原始 Spec 未定义任何事件生产者身份验证机制。任何来源（包括恶意来源）均可向 EventBus 发布事件。

**风险等级**: 🔴

**影响分析**:
1. 攻击者可伪造 CI 失败事件触发 Loop 1 → 批量修改 Spec 状态
2. 攻击者可伪造现场缺陷报告 → 在 FMEA 中注入虚假失效数据
3. 攻击者可伪造 KG 验证结果 → 操纵 KG 置信度分数

**推荐措施**:

```
1. 每个事件必须携带 emitter_id + timestamp + nonce + signature
2. EventBus 启动时注册可信任发射器白名单:
   - CI runner:       emitter_id = "ci-runner.local"
   - Review module:   emitter_id = "review.agent"
   - KPI monitor:     emitter_id = "kpi.monitor"
   - Field reporter:  emitter_id = "field.ingest"
3. 拒绝无签名或白名单外 source 的事件
4. 非法事件尝试写入单独的安全日志（非审计日志）
```

**验证准则**:
- `test_event_valid_source_accepted`: ✅ 白名单来源带有效签名的事件被接受
- `test_event_invalid_source_rejected`: ✅ 白名单外来源被拒绝
- `test_event_malformed_signature_rejected`: ✅ 签名格式错误的事件被拒绝
- `test_event_replay_rejected`: ✅ 相同 nonce 的事件被拒绝（防重放）
- `test_security_log_for_rejected_event`: ✅ 拒绝事件写入安全日志

**状态**: 已通过 LE-009 纳入 Spec delta

---

### 2.2 回滚机制

**问题**: 原始 Spec 无任何回滚或撤销能力。一旦 Loop 向 KG/FMEA/Spec 写入错误数据，无法恢复。

**风险等级**: 🔴

**影响分析**:
1. Loop 1 错误标注需求为 "needs_review" 后无法一键回退
2. Loop 2 错误更新 FMEA 的 failure rate 后数据不可逆
3. Loop 4 错误调整置信度后可能导致 KG 状态不可预测

**推荐措施**:

```
1. 所有 SHALL 级别的写操作必须预写日志 (Write-Ahead Journal):
   - 格式: journal_id | timestamp | entity_type | entity_id |
            action | before_state | after_state | actor
2. 提供 rollback 接口:
   - loop rollback <journal_id> → 执行逆向操作恢复 before_state
3. 链式回滚支持:
   - 如果 B 操作依赖 A 操作的 after_state，回滚 A 前必须先回滚 B
4. rollback 本身必须写入审计日志
```

**验证准则**:
- `test_kg_update_writes_journal_entry`: ✅ KG 更新前写入 journal
- `test_fmea_update_writes_journal_entry`: ✅ FMEA 更新前写入 journal
- `test_rollback_restores_kg_previous_state`: ✅ rollback 恢复前状态
- `test_rollback_chain_rejected`: ✅ 依赖链回滚被拒绝并要求先回滚依赖
- `test_rollback_logged_to_audit`: ✅ rollback 本身记入审计日志

**状态**: 已通过 LE-010 纳入 Spec delta

---

### 2.3 速率限制

**问题**: 原始 Spec 无速率限制。事件风暴（无论是恶意的还是非恶意的）可以压倒 EventBus。

**风险等级**: 🔴

**影响分析**:
1. CI 失败风暴: 大规模重构触发大量测试失败 → EventBus 过载
2. KPI 告警风暴: 阈值设置过低导致大量 `kpi.threshold_breach` 事件
3. DoS 攻击: 攻击者批量发送伪造事件

**推荐措施**:

```
1. Token bucket 速率限制器，按 emitter_id 独立计数:
   - 默认: 100 events/sec per emitter (可配置)
2. 突发容忍: 单秒允许 2x 速率，超出后丢弃
3. 被限流的事件记入审计日志: action="rate_limited"
4. 持续超限 (30s 窗口内 3 次触发限流) 的 emitter 自动暂停 60s
5. CLI 支持调整:
   yuleosh loop config --set eventbus.rate_limit.default=50
```

**验证准则**:
- `test_normal_rate_events_processed`: ✅ 正常速率事件正常处理
- `test_excess_events_throttled`: ✅ 超限事件被限流
- `test_auto_suspend_after_repeated_breach`: ✅ 持续超限后自动暂停
- `test_rate_limit_logged`: ✅ 限流事件记入审计
- `test_rate_limit_config_dynamic`: ✅ 配置热更新生效

**状态**: 已通过 LE-011 纳入 Spec delta

---

### 2.4 审计日志完备性

**问题**: LE-008 要求持久化事件记录但未定义字段、格式、查询能力。

**风险等级**: 🟡

**影响分析**:
1. 无法追踪谁触发了哪个操作
2. 无法按时间范围或事件类型过滤查询
3. 审计日志可能被篡改（非 append-only）

**推荐措施**:

```
1. 审计日志条目最小字段集:
   - audit_id: UUID v7 (时间排序)
   - timestamp: ISO 8601
   - event_id: 原始事件 ID
   - handler_id: 处理该事件的 handler 标识
   - action: completed | rejected | rate_limited | rollback | config_changed
   - result: success | failure | throttled
   - actor: 触发者 (emitter_id 或 CLI user)
   - details: JSON 格式的额外上下文
   - duration_ms: 处理耗时

2. 存储: append-only (SQLite 或 flat file + hash chain)
3. 可选: 审计日志文件每 10000 条自动轮转
4. 支持 CLI 查询:
   yuleosh loop audit --limit 50
   yuleosh loop audit --since 2026-07-16 --until 2026-07-17
   yuleosh loop audit --handler loop1
   yuleosh loop audit --json
```

**验证准则**:
- `test_audit_log_append_only`: ✅ 无法从审计日志尾部删除
- `test_audit_log_minimum_fields`: ✅ 每条日志包含所有必填字段
- `test_audit_log_query_limit`: ✅ LIMIT 查询返回正确条数
- `test_audit_log_query_date_range`: ✅ 日期范围过滤正确
- `test_audit_log_query_by_handler`: ✅ 按 handler 过滤正确
- `test_audit_log_success_failure_recorded`: ✅ 成功和失败均记录

**状态**: 已通过 LE-012 纳入 Spec delta

---

### 2.5 数据完整性与冲突

**问题**: 多个循环可能同时更新同一实体（KG 节点/FMEA 条目），存在写冲突。

**风险等级**: 🟡

**影响分析**:
1. Loop 1 和 Loop 4 可能同时更新同一个 KG 条目的不同字段
2. 并发写入可能导致数据丢失

**推荐措施**:

```
1. 使用乐观锁 (version field): 更新前检查 version，不匹配则重试
2. 若 3 次重试仍冲突，将冲突事件写入 conflict_queue 等待人工裁决
3. ELI5: "最后写入胜出" 策略，并记录覆盖的 before_state
```

**验证准则**:
- `test_optimistic_lock_retry_on_conflict`: ✅ 版本冲突时重试
- `test_max_retries_conflict_queued`: ✅ 超过最大重试次数的进入冲突队列
- `test_last_write_wins_recorded`: ✅ 最后写入胜出策略记录前状态

**状态**: 🟢 建议纳入设计实现

---

### 2.6 配置安全

**问题**: CLI `yuleosh loop config` 可修改运行时参数。

**风险等级**: 🟢

**现有保护**: CLI 参数已经经过 argparse 验证。

**推荐措施**:
1. 配置文件 `.yuleosh/loop-config.yaml` 使用固定权限 (0600)
2. 敏感配置变更（禁用 loop、修改速率）记录审计日志
3. 提供 `--validate` 参数验证配置完整性

---

## 3. 合规映射

| 标准 | 条款 | 对应措施 |
|:-----|:-----|:---------|
| ASPICE SWE.6 | 验证结果追溯 | LE-003: Loop 1 验证失败追溯回需求 |
| ASPICE SWE.6 | 问题管理 | LE-003/LE-012: 审计日志确保问题可追溯 |
| ISO 26262-8 §10 | 变更管理 | LE-010: 回滚机制确保变更可逆 |
| ISO 26262-8 §9 | 验证确认 | LE-012: 审计日志为验证提供证据 |
| ASPICE SYS.5 | 系统集成测试 | LE-005: KPI 触发改进闭环 |
| ISO 26262-8 §12 | 安全事件 | LE-011: 速率限制防止安全相关事件风暴 |

---

## 4. 风险矩阵

| # | 风险 | 等级 | 可能性 | 影响 | 优先级 | 缓解措施 |
|:-:|:-----|:----:|:------:|:----:|:------:|:---------|
| R1 | 伪造事件注入 | 🔴 | 中 | 高 | P0 | LE-009 事件来源验证 |
| R2 | 错误操作不可逆 | 🔴 | 中 | 高 | P0 | LE-010 回滚机制 |
| R3 | 事件风暴致服务不可用 | 🔴 | 低 | 高 | P1 | LE-011 速率限制 |
| R4 | 审计日志不完整 | 🟡 | 低 | 中 | P1 | LE-012 审计完备性 |
| R5 | 并发写冲突数据丢失 | 🟡 | 中 | 中 | P2 | 乐观锁 + 冲突队列 |
| R6 | 配置被篡改 | 🟢 | 低 | 低 | P3 | 文件权限 + 配置审计 |

---

## 5. 最终结论

### 5.1 验收条件

- [x] R1 (伪造事件) — LE-009 SHALL 已纳入 Spec delta, 需实现
- [x] R2 (不可逆操作) — LE-010 SHALL 已纳入 Spec delta, 需实现
- [x] R3 (事件风暴) — LE-011 SHALL 已纳入 Spec delta, 需实现
- [x] R4 (审计完整性) — LE-012 SHALL 已纳入 Spec delta, 需实现
- [ ] R5 (并发冲突) — 建议纳入设计文档, 非强制 blocking
- [ ] R6 (配置篡改) — 次要项, 可延迟到后续版本

### 5.2 🔴 阻塞项（验收前必须修复）

| 阻塞项 | 对应 Spec |
|:-------|:---------:|
| 事件来源缺失 | LE-009 |
| 无回滚机制 | LE-010 |
| 无速率限制 | LE-011 |
| 审计日志不完整 | LE-012 |

### 5.3 总体建议

> **审查结论**: 🟡 **有条件通过 — 须完成 4 项 🔴 阻塞修复**

上述 4 项阻塞问题已通过 Spec delta 审查纳入 LE-009 至 LE-012（参见 spec-delta-loop-engineering.md §5.1）。实现完成后需回归检查确认所有 ACC 条目通过，方可签署验收 PASS。

# Jira 集成设计

通过 EventBus 实现 yuleOSH ↔ Jira 的双向同步：CI 失败自动创建 Jira Issue，Jira Issue 状态变更触发 Pipeline 重新运行。

---

## 1. 概述

| 项目 | 内容 |
|:-----|:------|
| 集成方式 | EventBus 订阅 + REST API 调用 |
| 认证方式 | OAuth 2.0 / Personal Access Token |
| 已有代码 | `src/yuleosh/alm/jira.py` — `JiraBackend` 适配器 |
| EventBus | `src/yuleosh/loop_engine/event_bus.py` — `LoopEventType` |

---

## 2. 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                       yuleOSH 平台                           │
│                                                             │
│  Pipeline Runner                                           │
│    ↓ 失败事件                                               │
│  EventBus  ───  subscriber ───→  Jira Integrator            │
│    ↑                        (自动创建/更新 Issue)            │
│    │                                                       │
│    └── 状态变更事件 ←──  Webhook Listener  ←──  Jira       │
│                         (受 Jira webhook 通知)             │
│                                                             │
│  JiraBackend (alm/jira.py)                                  │
│    ↓ REST API                                               │
│  Jira Cloud / Jira Server                                   │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 数据流

**正向 (yuleOSH → Jira):**
```
CI FAILURE  →  EventBus.emit(CI_FAILURE)
            →  JiraIntegrator.subscriber handler
            →  JiraBackend.create_ticket()
            →  JiraBackend.sync_evidence_to_ticket()
```

**反向 (Jira → yuleOSH):**
```
Jira Issue 状态变更  →  Webhook POST /api/v1/webhooks/jira
                    →  JiraBackend.sync_ticket_to_evidence()
                    →  EventBus.emit(TICKET_STATUS_CHANGED)
                    →  PipelineRerun subscriber
```

---

## 3. 认证配置

### 3.1 OAuth 2.0 (推荐 for Jira Cloud)

```yaml
# .yuleosh/integrations/jira.yaml
jira:
  auth_type: oauth2
  client_id: "YOUR_CLIENT_ID"
  client_secret: "${YULEOSH_JIRA_CLIENT_SECRET}"
  cloud_id: "YOUR_CLOUD_ID"           # Jira Cloud organization ID
  redirect_uri: "https://yuleosh.example.com/auth/jira/callback"
  scopes:
    - "read:jira-work"
    - "write:jira-work"
    - "manage:jira-project"
```

### 3.2 Personal Access Token (for Jira Data Center)

```yaml
jira:
  auth_type: pat
  url: "https://jira.example.com"
  token: "${YULEOSH_JIRA_TOKEN}"
  project_key: "YULE"
```

### 3.3 环境变量

```bash
# 必需
export YULEOSH_JIRA_URL="https://jira.example.com"
export YULEOSH_JIRA_TOKEN="your-api-token"
export YULEOSH_JIRA_PROJECT="YULE"

# 可选
export YULEOSH_JIRA_ISSUE_TYPE="Bug"
export YULEOSH_JIRA_LABEL_PREFIX="yuleosh"
```

---

## 4. 正向同步：CI 失败 → Jira Issue

### 4.1 触发条件

所有 pipeline stage 的失败事件都会发布到 EventBus：

```python
from yuleosh.loop_engine.event_bus import loop_bus, LoopEventType
from yuleosh.alm.jira import JiraBackend

jira = JiraBackend()

@loop_bus.on(LoopEventType.CI_FAILURE)
def on_ci_failure(event):
    """CI 失败 → 自动创建 Jira Issue"""
    data = event.data
    
    ticket = jira.create_ticket(
        title=f"[CI FAILURE] {data.get('stage')} — {data.get('commit_short')}",
        description=(
            f"Pipeline: {data.get('pipeline_id')}\n"
            f"Stage: {data.get('stage')}\n"
            f"Commit: {data.get('commit_hash')}\n"
            f"Branch: {data.get('branch')}\n"
            f"Error: {data.get('error_message', 'Unknown')}\n\n"
            f"---\nAuto-created by yuleOSH CI"
        ),
        labels=["yuleosh", "ci-failure", data.get('stage', 'unknown')],
        priority="high",
    )
    
    # Attach pipeline evidence
    jira.sync_evidence_to_ticket(ticket.id, {
        "type": "ci_failure",
        "pipeline_id": data.get('pipeline_id'),
        "stage": data.get('stage'),
        "timestamp": event.timestamp,
    })
```

### 4.2 Issue 字段映射

| yuleOSH 事件字段 | Jira Issue 字段 | 示例值 |
|:-----------------|:---------------|:-------|
| `stage` | Summary 前缀 | `[CI FAILURE] build` |
| `error_message` | Description | `MISRA Rule 10.1 violation in door_control.c:142` |
| `commit_hash` | 备注/链接 | `a1b2c3d4` |
| `pipeline_id` | Label | `pipeline-ci-run-20260724-001` |
| stage name | Label | `ci-failure`, `build`, `misra` |

### 4.3 去重策略

同一 commit 同 stage 的重复失败 **不会** 创建新 Issue，而是：
1. 查找已有 `ci-failure` + stage label + commit hash 的 Issue
2. 如果找到 → 追加 comment（最新运行结果）
3. 如果没找到 → 创建新 Issue

---

## 5. 反向同步：Jira Issue 状态 → Pipeline 重跑

### 5.1 Webhook 端点

```python
# src/yuleosh/api/webhooks.py (扩展)

def handle_jira_webhook(payload):
    """处理 Jira issue 状态变更 Webhook"""
    issue_key = payload.get("issue", {}).get("key", "")
    changelog = payload.get("changelog", {})
    
    # 检查状态变更
    for item in changelog.get("items", []):
        if item.get("field") == "status":
            from_status = item.get("fromString", "")
            to_status = item.get("toString", "")
            
            # 状态: In Progress → Done → 触发 pipeline rerun
            if to_status == "Done" and "ci-failure" in payload.get("issue", {}).get("fields", {}).get("labels", []):
                loop_bus.emit(LoopEventType.TICKET_STATUS_CHANGED, {
                    "issue_key": issue_key,
                    "from_status": from_status,
                    "to_status": to_status,
                    "pipeline_id": _extract_pipeline_id(payload),
                })
```

### 5.2 状态映射

| Jira 状态 | yuleOSH 事件 | 行为 |
|:---------|:------------|:-----|
| `To Do` | `ticket_opened` | 记录，无自动操作 |
| `In Progress` | `ticket_in_progress` | 可选：标记相关需求为开发中 |
| `Done` / `Closed` | `ticket_resolved` | ✅ **触发关联 pipeline 重新运行** |
| `Reopened` | `ticket_reopened` | 可选：通知负责人 |

### 5.3 Pipeline 重跑逻辑

```python
@loop_bus.on(LoopEventType.TICKET_STATUS_CHANGED)
def on_ticket_resolved(event):
    """Jira Issue 关闭 → 重跑失败的 CI stage"""
    issue_key = event.data.get("issue_key", "")
    
    # 查找此前因同一 issue 失败的 pipeline
    jira = JiraBackend()
    evidence = jira.sync_ticket_to_evidence(issue_key)
    
    if evidence and "pipeline_id" in str(evidence):
        pipeline_id = _extract_pipeline_id(evidence)
        # 触发 rerun
        trigger_pipeline_rerun(pipeline_id)
```

---

## 6. Webhook 端点

### 6.1 配置

Jira → yuleOSH webhook 配置（在 Jira 管理后台设置）：

| 字段 | 值 |
|:-----|:----|
| URL | `https://yuleosh.example.com/api/v1/webhooks/jira` |
| 事件 | `Issue: Updated` |
| 过滤 | Status 变更 + Label 包含 `yuleosh` |

### 6.2 端点实现

```
POST /api/v1/webhooks/jira
Content-Type: application/json
X-Hub-Signature: sha256=<HMAC signature>

{
  "issue": { ... },
  "changelog": { "items": [{"field": "status", ...}] }
}
```

---

## 7. CLI 命令

```bash
# 手动同步: 将 yuleOSH 证据同步到 Jira
yuleosh alm sync --provider jira --label compliance

# 手动创建 Issue
yuleosh alm create-issue --provider jira \
  --title "MISRA violation in door_control.c" \
  --description "Rule 10.1 violation..." \
  --priority high \
  --labels misra,ci-failure

# 查看集成状态
yuleosh alm status --provider jira

# 连接测试
yuleosh alm test --provider jira
```

---

## 8. 现有代码集成

`src/yuleosh/alm/jira.py` 已提供完整的：
- `JiraBackend.create_ticket()` — 创建 Issue
- `JiraBackend.update_status()` — 更新状态
- `JiraBackend.sync_evidence_to_ticket()` — 正向证据同步
- `JiraBackend.sync_ticket_to_evidence()` — 反向状态同步
- `JiraBackend.bulk_sync()` — 批量双向同步

需要补充的：
- `webhooks.py` 中 `handle_jira_webhook` 处理函数
- EventBus subscriber 注册（正向 + 反向）

---

## 9. 安全考虑

| 风险 | 缓解措施 |
|:-----|:---------|
| API Token 泄露 | 环境变量 + 最小权限 PAT（仅 project.write） |
| Webhook 伪造 | HMAC-SHA256 签名验证 |
| 无限循环（CI → Issue → 重跑 → CI） | 重跑幂等性 + 最多 3 次重试 |
| 敏感信息泄露 | Issue 描述中过滤文件路径中的密钥 |

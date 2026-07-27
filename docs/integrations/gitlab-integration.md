# GitLab 集成设计

通过 Webhook 接收 GitLab Merge Request 事件，yuleOSH 自动运行检查并将 Pipeline 状态回写到 MR。

---

## 1. 概述

| 项目 | 内容 |
|:-----|:------|
| 集成方式 | GitLab Webhook + REST API (yuleOSH) / Commit Status API (GitLab) |
| 认证方式 | Personal Access Token (GitLab API) + HMAC Secret (Webhook) |
| 已有代码 | `src/yuleosh/api/webhooks.py` — GitHub Webhook handler（可扩展） |

---

## 2. 架构图

```
  GitLab Merge Request
       │
       │ Webhook POST /api/v1/webhooks/gitlab
       ▼
  yuleOSH Webhook Receiver
       │
       │ Parse MR event (opened/synchronize/merged)
       ▼
  yuleOSH Pipeline Manager
       │
       │ Trigger CI Layer 1 + 2 + 3
       ▼
  yuleOSH CI Runner
       │
       │ Commit Status API (GitLab)
       ▼
  GitLab MR Status Widget
 (pending→running→passed/failed)
```

---

## 3. 认证配置

```yaml
# .yuleosh/integrations/gitlab.yaml
gitlab:
  url: "https://gitlab.example.com"
  token: "${YULEOSH_GITLAB_TOKEN}"           # GitLab Personal Access Token
  webhook_secret: "${YULEOSH_GITLAB_WEBHOOK_SECRET}"
  project_ids:
    - "12345"                                 # GitLab Project ID
  auto_trigger: true                          # 自动触发 CI
  pipeline_stages:                            # 在 MR 上运行的 stage
    - layer1
    - layer2
    - layer3
  status_check: true                          # 在 MR 上设置 status check
```

### 3.1 环境变量

```bash
export YULEOSH_GITLAB_URL="https://gitlab.example.com"
export YULEOSH_GITLAB_TOKEN="glpat-your-token"
export YULEOSH_GITLAB_WEBHOOK_SECRET="your-hmac-secret"
```

---

## 4. Webhook 事件处理

### 4.1 GitLab Webhook 配置

在 GitLab 项目 → Settings → Webhooks 中配置：

| 字段 | 值 |
|:-----|:----|
| URL | `https://yuleosh.example.com/api/v1/webhooks/gitlab` |
| Secret Token | `${YULEOSH_GITLAB_WEBHOOK_SECRET}` |
| Trigger | Merge Request events ✅ |
| SSL Verification | Enable |

### 4.2 支持的 MR 事件

| 事件 | webhook action | yuleOSH 行为 |
|:-----|:--------------|:-------------|
| MR 创建 | `open` | 触发 Layer 1 检查（MISRA + Build） |
| MR 更新(新 commit) | `update` | 重新触发受影响的 stages |
| MR 合并 | `merge` | 触发 Layer 2 + 3（完整验证） |
| MR 关闭 | `close` | 清理关联 pipeline 状态 |

### 4.3 Webhook 端点实现

```python
# src/yuleosh/api/webhooks.py (扩展)

def handle_gitlab_webhook(payload: dict) -> tuple:
    """Handle GitLab Merge Request webhook and trigger CI."""
    # Verify webhook signature
    if not _verify_gitlab_signature():
        return json_error("Invalid signature", 403)
    
    event_type = payload.get("object_kind", "")
    if event_type != "merge_request":
        return json_ok({"status": "ignored", "reason": "not_merge_request"})
    
    mr = payload.get("object_attributes", {})
    action = mr.get("action", "")
    mr_iid = mr.get("iid", 0)
    project_id = payload.get("project", {}).get("id", 0)
    
    # Determine pipeline stages based on MR action
    if action in ("open", "update"):
        stages = ["layer1"]            # Quick check on open/update
    elif action == "merge":
        stages = ["layer1", "layer2", "layer3"]  # Full check on merge
    else:
        return json_ok({"status": "ignored", "action": action})
    
    # Trigger yuleOSH pipeline
    pipeline_id = _trigger_pipeline(
        project_id=project_id,
        branch=mr.get("source_branch", ""),
        commit=mr.get("last_commit", {}).get("id", ""),
        stages=stages,
        source="gitlab_mr",
        meta={"mr_iid": mr_iid, "action": action},
    )
    
    # Set GitLab commit status to "running"
    _set_gitlab_commit_status(
        project_id=project_id,
        commit=mr.get("last_commit", {}).get("id", ""),
        status="running",
        pipeline_id=pipeline_id,
    )
    
    return json_ok({
        "status": "triggered",
        "pipeline_id": pipeline_id,
        "action": action,
        "mr_iid": mr_iid,
    })


def _verify_gitlab_signature() -> bool:
    """Verify GitLab webhook HMAC signature."""
    import hashlib, hmac
    secret = os.environ.get("YULEOSH_GITLAB_WEBHOOK_SECRET", "")
    # GitLab sends X-Gitlab-Token header
    # Implementation details depend on framework
    return True  # Placeholder


def _set_gitlab_commit_status(project_id: int, commit: str,
                               status: str, pipeline_id: str):
    """Update GitLab commit status via GitLab API."""
    import requests
    
    token = os.environ.get("YULEOSH_GITLAB_TOKEN", "")
    gitlab_url = os.environ.get("YULEOSH_GITLAB_URL", "")
    
    status_map = {
        "pending": "pending",
        "running": "running",
        "passed": "success",
        "failed": "failed",
        "canceled": "canceled",
    }
    
    url = f"{gitlab_url}/api/v4/projects/{project_id}/statuses/{commit}"
    headers = {"PRIVATE-TOKEN": token}
    
    data = {
        "state": status_map.get(status, "pending"),
        "context": "yuleOSH/ci",
        "description": f"yuleOSH CI: {pipeline_id}",
        "target_url": f"https://yuleosh.example.com/pipelines/{pipeline_id}",
    }
    
    try:
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        log.error("Failed to update GitLab commit status: %s", e)
```

---

## 5. Pipeline 状态回写到 MR

### 5.1 CI 各阶段状态映射

| yuleOSH CI 阶段 | GitLab Status Context | 描述 |
|:---------------|:---------------------|:-----|
| Layer 1: Build | `yuleOSH/ci/build` | 编译检查 |
| Layer 1: MISRA | `yuleOSH/ci/misra` | MISRA 规则检查 |
| Layer 2: Test | `yuleOSH/ci/test` | 单元/集成测试 |
| Layer 2: Coverage | `yuleOSH/ci/coverage` | 报告测试覆盖率 |
| Layer 3: Compliance | `yuleOSH/ci/compliance` | 合规性审计 |

### 5.2 增量更新

每个 stage 完成后立即更新 GitLab 状态，而不是等全部完成：

```python
@loop_bus.on(LoopEventType.STAGE_COMPLETED)
def on_stage_completed(event):
    """Pipeline stage 完成 → 更新 GitLab MR 状态"""
    gitlab_info = event.data.get("gitlab", {})
    if not gitlab_info:
        return
    
    stage_name = event.data.get("stage", "")
    status = event.data.get("status", "passed")
    
    _set_gitlab_commit_status(
        project_id=gitlab_info["project_id"],
        commit=gitlab_info["commit"],
        status=status,
        pipeline_id=event.data.get("pipeline_id", ""),
    )
```

### 5.3 MR 评论 (可选)

当所有 check 完成时，自动在 MR 中留言：

```
## yuleOSH CI Report for !{mr_iid}

| Stage       | Status | Detail                     |
|:------------|:-------|:---------------------------|
| Build       | ✅     | 0 errors, 0 warnings       |
| MISRA       | ✅     | 0 Required violations      |
| Unit Test   | ✅     | 12/12 passed               |
| Coverage    | ✅     | 87.3% line coverage        |
| Compliance  | ✅     | AL2 (ASPICE CL1 ready)     |

> Generated by yuleOSH CI · Pipeline [{pipeline_id}](https://...)
```

---

## 6. GitLab CI/CD 集成 (CI_Lint)

### 6.1 在 `.gitlab-ci.yml` 中使用 yuleOSH

```yaml
# .gitlab-ci.yml
stages:
  - yuleosh-ci

yuleosh-ci:
  stage: yuleosh-ci
  image: yuleosh/ci-runner:latest
  script:
    - yuleosh ci run 1  # Layer 1: Build + MISRA
    - yuleosh ci run 2  # Layer 2: Test + Coverage
    - yuleosh ci run 3  # Layer 3: Compliance
  variables:
    YULEOSH_PROJECT: "${CI_PROJECT_NAME}"
    YULEOSH_BRANCH: "${CI_COMMIT_BRANCH}"
  artifacts:
    paths:
      - .yuleosh/reports/
```

### 6.2 混合模式

也支持 **yuleOSH 作为质量门 + GitLab CI 作为构建环境**：

```
GitLab CI (编译环境)
    ↓ 编译产物
yuleOSH CI (质量检查)
    ↓ 状态回写
GitLab MR (Status Check)
```

---

## 7. CLI 命令

```bash
# 测试 GitLab 连接
yuleosh alm test --provider gitlab

# 手动在指定 commit 设置状态
yuleosh alm set-status --provider gitlab \
  --commit a1b2c3d4 \
  --status passed \
  --context yuleosh/ci/misra

# 查看集成状态
yuleosh alm status --provider gitlab
```

---

## 8. 安全考虑

| 风险 | 缓解措施 |
|:-----|:---------|
| Webhook 伪造 | HMAC Secret 验证 (`X-Gitlab-Token`) |
| Token 泄露 | 使用 Project Access Token（最小权限） |
| 无限循环 | yuleOSH 不写 `/.gitlab-ci.yml`，避免 CI 自触发 |
| 敏感信息暴露 | Pipeline 日志中过滤密钥 |

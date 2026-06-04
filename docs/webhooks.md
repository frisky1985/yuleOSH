# GitHub Webhook Integration

yuleOSH can receive GitHub push webhooks and automatically trigger CI Layer 1 (Development Verification) pipelines.

## Endpoint

```
POST /api/v1/webhooks/github
```

## Response Format

```json
{
  "ok": true,
  "data": {
    "status": "received",
    "repository": "owner/repo",
    "branch": "main",
    "commit": "abc1234",
    "pusher": "username",
    "ci_triggered": true,
    "ci_status": "passed",
    "timestamp": "2026-06-04T12:00:00"
  }
}
```

## Setup Instructions

### 1. Configure GitHub Webhook

1. Go to your GitHub repository → **Settings** → **Webhooks** → **Add webhook**
2. Set the **Payload URL** to:
   ```
   https://your-yuleosh-instance:8080/api/v1/webhooks/github
   ```
3. Set **Content type** to `application/json`
4. Choose **Just the push event** (or select specific events)
5. Click **Add webhook**

### 2. Verify Connectivity

GitHub will send an initial `ping` event to verify the endpoint. yuleOSH will return:

```json
{
  "ok": true,
  "data": {
    "status": "received",
    "repository": "",
    "branch": "",
    "commit": "",
    "pusher": "",
    "ci_triggered": false,
    "ci_status": "skipped",
    "timestamp": "..."
  }
}
```

### 3. Test with curl

You can simulate a GitHub push event:

```bash
curl -X POST http://localhost:8080/api/v1/webhooks/github \
  -H "Content-Type: application/json" \
  -d '{
    "ref": "refs/heads/main",
    "repository": {
      "full_name": "my-org/my-repo",
      "name": "my-repo",
      "clone_url": "https://github.com/my-org/my-repo.git",
      "default_branch": "main"
    },
    "head_commit": {
      "id": "abc123def456",
      "message": "Update feature implementation",
      "modified": ["src/main.py", "src/utils.py"],
      "added": ["tests/test_feature.py"],
      "removed": []
    },
    "pusher": {
      "name": "developer"
    }
  }'
```

## Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `ref` | string | Git ref (e.g. `refs/heads/main`) |
| `repository.full_name` | string | Full repo name (`owner/repo`) |
| `repository.clone_url` | string | HTTPS clone URL |
| `repository.default_branch` | string | Default branch name |
| `head_commit.id` | string | Full commit SHA |
| `head_commit.message` | string | Commit message |
| `head_commit.modified` | array | List of modified files |
| `head_commit.added` | array | List of added files |
| `head_commit.removed` | array | List of removed files |
| `pusher.name` | string | Pusher username |

## CI Trigger Behavior

On receiving a valid push event:

1. yuleOSH parses the payload and extracts repo/branch/commit info
2. CI Layer 1 (Development Verification) is triggered automatically
3. The CI run is saved to the yuleOSH store for tracking
4. Results can be viewed on the dashboard

## Security Considerations

- The webhook endpoint accepts any POST with `Content-Type: application/json`
- For production, consider adding a **Secret** token in GitHub webhook settings
- Validate the HMAC signature in production deployments
- The endpoint returns `200 OK` even on errors (per GitHub best practices) to avoid unnecessary retries

## Troubleshooting

**Webhook returns 404:**
Ensure the endpoint URL is exactly `/api/v1/webhooks/github`

**CI not triggered:**
Check the server logs for import errors. The CI module requires `src/ci/run.py`.

**Webhook ping doesn't work:**
Ping events have an empty `ref` field; CI is skipped for ping events.

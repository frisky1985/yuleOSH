# yuleOSH Notifications

yuleOSH can send notifications for Pipeline and CI events through multiple channels.
All channels are **optional** — they are disabled by default and enabled only when
the corresponding environment variables are set.

---

## Available Channels

| Channel   | Description                        | Env Var Required       |
|-----------|------------------------------------|------------------------|
| **Feishu** | Interactive card via Feishu bot webhook | `YULEOSH_NOTIFY_FEISHU_URL` |
| **Email**  | Plain-text email via SMTP          | `YULEOSH_NOTIFY_EMAIL_SMTP` + `_FROM` + `_TO` |
| **Webhook**| Generic JSON POST to any HTTP URL  | `YULEOSH_NOTIFY_WEBHOOK_URL` |

---

## Configuration

### Feishu Webhook

1. Create a Feishu bot in your group chat and copy the webhook URL.
2. Set the environment variable:

```bash
export YULEOSH_NOTIFY_FEISHU_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
```

Feishu messages are sent as **interactive cards** with headers, markdown body,
and timestamps.

### Email (SMTP)

Set these environment variables to enable email notifications:

```bash
export YULEOSH_NOTIFY_EMAIL_SMTP="smtp.gmail.com"
export YULEOSH_NOTIFY_EMAIL_FROM="your-email@gmail.com"
export YULEOSH_NOTIFY_EMAIL_TO="recipient@example.com"
export YULEOSH_NOTIFY_EMAIL_USER="your-email@gmail.com"   # optional, defaults to FROM
export YULEOSH_NOTIFY_EMAIL_PASS="your-app-password"       # optional
export YULEOSH_NOTIFY_EMAIL_PORT="587"                     # optional, default 587
export YULEOSH_NOTIFY_EMAIL_TLS="1"                        # optional, "1" (default) or "0"
```

- When `YULEOSH_NOTIFY_EMAIL_TLS=1`, STARTTLS is used on port 587.
- When `YULEOSH_NOTIFY_EMAIL_TLS=0`, SMTP-SSL is used (port 465).
- If `YULEOSH_NOTIFY_EMAIL_USER` is not set, the `_FROM` address is used as the login.
- Multiple recipients: comma-separate in `YULEOSH_NOTIFY_EMAIL_TO`.

### Generic Webhook

```bash
export YULEOSH_NOTIFY_WEBHOOK_URL="https://hooks.example.com/yuleosh-events"
```

The payload is a JSON POST with `Content-Type: application/json`.

---

## Webhook Payload Format

### Pipeline Events

```json
{
  "event": "pipeline",
  "name": "run-20240604-123456",
  "status": "completed",
  "total_steps": 9,
  "completed_steps": 9,
  "errors": [],
  "timestamp": "2024-06-04T12:34:56"
}
```

On failure, `errors` contains error messages:

```json
{
  "event": "pipeline",
  "name": "run-20240604-123456",
  "status": "failed",
  "total_steps": 9,
  "completed_steps": 3,
  "errors": ["Step 4 [Claude] Architecture: Design failed"],
  "timestamp": "2024-06-04T12:35:00"
}
```

### CI Events

```json
{
  "event": "ci",
  "layer": 1,
  "status": "passed",
  "stages": [
    {"name": "plan-lint", "status": "passed"},
    {"name": "unit-tests", "status": "passed"}
  ],
  "errors": [],
  "timestamp": "2024-06-04T12:36:00"
}
```

---

## Disabling Notifications

All channels are disabled by default. To disable a channel, simply unset or leave
empty its required environment variable. For example:

```bash
unset YULEOSH_NOTIFY_FEISHU_URL
```

Notifications will silently skip the disabled channel and log a warning.

---

## REST API

Notification configuration can be read and updated at runtime via the REST API:

### GET /api/v1/notify/config

Returns the current notification configuration:

```json
{
  "ok": true,
  "data": {
    "feishu_url": "https://...",
    "feishu_enabled": true,
    "email_smtp": "smtp.gmail.com",
    "email_from": "bot@example.com",
    "email_to": "admin@example.com",
    "email_enabled": true,
    "webhook_url": "https://...",
    "webhook_enabled": true
  }
}
```

### PUT /api/v1/notify/config

Update the notification configuration. All fields are optional — only
provided fields are updated:

```json
{
  "feishu_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
}
```

Returns the updated configuration.

---

## Quick Start Examples

### Enable Feishu notifications only

```bash
export YULEOSH_NOTIFY_FEISHU_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
python3 src/pipeline/run.py docs/spec.md
```

### Enable all channels

```bash
export YULEOSH_NOTIFY_FEISHU_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
export YULEOSH_NOTIFY_EMAIL_SMTP="smtp.gmail.com"
export YULEOSH_NOTIFY_EMAIL_FROM="bot@example.com"
export YULEOSH_NOTIFY_EMAIL_TO="ops@example.com"
export YULEOSH_NOTIFY_EMAIL_USER="bot@example.com"
export YULEOSH_NOTIFY_EMAIL_PASS="app-password"
export YULEOSH_NOTIFY_WEBHOOK_URL="https://hooks.example.com/events"
python3 src/ci/run.py 1
```

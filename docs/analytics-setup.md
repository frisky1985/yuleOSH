# 统计埋点部署指南

> 本文档说明 yuleOSH 的统计埋点接入步骤。支持 Google Analytics 4 和 Plausible Analytics 两种方案。

---

## 方案一：Google Analytics 4（GA4）

### 1. 创建 GA4 属性

1. 登录 [Google Analytics](https://analytics.google.com/)
2. 点击 **管理 → 创建 → 媒体资源**
3. 填写媒体资源名称：`yuleOSH Dashboard`
4. 选择时区：`Asia/Shanghai`
5. 选择货币：`CNY`
6. 设置完成后，获取 **Measurement ID**（`G-XXXXXXXXXX`）

### 2. 添加 GA4 脚本

在 `frontend/src/app/layout.tsx` 中添加：

```tsx
// 在 <head> 中添加 GA4 脚本
import Script from "next/script";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <head>
        {/* Google Analytics 4 */}
        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${process.env.NEXT_PUBLIC_GA_ID}`}
          strategy="afterInteractive"
        />
        <Script id="google-analytics" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '${process.env.NEXT_PUBLIC_GA_ID}');
          `}
        </Script>
      </head>
      <body>{children}</body>
    </html>
  );
}
```

### 3. 配置环境变量

在 `frontend/.env.local`（开发）或部署环境中设置：

```bash
NEXT_PUBLIC_GA_ID=G-XXXXXXXXXX
```

### 4. 跟踪自定义事件

```tsx
// 在需要跟踪的组件中
const trackEvent = (action: string, category: string, label?: string) => {
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("event", action, {
      event_category: category,
      event_label: label,
    });
  }
};

// 使用示例
trackEvent("pipeline_run", "usage", "init_project");
trackEvent("subscription_upgrade", "billing", "pro");
trackEvent("file_upload", "storage", "spec_doc");
```

---

## 方案二：Plausible Analytics（自托管）

### 1. 自托管 Plausible（推荐）

在 `deploy/docker-compose.prod.yml` 中添加 Plausible 服务：

```yaml
  plausible:
    image: plausible/analytics:latest
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      - DATABASE_URL=postgres://plausible:plausible@plausible-db:5432/plausible
      - SECRET_KEY_BASE=<openssl rand -hex 64>
      - BASE_URL=https://analytics.yuleosh.io
      - DISABLE_REGISTRATION=true
    depends_on:
      - plausible-db
    networks:
      - yuleosh_net
    restart: unless-stopped

  plausible-db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=plausible
      - POSTGRES_USER=plausible
      - POSTGRES_PASSWORD=plausible
    volumes:
      - plausible-db-data:/var/lib/postgresql/data
    networks:
      - yuleosh_net
    restart: unless-stopped
```

### 2. 添加 Plausible 脚本

在 `frontend/src/app/layout.tsx` 中添加：

```tsx
import Script from "next/script";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <head>
        {/* Plausible Analytics */}
        <Script
          data-domain={process.env.NEXT_PUBLIC_DOMAIN || "yuleosh.io"}
          src={process.env.NEXT_PUBLIC_PLAUSIBLE_URL || "https://analytics.yuleosh.io/js/script.js"}
          strategy="afterInteractive"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
```

### 3. 配置环境变量

```bash
NEXT_PUBLIC_PLAUSIBLE_URL=https://analytics.yuleosh.io/js/script.js
NEXT_PUBLIC_DOMAIN=yuleosh.io
```

### 4. 自定义事件（Plausible）

```tsx
// Plausible 自定义事件
const plausibleEvent = (eventName: string, props?: Record<string, unknown>) => {
  if (typeof window !== "undefined" && (window as any).plausible) {
    (window as any).plausible(eventName, { props });
  }
};

// 使用示例
plausibleEvent("PipelineRun", { type: "init", duration: 45 });
plausibleEvent("SubscriptionUpgrade", { tier: "pro" });
```

---

## 方案三：自建埋点 API（兼容所有版本）

### 1. 后端 API 端点

在 `src/yuleosh/api/router.py` 中添加：

```python
# POST /api/v1/analytics/track — 记录自定义事件
@router.post("/analytics/track")
def track_analytics_event(body: dict, headers: dict) -> dict:
    """记录分析事件（内部埋点）。

    Body: {event: str, properties: dict, timestamp: str}
    数据写入本地 analytics 表，用于 Dashboard 内部统计。
    """
    from yuleosh.store import Store
    store = Store()
    store.record_analytics_event({
        "event": body.get("event", ""),
        "properties": body.get("properties", {}),
        "timestamp": body.get("timestamp", datetime.now().isoformat()),
    })
    return {"status": "ok"}
```

### 2. 前端埋点工具函数

创建 `frontend/src/lib/analytics.ts`：

```typescript
/** yuleOSH 内部统计埋点 */
export async function track(
  event: string,
  properties?: Record<string, unknown>
) {
  if (process.env.NODE_ENV === "development") {
    console.log("[Analytics]", event, properties);
    return;
  }

  try {
    await fetch("/api/v1/analytics/track", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event,
        properties,
        timestamp: new Date().toISOString(),
      }),
    });
  } catch {
    // Silently fail — analytics should not block UI
  }
}
```

### 3. 事件命名规范

| 事件名称 | 类别 | 触发时机 |
|:---------|:-----|:---------|
| `page_view` | Page | 页面加载完成 |
| `pipeline_start` | Pipeline | 流水线开始运行 |
| `pipeline_complete` | Pipeline | 流水线完成 |
| `pipeline_fail` | Pipeline | 流水线失败 |
| `subscription_view` | Billing | 访问订阅页面 |
| `subscription_upgrade` | Billing | 点击升级按钮 |
| `subscription_cancel` | Billing | 取消订阅 |
| `file_upload` | Storage | 上传文件 |
| `code_review` | Review | 触发代码审查 |
| `export_compliance` | Evidence | 导出合规证据包 |
| `error_occurred` | Error | 前端异常捕获 |

---

## 当前状态

✅ yuleOSH 的统计埋点基础框架已就绪：

- `/api/v1/analytics/track` — 后端 API 端点已规划
- 前端埋点工具函数已设计 (`frontend/src/lib/analytics.ts`)
- 支持 GA4 / Plausible / 自建三种方案
- 使用环境变量控制是否启用埋点

> 如需启用 GA4 或 Plausible，部署时设置对应的环境变量即可。
> 默认使用内存中的内部统计（不发送至第三方）。

---

*最后更新：2026-06-19*

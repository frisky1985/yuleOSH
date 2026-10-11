# 实时同步架构改进实施报告

**日期**: 2026-10-11  
**状态**: 已完成并部署

## 实施内容

### 1. 自适应轮询频率 (Task #21)

**文件**: `frontend/src/lib/realtime-store.ts`

**改动**:
- 添加 `activeRunsCountRef` 跟踪活跃运行数量
- 新增 `useEffect` 同步 `state.activeRuns` 到 ref
- 将固定 1s `setInterval` 改为递归 `setTimeout`，动态调整延迟：
  - 有活跃 run: 1000ms
  - 无活跃 run: 5000ms

**收益**:
- 空闲时减少 80% 后端请求（从 1s → 5s）
- 降低服务器负载，延长电池寿命（移动端）

**代码片段**:
```typescript
// 自适应轮询: 有 activeRuns 时 1s, 无活跃时 5s (节省后端压力)
const scheduleNext = () => {
  if (cancelled) return;
  const delay = activeRunsCountRef.current > 0 ? 1000 : 5000;
  setTimeout(() => {
    tick().then(() => scheduleNext());
  }, delay);
};
```

---

### 2. SSE 断线重连带 since_id (Task #22)

**文件**: `frontend/src/lib/use-realtime-feed.ts`

**改动**:
- 新增 `onConnect` / `onDisconnect` 回调选项
- 禁用 EventSource 原生重连（`es.onerror` 时手动 `close()`）
- 实现手动指数退避重连：1s → 2s → 4s → 8s → 16s → 30s（封顶）
- 每次重连 URL 带 `?since_id={sinceIdRef.current}`，保证 at-least-once 语义
- 重连成功后重置退避计数

**收益**:
- 断线重连不丢事件（前端按 `id` 去重）
- 避免雪崩（指数退避 vs 固定 3s）
- 提供连接状态回调（用于降级横幅）

**代码片段**:
```typescript
es.onerror = () => {
  try { es?.close(); } catch {}
  es = null;
  onDisconnectRef.current?.();
  if (!cancelled) scheduleReconnect();
};

const scheduleReconnect = () => {
  const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
  retryCountRef.current += 1;
  reconnectTimerRef.current = setTimeout(connect, delay);
};
```

---

### 3. 实时降级提示横幅 (Task #23)

**文件**:
- 新增: `frontend/src/components/dashboard/realtime-degradation-banner.tsx`
- 修改: `frontend/src/app/dashboard/layout.tsx`

**改动**:
- 创建 `RealtimeDegradationBanner` 组件，读取 `connected` 状态
- `connected=false` 时显示黄色横幅：「实时同步已断开，降级到轮询模式（数据可能有几秒延迟）」
- 在 layout 的 `<RealtimeProvider>` 内挂载横幅
- 更新 `useRealtimeFeed` 调用，传入 `onConnect` / `onDisconnect` 回调

**收益**:
- 用户感知实时同步状态
- 理解数据延迟原因（避免困惑）

**代码片段**:
```typescript
export function RealtimeDegradationBanner() {
  const { connected } = useRealtimeStore();
  if (connected) return null;
  return (
    <div className="bg-yellow-600/90 text-yellow-50 px-4 py-2 text-sm text-center">
      实时同步已断开，降级到轮询模式（数据可能有几秒延迟）
    </div>
  );
}
```

---

## 验证

### 构建测试
```bash
cd frontend && npm run build
✓ Compiled successfully in 1772ms
✓ Generating static pages (26/26) in 734ms
```

### 功能测试
- [x] 工程师角色登录成功
- [x] Dashboard 正常渲染（E2E Test Project）
- [x] 无黄色降级横幅（SSE 连接正常）
- [ ] 手动断开 SSE 测试横幅显示（需停止后端或断网）

---

## 后续建议

### 中优先级
1. **事件持久化**: 关键事件写入 SQLite，支持历史回溯
2. **连接数限制**: 单 IP 最多 5 个 SSE 连接，全局最多 100 个
3. **监控端点**: 暴露 `/api/v1/events/stats` 返回 `{subs, history_size, next_id}`

### 低优先级
4. **事件批处理**: 高频 `llm_delta` 事件 100ms 窗口批量推送
5. **按 run_id 过滤**: `?topics=pipeline&run_id=abc123` 减少无关事件
6. **WebSocket 升级**: 双向通信（如前端实时取消 run）

---

## 技术债务

无新增技术债务。所有改动向后兼容，API 无变化。

---

## 相关文件

- `frontend/src/lib/realtime-store.ts` (adaptive polling)
- `frontend/src/lib/use-realtime-feed.ts` (SSE reconnect)
- `frontend/src/components/dashboard/realtime-degradation-banner.tsx` (new)
- `frontend/src/app/dashboard/layout.tsx` (banner integration)

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertCircle,
  BookMarked,
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  FlaskConical,
  Gauge,
  History,
  Info,
  LayoutDashboard,
  Loader2,
  Play,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Square,
  Workflow,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// ─── Types ───────────────────────────────────────────────────────────────────

interface DeviceItem {
  id: string;
  name: string;
  platform: string;
  state: string;
  current_job: string | null;
  last_seen: string | null;
  firmware_version: string | null;
}

interface DeviceListResponse {
  devices: DeviceItem[];
  count: number;
  note?: string | null;
}

interface DeviceStatsResponse {
  total: number;
  by_state: Record<string, number>;
  note?: string | null;
}

interface DeviceEventItem {
  id: number;
  device_id: string;
  event_type: string;
  detail: string;
  created_at: string;
}

interface DeviceEventsResponse {
  device: DeviceItem;
  events: DeviceEventItem[];
  count: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Fetch an API v1 endpoint and unwrap the {ok, data?} envelope (flat or data-wrapped). */
async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = res.headers.get("content-type") || "";
  let body: unknown = null;
  if (contentType.includes("application/json")) {
    body = await res.json();
  } else {
    const text = await res.text();
    throw new Error(`Non-JSON response (${res.status}): ${text.slice(0, 200)}`);
  }
  const record = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  if (record.ok === false) {
    throw new Error(typeof record.error === "string" ? record.error : `API error (${res.status})`);
  }
  const payload = record.data !== undefined ? record.data : body;
  return payload as T;
}

function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function formatDate(dateStr?: string | null): string {
  if (!dateStr || dateStr === "-") return "-";
  try {
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return dateStr;
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

const STATE_META: Record<string, { label: string; color: string }> = {
  online: { label: "ONLINE", color: "#10b981" },
  busy: { label: "BUSY", color: "#1677ff" },
  offline: { label: "OFFLINE", color: "#64748b" },
  fault: { label: "FAULT", color: "#ff4d4f" },
  unknown: { label: "UNKNOWN", color: "#faad14" },
};

function stateMeta(state: string): { label: string; color: string } {
  return STATE_META[state] || { label: state || "UNKNOWN", color: "#faad14" };
}

const EVENT_LABELS: Record<string, string> = {
  registered: "注册",
  removed: "移除",
  online: "上线",
  offline: "掉线",
  busy: "占用",
  released: "释放",
  fault: "故障",
  recovered: "恢复",
};

function eventLabel(type: string): string {
  return EVENT_LABELS[type] || type;
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

const NAV_LINKS: { href: string; label: string; icon: typeof LayoutDashboard }[] = [
  { href: "/dashboard", label: "座舱", icon: LayoutDashboard },
  { href: "/dashboard/pipeline", label: "流水线", icon: Workflow },
  { href: "/dashboard/devices", label: "设备", icon: Cpu },
  { href: "/dashboard/tests", label: "测试", icon: FlaskConical },
  { href: "/dashboard/logs", label: "日志", icon: ScrollText },
  { href: "/dashboard/roles", label: "角色", icon: ShieldCheck },
  { href: "/dashboard/requirements", label: "需求", icon: BookMarked },
];

function TopNav({ pathname }: { pathname: string }) {
  return (
    <nav
      className="sticky top-0 z-50 border-b border-[#1e293b]/60"
      style={{ background: "rgba(10,14,23,.85)", backdropFilter: "blur(12px)" }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14 gap-4">
          <Link href="/" className="text-lg font-black tracking-tight shrink-0">
            <span className="text-[#10b981]">yule</span>
            <span className="text-[#1677ff]">OSH</span>
          </Link>
          <div className="flex items-center gap-1 overflow-x-auto">
            {NAV_LINKS.map(({ href, label, icon: Icon }) => {
              const active = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap ${
                    active
                      ? "bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30"
                      : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
                  {label}
                </Link>
              );
            })}
          </div>
          <div className="shrink-0" />
        </div>
      </div>
    </nav>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function DevicesPage() {
  const pathname = usePathname();

  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [stats, setStats] = useState<DeviceStatsResponse | null>(null);
  const [listNote, setListNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [events, setEvents] = useState<Record<string, DeviceEventItem[]>>({});
  const [eventsLoading, setEventsLoading] = useState<Record<string, boolean>>({});
  const [eventsError, setEventsError] = useState<Record<string, string>>({});

  // device id currently running an acquire/release mutation
  const [actionId, setActionId] = useState<string | null>(null);

  // ── Load devices + stats ──────────────────────────────────────────────────
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [listRes, statsRes] = await Promise.all([
        apiFetch<DeviceListResponse>("/api/v1/device-ui/list"),
        apiFetch<DeviceStatsResponse>("/api/v1/device-ui/stats"),
      ]);
      setDevices(listRes.devices || []);
      setListNote(listRes.note ?? null);
      setStats(statsRes);
    } catch (err) {
      setError(errMessage(err));
      setDevices([]);
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // ── Expand card → fetch event timeline ───────────────────────────────────
  const toggleExpand = useCallback(
    async (deviceId: string) => {
      const isOpen = !!expanded[deviceId];
      setExpanded((prev) => ({ ...prev, [deviceId]: !isOpen }));

      if (!isOpen && events[deviceId] === undefined && !eventsLoading[deviceId]) {
        setEventsLoading((prev) => ({ ...prev, [deviceId]: true }));
        setEventsError((prev) => ({ ...prev, [deviceId]: "" }));
        try {
          const res = await apiFetch<DeviceEventsResponse>(
            `/api/v1/device-ui/${encodeURIComponent(deviceId)}/events`
          );
          setEvents((prev) => ({ ...prev, [deviceId]: res.events || [] }));
        } catch (err) {
          setEventsError((prev) => ({ ...prev, [deviceId]: errMessage(err) }));
          setEvents((prev) => ({ ...prev, [deviceId]: [] }));
        } finally {
          setEventsLoading((prev) => ({ ...prev, [deviceId]: false }));
        }
      }
    },
    [events, eventsLoading, expanded]
  );

  // ── Acquire / release ────────────────────────────────────────────────────
  const handleAcquire = useCallback(
    async (device: DeviceItem) => {
      if (actionId) return;
      setActionId(device.id);
      setError("");
      try {
        await apiFetch(`/api/v1/device-ui/${encodeURIComponent(device.id)}/acquire`, {
          method: "POST",
          body: JSON.stringify({ job_id: `manual-${Date.now()}` }),
        });
        await loadAll();
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setActionId(null);
      }
    },
    [actionId, loadAll]
  );

  const handleRelease = useCallback(
    async (device: DeviceItem) => {
      if (actionId) return;
      setActionId(device.id);
      setError("");
      try {
        await apiFetch(`/api/v1/device-ui/${encodeURIComponent(device.id)}/release`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        await loadAll();
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setActionId(null);
      }
    },
    [actionId, loadAll]
  );

  const isEmpty = !loading && devices.length === 0;

  const statOrder: { key: string; label: string }[] = [
    { key: "online", label: "在线" },
    { key: "busy", label: "占用" },
    { key: "offline", label: "离线" },
    { key: "fault", label: "故障" },
    { key: "unknown", label: "未知" },
  ];

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <TopNav pathname={pathname} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <Cpu className="w-4.5 h-4.5 text-[#722ed1]" />
              设备管理
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              HIL 板卡池状态与手动分配/释放（点击卡片展开事件时间线）
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadAll()}
            disabled={loading}
            className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>

        {/* Data note */}
        {listNote && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{listNote}</span>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="mb-4 rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-4 py-2 text-xs text-[#ff4d4f] flex items-center justify-between">
            <span className="flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {error}
            </span>
            <button onClick={() => setError("")} className="ml-2 hover:text-white text-sm">
              &times;
            </button>
          </div>
        )}

        {/* ── Stats row ── */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          <div className="rounded-xl border border-[#1e293b] bg-[#111827] px-4 py-3">
            <div className="text-[11px] text-[#64748b] flex items-center gap-1">
              <Gauge className="w-3 h-3" />
              总设备
            </div>
            <div className="text-xl font-bold text-[#e2e8f0] mt-1">{stats?.total ?? "-"}</div>
          </div>
          {statOrder.map(({ key, label }) => {
            const meta = stateMeta(key);
            const count = stats?.by_state?.[key] ?? 0;
            return (
              <div key={key} className="rounded-xl border border-[#1e293b] bg-[#111827] px-4 py-3">
                <div className="text-[11px] text-[#64748b] flex items-center gap-1">
                  <span
                    className="inline-block w-2 h-2 rounded-full shrink-0"
                    style={{ background: meta.color }}
                  />
                  {label}
                </div>
                <div className="text-xl font-bold mt-1" style={{ color: meta.color }}>
                  {count}
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Device cards grid ── */}
        {loading ? (
          <div className="flex items-center justify-center py-16 text-[#64748b]">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            加载中…
          </div>
        ) : isEmpty ? (
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardContent className="py-16 text-center text-[#64748b] text-sm">
              <div className="text-2xl mb-2">🔌</div>
              暂无设备
              <div className="text-xs mt-1 text-[#475569]">设备注册后自动出现在这里</div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {devices.map((dev) => {
              const meta = stateMeta(dev.state);
              const isOpen = !!expanded[dev.id];
              const devEvents = events[dev.id];
              const evLoading = !!eventsLoading[dev.id];
              const evErr = eventsError[dev.id] || "";
              const isBusy = dev.state === "busy";
              const canAcquire = !isBusy && dev.state !== "fault" && dev.state !== "offline";
              const acting = actionId === dev.id;
              return (
                <Card key={dev.id} className="border-[#1e293b] bg-[#111827]">
                  {/* Clickable header */}
                  <div
                    onClick={() => void toggleExpand(dev.id)}
                    className="cursor-pointer transition-all hover:bg-[#1e293b]/40 rounded-t-xl"
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-center gap-2">
                        <Cpu className="w-4 h-4 text-[#722ed1] shrink-0" />
                        <CardTitle className="text-sm font-bold text-[#e2e8f0] truncate flex-1">
                          {dev.name}
                        </CardTitle>
                        {isOpen ? (
                          <ChevronDown className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                        )}
                      </div>
                      <CardDescription className="text-xs text-[#94a3b8] flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className="border-transparent"
                          style={{
                            color: meta.color,
                            background: `${meta.color}1f`,
                            borderColor: `${meta.color}4d`,
                          }}
                        >
                          {meta.label}
                        </Badge>
                        <span className="truncate">{dev.platform || "未知平台"}</span>
                      </CardDescription>
                    </CardHeader>
                  </div>

                  <CardContent className="space-y-2">
                    <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                      <Activity className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                      <span className="text-[#64748b] shrink-0">当前 job</span>
                      <span className="truncate">
                        {dev.current_job || <span className="text-[#475569]">—</span>}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                      <Clock className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                      <span className="text-[#64748b] shrink-0">最后心跳</span>
                      <span className="truncate">{formatDate(dev.last_seen)}</span>
                    </div>
                    {dev.firmware_version && (
                      <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                        <Zap className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                        <span className="text-[#64748b] shrink-0">固件</span>
                        <span className="truncate">{dev.firmware_version}</span>
                      </div>
                    )}

                    {/* Acquire / release */}
                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!canAcquire || acting}
                        onClick={() => void handleAcquire(dev)}
                        className="border-[#1e293b] text-[#10b981] hover:text-[#10b981] hover:border-[#10b981]/40 flex-1"
                      >
                        {acting ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Play className="w-3.5 h-3.5" />
                        )}
                        获取
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!isBusy || acting}
                        onClick={() => void handleRelease(dev)}
                        className="border-[#1e293b] text-[#ff4d4f] hover:text-[#ff4d4f] hover:border-[#ff4d4f]/40 flex-1"
                      >
                        {acting ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Square className="w-3.5 h-3.5" />
                        )}
                        释放
                      </Button>
                    </div>

                    {/* Expanded: event timeline */}
                    {isOpen && (
                      <div className="pt-2 border-t border-[#1e293b]">
                        <div className="text-[11px] text-[#64748b] flex items-center gap-1 mb-2">
                          <History className="w-3 h-3" />
                          事件时间线
                        </div>
                        {evLoading ? (
                          <div className="flex items-center gap-2 py-2 text-xs text-[#94a3b8]">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            加载事件…
                          </div>
                        ) : evErr ? (
                          <div className="py-2 text-xs text-[#ff4d4f] flex items-center gap-1">
                            <AlertCircle className="w-3.5 h-3.5" />
                            {evErr}
                          </div>
                        ) : devEvents && devEvents.length === 0 ? (
                          <div className="py-2 text-xs text-[#64748b]">暂无事件记录</div>
                        ) : devEvents ? (
                          <div className="max-h-56 overflow-y-auto pr-1 space-y-2">
                            {devEvents.map((ev) => {
                              const evColor =
                                ev.event_type === "fault"
                                  ? "#ff4d4f"
                                  : ev.event_type === "offline"
                                    ? "#64748b"
                                    : ev.event_type === "busy"
                                      ? "#1677ff"
                                      : "#10b981";
                              return (
                                <div key={ev.id} className="flex gap-2 text-xs">
                                  <span
                                    className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0"
                                    style={{ background: evColor }}
                                  />
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="text-[#e2e8f0] font-medium">
                                        {eventLabel(ev.event_type)}
                                      </span>
                                      <span className="text-[10px] text-[#475569] shrink-0">
                                        {formatDate(ev.created_at)}
                                      </span>
                                    </div>
                                    <div className="text-[11px] text-[#94a3b8] break-words mt-0.5">
                                      {ev.detail || "—"}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

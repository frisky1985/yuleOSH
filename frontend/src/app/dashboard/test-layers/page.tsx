"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Cpu,
  FlaskConical,
  Info,
  Layers,
  Loader2,
  RefreshCw,
} from "lucide-react";
// 导航（顶栏/左栏）由 dashboard/layout 统一渲染，页面只提供内容
import { Badge } from "@/components/ui/badge";

// ─── Types ───────────────────────────────────────────────────────────────────

/** GET /api/v1/tests/layers — one entry per test layer (unit→integration→hil→qualification). */
interface LayerItem {
  key: string;
  label: string;
  subtitle: string;
  badge: string;
  in_steps: boolean;
  status: string;
  passed?: number;
  failed?: number;
  skipped?: number;
  mock_mode?: boolean | null;
  commit?: string | null;
  timestamp?: string | null;
  source: string;
  updated_at: string;
  note?: string | null;
}

interface LayersResponse {
  project: string;
  order: string[];
  layers: LayerItem[];
  note?: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Fetch an API v1 endpoint and unwrap the {ok, data?} envelope. */
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

function statusMeta(status: string): { label: string; color: string } {
  const s = (status || "").toLowerCase();
  if (["passed", "pass", "success", "ok", "succeeded"].includes(s)) {
    return { label: "pass", color: "#10b981" };
  }
  if (["failed", "fail", "error", "errored"].includes(s)) {
    return { label: "fail", color: "#ff4d4f" };
  }
  if (["skipped", "skip", "skipped_by_user"].includes(s)) {
    return { label: "skip", color: "#faad14" };
  }
  if (["mock"].includes(s)) {
    return { label: "mock", color: "#faad14" };
  }
  return { label: status || "unknown", color: "#64748b" };
}

/** HIL shows MOCK when running in mock mode, otherwise its real pass/fail status. */
function layerBadge(item: LayerItem): { label: string; color: string } {
  if (item.key === "hil" && item.mock_mode === true) {
    return { label: "mock", color: "#faad14" };
  }
  return statusMeta(item.status);
}

function formatDate(dateStr?: string): string {
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

// ─── Page ────────────────────────────────────────────────────────────────────

export default function TestLayersPage() {
  const [layers, setLayers] = useState<LayerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<LayersResponse>("/api/v1/tests/layers");
      setLayers(res.layers || []);
      setNote(res.note ?? null);
    } catch (err) {
      setError(errMessage(err));
      setLayers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
  <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <Layers className="w-4.5 h-4.5 text-[#722ed1]" />
              测试分层视图 · Test Layers
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              四层递进验证（数据来自 .osh/sessions 与 .osh/ci 真实产物）
            </p>
          </div>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40 rounded-lg px-3 py-1.5 text-xs font-medium transition-all flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>

        {/* Data note */}
        {note && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{note}</span>
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

        {/* Pipeline order bar */}
        {layers.length > 0 && (
          <div className="flex items-center gap-2 mb-6 flex-wrap">
            {layers.map((l, i) => (
              <Fragment key={l.key}>
                <span
                  className={`px-2.5 py-1 rounded-lg border text-xs ${
                    l.key === "hil"
                      ? "border-[#854f0b] text-[#854f0b] bg-[#1a1407]"
                      : "border-[#1e293b] text-[#94a3b8]"
                  }`}
                >
                  <span className="font-mono font-medium mr-1">{l.badge}</span>
                  {l.label}
                </span>
                {i < layers.length - 1 && (
                  <span className="text-[#475569] text-sm">→</span>
                )}
              </Fragment>
            ))}
          </div>
        )}

        {/* Layer cards */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-[#64748b]">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            加载中…
          </div>
        ) : layers.length === 0 ? (
          <div className="py-20 text-center text-[#64748b] text-sm">
            <Layers className="w-6 h-6 mx-auto mb-2 opacity-50" />
            暂无数据
          </div>
        ) : (
          <div className="space-y-3">
            {layers.map((item) => {
              const isHil = item.key === "hil";
              const meta = layerBadge(item);
              return (
                <div
                  key={item.key}
                  className={`rounded-xl border bg-[#111827] px-4 py-3 ${
                    isHil ? "border-[#854f0b] bg-[#1a1407]" : "border-[#1e293b]"
                  }`}
                >
                  <div className="flex items-center gap-4">
                    {/* Layer badge */}
                    <div
                      className={`flex-0-0-auto w-14 text-center rounded-lg py-2 ${
                        isHil ? "bg-[#854f0b]/15" : "bg-[#0a0e17]"
                      }`}
                    >
                      <div
                        className={`text-sm font-bold font-mono ${
                          isHil ? "text-[#854f0b]" : "text-[#94a3b8]"
                        }`}
                      >
                        {item.badge}
                      </div>
                    </div>

                    {/* Name + meta */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#e2e8f0]">
                          {item.label}
                        </span>
                        <span className="text-[10px] text-[#475569]">{item.subtitle}</span>
                        {isHil && (
                          <span className="text-[10px] text-[#854f0b] border border-[#854f0b]/40 rounded px-1.5 py-0.5">
                            Hardware-in-the-Loop
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-[#64748b] font-mono mt-1 truncate">
                        {item.source}
                        {item.updated_at ? ` · ${formatDate(item.updated_at)}` : ""}
                      </div>
                    </div>

                    {/* Status / counts */}
                    {isHil ? (
                      <div className="flex flex-col items-end gap-1 shrink-0">
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
                        {item.commit && (
                          <span className="text-[10px] text-[#64748b] font-mono">
                            commit {item.commit}
                          </span>
                        )}
                        <span className="text-[10px] text-[#854f0b]">
                          {item.mock_mode ? "Mock 模式" : "真实硬件"}
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3 shrink-0">
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
                        <div className="flex gap-2 text-[11px] tabular-nums">
                          <span className="text-[#10b981]">通过 {item.passed ?? 0}</span>
                          <span className="text-[#ff4d4f]">失败 {item.failed ?? 0}</span>
                          <span className="text-[#faad14]">跳过 {item.skipped ?? 0}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* HIL-only footnote */}
                  {isHil && (
                    <div className="mt-3 text-[10px] text-[#854f0b] flex items-center gap-1.5 border-t border-[#854f0b]/20 pt-2">
                      <Info className="w-3 h-3 shrink-0" />
                      <span>
                        独立 CI Layer 2.5，不出现在 .osh/cache/steps 步骤清单内；真实硬件需在
                        self-hosted runner 直连执行。
                      </span>
                    </div>
                  )}

                  {/* Absent-layer note */}
                  {!isHil && item.note && (
                    <div className="mt-2 text-[10px] text-[#475569] flex items-center gap-1.5">
                      <Info className="w-3 h-3 shrink-0" />
                      <span>{item.note}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Legend */}
        <div className="mt-6 flex items-center gap-4 text-[11px] text-[#64748b]">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" /> pass
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#ff4d4f]" /> fail
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#faad14]" /> skip / mock
          </span>
          <span className="flex items-center gap-1.5">
            <Cpu className="w-3 h-3 text-[#854f0b]" /> HIL 独立层级
          </span>
        </div>
      </div>
  </div>
  );
}

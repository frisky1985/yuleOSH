"use client";

import { apiFetch } from "@/lib/api-fetch";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BarChart3,
  BookMarked,
  ChevronDown,
  ChevronRight,
  Cpu,
  FileText,
  FlaskConical,
  Info,
  LayoutDashboard,
  Loader2,
  RefreshCw,
  ScrollText,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react";
// 导航（顶栏/左栏）由 dashboard/layout 统一渲染，页面只提供内容

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

// ─── Types ───────────────────────────────────────────────────────────────────

interface LogEntry {
  run_id: string;
  file: string;
  line: number;
  content: string;
  level: string;
  updated_at?: string | null;
}

interface LogsListResponse {
  logs: LogEntry[];
  count: number;
  note?: string | null;
}

interface RunSummary {
  run_id: string;
  name?: string | null;
  project?: string | null;
  status?: string | null;
  log_files: number;
  total_lines: number;
  error_count: number;
  updated_at?: string | null;
}

interface LogsSummaryResponse {
  runs: RunSummary[];
  count: number;
  note?: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────


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

function levelMeta(level: string): { label: string; color: string } {
  const l = (level || "INFO").toUpperCase();
  if (l === "ERROR" || l === "FATAL") return { label: l, color: "#ff4d4f" };
  if (l === "WARN" || l === "WARNING") return { label: "WARN", color: "#faad14" };
  if (l === "DEBUG" || l === "TRACE") return { label: l, color: "#64748b" };
  return { label: l || "INFO", color: "#1677ff" };
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

// Navigation is rendered by the shared TopNav component
// (see src/components/dashboard/top-nav.tsx).

// ─── Page ────────────────────────────────────────────────────────────────────

interface LogFilters {
  query: string;
  device: string;
  pipeline: string;
  limit: string;
}

const DEFAULT_FILTERS: LogFilters = { query: "", device: "", pipeline: "", limit: "50" };

export default function LogsPage() {

  // ── Filter inputs (applied on submit) ────────────────────────────────────
  const [query, setQuery] = useState("");
  const [device, setDevice] = useState("");
  const [pipeline, setPipeline] = useState("");
  const [limit, setLimit] = useState(DEFAULT_FILTERS.limit);

  // ── Applied filters (drives the fetch) ───────────────────────────────────
  const [filters, setFilters] = useState<LogFilters>(DEFAULT_FILTERS);

  // ── Log list state ───────────────────────────────────────────────────────
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [listNote, setListNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // ── Summary state ────────────────────────────────────────────────────────
  const [summary, setSummary] = useState<RunSummary[]>([]);
  const [summaryNote, setSummaryNote] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState("");

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // ── Load log search results ──────────────────────────────────────────────
  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (filters.query.trim()) params.set("query", filters.query.trim());
      if (filters.device.trim()) params.set("device", filters.device.trim());
      if (filters.pipeline.trim()) params.set("pipeline", filters.pipeline.trim());
      const lim = parseInt(filters.limit, 10);
      if (!Number.isNaN(lim) && lim > 0) params.set("limit", String(Math.min(lim, 500)));
      const qs = params.toString();
      const res = await apiFetch<LogsListResponse>(`/api/v1/logs${qs ? `?${qs}` : ""}`);
      setLogs(res.logs || []);
      setListNote(res.note ?? null);
    } catch (err) {
      setError(errMessage(err));
      setLogs([]);
      setListNote(null);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  // ── Load per-run summary ─────────────────────────────────────────────────
  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    setSummaryError("");
    try {
      const res = await apiFetch<LogsSummaryResponse>("/api/v1/logs/summary");
      setSummary(res.runs || []);
      setSummaryNote(res.note ?? null);
    } catch (err) {
      setSummaryError(errMessage(err));
      setSummary([]);
      setSummaryNote(null);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setExpanded({});
    setFilters({ query, device, pipeline, limit });
  };

  const handleReset = () => {
    setQuery(DEFAULT_FILTERS.query);
    setDevice(DEFAULT_FILTERS.device);
    setPipeline(DEFAULT_FILTERS.pipeline);
    setLimit(DEFAULT_FILTERS.limit);
    setExpanded({});
    setFilters(DEFAULT_FILTERS);
  };

  const handleRefresh = () => {
    setExpanded({});
    void loadLogs();
    void loadSummary();
  };

  const toggleExpand = (key: string) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const isEmpty = !loading && logs.length === 0 && !error;

  return (
  <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <ScrollText className="w-4.5 h-4.5 text-[#722ed1]" />
              测试日志管理
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              检索测试运行日志（按 run/设备/流水线/关键词过滤，点击条目展开全文）
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={loading || summaryLoading}
            className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading || summaryLoading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>

        {/* Search bar */}
        <Card className="border-[#1e293b] bg-[#111827] mb-4">
          <CardContent className="pt-4 pb-4">
            <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs text-[#94a3b8] mb-1.5">关键词</label>
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索日志内容，如 error / boot / device id…"
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#475569]"
                />
              </div>
              <div className="w-44">
                <label className="block text-xs text-[#94a3b8] mb-1.5">设备</label>
                <Input
                  value={device}
                  onChange={(e) => setDevice(e.target.value)}
                  placeholder="设备 ID / 名称"
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#475569]"
                />
              </div>
              <div className="w-44">
                <label className="block text-xs text-[#94a3b8] mb-1.5">流水线 / Run</label>
                <Input
                  value={pipeline}
                  onChange={(e) => setPipeline(e.target.value)}
                  placeholder="run_id 或流水线名"
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#475569]"
                />
              </div>
              <div className="w-28">
                <label className="block text-xs text-[#94a3b8] mb-1.5">limit</label>
                <Input
                  type="number"
                  min={1}
                  max={500}
                  value={limit}
                  onChange={(e) => setLimit(e.target.value)}
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#475569]"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  type="submit"
                  size="sm"
                  disabled={loading}
                  className="bg-[#722ed1] hover:bg-[#5b21b6] text-white"
                >
                  <Search className="w-3.5 h-3.5" />
                  搜索
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleReset}
                  className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
                >
                  重置
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

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

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
          {/* ── Left: log list ── */}
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[#722ed1]" />
                  日志检索结果
                  {!loading && (
                    <span className="text-xs font-normal text-[#64748b]">共 {logs.length} 条</span>
                  )}
                </CardTitle>
              </div>
              <CardDescription className="text-xs text-[#64748b]">
                真实日志数据（扫描 .osh/sessions 下的 *.log），点击条目展开查看全文
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              {loading ? (
                <div className="flex items-center justify-center py-14 text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  加载中…
                </div>
              ) : isEmpty ? (
                <div className="py-14 text-center text-[#64748b] text-sm">
                  <div className="text-2xl mb-2">📄</div>
                  暂无日志
                  <div className="text-xs mt-1 text-[#475569]">
                    {listNote || "未找到匹配的日志记录"}
                  </div>
                </div>
              ) : (
                <div>
                  {/* Table header */}
                  <div className="grid grid-cols-[1fr_auto] gap-3 px-4 py-2 text-xs text-[#64748b] border-b border-[#1e293b]">
                    <span>日志内容</span>
                    <span className="w-36 text-right">时间</span>
                  </div>

                  {logs.map((log) => {
                    const key = `${log.run_id}\u0000${log.file}\u0000${log.line}`;
                    const isOpen = !!expanded[key];
                    const meta = levelMeta(log.level);
                    const preview =
                      log.content.length > 200 ? `${log.content.slice(0, 200)}…` : log.content;
                    return (
                      <div key={key} className="border-b border-[#1e293b] last:border-b-0">
                        {/* Row */}
                        <div
                          onClick={() => toggleExpand(key)}
                          className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3 items-center cursor-pointer transition-all hover:bg-[#1e293b]/50"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              {isOpen ? (
                                <ChevronDown className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                              ) : (
                                <ChevronRight className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                              )}
                              <Badge
                                variant="outline"
                                className="border-transparent shrink-0"
                                style={{
                                  color: meta.color,
                                  background: `${meta.color}1f`,
                                  borderColor: `${meta.color}4d`,
                                }}
                              >
                                {meta.label}
                              </Badge>
                              <span className="font-mono text-[10px] text-[#a78bfa] bg-[#722ed1]/10 border border-[#722ed1]/20 rounded px-1.5 py-0.5 shrink-0">
                                {log.run_id}
                              </span>
                              <span className="text-xs text-[#e2e8f0] font-medium truncate">
                                {log.file}
                              </span>
                              <span className="text-[10px] text-[#64748b] shrink-0">
                                :{log.line}
                              </span>
                            </div>
                            <div className="mt-1 pl-5 text-xs text-[#94a3b8] truncate">
                              {preview}
                            </div>
                          </div>
                          <div className="w-36 text-right text-xs text-[#64748b] shrink-0">
                            {formatDate(log.updated_at)}
                          </div>
                        </div>

                        {/* Expanded: full content */}
                        {isOpen && (
                          <div className="px-4 pb-4 pl-10">
                            <pre className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3 text-xs text-[#cbd5e1] whitespace-pre-wrap break-words leading-relaxed">
                              {log.content}
                            </pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── Right: per-run summary ── */}
          <Card className="border-[#1e293b] bg-[#111827] lg:sticky lg:top-20">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-[#722ed1]" />
                日志摘要
                {!summaryLoading && (
                  <span className="text-xs font-normal text-[#64748b]">
                    共 {summary.length} 个 run
                  </span>
                )}
              </CardTitle>
              <CardDescription className="text-xs text-[#64748b]">
                每个 run 的日志文件数 / 总行数 / ERROR 数
              </CardDescription>
            </CardHeader>
            <CardContent>
              {summaryError && (
                <div className="rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-3 py-2 text-xs text-[#ff4d4f] mb-3 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  {summaryError}
                </div>
              )}

              {summaryLoading ? (
                <div className="flex items-center justify-center py-12 text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  加载中…
                </div>
              ) : summary.length === 0 ? (
                <div className="py-12 text-center text-[#64748b] text-sm">
                  <div className="text-2xl mb-2">📊</div>
                  暂无日志
                  <div className="text-xs mt-1 text-[#475569]">
                    {summaryNote || "未发现 session 日志"}
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {summary.map((run) => (
                    <div
                      key={run.run_id}
                      className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-3"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-mono text-[10px] text-[#a78bfa] bg-[#722ed1]/10 border border-[#722ed1]/20 rounded px-1.5 py-0.5 truncate">
                          {run.run_id}
                        </span>
                        {run.name && (
                          <span className="text-xs text-[#e2e8f0] font-medium truncate">
                            {run.name}
                          </span>
                        )}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="rounded-md border border-[#1e293b] py-1.5">
                          <div className="text-sm font-bold text-[#e2e8f0]">{run.log_files}</div>
                          <div className="text-[10px] text-[#64748b]">日志文件</div>
                        </div>
                        <div className="rounded-md border border-[#1e293b] py-1.5">
                          <div className="text-sm font-bold text-[#e2e8f0]">{run.total_lines}</div>
                          <div className="text-[10px] text-[#64748b]">总行数</div>
                        </div>
                        <div
                          className="rounded-md border py-1.5"
                          style={{
                            borderColor: run.error_count > 0 ? "#ff4d4f4d" : "#1e293b",
                            background: run.error_count > 0 ? "#ff4d4f1f" : "transparent",
                          }}
                        >
                          <div
                            className="text-sm font-bold"
                            style={{ color: run.error_count > 0 ? "#ff4d4f" : "#e2e8f0" }}
                          >
                            {run.error_count}
                          </div>
                          <div className="text-[10px] text-[#64748b]">ERROR</div>
                        </div>
                      </div>
                      {run.updated_at && (
                        <div className="mt-2 text-[10px] text-[#475569] text-right">
                          更新于 {formatDate(run.updated_at)}
                        </div>
                      )}
                    </div>
                  ))}

                  {summaryNote && (
                    <div className="flex items-center gap-1.5 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-3 py-2 text-[11px] text-[#faad14]">
                      <Info className="w-3.5 h-3.5 shrink-0" />
                      {summaryNote}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
  </div>
  );
}

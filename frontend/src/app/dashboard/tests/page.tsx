"use client";

import { apiFetch } from "@/lib/api-fetch";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookMarked,
  Cpu,
  FlaskConical,
  History,
  Info,
  LayoutDashboard,
  Layers,
  ListChecks,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Target,
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

// ─── Types ───────────────────────────────────────────────────────────────────

type TestLayer = "unit" | "integration" | "qualification";

/** GET /api/v1/tests/runs — one entry per test artifact found (newest first). */
interface TestRunItem {
  run_id: string;
  layer: string;
  passed: number;
  failed: number;
  skipped: number;
  duration: number;
  status: string;
  updated_at: string;
}

interface TestRunsResponse {
  project: string;
  runs: TestRunItem[];
  count: number;
  note?: string | null;
}

/** GET /api/v1/tests?layer=xxx — run records carrying flattened case names. */
interface TestCaseRun extends TestRunItem {
  name: string;
  total: number;
  cases: string[];
}

interface TestCasesResponse {
  project: string;
  layer: string;
  runs: TestCaseRun[];
  summary: { passed: number; failed: number; skipped: number; total_cases: number };
  note?: string | null;
}

/** GET /api/v1/tests/coverage — latest coverage summary (null when absent). */
interface CoverageData {
  source: string;
  run_id: string | null;
  line_rate: number;
  branch_rate: number;
}

interface CoverageResponse {
  project: string;
  coverage: CoverageData | null;
  note?: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────


function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
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
  return { label: status || "unknown", color: "#64748b" };
}

const LAYER_TABS: { key: TestLayer; label: string; desc: string }[] = [
  { key: "unit", label: "单元测试", desc: "unit" },
  { key: "integration", label: "集成测试", desc: "integration" },
  { key: "qualification", label: "合格性测试", desc: "qualification" },
];

function layerLabel(layer: string): string {
  return LAYER_TABS.find((t) => t.key === layer)?.label || layer;
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

// Navigation is rendered by the shared TopNav component
// (see src/components/dashboard/top-nav.tsx).

// ─── Sub-components ──────────────────────────────────────────────────────────

function RateBar({ label, value, color }: { label: string; value: number; color: string }) {
  const v = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1.5">
        <span className="text-[#94a3b8]">{label}</span>
        <span className="text-[#e2e8f0] font-medium tabular-nums">{v.toFixed(1)}%</span>
      </div>
      <div className="h-2 rounded-full bg-[#1e293b] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${v}%`, background: color }}
        />
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function TestsPage() {

  const [activeLayer, setActiveLayer] = useState<TestLayer>("unit");

  // runs (history + per-layer latest summary) and coverage are fetched once
  const [runs, setRuns] = useState<TestRunItem[]>([]);
  const [coverage, setCoverage] = useState<CoverageData | null>(null);
  const [runsNote, setRunsNote] = useState<string | null>(null);
  const [coverageNote, setCoverageNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // case list refetches on every layer tab switch
  const [caseRuns, setCaseRuns] = useState<TestCaseRun[]>([]);
  const [casesNote, setCasesNote] = useState<string | null>(null);
  const [casesLoading, setCasesLoading] = useState(true);
  const [casesError, setCasesError] = useState("");

  // ── Load runs (execution history) + coverage ─────────────────────────────
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [runsRes, covRes] = await Promise.all([
        apiFetch<TestRunsResponse>("/api/v1/tests/runs"),
        apiFetch<CoverageResponse>("/api/v1/tests/coverage"),
      ]);
      setRuns(runsRes.runs || []);
      setRunsNote(runsRes.note ?? null);
      setCoverage(covRes.coverage ?? null);
      setCoverageNote(covRes.note ?? null);
    } catch (err) {
      setError(errMessage(err));
      setRuns([]);
      setCoverage(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Load test cases for the active layer ─────────────────────────────────
  const loadCases = useCallback(async (layer: TestLayer) => {
    setCasesLoading(true);
    setCasesError("");
    try {
      const res = await apiFetch<TestCasesResponse>(
        `/api/v1/tests?layer=${encodeURIComponent(layer)}`
      );
      setCaseRuns(res.runs || []);
      setCasesNote(res.note ?? null);
    } catch (err) {
      setCasesError(errMessage(err));
      setCaseRuns([]);
    } finally {
      setCasesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // refetch the case list whenever the layer tab changes
  useEffect(() => {
    void loadCases(activeLayer);
  }, [activeLayer, loadCases]);

  const handleRefresh = useCallback(() => {
    void loadAll();
    void loadCases(activeLayer);
  }, [loadAll, loadCases, activeLayer]);

  // ── Derived data ──────────────────────────────────────────────────────────
  // runs arrive newest-first, so the first entry per layer is its latest run
  const latestByLayer = useMemo(() => {
    const map: Record<string, TestRunItem | undefined> = {};
    for (const r of runs) {
      if (map[r.layer] === undefined) map[r.layer] = r;
    }
    return map;
  }, [runs]);

  // flatten per-run case names into table rows (status inherited from the run)
  const caseRows = useMemo(() => {
    const rows: { name: string; status: string; runId: string }[] = [];
    for (const r of caseRuns) {
      for (const name of r.cases || []) {
        rows.push({ name, status: r.status, runId: r.run_id });
      }
    }
    return rows;
  }, [caseRuns]);

  const historyRows = runs.slice(0, 10);
  const isEmptyRuns = !loading && runs.length === 0;
  const isEmptyCases = !casesLoading && caseRuns.length === 0;

  return (
  <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <FlaskConical className="w-4.5 h-4.5 text-[#722ed1]" />
              测试用例管理
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              三层测试统计、用例明细与覆盖率（数据来自 .osh/sessions 测试产物）
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleRefresh()}
            disabled={loading || casesLoading}
            className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>

        {/* Data note */}
        {runsNote && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{runsNote}</span>
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

        {/* ── Layer stats (latest run per layer) ── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
          {LAYER_TABS.map(({ key, label, desc }) => {
            const latest = latestByLayer[key];
            return (
              <div
                key={key}
                className="rounded-xl border border-[#1e293b] bg-[#111827] px-4 py-3"
              >
                <div className="flex items-center gap-2 mb-3">
                  <Layers className="w-3.5 h-3.5 text-[#722ed1]" />
                  <span className="text-xs font-medium text-[#e2e8f0]">{label}</span>
                  <span className="text-[10px] text-[#475569]">{desc}</span>
                  {latest && (
                    <span className="ml-auto text-[10px] text-[#475569] border border-[#1e293b] rounded px-1.5 py-0.5">
                      最新
                    </span>
                  )}
                </div>
                {latest ? (
                  <div className="grid grid-cols-3 gap-2">
                    <div className="text-center rounded-lg bg-[#0a0e17]/60 py-2">
                      <div className="text-[10px] text-[#94a3b8]">通过</div>
                      <div className="text-lg font-bold text-[#10b981] tabular-nums">
                        {latest.passed}
                      </div>
                    </div>
                    <div className="text-center rounded-lg bg-[#0a0e17]/60 py-2">
                      <div className="text-[10px] text-[#94a3b8]">失败</div>
                      <div className="text-lg font-bold text-[#ff4d4f] tabular-nums">
                        {latest.failed}
                      </div>
                    </div>
                    <div className="text-center rounded-lg bg-[#0a0e17]/60 py-2">
                      <div className="text-[10px] text-[#94a3b8]">跳过</div>
                      <div className="text-lg font-bold text-[#faad14] tabular-nums">
                        {latest.skipped}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-4 text-center text-xs text-[#64748b]">暂无数据</div>
                )}
              </div>
            );
          })}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6 items-start mb-6">
          {/* ── Test case list ── */}
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-[#722ed1]" />
                  用例列表
                  {!casesLoading && (
                    <span className="text-xs font-normal text-[#64748b]">
                      {layerLabel(activeLayer)} · 共 {caseRows.length} 条
                    </span>
                  )}
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent className="px-0">
              {/* Layer tabs */}
              <div className="flex items-center gap-1 px-4 pb-3 border-b border-[#1e293b]">
                {LAYER_TABS.map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setActiveLayer(key)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all border ${
                      activeLayer === key
                        ? "bg-[#722ed1]/15 text-[#722ed1] border-[#722ed1]/30"
                        : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b] border-transparent"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {casesLoading ? (
                <div className="flex items-center justify-center py-14 text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  加载中…
                </div>
              ) : casesError ? (
                <div className="py-14 text-center text-[#ff4d4f] text-sm flex items-center justify-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" />
                  {casesError}
                </div>
              ) : isEmptyCases ? (
                <div className="py-14 text-center text-[#64748b] text-sm">
                  <div className="text-2xl mb-2">🧪</div>
                  暂无数据
                  {casesNote && (
                    <div className="text-xs mt-1 text-[#475569]">{casesNote}</div>
                  )}
                </div>
              ) : caseRows.length === 0 ? (
                <div className="py-14 text-center text-[#64748b] text-sm">
                  该层有执行记录，但无用例明细（cases 为空）
                </div>
              ) : (
                <div>
                  {/* Table header */}
                  <div className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-2 text-xs text-[#64748b] border-b border-[#1e293b]">
                    <span>用例名</span>
                    <span className="w-20">状态</span>
                    <span className="w-32 text-right">所属 Run</span>
                  </div>
                  <div className="divide-y divide-[#1e293b]/60">
                    {caseRows.map((row, i) => {
                      const meta = statusMeta(row.status);
                      return (
                        <div
                          key={`${row.runId}-${row.name}-${i}`}
                          className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-2.5 items-center"
                        >
                          <span className="text-sm text-[#e2e8f0] truncate">{row.name}</span>
                          <div className="w-20">
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
                          </div>
                          <span className="w-32 text-right text-[10px] text-[#64748b] truncate">
                            {row.runId}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── Coverage ── */}
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <Target className="w-4 h-4 text-[#722ed1]" />
                覆盖率
              </CardTitle>
              {coverage && (
                <CardDescription className="text-xs text-[#64748b] truncate">
                  {coverage.source}
                  {coverage.run_id ? ` · ${coverage.run_id}` : ""}
                </CardDescription>
              )}
            </CardHeader>
            <CardContent>
              {coverage ? (
                <div className="space-y-4">
                  <RateBar
                    label="行覆盖率 line_rate"
                    value={coverage.line_rate}
                    color="#722ed1"
                  />
                  <RateBar
                    label="分支覆盖率 branch_rate"
                    value={coverage.branch_rate}
                    color="#10b981"
                  />
                </div>
              ) : (
                <div className="py-10 text-center text-[#64748b] text-sm">
                  <div className="text-2xl mb-2">🎯</div>
                  暂无数据
                  {coverageNote && (
                    <div className="text-xs mt-1 text-[#475569]">{coverageNote}</div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Run history (recent 10) ── */}
        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <History className="w-4 h-4 text-[#722ed1]" />
                执行历史
                {!loading && (
                  <span className="text-xs font-normal text-[#64748b]">
                    最近 {historyRows.length} 次
                  </span>
                )}
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            {loading ? (
              <div className="flex items-center justify-center py-14 text-[#64748b]">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                加载中…
              </div>
            ) : isEmptyRuns ? (
              <div className="py-14 text-center text-[#64748b] text-sm">
                <div className="text-2xl mb-2">📜</div>
                暂无数据
                {runsNote && <div className="text-xs mt-1 text-[#475569]">{runsNote}</div>}
              </div>
            ) : (
              <div>
                {/* Table header */}
                <div className="grid grid-cols-[1.2fr_1fr_0.6fr_0.6fr_0.6fr_0.7fr_1.2fr] gap-3 px-4 py-2 text-xs text-[#64748b] border-b border-[#1e293b]">
                  <span>Run ID</span>
                  <span>层级</span>
                  <span className="text-right">通过</span>
                  <span className="text-right">失败</span>
                  <span className="text-right">跳过</span>
                  <span>状态</span>
                  <span className="text-right">时间</span>
                </div>
                <div className="divide-y divide-[#1e293b]/60">
                  {historyRows.map((r) => {
                    const meta = statusMeta(r.status);
                    return (
                      <div
                        key={`${r.run_id}-${r.layer}`}
                        className="grid grid-cols-[1.2fr_1fr_0.6fr_0.6fr_0.6fr_0.7fr_1.2fr] gap-3 px-4 py-2.5 items-center text-xs"
                      >
                        <span className="text-[#94a3b8] truncate font-mono">{r.run_id}</span>
                        <span className="text-[#e2e8f0]">{layerLabel(r.layer)}</span>
                        <span className="text-right text-[#10b981] tabular-nums">{r.passed}</span>
                        <span className="text-right text-[#ff4d4f] tabular-nums">{r.failed}</span>
                        <span className="text-right text-[#faad14] tabular-nums">{r.skipped}</span>
                        <span>
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
                        </span>
                        <span className="text-right text-[#64748b]">
                          {formatDate(r.updated_at)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
  </div>
  );
}

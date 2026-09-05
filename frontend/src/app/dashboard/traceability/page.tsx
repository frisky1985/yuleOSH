"use client";

import { apiFetch } from "@/lib/api-fetch";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  FileCode,
  FlaskConical,
  FolderOpen,
  History,
  Info,
  ListChecks,
  Loader2,
  Network,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Square,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { usePersistentState } from "@/lib/sidebar-persistence";
import { useSidebarExtras } from "@/components/dashboard/engineer-sidebar";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Coverage {
  code: boolean;
  test: boolean;
  review: boolean;
  step: boolean;
  evidence: boolean;
}

interface MatrixRow {
  req_id: string;
  id: string | null;
  statement: string;
  section: string;
  coverage: Coverage;
  link_method?: string;
  code_files: string[];
  test_reports: Array<Record<string, unknown>>;
  step_handlers: unknown[];
  reviews: Array<Record<string, unknown>>;
  swr_mapping?: boolean;
}

interface MatrixSummary {
  total: number;
  with_code: number;
  with_test: number;
  with_review: number;
  with_step: number;
  with_evidence: number;
  test_coverage_pct: number;
  evidence_coverage_pct: number;
}

interface MatrixGapByType {
  no_code: number;
  no_test: number;
  no_review: number;
  no_step: number;
  no_evidence: number;
}

interface MatrixGapItem {
  req_id: string;
  missing: string[];
}

interface MatrixGaps {
  total_gaps: number;
  by_type: MatrixGapByType;
  items: MatrixGapItem[];
}

interface MatrixResponse {
  project: string;
  generated_at: string | null;
  requirements: MatrixRow[];
  summary: MatrixSummary;
  gaps: MatrixGaps;
  note?: string | null;
}

interface ProjectItem {
  id: number | string;
  name: string;
  slug?: string;
  description?: string;
}

interface ProjectsResponse {
  projects: ProjectItem[];
  count?: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DIM_META: { key: keyof Coverage; label: string; color: string }[] = [
  { key: "code", label: "代码", color: "#10b981" },
  { key: "test", label: "测试", color: "#faad14" },
  { key: "step", label: "步骤", color: "#1677ff" },
  { key: "review", label: "评审", color: "#13c2c2" },
  { key: "evidence", label: "证据", color: "#722ed1" },
];

const MISSING_LABEL: Record<string, string> = {
  code: "代码",
  test: "测试",
  step: "步骤",
  review: "评审",
  evidence: "证据",
};

// ─── Helpers ─────────────────────────────────────────────────────────────────


function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// Stage-6 (2026-09-05): 批量编辑 + 审计
type BatchOp = "export_csv" | "mark_reviewed" | "mark_unreviewed";
interface AuditEntry {
  id: string;
  ts: number;
  op: BatchOp;
  project: string;
  req_ids: string[];
  note: string;
  user_email: string;
}
const BATCH_OP_LABEL: Record<BatchOp, string> = {
  export_csv: "导出 CSV",
  mark_reviewed: "标记已审核",
  mark_unreviewed: "撤销审核",
};

/** 审计面板默认折叠条数（交付红线：长列表默认折叠 10 条且总数可见）。 */
const AUDIT_PREVIEW = 10;

/** 审计条目时间戳 → `MM-DD hh:mm:ss`（本地时区，便于人工核对）。 */
function formatAuditTs(ts: number): string {
  const d = new Date(ts);
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
    `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function TraceabilityPage() {
  // Projects (context for the matrix query)
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");

  const [matrix, setMatrix] = useState<MatrixResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Expandable rows: code / test / step / review detail
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // Stage-6 (2026-09-05): 批量编辑 + 审计
  // - selectedReqIds: 当前选中的需求 ID 集合 (用于批量操作)
  // - batchNote: 用户为本次批量操作填的备注 (审计字段)
  // - auditLog: 持久化的操作历史, 上限 100 条, 跨刷新保留
  const [selectedReqIds, setSelectedReqIds] = useState<Set<string>>(new Set());
  const [batchNote, setBatchNote] = useState("");
  const [auditLog, setAuditLog] = usePersistentState<AuditEntry[]>(
    "traceability", "auditLog", []);
  const [showAudit, setShowAudit] = useState(false);
  const [showAllAudit, setShowAllAudit] = useState(false);

  // ── 派生: 选中行数、是否全选 ──────────────────────────────────────────────
  const allReqIds = useMemo(
    () => (matrix?.requirements || []).map((r) => r.req_id),
    [matrix],
  );
  const allSelected =
    allReqIds.length > 0 && selectedReqIds.size === allReqIds.length;
  const someSelected = selectedReqIds.size > 0 && !allSelected;

  // Stage-6 (2026-09-05): 上报「追溯缺口数」给左栏徽标 —— 只要 5 个维度
  // (代码/测试/步骤/评审/证据) 任一未覆盖, 该需求就算一条缺口。
  const setSidebarExtras = useSidebarExtras();
  const gapCount = useMemo(
    () =>
      (matrix?.requirements || []).filter((r) =>
        DIM_META.some((d) => !r.coverage[d.key]),
      ).length,
    [matrix],
  );
  useEffect(() => {
    setSidebarExtras({ traceabilityGapCount: gapCount });
  }, [gapCount, setSidebarExtras]);

  // ── 切项目时清空选择 (避免上一项目的选中态串到新项目) ────────────────────
  useEffect(() => {
    setSelectedReqIds(new Set());
  }, [selectedProject]);

  // ── 批量操作: 写一条审计 + 视觉反馈 (前端无真正后端 mutation,
  //     仅记录到 localStorage 审计链) ─────────────────────────────────────
  const recordBatchOp = useCallback(
    (op: BatchOp, ids: string[]) => {
      if (ids.length === 0) return;
      const entry: AuditEntry = {
        id: `audit-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        ts: Date.now(),
        op,
        project: selectedProject || "(未选择)",
        req_ids: ids,
        note: batchNote.trim(),
        user_email: typeof window !== "undefined"
          ? (localStorage.getItem("yuleosh:session_email") || "anonymous")
          : "anonymous",
      };
      setAuditLog((prev) => [entry, ...prev].slice(0, 100));
      setBatchNote("");
      setSelectedReqIds(new Set());
    },
    [batchNote, selectedProject, setAuditLog],
  );

  // ── 批量导出 CSV ──────────────────────────────────────────────────────────
  const exportSelectedCSV = useCallback(() => {
    if (!matrix || selectedReqIds.size === 0) return;
    const rows = matrix.requirements.filter((r) => selectedReqIds.has(r.req_id));
    const header = ["req_id", "statement", "code", "test", "step", "review", "evidence"];
    const escape = (v: unknown) => {
      const s = String(v ?? "");
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csv = [
      header.join(","),
      ...rows.map((r) => [
        r.req_id,
        r.statement || r.section || "",
        r.coverage.code ? "✓" : "✕",
        r.coverage.test ? "✓" : "✕",
        r.coverage.step ? "✓" : "✕",
        r.coverage.review ? "✓" : "✕",
        r.coverage.evidence ? "✓" : "✕",
      ].map(escape).join(",")),
    ].join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `traceability-${selectedProject || "export"}-${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    recordBatchOp("export_csv", rows.map((r) => r.req_id));
  }, [matrix, selectedReqIds, selectedProject, recordBatchOp]);

  // ── Load project list ────────────────────────────────────────────────────
  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectsError("");
    try {
      const res = await apiFetch<ProjectsResponse>("/api/v1/project");
      const list = res.projects || [];
      setProjects(list);
      setSelectedProject((prev) => (prev && list.some((p) => p.name === prev) ? prev : list[0]?.name || ""));
    } catch (err) {
      setProjectsError(errMessage(err));
      setProjects([]);
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  // ── Load traceability matrix for the selected project ───────────────────
  const loadMatrix = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<MatrixResponse>(
        `/api/v1/matrix?project=${encodeURIComponent(selectedProject)}`
      );
      setMatrix(res);
      setExpanded({});
    } catch (err) {
      setError(errMessage(err));
      setMatrix(null);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (!selectedProject) return;
    void loadMatrix();
  }, [selectedProject, loadMatrix]);

  const toggleExpand = useCallback((reqId: string) => {
    setExpanded((prev) => ({ ...prev, [reqId]: !prev[reqId] }));
  }, []);

  const summary = matrix?.summary;
  const gaps = matrix?.gaps;
  const rows = matrix?.requirements || [];
  const isEmpty = !loading && rows.length === 0;
  const noProjects = !projectsLoading && projects.length === 0;

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <Network className="w-4.5 h-4.5 text-[#722ed1]" />
              追溯矩阵
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              需求 ↔ 代码 ↔ 测试 ↔ 步骤 ↔ 证据 全链路可追溯（基于本地 spec / 测试 / 证据包，无需外部 ALM）
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#64748b] shrink-0">项目</span>
              {projectsLoading ? (
                <span className="text-xs text-[#64748b] flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  加载中…
                </span>
              ) : (
                <Select value={selectedProject} onValueChange={(v) => setSelectedProject(v ?? "")}>
                  <SelectTrigger size="sm" className="w-44">
                    <SelectValue placeholder="选择项目" />
                  </SelectTrigger>
                  <SelectContent align="end">
                    {projects.map((p) => (
                      <SelectItem key={String(p.id)} value={p.name}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void loadMatrix()}
              disabled={loading || !selectedProject}
              className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              刷新
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowAudit((v) => !v)}
              className={
                "border-[#1e293b] hover:border-[#722ed1]/40 " +
                (showAudit
                  ? "text-[#722ed1] bg-[#722ed1]/10"
                  : "text-[#94a3b8] hover:text-white")
              }
              title="批量编辑操作审计 (本地持久化)"
            >
              <History className="w-3.5 h-3.5" />
              审计
              {auditLog.length > 0 && (
                <span className="ml-1 rounded-full bg-[#722ed1]/20 px-1.5 py-0.5 text-[10px] font-semibold">
                  {auditLog.length}
                </span>
              )}
            </Button>
          </div>
        </div>

        {/* Stage-6 (2026-09-05): 批量编辑工具栏 —— 选中行 > 0 时显示 */}
        {selectedReqIds.size > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-[#722ed1]/30 bg-[#722ed1]/5 px-3 py-2.5">
            <span className="text-xs text-[#722ed1] font-semibold">
              已选中 {selectedReqIds.size} 条
            </span>
            <input
              type="text"
              value={batchNote}
              onChange={(e) => setBatchNote(e.target.value)}
              placeholder="本次操作备注 (审计字段, 留空跳过)"
              className="flex-1 min-w-[200px] rounded-md border border-[#1e293b] bg-[#0b1220] px-2.5 py-1 text-xs text-[#e2e8f0] placeholder:text-[#475569] focus:border-[#722ed1]/40 focus:outline-none"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={exportSelectedCSV}
              className="border-[#10b981]/40 text-[#10b981] hover:bg-[#10b981]/10"
            >
              <Download className="w-3.5 h-3.5" />
              导出 CSV
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => recordBatchOp("mark_reviewed", [...selectedReqIds])}
              className="border-[#722ed1]/40 text-[#c4b5fd] hover:bg-[#722ed1]/10"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              标记已审核
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => recordBatchOp("mark_unreviewed", [...selectedReqIds])}
              className="border-[#94a3b8]/40 text-[#94a3b8] hover:bg-[#1e293b]"
            >
              <Square className="w-3.5 h-3.5" />
              撤销审核
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedReqIds(new Set())}
              className="text-[#64748b] hover:text-white"
            >
              清空选择
            </Button>
          </div>
        )}

        {/* Stage-6 (2026-09-05): 批量编辑审计面板 —— 「审计」按钮切换。
            长列表默认折叠 10 条 + 总数可见（交付红线），展开后显示全部。 */}
        {showAudit && (
          <div className="mb-4 rounded-lg border border-[#722ed1]/30 bg-[#0b1220] px-4 py-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 text-xs text-[#c4b5fd] font-semibold">
                <History className="w-3.5 h-3.5" />
                批量编辑审计
                <span className="rounded-full bg-[#722ed1]/20 px-1.5 py-0.5 text-[10px]">
                  共 {auditLog.length} 条
                </span>
              </div>
              {auditLog.length > 0 && (
                <button
                  type="button"
                  onClick={() => setAuditLog([])}
                  className="text-[10px] text-[#64748b] hover:text-[#ff7875] transition-colors"
                >
                  清空审计
                </button>
              )}
            </div>

            {auditLog.length === 0 ? (
              <div className="py-4 text-center text-[11px] text-[#475569]">
                暂无批量编辑记录 —— 选中需求行后执行「导出 CSV / 标记已审核 /
                撤销审核」即会在此留下审计条目（本地持久化，最多保留 100 条）。
              </div>
            ) : (
              <>
                <div className="space-y-1.5">
                  {(showAllAudit ? auditLog : auditLog.slice(0, AUDIT_PREVIEW))
                    .map((e) => (
                      <div
                        key={e.id}
                        className="flex items-start gap-2 rounded-md border border-[#1e293b] bg-[#111827] px-2.5 py-1.5"
                      >
                        <span className="text-[10px] font-mono text-[#64748b] shrink-0 pt-0.5">
                          {formatAuditTs(e.ts)}
                        </span>
                        <span className="rounded bg-[#722ed1]/15 text-[#c4b5fd] px-1.5 py-0.5 text-[10px] shrink-0">
                          {BATCH_OP_LABEL[e.op] || e.op}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="text-[11px] text-[#94a3b8]">
                            <span className="text-[#e2e8f0]">{e.project}</span>
                            <span className="mx-1 text-[#475569]">·</span>
                            {e.req_ids.length} 条需求
                            {e.req_ids.length > 0 && (
                              <span className="text-[#475569]">
                                （{e.req_ids.slice(0, 3).join(", ")}
                                {e.req_ids.length > 3 ? "…" : ""}）
                              </span>
                            )}
                          </div>
                          {e.note && (
                            <div className="text-[10px] text-[#64748b] mt-0.5 break-words">
                              备注：{e.note}
                            </div>
                          )}
                        </div>
                        <span className="text-[10px] text-[#475569] shrink-0 pt-0.5">
                          {e.user_email}
                        </span>
                      </div>
                    ))}
                </div>
                {auditLog.length > AUDIT_PREVIEW && (
                  <button
                    type="button"
                    onClick={() => setShowAllAudit((v) => !v)}
                    className="mt-2 inline-flex items-center gap-1 text-[10px] text-[#722ed1] hover:text-[#c4b5fd] transition-colors"
                  >
                    {showAllAudit ? (
                      <>
                        <ChevronUp className="w-3 h-3" />
                        收起（仅显示最近 {AUDIT_PREVIEW} 条）
                      </>
                    ) : (
                      <>
                        <ChevronDown className="w-3 h-3" />
                        展开全部 {auditLog.length} 条
                      </>
                    )}
                  </button>
                )}
              </>
            )}
          </div>
        )}

        {/* Data note */}
        {matrix?.note && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{matrix.note}</span>
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

        {noProjects ? (
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardContent className="py-14 text-center text-[#64748b] text-sm">
              <div className="text-2xl mb-2">📂</div>
              暂无项目
              <div className="text-xs mt-1 text-[#475569]">
                {projectsError ? `项目列表加载失败：${projectsError}` : "请先在座舱中创建项目"}
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6 items-start">
            {/* ── Left: matrix table ── */}
            <Card className="border-[#1e293b] bg-[#111827]">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-[#722ed1]" />
                  追溯矩阵
                  {!loading && summary && (
                    <span className="text-xs font-normal text-[#64748b]">
                      共 {summary.total} 条需求
                    </span>
                  )}
                </CardTitle>
                <CardDescription className="text-xs text-[#64748b]">
                  每行一个需求，五列表示代码/测试/步骤/评审/证据覆盖情况
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
                    <div className="text-2xl mb-2">🧩</div>
                    暂无追溯数据
                    <div className="text-xs mt-1 text-[#475569]">
                      {matrix?.note || "所选项目未解析到需求条目"}
                    </div>
                  </div>
                ) : (
                  <div>
                    {/* Table header */}
                    <div className="grid grid-cols-[28px_1fr_repeat(5,56px)] gap-2 px-4 py-2 text-xs text-[#64748b] border-b border-[#1e293b] items-center">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = someSelected;
                        }}
                        onChange={() => {
                          if (allSelected) setSelectedReqIds(new Set());
                          else setSelectedReqIds(new Set(allReqIds));
                        }}
                        className="w-4 h-4 cursor-pointer accent-[#722ed1]"
                        title={allSelected ? "取消全选" : "全选所有行"}
                      />
                      <span>需求</span>
                      {DIM_META.map((d) => (
                        <span
                          key={d.key}
                          className="text-center"
                          style={{ color: d.color }}
                          title={d.label}
                        >
                          {d.label}
                        </span>
                      ))}
                    </div>

                    {rows.map((r) => {
                      const isOpen = !!expanded[r.req_id];
                      const isSelected = selectedReqIds.has(r.req_id);
                      return (
                        <div key={r.req_id} className="border-b border-[#1e293b] last:border-b-0">
                          <div
                            className={
                              "grid grid-cols-[28px_1fr_repeat(5,56px)] gap-2 px-4 py-3 items-center cursor-pointer transition-all " +
                              (isSelected
                                ? "bg-[#722ed1]/5 hover:bg-[#722ed1]/10"
                                : "hover:bg-[#1e293b]/50")
                            }
                          >
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => {
                                e.stopPropagation();
                                setSelectedReqIds((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(r.req_id)) next.delete(r.req_id);
                                  else next.add(r.req_id);
                                  return next;
                                });
                              }}
                              onClick={(e) => e.stopPropagation()}
                              className="w-4 h-4 cursor-pointer accent-[#722ed1]"
                              title={isSelected ? "取消选择" : "选中此行"}
                            />
                            <div
                              onClick={() => toggleExpand(r.req_id)}
                              className="min-w-0 flex-1"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="text-xs font-mono text-[#722ed1] shrink-0">
                                  {r.req_id}
                                </span>
                                <span className="text-sm text-[#e2e8f0] truncate">
                                  {r.statement || r.section || "(无描述)"}
                                </span>
                              </div>
                              {r.link_method && (
                                <div className="text-[10px] text-[#475569] pl-0.5 mt-0.5">
                                  关联方式：{r.link_method}
                                  {r.swr_mapping ? " · SWR 映射表" : ""}
                                </div>
                              )}
                            </div>
                            {DIM_META.map((d) => {
                              const ok = r.coverage[d.key];
                              return (
                                <div
                                  key={d.key}
                                  onClick={() => toggleExpand(r.req_id)}
                                  className="text-center"
                                >
                                  <span
                                    className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[11px] font-bold"
                                    style={{
                                      color: ok ? d.color : "#64748b",
                                      background: ok ? `${d.color}1f` : "#1e293b",
                                    }}
                                    title={ok ? `${d.label}已覆盖` : `${d.label}缺失`}
                                  >
                                    {ok ? "✓" : "✕"}
                                  </span>
                                </div>
                              );
                            })}
                          </div>

                          {/* Expanded: coverage detail */}
                          {isOpen && (
                            <div className="px-4 pb-4 space-y-3">
                              <div className="grid grid-cols-2 gap-3">
                                <DetailCard
                                  icon={<FileCode className="w-3.5 h-3.5 text-[#10b981]" />}
                                  title="代码文件"
                                  color="#10b981"
                                  empty="未发现实现代码"
                                  items={r.code_files.map((f) => ({ label: f }))}
                                />
                                <DetailCard
                                  icon={<FlaskConical className="w-3.5 h-3.5 text-[#faad14]" />}
                                  title="测试报告"
                                  color="#faad14"
                                  empty="未发现测试"
                                  items={r.test_reports.map((t) => ({
                                    label: [
                                      String(t.file ?? ""),
                                      t.function ? `::${t.function}` : "",
                                      t.status ? ` [${t.status}]` : "",
                                    ].join("").trim() || "(测试)",
                                  }))}
                                />
                                <DetailCard
                                  icon={<Workflow className="w-3.5 h-3.5 text-[#1677ff]" />}
                                  title={`步骤处理 (${r.step_handlers.length})`}
                                  color="#1677ff"
                                  empty="无关联步骤"
                                  items={r.step_handlers.map((s, i) => ({
                                    label:
                                      typeof s === "string"
                                        ? s
                                        : String((s as Record<string, unknown>)?.name ?? (s as Record<string, unknown>)?.step_key ?? `步骤 ${i + 1}`),
                                  }))}
                                />
                                <DetailCard
                                  icon={<ShieldCheck className="w-3.5 h-3.5 text-[#13c2c2]" />}
                                  title="评审"
                                  color="#13c2c2"
                                  empty="无关联评审"
                                  items={r.reviews.map((rv) => ({
                                    label: [
                                      String(rv.file ?? ""),
                                      rv.reviewer ? ` by ${rv.reviewer}` : "",
                                    ].join("").trim() || "(评审)",
                                  }))}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Right: summary + gaps ── */}
            <div className="space-y-4 lg:sticky lg:top-20">
              {/* Coverage summary */}
              <Card className="border-[#1e293b] bg-[#111827]">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                    <Network className="w-4 h-4 text-[#722ed1]" />
                    覆盖率概览
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {!summary ? (
                    <div className="py-8 text-center text-[#64748b] text-sm">暂无数据</div>
                  ) : (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-2">
                        {DIM_META.map((d) => {
                          const val = (summary as unknown as Record<string, number>)[`with_${d.key}`] ?? 0;
                          const pct = summary.total ? Math.round((val / summary.total) * 100) : 0;
                          return (
                            <div
                              key={d.key}
                              className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-2"
                            >
                              <div className="flex items-baseline justify-between">
                                <span className="text-[11px] text-[#94a3b8]">{d.label}</span>
                                <span className="text-xs font-bold" style={{ color: d.color }}>
                                  {val}/{summary.total}
                                </span>
                              </div>
                              <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden mt-1.5">
                                <div
                                  className="h-full rounded-full"
                                  style={{ width: `${pct}%`, background: d.color }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Gap analysis */}
              <Card className="border-[#1e293b] bg-[#111827]">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-[#faad14]" />
                    覆盖缺口
                  </CardTitle>
                  <CardDescription className="text-xs text-[#64748b]">
                    各维度缺失的需求数量
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {!gaps ? (
                    <div className="py-8 text-center text-[#64748b] text-sm">暂无数据</div>
                  ) : (
                    <div className="space-y-3">
                      {/* by-type counts */}
                      <div className="grid grid-cols-5 gap-1.5">
                        {DIM_META.map((d) => {
                          const count = (gaps.by_type as unknown as Record<string, number>)[`no_${d.key}`] ?? 0;
                          return (
                            <div
                              key={d.key}
                              className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-1.5 text-center"
                            >
                              <div className="text-sm font-bold" style={{ color: count ? d.color : "#475569" }}>
                                {count}
                              </div>
                              <div className="text-[9px] text-[#64748b] mt-0.5">缺{d.label}</div>
                            </div>
                          );
                        })}
                      </div>

                      {/* gap items */}
                      {gaps.items.length === 0 ? (
                        <div className="py-4 text-center text-xs text-[#64748b]">
                          <div className="text-xl mb-1">🎉</div>
                          暂无缺口
                        </div>
                      ) : (
                        <div>
                          <div className="text-xs text-[#94a3b8] mb-2 flex items-center gap-1.5">
                            <AlertCircle className="w-3 h-3 text-[#faad14]" />
                            缺口明细
                            <span className="text-[#64748b]">{gaps.items.length} 条</span>
                          </div>
                          <div className="space-y-1.5 max-h-80 overflow-y-auto">
                            {gaps.items.map((g) => (
                              <div
                                key={g.req_id}
                                className="flex items-center gap-2 rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-2.5 py-2"
                              >
                                <span className="text-xs font-mono text-[#722ed1] shrink-0">
                                  {g.req_id}
                                </span>
                                <span className="flex gap-1 ml-auto shrink-0">
                                  {g.missing.map((m) => (
                                    <Badge
                                      key={m}
                                      variant="outline"
                                      className="border-transparent text-[10px]"
                                      style={{
                                        color: "#ff4d4f",
                                        background: "#ff4d4f1f",
                                        borderColor: "#ff4d4f4d",
                                      }}
                                    >
                                      缺{MISSING_LABEL[m] ?? m}
                                    </Badge>
                                  ))}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Footer hint */}
        <div className="mt-6 flex items-center gap-1 text-xs text-[#475569]">
          <ScrollText className="w-3 h-3" />
          需求来自 projects/&lt;项目&gt;/spec*.md；测试/步骤来自 .osh/sessions 与 .osh/cache/steps；证据来自 .osh/evidence/ 合规证据包。
        </div>
      </div>
    </div>
  );
}

// ─── Detail card (expanded row) ──────────────────────────────────────────────

function DetailCard({
  icon,
  title,
  color,
  empty,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  color: string;
  empty: string;
  items: { label: string }[];
}) {
  return (
    <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 overflow-hidden">
      <div
        className="flex items-center gap-2 px-3 py-2 border-b border-[#1e293b] text-xs"
        style={{ color }}
      >
        {icon}
        {title}
      </div>
      {items.length === 0 ? (
        <div className="px-3 py-2 text-[11px] text-[#475569]">{empty}</div>
      ) : (
        <ul className="px-3 py-2 space-y-1">
          {items.slice(0, 12).map((it, i) => (
            <li key={i} className="text-[11px] text-[#94a3b8] font-mono truncate" title={it.label}>
              {it.label}
            </li>
          ))}
          {items.length > 12 && (
            <li className="text-[11px] text-[#475569]">+{items.length - 12} 更多</li>
          )}
        </ul>
      )}
    </div>
  );
}

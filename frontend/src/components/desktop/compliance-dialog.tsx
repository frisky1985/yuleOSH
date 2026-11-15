"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FilePlus2,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api-fetch";

// ─── Types ────────────────────────────────────────────────────────────────

export interface ProcessScore {
  title?: string;
  score: string;
  coverage_pct: number;
  evidence_count: number;
  gap_count: number;
}

export interface ComplianceGap {
  process: string;
  type: string;
  ref_id?: string;
  title?: string;
  details?: string;
}

export interface ComplianceSummary {
  ok: boolean;
  status: string;
  overall_score?: string;
  overall_coverage_pct?: number;
  total_gaps?: number;
  total_evidences?: number;
  bp_summary: { total: number; passed: number; partial: number; failed: number };
  scores: Record<string, ProcessScore>;
  gaps: ComplianceGap[];
  errors: string[];
  generated_at?: string;
  compliance_report_path?: string | null;
  audit_report_path?: string | null;
  dashboard_path?: string | null;
}

export interface ComplianceDoc {
  name: string;
  title: string;
  path: string;
  exists: boolean;
}

interface ComplianceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

type Light = "green" | "amber" | "red";

// ─── Helpers ──────────────────────────────────────────────────────────────

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

/** 红黄绿只反映证据覆盖度（E1/E2/E3/NI），不代表 ASPICE 能力等级。 */
export function coverageLight(score?: ProcessScore): Light {
  if (!score) return "red";
  if (score.score === "NI") return "red";
  if (score.coverage_pct >= 80) return "green";
  if (score.coverage_pct >= 40) return "amber";
  return "red";
}

const LIGHT_CLS: Record<Light, { tile: string; dot: string; text: string }> = {
  green: {
    tile: "border-[#10b981]/40 bg-[#10b981]/5",
    dot: "bg-[#10b981]",
    text: "text-[#34d399]",
  },
  amber: {
    tile: "border-[#f59e0b]/40 bg-[#f59e0b]/5",
    dot: "bg-[#f59e0b]",
    text: "text-[#fbbf24]",
  },
  red: {
    tile: "border-[#ef4444]/40 bg-[#ef4444]/5",
    dot: "bg-[#ef4444]",
    text: "text-[#f87171]",
  },
};

const GAP_LABEL: Record<string, string> = {
  missing_evidence: "缺失证据",
  failed_evidence: "证据未通过",
  empty_evidence: "证据无实质内容",
};

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端合规检查仪表盘：过程域红黄绿、缺失证据清单、一键生成证据文档。 */
export function ComplianceDialog({ open, onOpenChange, projectId }: ComplianceDialogProps) {
  const [summary, setSummary] = useState<ComplianceSummary | null>(null);
  const [documents, setDocuments] = useState<ComplianceDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadDocuments = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await apiFetch<{ documents: ComplianceDoc[] }>(
        `/api/v1/desktop/projects/${projectId}/compliance/documents`,
      );
      setDocuments(data.documents || []);
    } catch {
      setDocuments([]);
    }
  }, [projectId]);

  const loadSummary = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ summary: ComplianceSummary }>(
        `/api/v1/desktop/projects/${projectId}/compliance`,
      );
      setSummary(data.summary);
    } catch (e) {
      // 尚未审计：后端返回 404，这里按空态处理而不是报错。
      setSummary(null);
      const msg = (e as Error).message || "";
      if (!/No audit summary/i.test(msg)) setError(msg || "加载合规结果失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setSummary(null);
    setDocuments([]);
    setError("");
    setNotice("");
    loadSummary();
    loadDocuments();
  }, [open, projectId, loadSummary, loadDocuments]);

  const runAudit = async () => {
    if (!projectId || running) return;
    setRunning(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ summary: ComplianceSummary }>(
        `/api/v1/desktop/projects/${projectId}/compliance/run`,
        { method: "POST", body: JSON.stringify({}) },
      );
      setSummary(data.summary);
      await loadDocuments();
      setNotice(
        data.summary.status === "not_run"
          ? "审计完成，但项目缺少可评估证据（fail-closed，不会误判为通过）。"
          : "合规审计完成，报告与证据包已生成。",
      );
    } catch (e) {
      setError((e as Error).message || "合规审计失败");
    } finally {
      setRunning(false);
    }
  };

  const generateMissingDocs = async () => {
    if (!projectId || generating) return;
    const missing = documents.filter((d) => !d.exists).map((d) => d.name);
    if (missing.length === 0) {
      setNotice("所有证据文档模板都已存在。");
      return;
    }
    setGenerating(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ created: string[]; skipped: string[] }>(
        `/api/v1/desktop/projects/${projectId}/templates`,
        { method: "POST", body: JSON.stringify({ templates: missing }) },
      );
      await loadDocuments();
      setNotice(`已生成 ${data.created.length} 份证据文档模板（${missing.length - data.created.length} 份已存在）。`);
    } catch (e) {
      setError((e as Error).message || "生成证据文档失败");
    } finally {
      setGenerating(false);
    }
  };

  const processes = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.scores || {}).sort(([a], [b]) =>
      a.localeCompare(b, "en", { numeric: true }),
    );
  }, [summary]);

  const counts = useMemo(() => {
    const acc = { green: 0, amber: 0, red: 0 };
    for (const [, s] of processes) acc[coverageLight(s)] += 1;
    return acc;
  }, [processes]);

  const missingDocs = documents.filter((d) => !d.exists);
  const overallLight: Light =
    summary?.overall_score === "NI" || !summary
      ? "red"
      : (summary.overall_coverage_pct ?? 0) >= 80
        ? "green"
        : (summary.overall_coverage_pct ?? 0) >= 40
          ? "amber"
          : "red";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(95vw,1060px)] max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#1677ff]" /> 合规检查
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            ASPICE 过程域证据覆盖度（E1/E2/E3/NI），红黄绿仅表示证据完整度，不代表能力等级。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={runAudit}
            disabled={!projectId || running}
            data-testid="compliance-run"
            className="h-8 bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
          >
            {running ? (
              <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 mr-1" />
            )}
            {summary ? "重新运行审计" : "运行合规审计"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={generateMissingDocs}
            disabled={!projectId || generating || missingDocs.length === 0}
            data-testid="compliance-generate-docs"
            className="h-8 border-[#1e293b] text-[#94a3b8] hover:text-white"
          >
            {generating ? (
              <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
            ) : (
              <FilePlus2 className="w-3.5 h-3.5 mr-1" />
            )}
            生成缺失证据文档{missingDocs.length ? `（${missingDocs.length}）` : ""}
          </Button>
          <button
            type="button"
            onClick={() => {
              loadSummary();
              loadDocuments();
            }}
            disabled={!projectId || loading}
            title="刷新"
            data-testid="compliance-reload"
            className="ml-auto text-[#64748b] hover:text-white disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
          </button>
        </div>

        <div
          className="min-h-0 space-y-3 overflow-y-auto scrollbar-dark pr-1"
          data-testid="compliance-dialog"
        >
          {error && (
            <div
              className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
              data-testid="compliance-error"
            >
              {error}
            </div>
          )}
          {notice && (
            <div
              className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]"
              data-testid="compliance-notice"
            >
              {notice}
            </div>
          )}

          {loading && !summary && (
            <div className="flex items-center justify-center gap-2 py-10 text-xs text-[#64748b]">
              <Loader2 className="w-4 h-4 animate-spin" /> 正在加载合规结果…
            </div>
          )}

          {!loading && !summary && !error && (
            <div
              className="rounded-md border border-[#1e293b] px-3 py-8 text-center text-xs text-[#64748b]"
              data-testid="compliance-empty"
            >
              还没有审计结果。点击「运行合规审计」生成证据包、报告与过程域评分。
            </div>
          )}

          {summary && (
            <>
              {/* ── 总体状态 ─────────────────────────────────────────── */}
              <section
                className={`rounded-md border p-3 ${LIGHT_CLS[overallLight].tile}`}
                data-testid="compliance-overall"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <span className={`inline-flex items-center gap-1 text-sm font-semibold ${LIGHT_CLS[overallLight].text}`}>
                    <span className={`h-2.5 w-2.5 rounded-full ${LIGHT_CLS[overallLight].dot}`} />
                    {summary.status === "completed"
                      ? "审计完成"
                      : summary.status === "partial"
                        ? "部分完成"
                        : "未通过（缺证据）"}
                  </span>
                  <span className="text-xs text-[#94a3b8]">
                    总体证据覆盖度 <span className="font-semibold text-[#e2e8f0]">{Math.round(summary.overall_coverage_pct ?? 0)}%</span>
                    （等级 {summary.overall_score ?? "NI"}）
                  </span>
                  <span className="text-xs text-[#94a3b8]">
                    实践通过 {summary.bp_summary.passed}/{summary.bp_summary.total}
                  </span>
                  <span className="text-xs text-[#94a3b8]">
                    证据 {summary.total_evidences ?? 0} · 差距 {summary.total_gaps ?? summary.gaps.length}
                  </span>
                  <span className="ml-auto text-[11px] text-[#64748b]">
                    {fmtTime(summary.generated_at)}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
                  <span className="text-[#34d399]">● 绿 {counts.green}</span>
                  <span className="text-[#fbbf24]">● 黄 {counts.amber}</span>
                  <span className="text-[#f87171]">● 红 {counts.red}</span>
                </div>
                {summary.errors.length > 0 && (
                  <div className="mt-2 text-[11px] text-[#fbbf24]">
                    审计阶段告警：{summary.errors.join("；")}
                  </div>
                )}
              </section>

              {/* ── 过程域红黄绿 ─────────────────────────────────────── */}
              <section>
                <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                  过程域状态（{processes.length}）
                </div>
                {processes.length === 0 ? (
                  <div className="rounded-md border border-[#1e293b] px-3 py-4 text-center text-[11px] text-[#64748b]">
                    没有可评估的过程域 — 请先补充需求与证据。
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4" data-testid="compliance-processes">
                    {processes.map(([pid, s]) => {
                      const light = coverageLight(s);
                      return (
                        <div
                          key={pid}
                          data-testid={`compliance-process-${pid}`}
                          className={`rounded-md border px-2 py-1.5 ${LIGHT_CLS[light].tile}`}
                        >
                          <div className="flex items-center gap-1.5">
                            <span className={`h-2 w-2 shrink-0 rounded-full ${LIGHT_CLS[light].dot}`} />
                            <span className="font-mono text-[11px] text-[#e2e8f0]">{pid}</span>
                            <span className={`ml-auto text-[10px] ${LIGHT_CLS[light].text}`}>
                              {s.score}
                            </span>
                          </div>
                          <div className="mt-0.5 truncate text-[10px] text-[#64748b]" title={s.title}>
                            {s.title || "—"}
                          </div>
                          <div className="mt-1 flex items-center justify-between text-[10px] text-[#94a3b8]">
                            <span>覆盖 {Math.round(s.coverage_pct)}%</span>
                            <span>
                              证据 {s.evidence_count} · 差距 {s.gap_count}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              {/* ── 缺失证据清单 ─────────────────────────────────────── */}
              <section>
                <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                  <AlertTriangle className="w-3.5 h-3.5" /> 缺失证据清单（{summary.gaps.length}）
                </div>
                {summary.gaps.length === 0 ? (
                  <div className="flex items-center gap-1 rounded-md border border-[#10b981]/30 bg-[#10b981]/5 px-3 py-2 text-[11px] text-[#34d399]">
                    <CheckCircle2 className="w-3.5 h-3.5" /> 未发现证据缺口。
                  </div>
                ) : (
                  <div className="max-h-48 space-y-1 overflow-y-auto scrollbar-dark" data-testid="compliance-gaps">
                    {summary.gaps.map((g, i) => (
                      <div
                        key={`${g.process}-${g.type}-${i}`}
                        className="flex items-start gap-2 rounded border border-[#1e293b] px-2 py-1.5 text-[11px]"
                      >
                        <span className="mt-0.5 shrink-0 font-mono text-[#e2e8f0]">{g.process}</span>
                        <span
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${
                            g.type === "missing_evidence"
                              ? "bg-[#ef4444]/15 text-[#f87171]"
                              : "bg-[#f59e0b]/15 text-[#fbbf24]"
                          }`}
                        >
                          {GAP_LABEL[g.type] || g.type}
                        </span>
                        <span className="min-w-0 text-[#94a3b8]">
                          {g.ref_id ? <span className="font-mono text-[#e2e8f0]">{g.ref_id} </span> : null}
                          {g.title || g.details || "—"}
                          {g.title && g.details ? (
                            <span className="text-[#64748b]"> — {g.details}</span>
                          ) : null}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {(summary.compliance_report_path || summary.audit_report_path) && (
                <div className="space-y-0.5 text-[10px] text-[#475569]">
                  {summary.compliance_report_path && (
                    <div>合规报告：{summary.compliance_report_path}</div>
                  )}
                  {summary.audit_report_path && <div>审计报告：{summary.audit_report_path}</div>}
                </div>
              )}
            </>
          )}

          {/* ── 证据文档（无审计结果时也可生成） ─────────────────────── */}
          {documents.length > 0 && (
            <EvidenceDocs documents={documents} missingCount={missingDocs.length} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EvidenceDocs({
  documents,
  missingCount,
}: {
  documents: ComplianceDoc[];
  missingCount: number;
}) {
  return (
    <section>
      <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
        证据文档
        <span className="font-normal normal-case text-[#475569]">
          已存在 {documents.length - missingCount}/{documents.length}
        </span>
      </div>
      <div className="grid gap-1 sm:grid-cols-2" data-testid="compliance-documents">
        {documents.map((doc) => (
          <div
            key={doc.name}
            data-testid={`compliance-doc-${doc.name}`}
            className="flex items-center gap-2 rounded border border-[#1e293b] px-2 py-1.5 text-[11px]"
          >
            {doc.exists ? (
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-[#10b981]" />
            ) : (
              <XCircle className="w-3.5 h-3.5 shrink-0 text-[#ef4444]" />
            )}
            <span className="truncate text-[#e2e8f0]" title={doc.title}>
              {doc.title}
            </span>
            <span className="ml-auto shrink-0 font-mono text-[10px] text-[#475569]">
              {doc.path}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

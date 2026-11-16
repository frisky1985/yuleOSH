"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Loader2,
  RefreshCw,
  ShieldAlert,
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

export interface RtmRequirement {
  req_id: string;
  statement: string;
  status: string;
  has_code: boolean;
  has_test: boolean;
  has_design?: boolean;
  has_review: boolean;
  design_files: string[];
  code_files: string[];
  test_files: string[];
}

export interface RtmSummary {
  total_requirements: number;
  with_design_coverage?: number;
  with_implementation: number;
  with_test_coverage: number;
  with_review_coverage?: number;
  coverage_pct: number;
  design_coverage_pct?: number;
  review_coverage_pct?: number;
  orphaned_tests?: number;
}

export interface TraceGate {
  status?: string;
  threshold?: number;
  reason?: string;
}

export interface RtmPayload {
  summary: RtmSummary;
  requirements: RtmRequirement[];
  orphaned_test_files: string[];
  baseline: string | null;
  generated: string | null;
  gate?: TraceGate;
}

export interface ChainProblem {
  code: string;
  severity: string;
  message: string;
}

export interface ChainGate {
  id: string;
  severity: string;
  status: string;
  detail: string;
}

export interface ChainPayload {
  status: string;
  summary: Record<string, number | string>;
  metrics: Record<string, number | string>;
  generated_at: string | null;
  source: string;
  problems: ChainProblem[];
  problem_total: number;
  gates: ChainGate[];
  v_model: { pairs: number; required_pairs: number; required_passed: number };
}

interface TraceabilityDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
  /** 点击 RTM 中的产物文件名时打开对应文件（关闭弹窗后跳到工作区预览）。 */
  onOpenArtifact?: (path: string) => void;
}

type Tab = "rtm" | "chain";

// ─── Helpers ──────────────────────────────────────────────────────────────

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

function CoverCell({ files }: { files?: string[] }) {
  const n = files?.length ?? 0;
  if (!n) return <span className="text-[#475569]">—</span>;
  return (
    <span className="inline-flex items-center gap-1 text-[#10b981]">
      <CheckCircle2 className="w-3.5 h-3.5" />
      {n}
    </span>
  );
}

function ChainStatusChip({ status }: { status?: string }) {
  const pass = status === "PASS";
  return (
    <span
      data-testid="chain-status"
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
        pass
          ? "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]"
          : "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]"
      }`}
    >
      {pass ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
      {pass ? "校验通过" : "校验未通过"}
    </span>
  );
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端 ASPICE 追溯视图：RTM 矩阵 + 审计链校验结果。 */
export function TraceabilityDialog({
  open,
  onOpenChange,
  projectId,
  onOpenArtifact,
}: TraceabilityDialogProps) {
  const [tab, setTab] = useState<Tab>("rtm");
  const [rtm, setRtm] = useState<RtmPayload | null>(null);
  const [chain, setChain] = useState<ChainPayload | null>(null);
  const [loadingRtm, setLoadingRtm] = useState(false);
  const [loadingChain, setLoadingChain] = useState(false);
  const [errorRtm, setErrorRtm] = useState("");
  const [errorChain, setErrorChain] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const loadRtm = useCallback(async () => {
    if (!projectId) return;
    setLoadingRtm(true);
    setErrorRtm("");
    try {
      const data = await apiFetch<RtmPayload>(`/api/v1/desktop/projects/${projectId}/traceability`);
      setRtm(data);
    } catch (e) {
      setRtm(null);
      setErrorRtm((e as Error).message || "加载追溯矩阵失败");
    } finally {
      setLoadingRtm(false);
    }
  }, [projectId]);

  const loadChain = useCallback(async () => {
    if (!projectId) return;
    setLoadingChain(true);
    setErrorChain("");
    try {
      const data = await apiFetch<ChainPayload>(`/api/v1/desktop/projects/${projectId}/evidence-chain`);
      setChain(data);
    } catch (e) {
      setChain(null);
      setErrorChain((e as Error).message || "审计链校验失败");
    } finally {
      setLoadingChain(false);
    }
  }, [projectId]);

  // Reset whenever the dialog is (re)opened for a project.
  useEffect(() => {
    if (!open) return;
    setTab("rtm");
    setRtm(null);
    setChain(null);
    setExpanded({});
    setErrorRtm("");
    setErrorChain("");
  }, [open, projectId]);

  useEffect(() => {
    if (open && projectId) loadRtm();
  }, [open, projectId, loadRtm]);

  useEffect(() => {
    if (open && tab === "chain" && projectId && !chain && !loadingChain && !errorChain) {
      loadChain();
    }
  }, [open, tab, projectId, chain, loadingChain, errorChain, loadChain]);

  const refreshRtm = async () => {
    if (!projectId || loadingRtm) return;
    setLoadingRtm(true);
    setErrorRtm("");
    try {
      await apiFetch(`/api/v1/desktop/projects/${projectId}/traceability/refresh`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      const data = await apiFetch<RtmPayload>(`/api/v1/desktop/projects/${projectId}/traceability`);
      setRtm(data);
      // Matrix changed — the chain verdict is stale.
      setChain(null);
    } catch (e) {
      setErrorRtm((e as Error).message || "生成追溯矩阵失败");
    } finally {
      setLoadingRtm(false);
    }
  };

  const summary = rtm?.summary;
  const rows = rtm?.requirements ?? [];
  const gateStatus = rtm?.gate?.status;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(94vw,1040px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-[#1677ff]" /> 追溯与审计
            {gateStatus && (
              <span
                className={`rounded-full border px-2 py-0.5 text-[11px] font-normal ${
                  gateStatus === "passed"
                    ? "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]"
                    : "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]"
                }`}
              >
                RTM 门禁 {gateStatus === "passed" ? "通过" : gateStatus === "failed" ? "未通过" : "未评估"}
              </span>
            )}
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            需求 → 设计 → 代码 → 测试的覆盖关系，以及证据链完整性校验结果。
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-1 border-b border-[#1e293b]" data-testid="traceability-dialog">
          <button
            type="button"
            onClick={() => setTab("rtm")}
            data-testid="traceability-tab-rtm"
            className={`px-3 py-2 text-xs border-b-2 -mb-px transition-colors ${
              tab === "rtm"
                ? "border-[#1677ff] text-[#e2e8f0]"
                : "border-transparent text-[#64748b] hover:text-[#94a3b8]"
            }`}
          >
            追溯矩阵（RTM）
          </button>
          <button
            type="button"
            onClick={() => setTab("chain")}
            data-testid="traceability-tab-chain"
            className={`px-3 py-2 text-xs border-b-2 -mb-px transition-colors ${
              tab === "chain"
                ? "border-[#1677ff] text-[#e2e8f0]"
                : "border-transparent text-[#64748b] hover:text-[#94a3b8]"
            }`}
          >
            审计链校验
          </button>
          <div className="ml-auto pb-1">
            {tab === "rtm" ? (
              <Button
                variant="outline"
                size="sm"
                onClick={refreshRtm}
                disabled={!projectId || loadingRtm}
                data-testid="rtm-refresh"
                className="border-[#1e293b] text-[#94a3b8] hover:text-white"
              >
                {loadingRtm ? (
                  <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5 mr-1" />
                )}
                {rtm ? "重新生成" : "生成矩阵"}
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={loadChain}
                disabled={!projectId || loadingChain}
                data-testid="chain-refresh"
                className="border-[#1e293b] text-[#94a3b8] hover:text-white"
              >
                {loadingChain ? (
                  <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5 mr-1" />
                )}
                重新校验
              </Button>
            )}
          </div>
        </div>

        <div className="min-h-0 overflow-y-auto scrollbar-dark pr-1">
          {tab === "rtm" ? (
            <div className="space-y-3 py-1">
              {errorRtm && !rtm && (
                <div
                  className="rounded-md border border-[#1e293b] bg-[#0b1020] px-3 py-6 text-center text-xs text-[#64748b]"
                  data-testid="rtm-empty"
                >
                  尚未生成追溯矩阵。
                  <div className="mt-1 text-[#475569]">{errorRtm}</div>
                </div>
              )}

              {loadingRtm && !rtm && (
                <div className="flex items-center justify-center gap-2 py-10 text-xs text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin" /> 正在加载追溯矩阵…
                </div>
              )}

              {rtm && (
                <>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-5" data-testid="rtm-summary">
                    <Stat label="需求" value={summary?.total_requirements ?? 0} />
                    <Stat label="设计覆盖" value={summary?.with_design_coverage ?? 0} />
                    <Stat label="实现覆盖" value={summary?.with_implementation ?? 0} />
                    <Stat label="测试覆盖" value={summary?.with_test_coverage ?? 0} />
                    <Stat label="测试覆盖率" value={`${summary?.coverage_pct ?? 0}%`} tone="accent" />
                  </div>

                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-[#64748b]">
                    <span>生成时间：{fmtTime(rtm.generated)}</span>
                    {rtm.baseline && <span>基线：{rtm.baseline}</span>}
                    {rtm.gate?.reason && <span>门禁：{rtm.gate.reason}</span>}
                    {summary?.orphaned_tests ? (
                      <span className="text-[#f59e0b]">孤立测试：{summary.orphaned_tests} 个</span>
                    ) : null}
                  </div>

                  {rows.length === 0 ? (
                    <div className="rounded-md border border-[#1e293b] px-3 py-6 text-center text-xs text-[#64748b]">
                      未解析到需求编号。请先在「需求」中输入带编号的需求（如 REQ-001 / SYS-001）。
                    </div>
                  ) : (
                    <table className="w-full text-left text-xs" data-testid="rtm-table">
                      <thead>
                        <tr className="text-[11px] text-[#64748b]">
                          <th className="py-1.5 pr-2 font-medium">需求</th>
                          <th className="py-1.5 pr-2 font-medium">设计</th>
                          <th className="py-1.5 pr-2 font-medium">代码</th>
                          <th className="py-1.5 pr-2 font-medium">测试</th>
                          <th className="py-1.5 pr-2 font-medium">评审</th>
                          <th className="py-1.5 font-medium">状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => {
                          const isOpen = !!expanded[row.req_id];
                          const covered = row.status === "Covered";
                          return (
                            <Fragment key={row.req_id}>
                              <tr
                                data-testid={`rtm-row-${row.req_id}`}
                                onClick={() =>
                                  setExpanded((s) => ({ ...s, [row.req_id]: !s[row.req_id] }))
                                }
                                className="cursor-pointer border-t border-[#1e293b] hover:bg-[#111827]"
                              >
                                <td className="py-1.5 pr-2">
                                  <div className="flex items-center gap-1">
                                    {isOpen ? (
                                      <ChevronDown className="w-3 h-3 text-[#64748b]" />
                                    ) : (
                                      <ChevronRight className="w-3 h-3 text-[#64748b]" />
                                    )}
                                    <span className="font-mono text-[#e2e8f0]">{row.req_id}</span>
                                    {row.statement && (
                                      <span className="ml-1 truncate text-[11px] text-[#64748b]">
                                        {row.statement}
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="py-1.5 pr-2"><CoverCell files={row.design_files} /></td>
                                <td className="py-1.5 pr-2"><CoverCell files={row.code_files} /></td>
                                <td className="py-1.5 pr-2"><CoverCell files={row.test_files} /></td>
                                <td className="py-1.5 pr-2">
                                  {row.has_review ? (
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[#10b981]" />
                                  ) : (
                                    <span className="text-[#475569]">—</span>
                                  )}
                                </td>
                                <td className="py-1.5">
                                  <span
                                    className={`rounded-full border px-2 py-0.5 text-[10px] ${
                                      covered
                                        ? "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]"
                                        : "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]"
                                    }`}
                                  >
                                    {covered ? "已覆盖" : "未覆盖"}
                                  </span>
                                </td>
                              </tr>
                              {isOpen && (
                                <tr className="border-t border-[#1e293b] bg-[#0b1020]">
                                  <td colSpan={6} className="px-3 py-2">
                                    <FileGroups row={row} onOpenArtifact={onOpenArtifact} />
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  )}

                  {rtm.orphaned_test_files?.length > 0 && (
                    <div className="rounded-md border border-[#f59e0b]/30 bg-[#f59e0b]/5 px-3 py-2 text-[11px] text-[#fbbf24]">
                      <div className="mb-1 flex items-center gap-1">
                        <AlertTriangle className="w-3.5 h-3.5" /> 未关联需求的测试文件
                      </div>
                      <div className="font-mono text-[#94a3b8]">
                        {rtm.orphaned_test_files.slice(0, 10).join("、")}
                        {rtm.orphaned_test_files.length > 10 ? ` 等 ${rtm.orphaned_test_files.length} 个` : ""}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="space-y-3 py-1">
              {errorChain && !chain && (
                <div
                  className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
                  data-testid="chain-empty"
                >
                  {errorChain}
                </div>
              )}

              {loadingChain && !chain && (
                <div className="flex items-center justify-center gap-2 py-10 text-xs text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin" /> 正在校验证据链…
                </div>
              )}

              {chain && (
                <>
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-[#64748b]">
                    <ChainStatusChip status={chain.status} />
                    <span>校验时间：{fmtTime(chain.generated_at)}</span>
                    <span>数据源：{chain.source || "—"}</span>
                    {chain.problem_total > chain.problems.length && (
                      <span>问题共 {chain.problem_total} 条，展示前 {chain.problems.length} 条</span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
                    <Stat label="需求" value={num(chain.summary.requirements)} />
                    <Stat label="节点" value={num(chain.summary.nodes)} />
                    <Stat label="边" value={num(chain.summary.edges)} />
                    <Stat label="测试覆盖" value={`${num(chain.summary.test_coverage_pct)}%`} />
                    <Stat label="代码覆盖" value={`${num(chain.summary.code_coverage_pct)}%`} />
                    <Stat
                      label="门禁"
                      value={`${num(chain.summary.gates_pass)}/${num(chain.summary.gates_pass) + num(chain.summary.gates_fail)}`}
                      tone={num(chain.summary.gates_fail) ? "warn" : "accent"}
                    />
                  </div>

                  <div className="grid gap-3 lg:grid-cols-2">
                    <section>
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                        门禁结果
                      </div>
                      <div className="space-y-1" data-testid="chain-gates">
                        {chain.gates.length === 0 && (
                          <div className="text-xs text-[#475569]">暂无可评估门禁。</div>
                        )}
                        {chain.gates.map((g) => (
                          <div
                            key={`${g.id}-${g.detail}`}
                            className="flex items-start gap-2 rounded border border-[#1e293b] px-2 py-1.5"
                          >
                            {g.status === "PASS" ? (
                              <CheckCircle2 className="mt-0.5 w-3.5 h-3.5 shrink-0 text-[#10b981]" />
                            ) : g.status === "FAIL" ? (
                              <XCircle className="mt-0.5 w-3.5 h-3.5 shrink-0 text-[#ef4444]" />
                            ) : (
                              <AlertTriangle className="mt-0.5 w-3.5 h-3.5 shrink-0 text-[#f59e0b]" />
                            )}
                            <div className="min-w-0">
                              <div className="font-mono text-[11px] text-[#e2e8f0]">{g.id}</div>
                              <div className="truncate text-[11px] text-[#64748b]" title={g.detail}>
                                {g.detail}
                              </div>
                            </div>
                            <span
                              className={`ml-auto shrink-0 text-[10px] ${
                                g.status === "PASS"
                                  ? "text-[#34d399]"
                                  : g.status === "FAIL"
                                    ? "text-[#f87171]"
                                    : "text-[#fbbf24]"
                              }`}
                            >
                              {g.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    </section>

                    <section>
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                        问题（ERROR / WARNING）
                      </div>
                      <div className="space-y-1" data-testid="chain-problems">
                        {chain.problems.length === 0 && (
                          <div className="text-xs text-[#475569]">未发现问题。</div>
                        )}
                        {chain.problems.map((p, i) => (
                          <div
                            key={`${p.code}-${i}`}
                            className="rounded border border-[#1e293b] px-2 py-1.5"
                          >
                            <div className="flex items-center gap-2">
                              <span
                                className={`rounded px-1.5 py-0.5 text-[10px] ${
                                  p.severity === "ERROR"
                                    ? "bg-[#ef4444]/15 text-[#f87171]"
                                    : "bg-[#f59e0b]/15 text-[#fbbf24]"
                                }`}
                              >
                                {p.severity}
                              </span>
                              <span className="font-mono text-[11px] text-[#e2e8f0]">{p.code}</span>
                            </div>
                            <div className="mt-0.5 text-[11px] leading-relaxed text-[#94a3b8]">
                              {p.message}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "default" | "accent" | "warn";
}) {
  const toneClass =
    tone === "accent" ? "text-[#34d399]" : tone === "warn" ? "text-[#fbbf24]" : "text-[#e2e8f0]";
  return (
    <div className="rounded-md border border-[#1e293b] bg-[#0b1020] px-2 py-1.5">
      <div className="text-[10px] text-[#64748b]">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${toneClass}`}>{value}</div>
    </div>
  );
}

function FileGroups({
  row,
  onOpenArtifact,
}: {
  row: RtmRequirement;
  onOpenArtifact?: (path: string) => void;
}) {
  const groups: Array<[string, string[]]> = [
    ["设计", row.design_files || []],
    ["代码", row.code_files || []],
    ["测试", row.test_files || []],
  ];
  return (
    <div className="space-y-1 text-[11px]">
      {groups.map(([label, files]) => (
        <div key={label} className="flex gap-2">
          <span className="w-8 shrink-0 text-[#64748b]">{label}</span>
          <span className="flex flex-wrap gap-x-1 font-mono text-[#94a3b8]">
            {files.length
              ? files.map((file, idx) => (
                <span key={file}>
                  <button
                    type="button"
                    data-testid={`rtm-file-${file}`}
                    onClick={() => onOpenArtifact?.(file)}
                    className="underline-offset-2 hover:text-[#38bdf8] hover:underline"
                    title={`打开 ${file}`}
                  >
                    {file}
                  </button>
                  {idx < files.length - 1 ? "、" : ""}
                </span>
              ))
              : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Flag,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-fetch";

// ─── Types ────────────────────────────────────────────────────────────────

export type RiskStatus = "open" | "mitigated" | "closed";
export type MilestoneStatus = "not_started" | "in_progress" | "completed";
export type Scale = "low" | "medium" | "high";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface RiskRow {
  id: string;
  description: string;
  likelihood: Scale;
  impact: Scale;
  level: RiskLevel;
  status: RiskStatus;
  owner: string;
}

export interface RiskDetail extends RiskRow {
  mitigation: string;
  owner_role: string;
  acceptance: { accepted_by: string; role: string; accepted_at: string } | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface Milestone {
  id: string;
  title: string;
  target_date: string;
  deliverable: string;
  status: MilestoneStatus;
  created_at: string;
  updated_at: string;
}

interface ProjectMgmtDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

// ─── Metadata ─────────────────────────────────────────────────────────────

/** Mirrors yuleosh.desktop.project_mgmt._LEVEL_MATRIX. */
export const RISK_MATRIX: Record<Scale, Record<Scale, RiskLevel>> = {
  low: { low: "low", medium: "low", high: "medium" },
  medium: { low: "low", medium: "medium", high: "high" },
  high: { low: "medium", medium: "high", high: "critical" },
};

const LEVEL_META: Record<RiskLevel, { label: string; cls: string; bg: string }> = {
  low: {
    label: "低",
    cls: "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]",
    bg: "bg-[#10b981]/15",
  },
  medium: {
    label: "中",
    cls: "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]",
    bg: "bg-[#f59e0b]/15",
  },
  high: {
    label: "高",
    cls: "border-[#f97316]/40 bg-[#f97316]/10 text-[#fb923c]",
    bg: "bg-[#f97316]/20",
  },
  critical: {
    label: "严重",
    cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]",
    bg: "bg-[#ef4444]/25",
  },
};

const RISK_STATUS_META: Record<RiskStatus, { label: string; cls: string }> = {
  open: { label: "未缓解", cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]" },
  mitigated: { label: "已缓解", cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]" },
  closed: { label: "已关闭", cls: "border-[#475569]/40 bg-[#475569]/10 text-[#64748b]" },
};

const MILESTONE_STATUS_META: Record<MilestoneStatus, { label: string; cls: string }> = {
  not_started: { label: "未开始", cls: "border-[#475569]/40 bg-[#475569]/10 text-[#94a3b8]" },
  in_progress: { label: "进行中", cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]" },
  completed: { label: "已完成", cls: "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]" },
};

const SCALES: Scale[] = ["low", "medium", "high"];
const SCALE_LABEL: Record<Scale, string> = { low: "低", medium: "中", high: "高" };
const MILESTONE_STATUSES: MilestoneStatus[] = ["not_started", "in_progress", "completed"];

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function computeRiskLevel(likelihood: Scale, impact: Scale): RiskLevel {
  return RISK_MATRIX[likelihood]?.[impact] ?? "medium";
}

function LevelBadge({ level }: { level: RiskLevel }) {
  const meta = LEVEL_META[level] ?? LEVEL_META.medium;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

function RiskStatusBadge({ status }: { status: RiskStatus }) {
  const meta = RISK_STATUS_META[status] ?? RISK_STATUS_META.open;
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

function MilestoneStatusBadge({ status }: { status: MilestoneStatus }) {
  const meta = MILESTONE_STATUS_META[status] ?? MILESTONE_STATUS_META.not_started;
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端项目管理（MAN.3）：风险登记与影响矩阵、里程碑进度。 */
export function ProjectMgmtDialog({ open, onOpenChange, projectId }: ProjectMgmtDialogProps) {
  const [tab, setTab] = useState<"risks" | "milestones">("risks");
  const [risks, setRisks] = useState<RiskRow[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [selectedRiskId, setSelectedRiskId] = useState<string | null>(null);
  const [riskDetail, setRiskDetail] = useState<RiskDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // risk form
  const [riskDesc, setRiskDesc] = useState("");
  const [likelihood, setLikelihood] = useState<Scale>("medium");
  const [impact, setImpact] = useState<Scale>("medium");
  const [riskOwner, setRiskOwner] = useState("");
  const [riskNote, setRiskNote] = useState("");

  // milestone form
  const [msTitle, setMsTitle] = useState("");
  const [msDate, setMsDate] = useState("");
  const [msDeliverable, setMsDeliverable] = useState("");

  const skipDetailRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const [riskData, msData] = await Promise.all([
        apiFetch<{ risks: RiskRow[] }>(`/api/v1/desktop/projects/${projectId}/risks`),
        apiFetch<{ milestones: Milestone[] }>(`/api/v1/desktop/projects/${projectId}/milestones`),
      ]);
      const list = riskData.risks || [];
      setRisks(list);
      setMilestones(msData.milestones || []);
      setSelectedRiskId((cur) => (list.some((r) => r.id === cur) ? cur : list[0]?.id ?? null));
    } catch (e) {
      setError((e as Error).message || "加载风险与里程碑失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setTab("risks");
    setRisks([]);
    setMilestones([]);
    setSelectedRiskId(null);
    setRiskDetail(null);
    skipDetailRef.current = null;
    setRiskDesc("");
    setLikelihood("medium");
    setImpact("medium");
    setRiskOwner("");
    setRiskNote("");
    setMsTitle("");
    setMsDate("");
    setMsDeliverable("");
    setError("");
    setNotice("");
    load();
  }, [open, projectId, load]);

  // The list endpoint omits mitigation / acceptance — fetch them on selection.
  useEffect(() => {
    if (!open || !projectId || !selectedRiskId || tab !== "risks") {
      setRiskDetail(null);
      return;
    }
    if (skipDetailRef.current === selectedRiskId) {
      skipDetailRef.current = null;
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    apiFetch<{ risk: RiskDetail }>(
      `/api/v1/desktop/projects/${projectId}/risks/${selectedRiskId}`,
    )
      .then((data) => {
        if (!cancelled) setRiskDetail(data.risk);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message || "加载风险详情失败");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId, selectedRiskId, tab]);

  const stats = useMemo(() => {
    const open = risks.filter((r) => r.status === "open").length;
    const mitigated = risks.filter((r) => r.status === "mitigated").length;
    const critical = risks.filter((r) => r.level === "critical" && r.status !== "closed").length;
    const done = milestones.filter((m) => m.status === "completed").length;
    const pct = milestones.length ? Math.round((done / milestones.length) * 100) : 0;
    return { open, mitigated, critical, done, pct };
  }, [risks, milestones]);

  const matrixCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of risks) {
      if (r.status === "closed") continue;
      const key = `${r.likelihood}-${r.impact}`;
      counts[key] = (counts[key] ?? 0) + 1;
    }
    return counts;
  }, [risks]);

  const createRisk = async () => {
    if (!projectId || working) return;
    const desc = riskDesc.trim();
    if (!desc) {
      setError("风险描述不能为空");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ risk: RiskDetail }>(
        `/api/v1/desktop/projects/${projectId}/risks`,
        {
          method: "POST",
          body: JSON.stringify({
            description: desc,
            likelihood,
            impact,
            owner: riskOwner.trim() || "unassigned",
          }),
        },
      );
      setRisks((prev) => [data.risk, ...prev]);
      skipDetailRef.current = data.risk.id;
      setSelectedRiskId(data.risk.id);
      setRiskDetail(data.risk);
      setRiskDesc("");
      setRiskOwner("");
      setNotice(`已登记风险 ${data.risk.id}（等级：${LEVEL_META[data.risk.level].label}）`);
    } catch (e) {
      setError((e as Error).message || "登记风险失败");
    } finally {
      setWorking(false);
    }
  };

  const transitionRisk = async (target: RiskStatus) => {
    if (!projectId || !riskDetail || working) return;
    const note = riskNote.trim();
    if (target === "mitigated" && !note && !riskDetail.mitigation) {
      setError("标记已缓解需要填写缓解措施");
      return;
    }
    if (target === "closed" && !note) {
      setError("关闭风险需要填写管理批准人（accepted_by）");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const body: Record<string, string> = { status: target };
      if (target === "mitigated" && note) body.mitigation = note;
      if (target === "closed") body.accepted_by = note;
      const data = await apiFetch<{ risk: RiskDetail }>(
        `/api/v1/desktop/projects/${projectId}/risks/${riskDetail.id}/transition`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setRiskDetail(data.risk);
      setRisks((prev) =>
        prev.map((r) => (r.id === data.risk.id ? { ...r, status: data.risk.status } : r)),
      );
      setRiskNote("");
      setNotice(`${riskDetail.id} 状态已更新为${RISK_STATUS_META[target].label}`);
    } catch (e) {
      setError((e as Error).message || "风险状态流转失败");
    } finally {
      setWorking(false);
    }
  };

  const addMilestone = async () => {
    if (!projectId || working) return;
    const title = msTitle.trim();
    if (!title) {
      setError("里程碑标题不能为空");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ milestone: Milestone }>(
        `/api/v1/desktop/projects/${projectId}/milestones`,
        {
          method: "POST",
          body: JSON.stringify({
            title,
            target_date: msDate.trim(),
            deliverable: msDeliverable.trim(),
          }),
        },
      );
      setMilestones((prev) => [...prev, data.milestone]);
      setMsTitle("");
      setMsDate("");
      setMsDeliverable("");
      setNotice(`已添加里程碑 ${data.milestone.id}`);
    } catch (e) {
      setError((e as Error).message || "添加里程碑失败");
    } finally {
      setWorking(false);
    }
  };

  const updateMilestone = async (milestone: Milestone, status: MilestoneStatus) => {
    if (!projectId || working) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ milestone: Milestone }>(
        `/api/v1/desktop/projects/${projectId}/milestones/${milestone.id}`,
        { method: "PATCH", body: JSON.stringify({ status }) },
      );
      setMilestones((prev) =>
        prev.map((m) => (m.id === data.milestone.id ? data.milestone : m)),
      );
      setNotice(`${milestone.id} 状态已更新为${MILESTONE_STATUS_META[status].label}`);
    } catch (e) {
      setError((e as Error).message || "更新里程碑状态失败");
    } finally {
      setWorking(false);
    }
  };

  const exportReport = async () => {
    if (!projectId || working) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ path: string }>(
        `/api/v1/desktop/projects/${projectId}/project-mgmt/export`,
      );
      setNotice(`已导出项目管理报告：${data.path}`);
    } catch (e) {
      setError((e as Error).message || "导出项目管理报告失败");
    } finally {
      setWorking(false);
    }
  };

  const selectedRisk = riskDetail && riskDetail.id === selectedRiskId ? riskDetail : null;
  const overdue = (m: Milestone) =>
    Boolean(m.target_date) && m.status !== "completed" && m.target_date < today();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(95vw,1080px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Flag className="w-5 h-5 text-[#722ed1]" /> 风险与里程碑
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            MAN.3 项目管理：风险登记与似然×影响矩阵、缓解与管理批准闭环、里程碑进度与完成度。
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-1.5" data-testid="pm-tabs">
          {([
            ["risks", `风险（${risks.length}）`],
            ["milestones", `里程碑（${milestones.length}）`],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              data-testid={`pm-tab-${key}`}
              className={`rounded-md border px-2.5 py-1 text-[11px] transition-colors ${
                tab === key
                  ? "border-[#722ed1]/50 bg-[#722ed1]/15 text-[#c4b5fd]"
                  : "border-[#1e293b] text-[#94a3b8] hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            onClick={load}
            disabled={!projectId || loading}
            title="刷新"
            data-testid="pm-reload"
            className="ml-auto text-[#64748b] hover:text-white disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
          </button>
          <Button
            size="sm"
            variant="outline"
            onClick={exportReport}
            disabled={working || (!risks.length && !milestones.length)}
            data-testid="pm-export"
            className="h-7 border-[#1e293b] text-[11px] text-[#94a3b8] hover:text-white"
          >
            <FileText className="w-3 h-3 mr-1" />导出报告
          </Button>
        </div>

        {error && (
          <div
            className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
            data-testid="pm-error"
          >
            {error}
          </div>
        )}
        {notice && (
          <div
            className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]"
            data-testid="pm-notice"
          >
            {notice}
          </div>
        )}

        {tab === "risks" ? (
          <div
            className="grid min-h-0 gap-3 overflow-hidden md:grid-cols-[320px_1fr]"
            data-testid="pm-risks"
          >
            {/* 左：登记 + 列表 */}
            <div className="flex min-h-0 flex-col gap-2">
              <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5">
                <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-[#94a3b8]">
                  <Plus className="w-3 h-3" /> 登记风险
                </div>
                <div className="space-y-1.5">
                  <Input
                    value={riskDesc}
                    onChange={(e) => setRiskDesc(e.target.value)}
                    placeholder="风险描述（必填）"
                    data-testid="pm-risk-desc"
                    className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                  />
                  <div className="flex gap-1.5">
                    <select
                      value={likelihood}
                      onChange={(e) => setLikelihood(e.target.value as Scale)}
                      data-testid="pm-risk-likelihood"
                      className="h-8 flex-1 rounded-md border border-[#1e293b] bg-[#111827] px-1 text-[11px] text-[#e2e8f0]"
                    >
                      {SCALES.map((s) => (
                        <option key={s} value={s}>{`可能性：${SCALE_LABEL[s]}`}</option>
                      ))}
                    </select>
                    <select
                      value={impact}
                      onChange={(e) => setImpact(e.target.value as Scale)}
                      data-testid="pm-risk-impact"
                      className="h-8 flex-1 rounded-md border border-[#1e293b] bg-[#111827] px-1 text-[11px] text-[#e2e8f0]"
                    >
                      {SCALES.map((s) => (
                        <option key={s} value={s}>{`影响：${SCALE_LABEL[s]}`}</option>
                      ))}
                    </select>
                  </div>
                  <Input
                    value={riskOwner}
                    onChange={(e) => setRiskOwner(e.target.value)}
                    placeholder="责任人"
                    data-testid="pm-risk-owner"
                    className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                  />
                  <div
                    className="flex items-center justify-between rounded border border-[#1e293b] px-2 py-1 text-[10px] text-[#64748b]"
                    data-testid="pm-risk-preview"
                  >
                    <span>自动评级</span>
                    <LevelBadge level={computeRiskLevel(likelihood, impact)} />
                  </div>
                  <Button
                    size="sm"
                    onClick={createRisk}
                    disabled={!projectId || working}
                    data-testid="pm-risk-create"
                    className="h-8 w-full bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
                  >
                    {working ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "登记"}
                  </Button>
                </div>
              </section>

              <div
                className="min-h-0 flex-1 space-y-1 overflow-y-auto scrollbar-dark pr-1"
                data-testid="pm-risk-list"
              >
                {!loading && risks.length === 0 && (
                  <div
                    className="rounded-md border border-[#1e293b] px-3 py-6 text-center text-[11px] text-[#64748b]"
                    data-testid="pm-risk-empty"
                  >
                    还没有风险记录。
                  </div>
                )}
                {risks.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => {
                      setSelectedRiskId(r.id);
                      setRiskNote("");
                      setError("");
                      setNotice("");
                    }}
                    data-testid={`pm-risk-row-${r.id}`}
                    className={`w-full rounded-md border px-2 py-1.5 text-left transition-colors ${
                      r.id === selectedRiskId
                        ? "border-[#1677ff]/50 bg-[#1677ff]/10"
                        : "border-[#1e293b] hover:bg-[#111827]"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <LevelBadge level={r.level} />
                      <span className="ml-auto"><RiskStatusBadge status={r.status} /></span>
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-[#e2e8f0]">{r.description}</div>
                    <div className="mt-0.5 text-[10px] text-[#475569]">
                      {r.id} · 责任人 {r.owner || "unassigned"}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* 右：统计 + 矩阵 + 详情 */}
            <div className="min-h-0 space-y-2 overflow-y-auto scrollbar-dark pr-1">
              <div className="grid grid-cols-4 gap-2" data-testid="pm-risk-stats">
                <Stat label="风险总数" value={risks.length} />
                <Stat label="未缓解" value={stats.open} warn={stats.open > 0} />
                <Stat label="已缓解" value={stats.mitigated} />
                <Stat label="未关闭严重" value={stats.critical} warn={stats.critical > 0} />
              </div>

              <section className="rounded-md border border-[#1e293b] p-3">
                <div className="mb-2 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                  <ShieldCheck className="w-3.5 h-3.5" /> 风险矩阵（未关闭）
                </div>
                <table className="w-full border-separate border-spacing-1" data-testid="pm-risk-matrix">
                  <thead>
                    <tr>
                      <th className="w-16 text-[10px] font-normal text-[#475569]">可能性 \ 影响</th>
                      {SCALES.map((s) => (
                        <th key={s} className="text-[10px] font-normal text-[#64748b]">
                          {SCALE_LABEL[s]}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...SCALES].reverse().map((l) => (
                      <tr key={l}>
                        <td className="text-right text-[10px] text-[#64748b]">{SCALE_LABEL[l]}</td>
                        {SCALES.map((i) => {
                          const level = computeRiskLevel(l, i);
                          const count = matrixCounts[`${l}-${i}`] ?? 0;
                          return (
                            <td key={i}>
                              <div
                                data-testid={`pm-matrix-${l}-${i}`}
                                className={`flex h-9 items-center justify-center rounded border border-white/5 text-[11px] tabular-nums ${
                                  LEVEL_META[level].bg
                                } ${count ? "text-[#e2e8f0] font-semibold" : "text-[#475569]"}`}
                                title={`可能性${SCALE_LABEL[l]} × 影响${SCALE_LABEL[i]} → ${LEVEL_META[level].label}`}
                              >
                                {count || "·"}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              {!selectedRisk && !detailLoading && (
                <div className="rounded-md border border-[#1e293b] px-3 py-8 text-center text-xs text-[#64748b]">
                  选择左侧的风险查看详情。
                </div>
              )}

              {selectedRisk && (
                <section className="rounded-md border border-[#1e293b] p-3" data-testid="pm-risk-detail">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-[#e2e8f0]">{selectedRisk.id}</span>
                    <LevelBadge level={selectedRisk.level} />
                    <RiskStatusBadge status={selectedRisk.status} />
                    <span className="text-[10px] text-[#475569]">
                      可能性 {SCALE_LABEL[selectedRisk.likelihood]} × 影响 {SCALE_LABEL[selectedRisk.impact]}
                    </span>
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#e2e8f0]">
                    {selectedRisk.description}
                  </div>
                  <div className="mt-1 grid gap-1 text-[10px] text-[#64748b] sm:grid-cols-2">
                    <div>责任人：{selectedRisk.owner || "unassigned"}</div>
                    <div>更新：{fmtTime(selectedRisk.updated_at)}</div>
                    <div>缓解措施：{selectedRisk.mitigation || "未填写"}</div>
                    <div>
                      批准关闭：
                      {selectedRisk.acceptance
                        ? `${selectedRisk.acceptance.accepted_by}（${selectedRisk.acceptance.role}）`
                        : "—"}
                    </div>
                  </div>

                  {selectedRisk.status !== "closed" && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <Input
                        value={riskNote}
                        onChange={(e) => setRiskNote(e.target.value)}
                        placeholder={
                          selectedRisk.status === "mitigated"
                            ? "管理批准人（关闭必填）"
                            : "缓解措施（标记已缓解必填）"
                        }
                        data-testid="pm-risk-note"
                        className="h-8 max-w-[240px] border-[#1e293b] bg-[#111827] text-xs"
                      />
                      {selectedRisk.status === "open" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => transitionRisk("mitigated")}
                          disabled={working}
                          data-testid="pm-risk-mitigate"
                          className="h-7 border-[#1677ff]/40 text-[11px] text-[#60a5fa] hover:bg-[#1677ff]/10"
                        >
                          <CheckCircle2 className="w-3 h-3 mr-1" />标记已缓解
                        </Button>
                      )}
                      {selectedRisk.status === "mitigated" && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => transitionRisk("closed")}
                            disabled={working}
                            data-testid="pm-risk-close"
                            className="h-7 border-[#10b981]/40 text-[11px] text-[#34d399] hover:bg-[#10b981]/10"
                          >
                            <CheckCircle2 className="w-3 h-3 mr-1" />批准关闭
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => transitionRisk("open")}
                            disabled={working}
                            data-testid="pm-risk-reopen"
                            className="h-7 border-[#1e293b] text-[11px] text-[#94a3b8] hover:text-white"
                          >
                            <RotateCcw className="w-3 h-3 mr-1" />重新打开
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                </section>
              )}
            </div>
          </div>
        ) : (
          <div className="grid min-h-0 gap-3 overflow-hidden md:grid-cols-[320px_1fr]" data-testid="pm-milestones">
            {/* 左：新增里程碑 */}
            <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5">
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-[#94a3b8]">
                <Plus className="w-3 h-3" /> 新增里程碑
              </div>
              <div className="space-y-1.5">
                <Input
                  value={msTitle}
                  onChange={(e) => setMsTitle(e.target.value)}
                  placeholder="里程碑标题（必填）"
                  data-testid="pm-ms-title"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Input
                  type="date"
                  value={msDate}
                  onChange={(e) => setMsDate(e.target.value)}
                  data-testid="pm-ms-date"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Input
                  value={msDeliverable}
                  onChange={(e) => setMsDeliverable(e.target.value)}
                  placeholder="交付物（可选）"
                  data-testid="pm-ms-deliverable"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Button
                  size="sm"
                  onClick={addMilestone}
                  disabled={!projectId || working}
                  data-testid="pm-ms-create"
                  className="h-8 w-full bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
                >
                  {working ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "添加"}
                </Button>
              </div>
            </section>

            {/* 右：进度 + 列表 */}
            <div className="min-h-0 space-y-2 overflow-y-auto scrollbar-dark pr-1">
              <section className="rounded-md border border-[#1e293b] p-3" data-testid="pm-progress">
                <div className="flex items-center justify-between text-[11px] text-[#94a3b8]">
                  <span>完成度</span>
                  <span className="tabular-nums text-[#e2e8f0]">
                    {stats.done}/{milestones.length} · {stats.pct}%
                  </span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#1e293b]">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-[#10b981] to-[#34d399] transition-all duration-300"
                    style={{ width: `${stats.pct}%` }}
                  />
                </div>
                <div className="mt-1.5 flex gap-3 text-[10px] text-[#64748b]">
                  {MILESTONE_STATUSES.map((s) => (
                    <span key={s}>
                      {MILESTONE_STATUS_META[s].label}{" "}
                      {milestones.filter((m) => m.status === s).length}
                    </span>
                  ))}
                </div>
              </section>

              {milestones.length === 0 ? (
                <div
                  className="rounded-md border border-[#1e293b] px-3 py-8 text-center text-xs text-[#64748b]"
                  data-testid="pm-ms-empty"
                >
                  还没有里程碑。
                </div>
              ) : (
                <div className="space-y-1.5" data-testid="pm-ms-list">
                  {milestones.map((m) => (
                    <div
                      key={m.id}
                      data-testid={`pm-ms-row-${m.id}`}
                      className="rounded-md border border-[#1e293b] px-2.5 py-2"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[11px] text-[#e2e8f0]">{m.title}</span>
                        <MilestoneStatusBadge status={m.status} />
                        {overdue(m) && (
                          <span className="rounded border border-[#ef4444]/40 bg-[#ef4444]/10 px-1.5 py-0.5 text-[10px] text-[#f87171]">
                            <AlertTriangle className="mr-1 inline w-3 h-3" />已逾期
                          </span>
                        )}
                        <select
                          value={m.status}
                          onChange={(e) => updateMilestone(m, e.target.value as MilestoneStatus)}
                          disabled={working}
                          data-testid={`pm-ms-status-${m.id}`}
                          className="ml-auto h-7 rounded border border-[#1e293b] bg-[#111827] px-1 text-[10px] text-[#94a3b8]"
                        >
                          {MILESTONE_STATUSES.map((s) => (
                            <option key={s} value={s}>{MILESTONE_STATUS_META[s].label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-[#64748b]">
                        <span>目标日期：{m.target_date || "—"}</span>
                        <span>交付物：{m.deliverable || "—"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Stat({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className="rounded-md border border-[#1e293b] bg-[#0b1020] px-2 py-1.5">
      <div className="text-[10px] text-[#64748b]">{label}</div>
      <div
        className={`text-sm font-semibold tabular-nums ${
          warn ? "text-[#f87171]" : "text-[#e2e8f0]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

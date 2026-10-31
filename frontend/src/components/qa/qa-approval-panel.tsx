"use client";

import { useCallback, useEffect, useState } from "react";
import { approveQaAudit, getQaAudit, listQaAudits } from "@/lib/qa-api";
import type { AuditStatus, QaAudit, QaAuditSummary } from "@/lib/qa-api";

const STATUS_LABEL: Record<AuditStatus, string> = {
  open: "进行中",
  pending_approval: "待批准",
  closed: "已关闭",
};

export function QaApprovalPanel({ projectId }: { projectId: string }) {
  const [audits, setAudits] = useState<QaAuditSummary[]>([]);
  const [active, setActive] = useState<QaAudit | null>(null);
  const [approver, setApprover] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setAudits(await listQaAudits(projectId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载审计列表失败");
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openDetail = useCallback(
    async (auditId: string) => {
      setError(null);
      try {
        setActive(await getQaAudit(projectId, auditId));
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载审计详情失败");
      }
    },
    [projectId],
  );

  const canApprove =
    !!active &&
    active.status === "pending_approval" &&
    active.findings.every((f) => f.status === "closed") &&
    approver.trim().length > 0;

  const onApprove = useCallback(async () => {
    if (!active || !canApprove) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await approveQaAudit(projectId, active.id, {
        approver: approver.trim(),
        role: "qa_lead",
        note: note.trim(),
      });
      setActive(updated);
      setApprover("");
      setNote("");
      await refresh();
    } catch (e) {
      // 400：approver 缺失 / 仍有未关闭不符合项，直接展示后端原文。
      setError(e instanceof Error ? e.message : "批准失败");
    } finally {
      setBusy(false);
    }
  }, [active, canApprove, approver, note, projectId, refresh]);

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-600">{error}</p>}

      <ul className="divide-y">
        {audits.map((a) => (
          <li key={a.id} className="flex items-center justify-between py-2">
            <button className="text-left" onClick={() => openDetail(a.id)}>
              <span className="font-medium">{a.title}</span>
              <span className="ml-2 text-xs text-gray-500">
                {STATUS_LABEL[a.status]} · {a.open_findings}/{a.finding_count} 未关闭
                {a.approved_by && ` · 批准人 ${a.approved_by}`}
              </span>
            </button>
            {a.status === "pending_approval" && (
              <button
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-40"
                onClick={() => openDetail(a.id)}
              >
                批准
              </button>
            )}
          </li>
        ))}
      </ul>

      {active && (
        <section className="rounded border p-4">
          <h3 className="font-semibold">
            {active.title}（{STATUS_LABEL[active.status]}）
          </h3>
          <p className="text-xs text-gray-500">
            审计员：{active.auditor}（{active.auditor_role}）
          </p>

          {active.findings.length === 0 ? (
            <p className="mt-2 text-sm text-amber-700">
              该审计无不符合项记录；批准仅表示管理层确认，不代表质量合格。
            </p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm">
              {active.findings.map((f) => (
                <li key={f.id}>
                  [{f.severity}] {f.description} — {f.status}
                  {f.assigned_to !== "unassigned" && ` · 责任人 ${f.assigned_to}`}
                </li>
              ))}
            </ul>
          )}

          {active.status === "pending_approval" && (
            <div className="mt-4 space-y-2">
              <input
                className="w-full rounded border px-2 py-1"
                placeholder="批准人（必填）"
                value={approver}
                onChange={(e) => setApprover(e.target.value)}
              />
              <input
                className="w-full rounded border px-2 py-1"
                placeholder="备注（可选）"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <button
                className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white disabled:opacity-40"
                disabled={!canApprove || busy}
                onClick={onApprove}
              >
                {busy ? "提交中…" : "确认批准并关闭"}
              </button>
            </div>
          )}

          {active.status === "closed" && active.approval && (
            <p className="mt-3 text-sm text-green-700">
              已于 {active.approval.approved_at} 由 {active.approval.approved_by}
              （{active.approval.role}）批准。
            </p>
          )}
        </section>
      )}
    </div>
  );
}

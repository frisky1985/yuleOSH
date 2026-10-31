/**
 * QA 审计 API 封装（SUP.1）。
 *
 * 严格对齐桌面 API 返回结构：
 *   - 列表 GET  → `{ ok, audits }`
 *   - 详情 GET  → `{ ok, audit }`
 *   - 批准 POST → `{ ok, audit }`（失败返回 400 + `{ ok:false, error }`，
 *     apiFetch 会抛出带后端原文的 Error）
 */
import { apiFetch } from "@/lib/api-fetch";

export type AuditStatus = "open" | "pending_approval" | "closed";

export interface QaApproval {
  approved_by: string;
  role: string;
  note: string;
  approved_at: string;
}

export interface QaFinding {
  id: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "acknowledged" | "resolved" | "closed";
  assigned_to: string;
  verifier?: string;
}

export interface QaAudit {
  id: string;
  title: string;
  auditor: string;
  auditor_role: string;
  status: AuditStatus;
  approval: QaApproval | null;
  findings: QaFinding[];
}

export interface QaAuditSummary {
  id: string;
  title: string;
  auditor_role: string;
  status: AuditStatus;
  approved_by: string;
  finding_count: number;
  open_findings: number;
}

function auditBase(projectId: string): string {
  return `/api/v1/desktop/projects/${encodeURIComponent(projectId)}/qa`;
}

export async function listQaAudits(projectId: string): Promise<QaAuditSummary[]> {
  const res = await apiFetch<{ audits: QaAuditSummary[] }>(auditBase(projectId));
  return res.audits ?? [];
}

export async function getQaAudit(
  projectId: string,
  auditId: string,
): Promise<QaAudit> {
  const res = await apiFetch<{ audit: QaAudit }>(
    `${auditBase(projectId)}/${encodeURIComponent(auditId)}`,
  );
  return res.audit;
}

/** 批准并关闭审计。后端要求 approver 非空，且所有不符合项已关闭。 */
export async function approveQaAudit(
  projectId: string,
  auditId: string,
  payload: { approver: string; role?: string; note?: string },
): Promise<QaAudit> {
  const res = await apiFetch<{ audit: QaAudit }>(
    `${auditBase(projectId)}/${encodeURIComponent(auditId)}/approve`,
    { method: "POST", body: JSON.stringify(payload) },
  );
  return res.audit;
}

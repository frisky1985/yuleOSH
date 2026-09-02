// 证据包生成历史（前端本地持久化，localStorage，按项目隔离）。
//
// 头脑风暴项⑨「证据历史与下载」：后端 evidence 仅提供 generate/status，无列出
// 历史接口（与差距批量 _gap_batches 同理），故历史在前端本地记录，刷新/重进
// 可回看并再次下载。每条记录一次证据包生成（成功/失败）。
//
// 设计要点（与 gap-run-history 一致）：
// - 所有读写包 try/catch，隐私模式 / 配额满时静默降级。
// - 每项目最多保留 MAX_PER_PROJECT 条，超出丢弃最旧。

export type EvidenceHistoryStatus = "completed" | "failed";

export interface EvidenceHistoryEntry {
  id: string;
  projectId: string;
  taskId: string | null;
  download_url: string | null;
  note: string | null;
  status: EvidenceHistoryStatus;
  createdAt: number; // epoch ms
}

const PREFIX = "yuleosh_evidence_history_";
const MAX_PER_PROJECT = 20;

export function evidenceHistoryKey(projectId: string): string {
  return `${PREFIX}${projectId}`;
}

function newId(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return crypto.randomUUID();
    }
  } catch {
    /* ignore */
  }
  return `ev-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function listEvidenceHistory(projectId: string): EvidenceHistoryEntry[] {
  if (typeof window === "undefined" || !projectId) return [];
  try {
    const raw = window.localStorage.getItem(evidenceHistoryKey(projectId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter(
          (r): r is EvidenceHistoryEntry =>
            r && typeof r.id === "string" && typeof r.projectId === "string",
        )
      : [];
  } catch {
    return [];
  }
}

/** 新增一条证据生成记录（置顶），超量截断最旧。返回该记录 id。 */
export function recordEvidence(
  projectId: string,
  rec: {
    taskId?: string | null;
    download_url?: string | null;
    note?: string | null;
    status: EvidenceHistoryStatus;
    createdAt?: number;
  },
): string {
  const id = newId();
  const full: EvidenceHistoryEntry = {
    id,
    projectId,
    taskId: rec.taskId ?? null,
    download_url: rec.download_url ?? null,
    note: rec.note ?? null,
    status: rec.status,
    createdAt: rec.createdAt ?? Date.now(),
  };
  if (typeof window === "undefined" || !projectId) return id;
  try {
    const next = [full, ...listEvidenceHistory(projectId)].slice(0, MAX_PER_PROJECT);
    window.localStorage.setItem(evidenceHistoryKey(projectId), JSON.stringify(next));
  } catch {
    /* 忽略 */
  }
  return id;
}

export function clearEvidenceHistory(projectId: string): void {
  if (typeof window === "undefined" || !projectId) return;
  try {
    window.localStorage.removeItem(evidenceHistoryKey(projectId));
  } catch {
    /* 忽略 */
  }
}

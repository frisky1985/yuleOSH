// 差距批量运行历史（前端本地持久化，localStorage，按项目隔离）。
//
// 头脑风暴项④「运行历史」：后端 _gap_batches 为内存字典（重启即丢）且无列出
// 接口，故历史在前端本地记录，刷新/重进可回看。每条记录一次批量分析/修复运行。
//
// 设计要点（与 gap-selection 一致）：
// - 所有读写包 try/catch，隐私模式 / 配额满时静默降级。
// - 每项目最多保留 MAX_PER_PROJECT 条，超出丢弃最旧。

export type GapRunMode = "analyze" | "remediate";
export type GapRunStatus = "running" | "completed" | "failed";

export interface GapRunRecord {
  id: string;
  projectId: string;
  mode: GapRunMode;
  count: number;
  gapIds: string[];
  startedAt: number; // epoch ms
  status: GapRunStatus;
  batchId?: string;
}

const PREFIX = "yuleosh_gap_runs_";
const MAX_PER_PROJECT = 20;

export function gapRunsKey(projectId: string): string {
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
  return `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function listGapRuns(projectId: string): GapRunRecord[] {
  if (typeof window === "undefined" || !projectId) return [];
  try {
    const raw = window.localStorage.getItem(gapRunsKey(projectId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter(
          (r): r is GapRunRecord =>
            r && typeof r.id === "string" && typeof r.projectId === "string",
        )
      : [];
  } catch {
    return [];
  }
}

/** 新增一条运行记录（置顶），超量截断最旧。返回该记录 id。 */
export function recordGapRun(
  projectId: string,
  rec: Omit<GapRunRecord, "id" | "projectId" | "startedAt" | "status"> & {
    status?: GapRunStatus;
    startedAt?: number;
  },
): string {
  const id = newId();
  const full: GapRunRecord = {
    id,
    projectId,
    mode: rec.mode,
    count: rec.count,
    gapIds: rec.gapIds,
    batchId: rec.batchId,
    startedAt: rec.startedAt ?? Date.now(),
    status: rec.status ?? "running",
  };
  if (typeof window === "undefined" || !projectId) return id;
  try {
    const next = [full, ...listGapRuns(projectId)].slice(0, MAX_PER_PROJECT);
    window.localStorage.setItem(gapRunsKey(projectId), JSON.stringify(next));
  } catch {
    /* 忽略 */
  }
  return id;
}

export function updateGapRun(
  projectId: string,
  id: string,
  patch: Partial<Pick<GapRunRecord, "status" | "batchId">>,
): void {
  if (typeof window === "undefined" || !projectId) return;
  try {
    const runs = listGapRuns(projectId).map((r) =>
      r.id === id ? { ...r, ...patch } : r,
    );
    window.localStorage.setItem(gapRunsKey(projectId), JSON.stringify(runs));
  } catch {
    /* 忽略 */
  }
}

export function clearGapRuns(projectId: string): void {
  if (typeof window === "undefined" || !projectId) return;
  try {
    window.localStorage.removeItem(gapRunsKey(projectId));
  } catch {
    /* 忽略 */
  }
}

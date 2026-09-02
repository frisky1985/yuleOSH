// 差距分析批量选择持久化（localStorage，按项目隔离）。
//
// 用户在前端「差距分析」页勾选的差距项（selectedGapIds）在刷新 / 重进 /
// 切换项目后仍保留，避免每次进来重新勾选。按 projectId 分桶，互不污染。
//
// 设计要点：
// - 仅依赖浏览器 localStorage，无需后端端点（与 user-settings-dialog、
//   pipeline 的 persistSelected 保持一致的前端自包含持久化风格）。
// - 所有读写包 try/catch，隐私模式 / 配额满时静默降级，不影响主流程。
// - 空选择直接 removeItem，避免写入 "[]" 占位。

const PREFIX = "yuleosh_gap_sel_";

export function gapSelKey(projectId: string): string {
  return `${PREFIX}${projectId}`;
}

/** 读取某项目已持久化的差距选择；异常或缺失返回 []。 */
export function loadGapSelection(projectId: string): string[] {
  if (typeof window === "undefined" || !projectId) return [];
  try {
    const raw = window.localStorage.getItem(gapSelKey(projectId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((x): x is string => typeof x === "string")
      : [];
  } catch {
    return [];
  }
}

/** 持久化某项目的差距选择；空数组时清除键。 */
export function saveGapSelection(projectId: string, ids: string[]): void {
  if (typeof window === "undefined" || !projectId) return;
  try {
    if (!ids.length) {
      window.localStorage.removeItem(gapSelKey(projectId));
    } else {
      window.localStorage.setItem(gapSelKey(projectId), JSON.stringify([...new Set(ids)]));
    }
  } catch {
    /* 忽略隐私模式 / 配额满 */
  }
}

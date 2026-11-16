/**
 * 评审状态聚合：把 `/review` 接口返回的扁平评审记录按产物路径归并成
 * 「每个文件的最新状态」，供左侧产物树渲染状态圆点与图例统计。
 */

export type ReviewTone = "approved" | "needs_revision" | "rejected";

export interface ReviewLike {
  artifact: string;
  status: string;
  created_at: string;
}

export const REVIEW_TONE_META: Record<
  ReviewTone,
  { label: string; dot: string; text: string }
> = {
  approved: { label: "已批准", dot: "bg-[#10b981]", text: "text-[#10b981]" },
  needs_revision: { label: "待修订", dot: "bg-[#f59e0b]", text: "text-[#f59e0b]" },
  rejected: { label: "已拒绝", dot: "bg-[#ef4444]", text: "text-[#ef4444]" },
};

export const REVIEW_TONES: ReviewTone[] = ["approved", "needs_revision", "rejected"];

/** 目录聚合色优先级：越靠前越"需要关注"。 */
const TONE_SEVERITY: ReviewTone[] = ["rejected", "needs_revision", "approved"];

/** 树形文件节点（只依赖本模块需要的字段，避免耦合 UI 组件）。 */
export interface ReviewTreeFileNode {
  type: "dir" | "file";
  path: string;
  mtime?: number | null;
  children?: ReviewTreeFileNode[];
}

/** 左侧评审筛选器的取值。 */
export type ReviewFilter = "all" | "needs_revision" | "unreviewed" | "approved";


/**
 * 取每个产物的最新一条评审记录。
 *
 * 评审记录按追加写入，`created_at` 是 ISO 字符串，可直接按字典序比较；
 * 时间戳相同时后出现的记录获胜（写入顺序即评审顺序）。
 */
export function latestReviewByArtifact<T extends ReviewLike>(
  reviews: T[] | null | undefined,
): Map<string, T> {
  const latest = new Map<string, T>();
  for (const review of reviews || []) {
    if (!review?.artifact) continue;
    const prev = latest.get(review.artifact);
    if (!prev || (review.created_at || "") >= (prev.created_at || "")) {
      latest.set(review.artifact, review);
    }
  }
  return latest;
}

/** 把评审状态映射成可视化色系；pending / 空值等不参与标记。 */
export function reviewTone(status: string | null | undefined): ReviewTone | null {
  if (status === "approved") return "approved";
  if (status === "needs_revision") return "needs_revision";
  if (status === "rejected") return "rejected";
  return null;
}

/** 汇总「产物路径 → 色系」，未评审或状态不可视的产物不出现在结果里。 */
export function reviewToneByArtifact<T extends ReviewLike>(
  reviews: T[] | null | undefined,
): Record<string, ReviewTone> {
  const tones: Record<string, ReviewTone> = {};
  for (const [artifact, review] of latestReviewByArtifact(reviews)) {
    const tone = reviewTone(review.status);
    if (tone) tones[artifact] = tone;
  }
  return tones;
}

/** 统计各色系的产物数量，用于工具栏图例。 */
export function countReviewTones(
  tones: Record<string, ReviewTone> | null | undefined,
): Record<ReviewTone, number> {
  const counts: Record<ReviewTone, number> = {
    approved: 0,
    needs_revision: 0,
    rejected: 0,
  };
  for (const tone of Object.values(tones || {})) {
    if (tone in counts) counts[tone] += 1;
  }
  return counts;
}

/** 目录/分区聚合：取最严重的一个状态，全部未评审则返回 null。 */
export function aggregateReviewTone(
  tones: Array<ReviewTone | null | undefined>,
): ReviewTone | null {
  const present = new Set(tones.filter((t): t is ReviewTone => Boolean(t)));
  for (const tone of TONE_SEVERITY) {
    if (present.has(tone)) return tone;
  }
  return null;
}

/** 评审覆盖度：已评审文件数 / 文件总数。 */
export function reviewCoverage(
  paths: string[] | null | undefined,
  toneByArtifact: Record<string, ReviewTone> | null | undefined,
): { reviewed: number; total: number } {
  let reviewed = 0;
  for (const path of paths || []) {
    if (toneByArtifact?.[path]) reviewed += 1;
  }
  return { reviewed, total: paths?.length ?? 0 };
}

/**
 * 评审是否已过期：文件在最后一次评审之后被修改。
 *
 * 后端 mtime 是 Unix 秒，评审 `created_at` 是 ISO 字符串（无时区时按本地时间解析）。
 * 留 1 秒容差，避免同一秒内写入被误判。
 */
export function isReviewStale(
  fileMtimeSec: number | null | undefined,
  reviewCreatedAt: string | null | undefined,
): boolean {
  if (!fileMtimeSec || !reviewCreatedAt) return false;
  const reviewedAt = new Date(reviewCreatedAt).getTime();
  if (Number.isNaN(reviewedAt)) return false;
  return fileMtimeSec * 1000 > reviewedAt + 1000;
}

/**
 * 找出「评审已过期」的文件集合：文件有最新评审记录，但 mtime 晚于评审时间。
 */
export function staleArtifactsByTree(
  tree: ReviewTreeFileNode | null | undefined,
  latestReviews: Map<string, ReviewLike> | null | undefined,
): Set<string> {
  const stale = new Set<string>();
  if (!tree || !latestReviews) return stale;
  const walk = (node: ReviewTreeFileNode) => {
    if (node.type === "file") {
      const review = latestReviews.get(node.path);
      if (review && isReviewStale(node.mtime, review.created_at)) {
        stale.add(node.path);
      }
      return;
    }
    for (const child of node.children || []) walk(child);
  };
  walk(tree);
  return stale;
}

/**
 * 评审筛选器判定。
 *
 * - unreviewed：尚无任何可视评审结论
 * - needs_revision：待修订，或「已通过但文件随后被修改」（过期结论不可信）
 * - approved：已通过且未过期
 */
export function matchesReviewFilter(
  path: string,
  toneByArtifact: Record<string, ReviewTone> | null | undefined,
  filter: ReviewFilter,
  stalePaths?: Set<string> | null,
): boolean {
  if (filter === "all") return true;
  const tone = toneByArtifact?.[path] ?? null;
  const stale = Boolean(stalePaths?.has(path));
  if (filter === "unreviewed") return !tone;
  if (filter === "needs_revision") return tone === "needs_revision" || (tone === "approved" && stale);
  if (filter === "approved") return tone === "approved" && !stale;
  return true;
}


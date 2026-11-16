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

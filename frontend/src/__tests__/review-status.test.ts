import {
  countReviewTones,
  latestReviewByArtifact,
  reviewTone,
  reviewToneByArtifact,
} from "@/lib/review-status";

const rec = (artifact: string, status: string, created_at: string) => ({
  artifact,
  status,
  created_at,
});

describe("latestReviewByArtifact", () => {
  it("空输入返回空 Map", () => {
    expect(latestReviewByArtifact(null).size).toBe(0);
    expect(latestReviewByArtifact(undefined).size).toBe(0);
    expect(latestReviewByArtifact([]).size).toBe(0);
  });

  it("同一产物取 created_at 最新的一条", () => {
    const map = latestReviewByArtifact([
      rec("code/a.c", "needs_revision", "2026-01-01T00:00:00Z"),
      rec("code/a.c", "approved", "2026-01-02T00:00:00Z"),
      rec("code/a.c", "rejected", "2025-12-31T00:00:00Z"),
    ]);
    expect(map.get("code/a.c")?.status).toBe("approved");
  });

  it("时间戳相同时后写入的记录获胜", () => {
    const map = latestReviewByArtifact([
      rec("code/b.c", "rejected", "2026-01-01T00:00:00Z"),
      rec("code/b.c", "approved", "2026-01-01T00:00:00Z"),
    ]);
    expect(map.get("code/b.c")?.status).toBe("approved");
  });

  it("忽略缺少 artifact 的脏记录", () => {
    const map = latestReviewByArtifact([
      { artifact: "", status: "approved", created_at: "2026-01-01T00:00:00Z" },
      rec("code/c.c", "approved", "2026-01-01T00:00:00Z"),
    ]);
    expect(map.size).toBe(1);
    expect(map.has("code/c.c")).toBe(true);
  });
});

describe("reviewTone", () => {
  it("映射三种可视状态", () => {
    expect(reviewTone("approved")).toBe("approved");
    expect(reviewTone("needs_revision")).toBe("needs_revision");
    expect(reviewTone("rejected")).toBe("rejected");
  });

  it("pending / 未知 / 空值不标记", () => {
    expect(reviewTone("pending")).toBeNull();
    expect(reviewTone("something-else")).toBeNull();
    expect(reviewTone(null)).toBeNull();
    expect(reviewTone(undefined)).toBeNull();
  });
});

describe("reviewToneByArtifact", () => {
  it("按最新评审状态生成路径到色系的映射", () => {
    const tones = reviewToneByArtifact([
      rec("code/a.c", "needs_revision", "2026-01-01T00:00:00Z"),
      rec("code/a.c", "approved", "2026-01-03T00:00:00Z"),
      rec("tests/b.py", "rejected", "2026-01-02T00:00:00Z"),
      rec("design/c.md", "pending", "2026-01-02T00:00:00Z"),
    ]);
    expect(tones).toEqual({
      "code/a.c": "approved",
      "tests/b.py": "rejected",
    });
  });
});

describe("countReviewTones", () => {
  it("统计各色系数量", () => {
    expect(
      countReviewTones({
        "a.c": "approved",
        "b.c": "approved",
        "c.c": "needs_revision",
        "d.c": "rejected",
      }),
    ).toEqual({ approved: 2, needs_revision: 1, rejected: 1 });
  });

  it("空输入返回全 0", () => {
    expect(countReviewTones(null)).toEqual({
      approved: 0,
      needs_revision: 0,
      rejected: 0,
    });
  });
});

import {
  aggregateReviewTone,
  countReviewTones,
  isReviewStale,
  latestReviewByArtifact,
  matchesReviewFilter,
  reviewCoverage,
  reviewTone,
  reviewToneByArtifact,
  staleArtifactsByTree,
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

describe("aggregateReviewTone", () => {
  it("取最严重的状态", () => {
    expect(aggregateReviewTone(["approved", "needs_revision"])).toBe("needs_revision");
    expect(aggregateReviewTone(["approved", "rejected", "needs_revision"])).toBe("rejected");
  });

  it("全部未评审返回 null", () => {
    expect(aggregateReviewTone([])).toBeNull();
    expect(aggregateReviewTone([null, undefined])).toBeNull();
  });
});

describe("reviewCoverage", () => {
  it("统计已评审与总数", () => {
    expect(
      reviewCoverage(["a.c", "b.c", "c.c"], { "a.c": "approved", "c.c": "rejected" }),
    ).toEqual({ reviewed: 2, total: 3 });
  });

  it("空输入返回 0/0", () => {
    expect(reviewCoverage(null, null)).toEqual({ reviewed: 0, total: 0 });
  });
});

describe("isReviewStale", () => {
  const reviewedAt = "2026-01-01T10:00:00Z";
  const reviewedMs = new Date(reviewedAt).getTime();

  it("文件修改晚于评审时间 → 过期", () => {
    expect(isReviewStale(reviewedMs / 1000 + 120, reviewedAt)).toBe(true);
  });

  it("同一秒或更早 → 不过期", () => {
    expect(isReviewStale(reviewedMs / 1000, reviewedAt)).toBe(false);
    expect(isReviewStale(reviewedMs / 1000 - 60, reviewedAt)).toBe(false);
  });

  it("缺少 mtime 或时间非法 → 不过期", () => {
    expect(isReviewStale(null, reviewedAt)).toBe(false);
    expect(isReviewStale(123, "")).toBe(false);
    expect(isReviewStale(123, "not-a-date")).toBe(false);
  });
});

describe("staleArtifactsByTree", () => {
  const reviewedAt = "2026-01-01T10:00:00Z";
  const reviewedMs = new Date(reviewedAt).getTime();
  const tree = {
    type: "dir" as const,
    path: ".",
    children: [
      {
        type: "dir" as const,
        path: "code",
        children: [
          { type: "file" as const, path: "code/a.c", mtime: reviewedMs / 1000 + 60 },
          { type: "file" as const, path: "code/b.c", mtime: reviewedMs / 1000 - 60 },
        ],
      },
      { type: "file" as const, path: "code/c.c", mtime: reviewedMs / 1000 + 60 },
    ],
  };
  const latest = latestReviewByArtifact([
    rec("code/a.c", "approved", reviewedAt),
    rec("code/b.c", "approved", reviewedAt),
    rec("code/c.c", "needs_revision", reviewedAt),
  ]);

  it("只标记评审后被修改的文件", () => {
    expect(Array.from(staleArtifactsByTree(tree, latest))).toEqual(["code/a.c", "code/c.c"]);
  });

  it("无评审记录时不标记", () => {
    expect(staleArtifactsByTree(tree, new Map()).size).toBe(0);
  });
});

describe("matchesReviewFilter", () => {
  const tones = { "a.c": "approved" as const, "b.c": "needs_revision" as const };
  const stale = new Set(["a.c"]);

  it("all 全部保留", () => {
    expect(matchesReviewFilter("z.c", tones, "all")).toBe(true);
  });

  it("unreviewed 只保留无评审结论的文件", () => {
    expect(matchesReviewFilter("z.c", tones, "unreviewed")).toBe(true);
    expect(matchesReviewFilter("a.c", tones, "unreviewed")).toBe(false);
  });

  it("needs_revision 包含待修订与过期通过", () => {
    expect(matchesReviewFilter("b.c", tones, "needs_revision")).toBe(true);
    expect(matchesReviewFilter("a.c", tones, "needs_revision", stale)).toBe(true);
    expect(matchesReviewFilter("a.c", tones, "needs_revision")).toBe(false);
  });

  it("approved 排除过期结论", () => {
    expect(matchesReviewFilter("a.c", tones, "approved", new Set())).toBe(true);
    expect(matchesReviewFilter("a.c", tones, "approved", stale)).toBe(false);
  });
});

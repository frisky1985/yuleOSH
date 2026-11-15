/**
 * ReviewCenterDialog 单元测试。
 *
 * 覆盖点：
 *  - 跨产物列表包含未评审文件与统计
 *  - 按分区批量打标（POST 载荷）
 *  - 按 glob 批量打标
 *  - 未选文件时本地校验
 *  - 导出评审报告并展示预览
 *  - 清除评审记录
 *  - 状态筛选
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReviewCenterDialog } from "@/components/desktop/review-center-dialog";
import type { ReviewArtifactRow, ReviewCounts, ReviewSectionStat } from "@/components/desktop/review-center-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const ROWS: ReviewArtifactRow[] = [
  {
    artifact: "code/main.c",
    section: "code",
    status: "approved",
    review_id: "r1",
    comment: "结构清晰",
    author: "qa",
    reviewed_at: "2026-11-15T10:00:00",
  },
  {
    artifact: "code/util.c",
    section: "code",
    status: "unreviewed",
    review_id: null,
    comment: "",
    author: "",
    reviewed_at: null,
  },
  {
    artifact: "requirements/requirements.md",
    section: "requirements",
    status: "unreviewed",
    review_id: null,
    comment: "",
    author: "",
    reviewed_at: null,
  },
  {
    artifact: "tests/test_main.c",
    section: "tests",
    status: "needs_revision",
    review_id: "r2",
    comment: "缺少断言",
    author: "dev",
    reviewed_at: "2026-11-15T09:00:00",
  },
];

const COUNTS: ReviewCounts = {
  total_files: 4,
  approved: 1,
  rejected: 0,
  needs_revision: 1,
  unreviewed: 2,
};

const SECTIONS: ReviewSectionStat[] = [
  { section: "code", total: 2, approved: 1, rejected: 0, needs_revision: 0, unreviewed: 1 },
  { section: "requirements", total: 1, approved: 0, rejected: 0, needs_revision: 0, unreviewed: 1 },
  { section: "tests", total: 1, approved: 0, rejected: 0, needs_revision: 1, unreviewed: 0 },
];

const LIST_BODY = { artifacts: ROWS, counts: COUNTS, sections: SECTIONS };

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<ReviewCenterDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

function callMatching(predicate: (path: string, init?: RequestInit) => boolean) {
  return fetchMock.mock.calls.find(([path, init]) =>
    predicate(String(path), init as RequestInit | undefined),
  );
}

describe("ReviewCenterDialog", () => {
  it("展示跨产物列表、统计与未评审文件", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(LIST_BODY));
    renderDialog();

    expect(await screen.findByTestId("review-row-code/util.c")).toBeInTheDocument();
    expect(screen.getByTestId("review-stats")).toHaveTextContent("未评审2");
    expect(screen.getByTestId("review-stats")).toHaveTextContent("需处理1");
    expect(screen.getByTestId("review-row-code/main.c")).toHaveTextContent("通过");
    expect(screen.getByTestId("review-row-code/util.c")).toHaveTextContent("未评审");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/review",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByTestId("review-section-select")).toHaveValue("code");
  });

  it("按分区批量打标并刷新列表", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(LIST_BODY))
      .mockReturnValueOnce(jsonResponse({ matched: 2, created: 1, updated: 1 }))
      .mockReturnValueOnce(jsonResponse(LIST_BODY));
    renderDialog();
    await screen.findByTestId("review-row-code/util.c");

    fireEvent.change(screen.getByTestId("review-section-select"), {
      target: { value: "code" },
    });
    fireEvent.change(screen.getByTestId("review-bulk-status"), {
      target: { value: "approved" },
    });
    fireEvent.change(screen.getByTestId("review-bulk-comment"), {
      target: { value: "整体通过" },
    });
    fireEvent.click(screen.getByTestId("review-bulk-apply"));

    expect(await screen.findByTestId("review-notice")).toHaveTextContent("匹配 2 个文件");
    const call = callMatching((path) => path.endsWith("/review/bulk"))!;
    expect(call[0]).toBe("/api/v1/desktop/projects/p1/review/bulk");
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      scope: "section",
      section: "code",
      status: "approved",
      comment: "整体通过",
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("按 glob 批量打标时提交 pattern", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(LIST_BODY))
      .mockReturnValueOnce(jsonResponse({ matched: 2, created: 2, updated: 0 }))
      .mockReturnValueOnce(jsonResponse(LIST_BODY));
    renderDialog();
    await screen.findByTestId("review-row-code/util.c");

    fireEvent.click(screen.getByTestId("review-scope-glob"));
    fireEvent.change(screen.getByTestId("review-pattern"), {
      target: { value: "code/**/*.c" },
    });
    fireEvent.change(screen.getByTestId("review-bulk-status"), {
      target: { value: "needs_revision" },
    });
    fireEvent.click(screen.getByTestId("review-bulk-apply"));

    expect(await screen.findByTestId("review-notice")).toHaveTextContent("需修改");
    const call = callMatching((path) => path.endsWith("/review/bulk"))!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      scope: "glob",
      pattern: "code/**/*.c",
      status: "needs_revision",
      comment: "",
    });
  });

  it("未选文件时提示且不发请求", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(LIST_BODY));
    renderDialog();
    await screen.findByTestId("review-row-code/util.c");

    fireEvent.click(screen.getByTestId("review-scope-selected"));
    fireEvent.click(screen.getByTestId("review-bulk-apply"));

    expect(await screen.findByTestId("review-error")).toHaveTextContent("请先");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("选中文件后按产物批量打标", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(LIST_BODY))
      .mockReturnValueOnce(jsonResponse({ matched: 1, created: 1, updated: 0 }))
      .mockReturnValueOnce(jsonResponse(LIST_BODY));
    renderDialog();
    await screen.findByTestId("review-row-code/util.c");

    fireEvent.click(screen.getByTestId("review-check-code/util.c"));
    fireEvent.click(screen.getByTestId("review-scope-selected"));
    expect(screen.getByTestId("review-scope-selected")).toHaveTextContent("已选 1");
    fireEvent.click(screen.getByTestId("review-bulk-apply"));

    expect(await screen.findByTestId("review-notice")).toHaveTextContent("匹配 1 个文件");
    const call = callMatching((path) => path.endsWith("/review/bulk"))!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toMatchObject({
      scope: "artifact",
      artifacts: ["code/util.c"],
    });
  });

  it("导出评审报告并展示预览", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(LIST_BODY))
      .mockReturnValueOnce(jsonResponse({
        path: "evidence/review-report.md",
        content: "# 评审报告 — Demo\n\n## 未评审产物\n",
        reviewed_files: 2,
        total_files: 4,
      }));
    renderDialog();
    await screen.findByTestId("review-row-code/util.c");

    fireEvent.click(screen.getByTestId("review-export"));

    expect(await screen.findByTestId("review-notice")).toHaveTextContent("2/4");
    expect(screen.getByTestId("review-report-preview")).toHaveTextContent("未评审产物");
    const call = callMatching((path) => path.endsWith("/review/export"))!;
    expect(call[0]).toBe("/api/v1/desktop/projects/p1/review/export");
  });

  it("清除评审记录后恢复未评审", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(LIST_BODY))
      .mockReturnValueOnce(jsonResponse({ ok: true }))
      .mockReturnValueOnce(jsonResponse(LIST_BODY));
    renderDialog();
    await screen.findByTestId("review-row-code/main.c");

    fireEvent.click(screen.getByTestId("review-delete-code/main.c"));

    expect(await screen.findByTestId("review-notice")).toHaveTextContent("已清除");
    const call = callMatching(
      (path, init) => path.endsWith("/review/r1") && init?.method === "DELETE",
    )!;
    expect(call[0]).toBe("/api/v1/desktop/projects/p1/review/r1");
  });

  it("状态筛选只保留未评审文件", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(LIST_BODY));
    renderDialog();
    await screen.findByTestId("review-row-code/main.c");

    fireEvent.click(screen.getByTestId("review-filter-unreviewed"));

    expect(screen.getByTestId("review-row-code/util.c")).toBeInTheDocument();
    expect(screen.queryByTestId("review-row-code/main.c")).toBeNull();
    expect(screen.queryByTestId("review-row-tests/test_main.c")).toBeNull();
  });
});

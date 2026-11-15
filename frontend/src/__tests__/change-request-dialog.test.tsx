/**
 * ChangeRequestDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载列表并默认选中首条，展示详情与当前可执行动作
 *  - 创建变更请求（POST 载荷）与空标题本地校验
 *  - 草稿 → 影响分析：请求、状态更新、受影响需求/文件展示
 *  - 已分析 → 批准：状态流转载荷与界面切换
 *  - 已驳回 → 重新打开
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ChangeRequestDialog } from "@/components/desktop/change-request-dialog";
import type { ChangeRequest } from "@/components/desktop/change-request-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const HISTORY_DRAFT = [
  { from: null, to: "draft", author: "local", comment: "", at: "2026-11-15T09:00:00" },
];

const DRAFT: ChangeRequest = {
  id: "CR-20261115-aaaaaa",
  title: "调整车灯控制逻辑",
  reason: "客户要求支持自动大灯",
  author: "local",
  affected_requirements: ["REQ-001"],
  affected_artifacts: [],
  status: "draft",
  impact: null,
  history: HISTORY_DRAFT,
  created_at: "2026-11-15T09:00:00",
  updated_at: "2026-11-15T09:00:00",
};

const IMPACT = {
  change_request: DRAFT.id,
  generated_at: "2026-11-15T09:05:00",
  author: "local",
  requirements: [
    {
      id: "REQ-001",
      design: ["design/sdd.md"],
      code: ["code/main.c"],
      tests: ["tests/test_main.c"],
    },
  ],
  affected_artifacts: ["design/sdd.md", "code/main.c", "tests/test_main.c"],
  summary: { requirements: 1, code_files: 1, test_files: 1, design_files: 1 },
};

const ANALYZED: ChangeRequest = {
  ...DRAFT,
  status: "analyzed",
  impact: IMPACT,
  history: [
    ...HISTORY_DRAFT,
    { from: "draft", to: "analyzed", author: "local", comment: "", at: "2026-11-15T09:05:00" },
  ],
};

const REJECTED: ChangeRequest = {
  ...ANALYZED,
  status: "rejected",
  history: [
    ...ANALYZED.history,
    { from: "analyzed", to: "rejected", author: "local", comment: "影响面过大", at: "2026-11-15T09:10:00" },
  ],
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<ChangeRequestDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

describe("ChangeRequestDialog", () => {
  it("加载列表并默认选中首条，展示详情与可用动作", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ change_requests: [DRAFT] }));
    renderDialog();

    expect(await screen.findByTestId("cr-detail")).toHaveTextContent("调整车灯控制逻辑");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/change-requests",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByTestId(`cr-row-${DRAFT.id}`)).toHaveTextContent("草稿");
    expect(screen.getByTestId("cr-analyze")).toBeInTheDocument();
    expect(screen.getByTestId("cr-history")).toHaveTextContent("草稿");
  });

  it("创建变更请求时提交标题/原因/需求列表", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ change_requests: [] }));
    renderDialog();
    await screen.findByTestId("cr-empty");

    fetchMock.mockReturnValueOnce(jsonResponse({ change_request: DRAFT }, 201));
    fireEvent.change(screen.getByTestId("cr-title"), { target: { value: DRAFT.title } });
    fireEvent.change(screen.getByTestId("cr-reason"), { target: { value: DRAFT.reason } });
    fireEvent.change(screen.getByTestId("cr-requirements"), {
      target: { value: "REQ-001, REQ-002" },
    });
    fireEvent.click(screen.getByTestId("cr-create"));

    expect(await screen.findByTestId("cr-notice")).toHaveTextContent("已创建");
    const [path, opts] = fetchMock.mock.calls[1];
    expect(path).toBe("/api/v1/desktop/projects/p1/change-requests");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({
      title: DRAFT.title,
      reason: DRAFT.reason,
      requirements: ["REQ-001", "REQ-002"],
    });
    expect(await screen.findByTestId(`cr-row-${DRAFT.id}`)).toBeInTheDocument();
  });

  it("空标题时本地校验，不发创建请求", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ change_requests: [] }));
    renderDialog();
    await screen.findByTestId("cr-empty");

    fireEvent.click(screen.getByTestId("cr-create"));

    expect(await screen.findByTestId("cr-error")).toHaveTextContent("标题不能为空");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("草稿执行影响分析后展示受影响需求与文件", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ change_requests: [DRAFT] }));
    renderDialog();
    await screen.findByTestId("cr-detail");

    fetchMock.mockReturnValueOnce(jsonResponse({ impact: IMPACT, change_request: ANALYZED }));
    fireEvent.click(screen.getByTestId("cr-analyze"));

    expect(await screen.findByTestId("cr-impact")).toBeInTheDocument();
    const [path, opts] = fetchMock.mock.calls[1];
    expect(path).toBe(`/api/v1/desktop/projects/p1/change-requests/${DRAFT.id}/analyze`);
    expect(opts.method).toBe("POST");

    expect(screen.getByTestId("cr-impact-summary")).toHaveTextContent("受影响需求1");
    expect(screen.getByTestId("cr-impact")).toHaveTextContent("design/sdd.md");
    expect(screen.getByTestId("cr-impact")).toHaveTextContent("tests/test_main.c");
    expect(screen.getAllByTestId("cr-status-analyzed").length).toBeGreaterThan(0);
    expect(screen.getByTestId("cr-approve")).toBeInTheDocument();
  });

  it("已分析状态下批准并携带备注", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ change_requests: [ANALYZED] }));
    renderDialog();
    await screen.findByTestId("cr-approve");

    const approved = { ...ANALYZED, status: "approved" as const };
    fetchMock.mockReturnValueOnce(jsonResponse({ change_request: approved }));
    fireEvent.change(screen.getByTestId("cr-comment"), { target: { value: "同意实施" } });
    fireEvent.click(screen.getByTestId("cr-approve"));

    await waitFor(() =>
      expect(screen.getByTestId(`cr-row-${ANALYZED.id}`)).toHaveTextContent("已批准"),
    );
    const [path, opts] = fetchMock.mock.calls[1];
    expect(path).toBe(`/api/v1/desktop/projects/p1/change-requests/${ANALYZED.id}/transition`);
    expect(JSON.parse(opts.body)).toEqual({ status: "approved", comment: "同意实施" });
    expect(screen.getByTestId("cr-close")).toBeInTheDocument();
  });

  it("已驳回的变更请求可以重新打开", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ change_requests: [REJECTED] }));
    renderDialog();
    await screen.findByTestId("cr-reopen");

    fetchMock.mockReturnValueOnce(jsonResponse({ change_request: DRAFT }));
    fireEvent.click(screen.getByTestId("cr-reopen"));

    await waitFor(() =>
      expect(screen.getByTestId(`cr-row-${REJECTED.id}`)).toHaveTextContent("草稿"),
    );
    const [, opts] = fetchMock.mock.calls[1];
    expect(JSON.parse(opts.body)).toEqual({ status: "draft", comment: "" });
  });
});

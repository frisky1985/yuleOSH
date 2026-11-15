/**
 * IssueTrackerDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载列表 + 详情，默认选中首条并展示可用流转动作
 *  - 空标题本地校验，不发起创建请求
 *  - 创建问题（POST 载荷：标题/描述/严重度/责任人）
 *  - 严重度筛选
 *  - open → analyzed：携带根因分析并刷新状态
 *  - verified → closed：状态流转
 *  - 导出问题报告
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { IssueTrackerDialog } from "@/components/desktop/issue-tracker-dialog";
import type { IssueDetail, IssueRow } from "@/components/desktop/issue-tracker-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const ROW_OPEN: IssueRow = {
  id: "ISSUE-20261115-aaaaaa",
  title: "上电时车灯闪烁",
  severity: "high",
  status: "open",
  owner: "alice",
  created_at: "2026-11-15T09:00:00",
  closed_at: null,
};

const DETAIL_OPEN: IssueDetail = {
  ...ROW_OPEN,
  description: "冷启动 3 次中有 1 次出现闪烁",
  reported_by: "tester",
  verified_by: "",
  root_cause: "",
  resolution: "",
  verification: "",
  updated_at: "2026-11-15T09:00:00",
};

const DETAIL_ANALYZED: IssueDetail = {
  ...DETAIL_OPEN,
  status: "analyzed",
  root_cause: "电源时序冲突",
  updated_at: "2026-11-15T09:20:00",
};

const DETAIL_VERIFIED: IssueDetail = {
  ...DETAIL_OPEN,
  status: "verified",
  root_cause: "电源时序冲突",
  resolution: "增加上电延时",
  verification: "冷启动 20 次无闪烁",
  verified_by: "qa",
};

const ROW_LOW: IssueRow = {
  id: "ISSUE-20261115-bbbbbb",
  title: "日志缺少时间戳",
  severity: "low",
  status: "open",
  owner: "bob",
  created_at: "2026-11-15T09:10:00",
  closed_at: null,
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<IssueTrackerDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

function callWithSuffix(suffix: string) {
  return fetchMock.mock.calls.find(([path]) => String(path).endsWith(suffix));
}

describe("IssueTrackerDialog", () => {
  it("加载列表与详情，默认选中首条并展示可执行动作", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ issues: [ROW_OPEN] }))
      .mockReturnValueOnce(jsonResponse({ issue: DETAIL_OPEN }));
    renderDialog();

    expect(await screen.findByTestId("issue-detail")).toHaveTextContent("上电时车灯闪烁");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/issues",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByTestId("issue-stats")).toHaveTextContent("总计1");
    expect(screen.getByTestId("issue-move-analyzed")).toBeInTheDocument();
    expect(screen.getByTestId("issue-move-rejected")).toBeInTheDocument();
    expect(screen.getByTestId("issue-root-cause")).toHaveTextContent("未填写");
  });

  it("空标题时本地校验，不发创建请求", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ issues: [] }));
    renderDialog();
    await screen.findByTestId("issue-empty");

    fireEvent.click(screen.getByTestId("issue-create"));

    expect(await screen.findByTestId("issue-error")).toHaveTextContent("标题不能为空");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("创建问题时提交标题/描述/严重度/责任人", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ issues: [] }));
    renderDialog();
    await screen.findByTestId("issue-empty");

    fetchMock.mockReturnValueOnce(
      jsonResponse(
        {
          issue: {
            ...DETAIL_OPEN,
            id: "ISSUE-20261115-cccccc",
            title: "制动灯不亮",
            severity: "critical",
            owner: "carol",
          },
        },
        201,
      ),
    );
    fireEvent.change(screen.getByTestId("issue-title"), { target: { value: "制动灯不亮" } });
    fireEvent.change(screen.getByTestId("issue-description"), {
      target: { value: "踩刹车时制动灯无响应" },
    });
    fireEvent.change(screen.getByTestId("issue-severity"), { target: { value: "critical" } });
    fireEvent.change(screen.getByTestId("issue-owner"), { target: { value: "carol" } });
    fireEvent.click(screen.getByTestId("issue-create"));

    expect(await screen.findByTestId("issue-notice")).toHaveTextContent("已创建");
    const [, opts] = fetchMock.mock.calls.find(
      ([path, init]) => String(path).endsWith("/issues") && init?.method === "POST",
    )!;
    expect(JSON.parse(opts.body)).toEqual({
      title: "制动灯不亮",
      description: "踩刹车时制动灯无响应",
      severity: "critical",
      owner: "carol",
    });
    expect(screen.getAllByTestId("issue-status-open").length).toBeGreaterThan(0);
  });

  it("按严重度筛选列表", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ issues: [ROW_OPEN, ROW_LOW] }))
      .mockReturnValueOnce(jsonResponse({ issue: DETAIL_OPEN }));
    renderDialog();
    await screen.findByTestId("issue-detail");
    expect(screen.getByTestId(`issue-row-${ROW_LOW.id}`)).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("issue-severity-filter"), {
      target: { value: "low" },
    });

    expect(screen.queryByTestId(`issue-row-${ROW_OPEN.id}`)).toBeNull();
    expect(screen.getByTestId(`issue-row-${ROW_LOW.id}`)).toBeInTheDocument();
  });

  it("open → analyzed 时携带根因分析", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ issues: [ROW_OPEN] }))
      .mockReturnValueOnce(jsonResponse({ issue: DETAIL_OPEN }));
    renderDialog();
    await screen.findByTestId("issue-move-analyzed");

    fetchMock.mockReturnValueOnce(jsonResponse({ issue: DETAIL_ANALYZED }));
    fireEvent.change(screen.getByTestId("issue-note"), {
      target: { value: "电源时序冲突" },
    });
    fireEvent.click(screen.getByTestId("issue-move-analyzed"));

    expect(await screen.findByTestId("issue-notice")).toHaveTextContent("已分析");
    const [path, opts] = callWithSuffix(`/issues/${ROW_OPEN.id}/transition`)!;
    expect(path).toBe(`/api/v1/desktop/projects/p1/issues/${ROW_OPEN.id}/transition`);
    expect(JSON.parse(opts.body)).toEqual({
      status: "analyzed",
      root_cause: "电源时序冲突",
    });
    expect(screen.getByTestId("issue-root-cause")).toHaveTextContent("电源时序冲突");
    expect(screen.getByTestId("issue-move-resolved")).toBeInTheDocument();
  });

  it("已验证的问题可以关闭", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ issues: [{ ...ROW_OPEN, status: "verified" }] }))
      .mockReturnValueOnce(jsonResponse({ issue: DETAIL_VERIFIED }));
    renderDialog();
    await screen.findByTestId("issue-move-closed");

    fetchMock.mockReturnValueOnce(
      jsonResponse({ issue: { ...DETAIL_VERIFIED, status: "closed", closed_at: "2026-11-15T10:00:00" } }),
    );
    fireEvent.click(screen.getByTestId("issue-move-closed"));

    expect(await screen.findByTestId("issue-notice")).toHaveTextContent("已关闭");
    const [, opts] = callWithSuffix(`/issues/${ROW_OPEN.id}/transition`)!;
    expect(JSON.parse(opts.body)).toEqual({ status: "closed" });
    await waitFor(() =>
      expect(screen.getByTestId(`issue-row-${ROW_OPEN.id}`)).toHaveTextContent("已关闭"),
    );
  });

  it("导出问题报告并展示归档路径", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ issues: [ROW_OPEN] }))
      .mockReturnValueOnce(jsonResponse({ issue: DETAIL_OPEN }))
      .mockReturnValueOnce(
        jsonResponse({ path: "/tmp/p1/.osh/evidence/issue-report.md" }),
      );
    renderDialog();
    await screen.findByTestId("issue-detail");

    fireEvent.click(screen.getByTestId("issue-export"));

    expect(await screen.findByTestId("issue-notice")).toHaveTextContent("issue-report.md");
    const [path] = callWithSuffix("/issues/export")!;
    expect(path).toBe("/api/v1/desktop/projects/p1/issues/export");
  });
});

/**
 * PipelineRunDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时请求运行详情并展示步骤、日志、结果
 *  - 运行中状态自动轮询，结束后刷新为终态
 *  - 失败原因展示
 *  - 运行中 / 已有活跃运行时禁用「重新运行」
 *  - 加载失败展示错误
 *  - 关闭按钮回调
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { PipelineRunDialog } from "@/components/desktop/pipeline-run-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const fetchMock = jest.fn();

beforeAll(() => {
  if (!("ResizeObserver" in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = jest.fn();
});

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

afterEach(() => {
  jest.restoreAllMocks();
});

const baseDetail = {
  job_id: "job-abc123456",
  status: "passed",
  progress: 100,
  started_at: "2026-11-15T10:00:00",
  completed_at: "2026-11-15T10:01:30",
  stages: [
    { key: "arxml_parse", name: "解析需求", status: "passed" },
    { key: "ci_compile", name: "编译", status: "passed" },
  ],
  logs: ["[10:00:01] start", "[10:01:30] done"],
  logs_total: 12,
  result: { summary: "All 6 stages completed successfully" },
};

describe("PipelineRunDialog", () => {
  it("加载并展示步骤、日志与结果", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(baseDetail));

    render(
      <PipelineRunDialog open onOpenChange={jest.fn()} projectId="p1" jobId="job-abc123456" />,
    );

    expect(await screen.findByText("解析需求")).toBeInTheDocument();
    expect(screen.getByText("编译")).toBeInTheDocument();
    expect(screen.getByText("已通过")).toBeInTheDocument();
    expect(screen.getByText("12 条")).toBeInTheDocument();
    expect(screen.getByText("[10:00:01] start")).toBeInTheDocument();
    expect(screen.getByText("All 6 stages completed successfully")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/pipeline/status/job-abc123456",
      expect.anything(),
    );
  });

  it("运行中自动轮询，结束后更新为终态", async () => {
    fetchMock
      .mockReturnValueOnce(
        jsonResponse({
          ...baseDetail,
          status: "running",
          progress: 40,
          completed_at: null,
          logs: ["[10:00:01] start"],
          logs_total: 1,
          result: null,
        }),
      )
      .mockReturnValueOnce(jsonResponse(baseDetail));

    render(
      <PipelineRunDialog open onOpenChange={jest.fn()} projectId="p1" jobId="job-abc123456" />,
    );

    expect(await screen.findByText("运行中")).toBeInTheDocument();
    expect(await screen.findByText("已通过", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("失败时展示原因", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({
        ...baseDetail,
        status: "failed",
        progress: 70,
        result: { error: "ci_compile failed: syntax error" },
      }),
    );

    render(
      <PipelineRunDialog open onOpenChange={jest.fn()} projectId="p1" jobId="job-abc123456" />,
    );

    expect(await screen.findByText("ci_compile failed: syntax error")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();
  });

  it("运行中禁用「重新运行」", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({ ...baseDetail, status: "running", completed_at: null, result: null }),
    );

    render(
      <PipelineRunDialog
        open
        onOpenChange={jest.fn()}
        projectId="p1"
        jobId="job-abc123456"
        onRerun={jest.fn()}
      />,
    );

    expect(await screen.findByText("运行中")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重新运行/ })).toBeDisabled();
  });

  it("终态下可重新运行并回调", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(baseDetail));
    const onRerun = jest.fn();

    render(
      <PipelineRunDialog
        open
        onOpenChange={jest.fn()}
        projectId="p1"
        jobId="job-abc123456"
        onRerun={onRerun}
      />,
    );

    const btn = await screen.findByRole("button", { name: /重新运行/ });
    await screen.findByText("已通过");
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(onRerun).toHaveBeenCalledTimes(1);
  });

  it("加载失败展示错误", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({ ok: false, error: "Job not found" }, 404),
    );

    render(
      <PipelineRunDialog open onOpenChange={jest.fn()} projectId="p1" jobId="missing" />,
    );

    expect(await screen.findByText("Job not found")).toBeInTheDocument();
  });

  it("点击关闭触发 onOpenChange(false)", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(baseDetail));
    const onOpenChange = jest.fn();

    render(
      <PipelineRunDialog open onOpenChange={onOpenChange} projectId="p1" jobId="job-abc123456" />,
    );

    await screen.findByText("已通过");
    // 页脚「关闭」与右上角关闭图标同名，取页脚按钮。
    const closeButtons = screen.getAllByRole("button", { name: "关闭" });
    fireEvent.click(closeButtons[closeButtons.length - 1]);
    // Base UI 会附带事件详情作为第二个参数，只校验关闭意图。
    expect(onOpenChange.mock.calls[0][0]).toBe(false);
  });

  it("未打开时不发起请求", () => {
    render(
      <PipelineRunDialog open={false} onOpenChange={jest.fn()} projectId="p1" jobId="job-abc123456" />,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

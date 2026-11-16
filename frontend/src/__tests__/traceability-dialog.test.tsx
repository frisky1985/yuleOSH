/**
 * TraceabilityDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载 RTM，渲染需求 → 设计 / 代码 / 测试覆盖行与摘要
 *  - 点击需求行展开文件明细
 *  - 切换到「审计链校验」加载证据链结果（状态 / 门禁 / 问题）
 *  - 「重新生成」先 POST refresh 再 GET 最新矩阵
 *  - 无矩阵时展示空态，可从空态直接生成
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { TraceabilityDialog } from "@/components/desktop/traceability-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const RTM = {
  summary: {
    total_requirements: 2,
    with_design_coverage: 1,
    with_implementation: 1,
    with_test_coverage: 1,
    with_review_coverage: 0,
    coverage_pct: 50,
    design_coverage_pct: 50,
    orphaned_tests: 1,
  },
  requirements: [
    {
      req_id: "REQ-001",
      statement: "The system SHALL switch the lamp on request.",
      status: "Covered",
      has_code: true,
      has_test: true,
      has_design: true,
      has_review: false,
      design_files: ["design/sdd.md"],
      code_files: ["code/main.c"],
      test_files: ["tests/test_main.c"],
    },
    {
      req_id: "REQ-002",
      statement: "The system SHALL report fault status.",
      status: "Not Covered",
      has_code: false,
      has_test: false,
      has_design: false,
      has_review: false,
      design_files: [],
      code_files: [],
      test_files: [],
    },
  ],
  orphaned_test_files: ["tests/test_orphan.c"],
  baseline: null,
  generated: "2026-11-15T10:00:00",
  gate: { status: "failed", threshold: 60, reason: "coverage 50.0% < 60.0%" },
};

const CHAIN = {
  status: "FAIL",
  summary: {
    nodes: 3,
    edges: 2,
    requirements: 1,
    test_coverage_pct: 100,
    code_coverage_pct: 100,
    gates_pass: 18,
    gates_fail: 3,
    problems_error: 6,
    problems_warning: 1,
  },
  metrics: {},
  generated_at: "2026-11-15T10:01:00",
  source: "traceability-matrix.json",
  problems: [
    { code: "W-CHAIN-REVIEW", severity: "WARNING", message: "需求缺少评审记录" },
  ],
  problem_total: 1,
  gates: [
    { id: "G-REQ", severity: "INFO", status: "PASS", detail: "1/1 requirements covered" },
    { id: "G-REVIEW", severity: "ERROR", status: "FAIL", detail: "missing review records" },
  ],
  v_model: { pairs: 8, required_pairs: 5, required_passed: 0 },
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(onOpenChange = jest.fn(), projectId: string | null = "p1") {
  render(
    <TraceabilityDialog open onOpenChange={onOpenChange} projectId={projectId} />,
  );
  return onOpenChange;
}

describe("TraceabilityDialog", () => {
  it("打开时加载 RTM 并渲染覆盖关系", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(RTM));
    renderDialog();

    expect(await screen.findByTestId("rtm-table")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/traceability",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    const summary = screen.getByTestId("rtm-summary");
    expect(summary).toHaveTextContent("需求2");
    expect(summary).toHaveTextContent("测试覆盖率50%");
    expect(screen.getByText("RTM 门禁 未通过")).toBeInTheDocument();

    const covered = screen.getByTestId("rtm-row-REQ-001");
    expect(covered).toHaveTextContent("已覆盖");
    const uncovered = screen.getByTestId("rtm-row-REQ-002");
    expect(uncovered).toHaveTextContent("未覆盖");

    // 未关联需求的测试提示
    expect(screen.getByText(/tests\/test_orphan\.c/)).toBeInTheDocument();
  });

  it("点击需求行展开设计/代码/测试文件明细", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(RTM));
    renderDialog();
    await screen.findByTestId("rtm-table");

    expect(screen.queryByText("design/sdd.md")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("rtm-row-REQ-001"));
    expect(screen.getByText("design/sdd.md")).toBeInTheDocument();
    expect(screen.getByText("code/main.c")).toBeInTheDocument();
    expect(screen.getByText("tests/test_main.c")).toBeInTheDocument();
  });

  it("展开后点击文件名触发 onOpenArtifact", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(RTM));
    const onOpenArtifact = jest.fn();
    render(
      <TraceabilityDialog
        open
        onOpenChange={jest.fn()}
        projectId="p1"
        onOpenArtifact={onOpenArtifact}
      />,
    );
    await screen.findByTestId("rtm-table");

    fireEvent.click(screen.getByTestId("rtm-row-REQ-001"));
    fireEvent.click(screen.getByTestId("rtm-file-code/main.c"));

    expect(onOpenArtifact).toHaveBeenCalledWith("code/main.c");
  });

  it("切换到审计链校验时加载校验结果", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(RTM));
    fetchMock.mockReturnValueOnce(jsonResponse(CHAIN));
    renderDialog();
    await screen.findByTestId("rtm-table");

    fireEvent.click(screen.getByTestId("traceability-tab-chain"));

    expect(await screen.findByTestId("chain-status")).toHaveTextContent("校验未通过");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/evidence-chain",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByTestId("chain-gates")).toHaveTextContent("G-REVIEW");
    expect(screen.getByTestId("chain-problems")).toHaveTextContent("W-CHAIN-REVIEW");
    expect(screen.getByText("数据源：traceability-matrix.json")).toBeInTheDocument();
  });

  it("重新生成先触发 refresh 再拉取最新矩阵", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(RTM));
    renderDialog();
    await screen.findByTestId("rtm-table");

    const updated = { ...RTM, summary: { ...RTM.summary, total_requirements: 3 } };
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true }));
    fetchMock.mockReturnValueOnce(jsonResponse(updated));

    fireEvent.click(screen.getByTestId("rtm-refresh"));

    await waitFor(() => expect(screen.getByTestId("rtm-summary")).toHaveTextContent("需求3"));
    const [refreshPath, refreshOpts] = fetchMock.mock.calls[1];
    expect(refreshPath).toBe("/api/v1/desktop/projects/p1/traceability/refresh");
    expect(refreshOpts.method).toBe("POST");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/v1/desktop/projects/p1/traceability");
  });

  it("无矩阵时展示空态并可直接生成", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({ ok: false, error: "No traceability matrix; refresh first" }, 404),
    );
    renderDialog();

    expect(await screen.findByTestId("rtm-empty")).toHaveTextContent("尚未生成追溯矩阵");
    expect(screen.getByTestId("rtm-refresh")).toHaveTextContent("生成矩阵");

    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true }));
    fetchMock.mockReturnValueOnce(jsonResponse(RTM));
    fireEvent.click(screen.getByTestId("rtm-refresh"));

    expect(await screen.findByTestId("rtm-table")).toBeInTheDocument();
  });

  it("没有选中工程时不发请求", () => {
    renderDialog(jest.fn(), null);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/**
 * QualityGatesDialog 单元测试。
 *
 * 覆盖点：
 *  - 四类门禁与总体状态渲染，状态到色彩的映射
 *  - 最近一次运行的门禁明细（含咨询性门禁、未执行/过期提示）
 *  - 仅有运行记录（无 gate-summary）时的降级提示
 *  - 加载失败展示错误
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QualityGatesDialog, gateTone } from "@/components/desktop/quality-gates-dialog";
import type { QualityGatesReport } from "@/components/desktop/quality-gates-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const REPORT: QualityGatesReport = {
  overall: "green",
  worst_status: "passed",
  generated_at: "2026-11-15T12:00:00",
  categories: [
    {
      key: "traceability",
      name: "追溯门禁",
      status: "passed",
      detail: "coverage 100.0% >= 60.0%",
      metrics: [
        { label: "需求总数", value: 2 },
        { label: "测试覆盖", value: "100.0%" },
      ],
    },
    {
      key: "review",
      name: "评审门禁",
      status: "passed",
      detail: "2 项评审全部通过",
      metrics: [{ label: "评审总数", value: 2 }],
    },
    {
      key: "ci",
      name: "CI 门禁",
      status: "passed",
      detail: "最近运行 job-1：passed",
      metrics: [{ label: "运行状态", value: "passed" }],
    },
    {
      key: "test",
      name: "测试门禁",
      status: "passed",
      detail: "通过 3 / 失败 0",
      metrics: [{ label: "覆盖率", value: "82%" }],
    },
  ],
  latest_run: {
    job_id: "job-1",
    run_status: "passed",
    started_at: "2026-11-15T10:00:00",
    completed_at: "2026-11-15T10:05:00",
    source: "gate-summary",
    session: "s1",
    summary_timestamp: "2026-11-15T10:05:00",
    summary_path: ".osh/sessions/s1/gate-summary.json",
    worst_gate_status: "passed",
    gates: [
      { gate: "G1", name: "SWE.1 需求 Gate", status: "passed", advisory: false, step_total: 4 },
      { gate: "G4", name: "方案评审 Gate", status: "passed", advisory: true, step_total: 1 },
      { gate: "G7", name: "SWE.5 集成 Gate", status: "failed", advisory: false, step_total: 5 },
    ],
    not_run_gates: ["G9"],
    stale_gates: ["G10"],
  },
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<QualityGatesDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

describe("gateTone", () => {
  it("将门禁状态映射为可读标签与色彩", () => {
    expect(gateTone("passed").label).toBe("通过");
    expect(gateTone("passed").dot).toContain("10b981");
    expect(gateTone("failed").label).toBe("未通过");
    expect(gateTone("failed").dot).toContain("ef4444");
    expect(gateTone("stale").label).toBe("证据过期");
    expect(gateTone("not-run").label).toBe("未执行");
    expect(gateTone("skipped").label).toBe("不适用");
  });
});

describe("QualityGatesDialog", () => {
  it("渲染四类门禁与总体状态", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(REPORT));
    renderDialog();

    expect(await screen.findByTestId("quality-overall")).toHaveTextContent("门禁全部通过");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/quality-gates",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    for (const key of ["traceability", "review", "ci", "test"]) {
      expect(screen.getByTestId(`quality-category-${key}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("quality-category-traceability")).toHaveTextContent("100.0%");
    expect(screen.getByTestId("quality-category-test")).toHaveTextContent("82%");
  });

  it("展示最近一次运行的门禁明细、咨询性标记与未执行/过期提示", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(REPORT));
    renderDialog();
    await screen.findByTestId("quality-latest-run");

    expect(screen.getByTestId("quality-latest-run")).toHaveTextContent("job-1");
    expect(screen.getByTestId("quality-gate-G1")).toHaveTextContent("通过");
    expect(screen.getByTestId("quality-gate-G4")).toHaveTextContent("咨询");
    expect(screen.getByTestId("quality-gate-G7")).toHaveTextContent("未通过");
    expect(screen.getByTestId("quality-latest-run")).toHaveTextContent("未执行门禁：G9");
    expect(screen.getByTestId("quality-latest-run")).toHaveTextContent("证据过期门禁：G10");
    expect(screen.getByTestId("quality-latest-run")).toHaveTextContent(
      ".osh/sessions/s1/gate-summary.json",
    );
  });

  it("仅运行记录时给出无法逐门禁结论的降级提示", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({
        ...REPORT,
        overall: "unverified",
        worst_status: "not-run",
        categories: REPORT.categories.map((c) =>
          c.key === "test" ? { ...c, status: "not-run", detail: "尚无测试产物" } : c,
        ),
        latest_run: {
          ...REPORT.latest_run,
          source: "run-record",
          gates: [],
          not_run_gates: [],
          stale_gates: [],
          summary_path: undefined,
        },
      }),
    );
    renderDialog();

    expect(await screen.findByTestId("quality-overall")).toHaveTextContent("存在未验证门禁");
    expect(screen.getByTestId("quality-category-test")).toHaveTextContent("未执行");
    expect(screen.getByTestId("quality-no-summary")).toBeInTheDocument();
  });

  it("尚无运行记录时展示空态", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({
        ...REPORT,
        overall: "unverified",
        worst_status: "not-run",
        latest_run: {
          ...REPORT.latest_run,
          job_id: null,
          source: "none",
          gates: [],
        },
      }),
    );
    renderDialog();
    expect(await screen.findByTestId("quality-no-run")).toBeInTheDocument();
    expect(screen.queryByTestId("quality-latest-run")).not.toBeInTheDocument();
  });

  it("加载失败时展示后端错误并可重新加载", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({ ok: false, error: "Project not found" }, 404),
    );
    renderDialog();

    expect(await screen.findByTestId("quality-error")).toHaveTextContent("Project not found");

    fetchMock.mockReturnValueOnce(jsonResponse(REPORT));
    fireEvent.click(screen.getByTestId("quality-reload"));
    expect(await screen.findByTestId("quality-overall")).toHaveTextContent("门禁全部通过");
  });
});

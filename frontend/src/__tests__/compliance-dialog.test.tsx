/**
 * ComplianceDialog 单元测试。
 *
 * 覆盖点：
 *  - 无审计结果时的空态与证据文档清单（缺失计数）
 *  - 运行合规审计：POST、总体状态、过程域红黄绿、缺失证据清单渲染
 *  - 一键生成缺失证据文档：仅提交缺失项并在完成后刷新
 *  - 全部文档已存在时生成按钮禁用
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ComplianceDialog, coverageLight } from "@/components/desktop/compliance-dialog";
import type { ComplianceSummary } from "@/components/desktop/compliance-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const DOCS = [
  { name: "qa-plan", title: "质量保证计划", path: "docs/qa-plan.md", exists: true },
  { name: "risk-register", title: "风险登记表", path: "docs/risk-register.md", exists: false },
  { name: "project-plan", title: "项目计划", path: "docs/project-plan.md", exists: false },
];

const SUMMARY: ComplianceSummary = {
  ok: true,
  status: "completed",
  overall_score: "E2",
  overall_coverage_pct: 72.5,
  total_gaps: 3,
  total_evidences: 8,
  bp_summary: { total: 10, passed: 7, partial: 2, failed: 1 },
  scores: {
    "SWE.3": {
      title: "软件详细设计与单元构建",
      score: "NI",
      coverage_pct: 20,
      evidence_count: 1,
      gap_count: 2,
    },
    "SWE.4": {
      title: "软件单元验证",
      score: "E1",
      coverage_pct: 55,
      evidence_count: 2,
      gap_count: 1,
    },
    "SYS.2": {
      title: "系统需求分析",
      score: "E2",
      coverage_pct: 90,
      evidence_count: 3,
      gap_count: 0,
    },
  },
  gaps: [
    {
      process: "SWE.3",
      type: "missing_evidence",
      ref_id: "BP1",
      title: "缺少详细设计证据",
      details: "design/",
    },
    {
      process: "SWE.4",
      type: "empty_evidence",
      ref_id: "BP2",
      title: "单元测试报告为空",
    },
  ],
  errors: [],
  generated_at: "2026-11-15T12:00:00",
  compliance_report_path: "docs/compliance-check-report.md",
  audit_report_path: ".osh/reports/aspice-report.md",
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<ComplianceDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

describe("coverageLight", () => {
  it("按证据覆盖度映射红黄绿，NI 一律红", () => {
    expect(coverageLight({ score: "E3", coverage_pct: 95, evidence_count: 1, gap_count: 0 })).toBe("green");
    expect(coverageLight({ score: "E1", coverage_pct: 50, evidence_count: 1, gap_count: 0 })).toBe("amber");
    expect(coverageLight({ score: "E1", coverage_pct: 10, evidence_count: 1, gap_count: 0 })).toBe("red");
    expect(coverageLight({ score: "NI", coverage_pct: 100, evidence_count: 1, gap_count: 0 })).toBe("red");
    expect(coverageLight(undefined)).toBe("red");
  });
});

describe("ComplianceDialog", () => {
  it("无审计结果时展示空态与证据文档清单", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({ ok: false, error: "No audit summary yet. POST /compliance/run first." }, 404),
    );
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, documents: DOCS, missing: ["risk-register", "project-plan"] }));

    renderDialog();

    expect(await screen.findByTestId("compliance-empty")).toBeInTheDocument();
    expect(await screen.findByTestId("compliance-documents")).toBeInTheDocument();
    expect(screen.getByTestId("compliance-generate-docs")).toHaveTextContent("2");
    expect(screen.getByTestId("compliance-doc-risk-register")).toBeInTheDocument();
    // 404 表示「尚未审计」，不应作为错误展示
    expect(screen.queryByTestId("compliance-error")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/desktop/projects/p1/compliance",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/desktop/projects/p1/compliance/documents",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("运行审计后渲染总体状态、过程域红黄绿与缺失证据", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({ ok: false, error: "No audit summary yet." }, 404),
    );
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, documents: DOCS, missing: [] }));
    renderDialog();
    await screen.findByTestId("compliance-empty");

    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, summary: SUMMARY, documents: DOCS }));
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, documents: DOCS, missing: ["risk-register", "project-plan"] }));

    fireEvent.click(screen.getByTestId("compliance-run"));

    const overall = await screen.findByTestId("compliance-overall");
    expect(overall).toHaveTextContent("审计完成");
    expect(overall).toHaveTextContent("73%");
    expect(overall).toHaveTextContent("实践通过 7/10");
    expect(overall).toHaveTextContent("● 绿 1");
    expect(overall).toHaveTextContent("● 黄 1");
    expect(overall).toHaveTextContent("● 红 1");

    const post = fetchMock.mock.calls[2];
    expect(post[0]).toBe("/api/v1/desktop/projects/p1/compliance/run");
    expect(post[1].method).toBe("POST");

    expect(screen.getByTestId("compliance-process-SWE.3")).toHaveTextContent("软件详细设计与单元构建");
    expect(screen.getByTestId("compliance-process-SWE.3")).toHaveTextContent("覆盖 20%");
    expect(screen.getByTestId("compliance-process-SYS.2")).toHaveTextContent("E2");

    const gaps = screen.getByTestId("compliance-gaps");
    expect(gaps).toHaveTextContent("缺失证据");
    expect(gaps).toHaveTextContent("缺少详细设计证据");
    expect(gaps).toHaveTextContent("证据无实质内容");
  });

  it("一键生成缺失证据文档只提交缺失项并在完成后刷新", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, summary: SUMMARY, documents: DOCS }));
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, documents: DOCS, missing: ["risk-register", "project-plan"] }));
    renderDialog();
    await screen.findByTestId("compliance-documents");

    fetchMock.mockReturnValueOnce(
      jsonResponse({ ok: true, created: ["risk-register", "project-plan"], skipped: [] }),
    );
    fetchMock.mockReturnValueOnce(
      jsonResponse({
        ok: true,
        documents: DOCS.map((d) => ({ ...d, exists: true })),
        missing: [],
      }),
    );

    fireEvent.click(screen.getByTestId("compliance-generate-docs"));

    expect(await screen.findByTestId("compliance-notice")).toHaveTextContent(
      "已生成 2 份证据文档模板",
    );
    const [path, opts] = fetchMock.mock.calls[2];
    expect(path).toBe("/api/v1/desktop/projects/p1/templates");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ templates: ["risk-register", "project-plan"] });
    await waitFor(() =>
      expect(screen.getByTestId("compliance-generate-docs")).toBeDisabled(),
    );
  });

  it("全部证据文档已存在时不触发生成请求", async () => {
    const allDocs = DOCS.map((d) => ({ ...d, exists: true }));
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, summary: SUMMARY, documents: allDocs }));
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true, documents: allDocs, missing: [] }));
    renderDialog();
    await screen.findByTestId("compliance-documents");

    expect(screen.getByTestId("compliance-generate-docs")).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

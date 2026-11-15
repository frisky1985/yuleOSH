/**
 * ProjectMgmtDialog 单元测试。
 *
 * 覆盖点：
 *  - 加载风险与里程碑，默认展示风险页、矩阵计数与详情
 *  - 空风险描述本地校验
 *  - 登记风险（POST 载荷）与自动评级
 *  - 风险 open → mitigated（缓解措施必填）
 *  - 风险 mitigated → closed（管理批准人必填）
 *  - 里程碑完成度与状态更新（PATCH）
 *  - 导出项目管理报告
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ProjectMgmtDialog, computeRiskLevel } from "@/components/desktop/project-mgmt-dialog";
import type { Milestone, RiskDetail, RiskRow } from "@/components/desktop/project-mgmt-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const RISK_ROW: RiskRow = {
  id: "RSK-20261115-aaaaaa",
  description: "供应商芯片交期延迟",
  likelihood: "high",
  impact: "high",
  level: "critical",
  status: "open",
  owner: "alice",
};

const RISK_DETAIL: RiskDetail = {
  ...RISK_ROW,
  mitigation: "",
  owner_role: "risk_owner",
  acceptance: null,
  created_at: "2026-11-15T09:00:00",
  updated_at: "2026-11-15T09:00:00",
  closed_at: null,
};

const RISK_MITIGATED: RiskDetail = {
  ...RISK_DETAIL,
  status: "mitigated",
  mitigation: "提前锁定第二供应商",
  updated_at: "2026-11-15T09:30:00",
};

const RISK_CLOSED: RiskDetail = {
  ...RISK_MITIGATED,
  status: "closed",
  acceptance: {
    accepted_by: "pm",
    role: "project_manager",
    accepted_at: "2026-11-15T10:00:00",
  },
  closed_at: "2026-11-15T10:00:00",
};

const MS_DONE: Milestone = {
  id: "MS-20261115-aaaaaa",
  title: "需求基线",
  target_date: "2026-11-10",
  deliverable: "SRS v1.0",
  status: "completed",
  created_at: "2026-11-01T09:00:00",
  updated_at: "2026-11-10T09:00:00",
};

const MS_PROGRESS: Milestone = {
  ...MS_DONE,
  id: "MS-20261115-bbbbbb",
  title: "设计基线",
  target_date: "2026-11-20",
  deliverable: "SDD v1.0",
  status: "in_progress",
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<ProjectMgmtDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

function callMatching(predicate: (path: string, init?: RequestInit) => boolean) {
  return fetchMock.mock.calls.find(([path, init]) =>
    predicate(String(path), init as RequestInit | undefined),
  );
}

describe("computeRiskLevel", () => {
  it("与后端 3×3 矩阵一致", () => {
    expect(computeRiskLevel("low", "low")).toBe("low");
    expect(computeRiskLevel("low", "high")).toBe("medium");
    expect(computeRiskLevel("medium", "high")).toBe("high");
    expect(computeRiskLevel("high", "high")).toBe("critical");
    expect(computeRiskLevel("high", "low")).toBe("medium");
  });
});

describe("ProjectMgmtDialog", () => {
  it("加载风险与里程碑，展示矩阵计数与风险详情", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ risks: [RISK_ROW] }))
      .mockReturnValueOnce(jsonResponse({ milestones: [MS_DONE, MS_PROGRESS] }))
      .mockReturnValueOnce(jsonResponse({ risk: RISK_DETAIL }));
    renderDialog();

    expect(await screen.findByTestId("pm-risk-detail")).toHaveTextContent("供应商芯片交期延迟");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/risks",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/milestones",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByTestId("pm-matrix-high-high")).toHaveTextContent("1");
    expect(screen.getByTestId("pm-risk-stats")).toHaveTextContent("未缓解1");
    expect(screen.getByTestId("pm-risk-mitigate")).toBeInTheDocument();
  });

  it("空风险描述时本地校验，不发创建请求", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ risks: [] }))
      .mockReturnValueOnce(jsonResponse({ milestones: [] }));
    renderDialog();
    await screen.findByTestId("pm-risk-empty");

    fireEvent.click(screen.getByTestId("pm-risk-create"));

    expect(await screen.findByTestId("pm-error")).toHaveTextContent("风险描述不能为空");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("登记风险时提交可能性/影响/责任人，并按矩阵评级", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ risks: [] }))
      .mockReturnValueOnce(jsonResponse({ milestones: [] }));
    renderDialog();
    await screen.findByTestId("pm-risk-empty");

    fireEvent.change(screen.getByTestId("pm-risk-desc"), {
      target: { value: RISK_ROW.description },
    });
    fireEvent.change(screen.getByTestId("pm-risk-likelihood"), { target: { value: "high" } });
    fireEvent.change(screen.getByTestId("pm-risk-impact"), { target: { value: "high" } });
    fireEvent.change(screen.getByTestId("pm-risk-owner"), { target: { value: "alice" } });

    expect(screen.getByTestId("pm-risk-preview")).toHaveTextContent("严重");

    fetchMock.mockReturnValueOnce(jsonResponse({ risk: RISK_DETAIL }, 201));
    fireEvent.click(screen.getByTestId("pm-risk-create"));

    expect(await screen.findByTestId("pm-notice")).toHaveTextContent("已登记风险");
    const call = callMatching(
      (path, init) => path.endsWith("/risks") && init?.method === "POST",
    )!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      description: RISK_ROW.description,
      likelihood: "high",
      impact: "high",
      owner: "alice",
    });
    expect(screen.getByTestId(`pm-risk-row-${RISK_ROW.id}`)).toBeInTheDocument();
  });

  it("标记已缓解时必须填写缓解措施", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ risks: [RISK_ROW] }))
      .mockReturnValueOnce(jsonResponse({ milestones: [] }))
      .mockReturnValueOnce(jsonResponse({ risk: RISK_DETAIL }));
    renderDialog();
    await screen.findByTestId("pm-risk-mitigate");

    fireEvent.click(screen.getByTestId("pm-risk-mitigate"));
    expect(await screen.findByTestId("pm-error")).toHaveTextContent("缓解措施");

    fetchMock.mockReturnValueOnce(jsonResponse({ risk: RISK_MITIGATED }));
    fireEvent.change(screen.getByTestId("pm-risk-note"), {
      target: { value: "提前锁定第二供应商" },
    });
    fireEvent.click(screen.getByTestId("pm-risk-mitigate"));

    expect(await screen.findByTestId("pm-notice")).toHaveTextContent("已缓解");
    const call = callMatching((path) => path.endsWith("/transition"))!;
    expect(call[0]).toBe(`/api/v1/desktop/projects/p1/risks/${RISK_ROW.id}/transition`);
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      status: "mitigated",
      mitigation: "提前锁定第二供应商",
    });
    expect(screen.getByTestId("pm-risk-close")).toBeInTheDocument();
  });

  it("关闭已缓解风险需要管理批准人", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ risks: [{ ...RISK_ROW, status: "mitigated" }] }))
      .mockReturnValueOnce(jsonResponse({ milestones: [] }))
      .mockReturnValueOnce(jsonResponse({ risk: RISK_MITIGATED }));
    renderDialog();
    await screen.findByTestId("pm-risk-close");

    fireEvent.click(screen.getByTestId("pm-risk-close"));
    expect(await screen.findByTestId("pm-error")).toHaveTextContent("批准人");

    fetchMock.mockReturnValueOnce(jsonResponse({ risk: RISK_CLOSED }));
    fireEvent.change(screen.getByTestId("pm-risk-note"), { target: { value: "pm" } });
    fireEvent.click(screen.getByTestId("pm-risk-close"));

    expect(await screen.findByTestId("pm-notice")).toHaveTextContent("已关闭");
    const call = callMatching((path) => path.endsWith("/transition"))!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      status: "closed",
      accepted_by: "pm",
    });
    expect(screen.queryByTestId("pm-risk-close")).toBeNull();
  });

  it("里程碑完成度与状态更新", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ risks: [] }))
      .mockReturnValueOnce(jsonResponse({ milestones: [MS_DONE, MS_PROGRESS] }));
    renderDialog();
    await screen.findByTestId("pm-risk-empty");

    fireEvent.click(screen.getByTestId("pm-tab-milestones"));
    expect(await screen.findByTestId("pm-progress")).toHaveTextContent("1/2 · 50%");

    fetchMock.mockReturnValueOnce(
      jsonResponse({ milestone: { ...MS_PROGRESS, status: "completed" } }),
    );
    fireEvent.change(screen.getByTestId(`pm-ms-status-${MS_PROGRESS.id}`), {
      target: { value: "completed" },
    });

    expect(await screen.findByTestId("pm-notice")).toHaveTextContent("已完成");
    const call = callMatching((path, init) => path.endsWith(`/milestones/${MS_PROGRESS.id}`) && init?.method === "PATCH")!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ status: "completed" });
    expect(screen.getByTestId("pm-progress")).toHaveTextContent("2/2 · 100%");
  });

  it("导出项目管理报告并展示归档路径", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ risks: [RISK_ROW] }))
      .mockReturnValueOnce(jsonResponse({ milestones: [MS_DONE] }))
      .mockReturnValueOnce(jsonResponse({ risk: RISK_DETAIL }))
      .mockReturnValueOnce(
        jsonResponse({ path: "/tmp/p1/.osh/evidence/project-mgmt-report.md" }),
      );
    renderDialog();
    await screen.findByTestId("pm-risk-detail");

    fireEvent.click(screen.getByTestId("pm-export"));

    expect(await screen.findByTestId("pm-notice")).toHaveTextContent("project-mgmt-report.md");
    const call = callMatching((path) => path.endsWith("/project-mgmt/export"))!;
    expect(call[0]).toBe("/api/v1/desktop/projects/p1/project-mgmt/export");
  });
});

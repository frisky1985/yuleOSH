/**
 * QaAuditDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载审计列表 + 详情，展示不符合项与统计
 *  - 空标题本地校验，不发起创建请求
 *  - 创建审计（POST 载荷）
 *  - 登记不符合项（POST 载荷）
 *  - 不符合项流转（open → acknowledged）
 *  - 全部关闭后管理批准（POST approver）
 *  - 存在未关闭不符合项时批准按钮禁用
 *  - 导出 QA 报告
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QaAuditDialog } from "@/components/desktop/qa-audit-dialog";
import type { QaAudit, QaAuditRow, QaFinding } from "@/components/desktop/qa-audit-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const FINDING_OPEN: QaFinding = {
  id: "FN-20261115-aaaaaa",
  description: "需求评审记录缺失批准人签字",
  severity: "high",
  status: "open",
  assigned_to: "alice",
  created_at: "2026-11-15T09:00:00",
  updated_at: "2026-11-15T09:00:00",
};

const FINDING_CLOSED: QaFinding = {
  ...FINDING_OPEN,
  status: "closed",
  resolution: "补充签字并归档",
  verifier: "qa_lead",
};

const ROW_OPEN: QaAuditRow = {
  id: "QA-20261115-aaaaaa",
  title: "SUP.1 过程审计",
  auditor: "alice",
  auditor_role: "qa_engineer",
  scope: "需求与评审记录",
  date: "2026-11-15T09:00:00",
  status: "open",
  approved_by: "",
  finding_count: 1,
  open_findings: 1,
};

const AUDIT_OPEN: QaAudit = {
  id: ROW_OPEN.id,
  title: ROW_OPEN.title,
  auditor: ROW_OPEN.auditor,
  auditor_role: ROW_OPEN.auditor_role,
  scope: ROW_OPEN.scope,
  date: ROW_OPEN.date,
  status: "open",
  approval: null,
  findings: [FINDING_OPEN],
  created_at: "2026-11-15T09:00:00",
  updated_at: "2026-11-15T09:00:00",
};

const AUDIT_PENDING: QaAudit = {
  ...AUDIT_OPEN,
  status: "pending_approval",
  findings: [FINDING_CLOSED],
  updated_at: "2026-11-15T10:00:00",
};

const AUDIT_CLOSED: QaAudit = {
  ...AUDIT_PENDING,
  status: "closed",
  approval: {
    approved_by: "lead",
    role: "qa_lead",
    note: "",
    approved_at: "2026-11-15T10:05:00",
  },
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<QaAuditDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

function callMatching(predicate: (path: string, init?: RequestInit) => boolean) {
  return fetchMock.mock.calls.find(([path, init]) =>
    predicate(String(path), init as RequestInit | undefined),
  );
}

describe("QaAuditDialog", () => {
  it("加载审计列表与详情，展示不符合项与统计", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ audits: [ROW_OPEN] }))
      .mockReturnValueOnce(jsonResponse({ audit: AUDIT_OPEN }));
    renderDialog();

    expect(await screen.findByTestId("qa-detail")).toHaveTextContent("SUP.1 过程审计");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/qa",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByTestId("qa-findings")).toHaveTextContent("需求评审记录缺失批准人签字");
    expect(screen.getByTestId("qa-stats")).toHaveTextContent("不符合项1");
    expect(screen.getByTestId("qa-approve")).toBeDisabled();
  });

  it("空标题时本地校验，不发创建请求", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ audits: [] }));
    renderDialog();
    await screen.findByTestId("qa-empty");

    fireEvent.click(screen.getByTestId("qa-create"));

    expect(await screen.findByTestId("qa-error")).toHaveTextContent("标题不能为空");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("创建审计时提交标题/审计员/范围", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ audits: [] }));
    renderDialog();
    await screen.findByTestId("qa-empty");

    fetchMock.mockReturnValueOnce(jsonResponse({ audit: { ...AUDIT_OPEN, findings: [] } }, 201));
    fireEvent.change(screen.getByTestId("qa-audit-title"), { target: { value: "SUP.1 过程审计" } });
    fireEvent.change(screen.getByTestId("qa-auditor"), { target: { value: "alice" } });
    fireEvent.change(screen.getByTestId("qa-scope"), { target: { value: "需求与评审记录" } });
    fireEvent.click(screen.getByTestId("qa-create"));

    expect(await screen.findByTestId("qa-notice")).toHaveTextContent("已创建审计");
    const call = callMatching(
      (path, init) => path.endsWith("/qa") && init?.method === "POST",
    )!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      title: "SUP.1 过程审计",
      auditor: "alice",
      scope: "需求与评审记录",
    });
    expect(screen.getByTestId(`qa-row-${ROW_OPEN.id}`)).toBeInTheDocument();
  });

  it("登记不符合项时提交描述/严重度/责任人", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ audits: [ROW_OPEN] }))
      .mockReturnValueOnce(jsonResponse({ audit: AUDIT_OPEN }));
    renderDialog();
    await screen.findByTestId("qa-detail");

    fetchMock.mockReturnValueOnce(jsonResponse({ finding: FINDING_OPEN }, 201));
    fireEvent.change(screen.getByTestId("qa-finding-desc"), {
      target: { value: FINDING_OPEN.description },
    });
    fireEvent.change(screen.getByTestId("qa-finding-severity"), { target: { value: "high" } });
    fireEvent.change(screen.getByTestId("qa-finding-assignee"), { target: { value: "alice" } });
    fireEvent.click(screen.getByTestId("qa-add-finding"));

    expect(await screen.findByTestId("qa-notice")).toHaveTextContent("已登记不符合项");
    const call = callMatching((path) => path.endsWith("/findings"))!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      description: FINDING_OPEN.description,
      severity: "high",
      assigned_to: "alice",
    });
  });

  it("不符合项 open → acknowledged 流转", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ audits: [ROW_OPEN] }))
      .mockReturnValueOnce(jsonResponse({ audit: AUDIT_OPEN }));
    renderDialog();
    await screen.findByTestId(`qa-finding-${FINDING_OPEN.id}`);

    fetchMock.mockReturnValueOnce(
      jsonResponse({ finding: { ...FINDING_OPEN, status: "acknowledged" } }),
    );
    fireEvent.click(screen.getByTestId(`qa-finding-${FINDING_OPEN.id}-to-acknowledged`));

    expect(await screen.findByTestId("qa-notice")).toHaveTextContent("已确认");
    const call = callMatching((path) => path.endsWith("/transition"))!;
    expect(call[0]).toBe(
      `/api/v1/desktop/projects/p1/qa/${ROW_OPEN.id}/findings/${FINDING_OPEN.id}/transition`,
    );
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      status: "acknowledged",
    });
  });

  it("全部不符合项关闭后可批准并关闭审计", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ audits: [{ ...ROW_OPEN, status: "pending_approval", open_findings: 0 }] }))
      .mockReturnValueOnce(jsonResponse({ audit: AUDIT_PENDING }));
    renderDialog();
    expect(await screen.findByTestId("qa-approve")).toBeEnabled();

    fetchMock.mockReturnValueOnce(jsonResponse({ audit: AUDIT_CLOSED }));
    fireEvent.change(screen.getByTestId("qa-approver"), { target: { value: "lead" } });
    fireEvent.click(screen.getByTestId("qa-approve"));

    expect(await screen.findByTestId("qa-notice")).toHaveTextContent("已由 lead 批准关闭");
    const call = callMatching((path) => path.endsWith("/approve"))!;
    expect(call[0]).toBe(`/api/v1/desktop/projects/p1/qa/${ROW_OPEN.id}/approve`);
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ approver: "lead" });
    expect(screen.getByTestId("qa-detail")).toHaveTextContent("已由 lead");
  });

  it("导出 QA 报告并展示归档路径", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse({ audits: [ROW_OPEN] }))
      .mockReturnValueOnce(jsonResponse({ audit: AUDIT_OPEN }))
      .mockReturnValueOnce(jsonResponse({ path: "/tmp/p1/.osh/evidence/qa-audit-report.md" }));
    renderDialog();
    await screen.findByTestId("qa-detail");

    fireEvent.click(screen.getByTestId("qa-export"));

    expect(await screen.findByTestId("qa-notice")).toHaveTextContent("qa-audit-report.md");
    const call = callMatching((path) => path.endsWith("/qa/export"))!;
    expect(call[0]).toBe("/api/v1/desktop/projects/p1/qa/export");
  });
});

/**
 * QaApprovalPanel 单元测试。
 *
 * 覆盖点：
 *  - 列表状态标注与「批准」入口仅在 pending_approval 出现
 *  - 详情加载（不符合项、责任人）
 *  - 批准前置条件：approver 非空 + 所有不符合项已关闭
 *  - 批准成功的状态流转与后端调用参数
 *  - 后端 400 错误原文透出且不改变状态
 *  - 空审计的「不代表质量合格」提示
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QaApprovalPanel } from "@/components/qa/qa-approval-panel";
import * as qaApi from "@/lib/qa-api";

jest.mock("@/lib/qa-api", () => ({
  listQaAudits: jest.fn(),
  getQaAudit: jest.fn(),
  approveQaAudit: jest.fn(),
}));

const mocked = qaApi as unknown as {
  listQaAudits: jest.Mock;
  getQaAudit: jest.Mock;
  approveQaAudit: jest.Mock;
};

function summary(over: Partial<qaApi.QaAuditSummary> = {}): qaApi.QaAuditSummary {
  return {
    id: "QA-1",
    title: "Process audit",
    auditor_role: "qa_engineer",
    status: "pending_approval",
    approved_by: "",
    finding_count: 1,
    open_findings: 0,
    ...over,
  };
}

function detail(over: Partial<qaApi.QaAudit> = {}): qaApi.QaAudit {
  return {
    id: "QA-1",
    title: "Process audit",
    auditor: "alice",
    auditor_role: "qa_engineer",
    status: "pending_approval",
    approval: null,
    findings: [
      {
        id: "FN-1",
        description: "Missing traceability",
        severity: "high",
        status: "closed",
        assigned_to: "bob",
        verifier: "qa",
      },
    ],
    ...over,
  };
}

describe("QaApprovalPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mocked.listQaAudits.mockResolvedValue([summary()]);
  });

  it("列表展示状态标注，且只为 pending_approval 提供批准入口", async () => {
    mocked.listQaAudits.mockResolvedValue([
      summary({ id: "QA-1", title: "待批准审计", status: "pending_approval" }),
      summary({ id: "QA-2", title: "进行中审计", status: "open", finding_count: 2, open_findings: 1 }),
    ]);

    render(<QaApprovalPanel projectId="p1" />);

    expect(await screen.findByText("待批准审计")).toBeInTheDocument();
    expect(screen.getByText("进行中审计")).toBeInTheDocument();
    expect(screen.getByText(/待批准 · 0\/1 未关闭/)).toBeInTheDocument();
    expect(screen.getByText(/进行中 · 1\/2 未关闭/)).toBeInTheDocument();

    // open 审计没有「批准」按钮 → 全局仅 1 个
    expect(screen.getAllByRole("button", { name: "批准" })).toHaveLength(1);
  });

  it("点击批准会加载详情并显示不符合项与责任人", async () => {
    mocked.getQaAudit.mockResolvedValue(detail());

    render(<QaApprovalPanel projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "批准" }));

    expect(await screen.findByText(/Missing traceability/)).toBeInTheDocument();
    expect(screen.getByText(/责任人 bob/)).toBeInTheDocument();
    expect(mocked.getQaAudit).toHaveBeenCalledWith("p1", "QA-1");
  });

  it("approver 为空时按钮禁用，输入后可用", async () => {
    mocked.getQaAudit.mockResolvedValue(detail());

    render(<QaApprovalPanel projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "批准" }));

    const submit = await screen.findByRole("button", { name: "确认批准并关闭" });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("批准人（必填）"), {
      target: { value: "qa-lead" },
    });
    expect(submit).not.toBeDisabled();
  });

  it("不符合项未全部关闭时不允许批准（fail-closed）", async () => {
    mocked.getQaAudit.mockResolvedValue(
      detail({
        findings: [
          {
            id: "FN-1",
            description: "still open",
            severity: "high",
            status: "resolved",
            assigned_to: "bob",
          },
        ],
      }),
    );

    render(<QaApprovalPanel projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "批准" }));

    fireEvent.change(await screen.findByPlaceholderText("批准人（必填）"), {
      target: { value: "qa-lead" },
    });
    expect(screen.getByRole("button", { name: "确认批准并关闭" })).toBeDisabled();
  });

  it("批准成功后展示关闭信息，并携带 approver/role/note 调用后端", async () => {
    const closed = detail({
      status: "closed",
      approval: {
        approved_by: "qa-lead",
        role: "qa_lead",
        note: "ok",
        approved_at: "2026-10-31T10:00:00",
      },
    });
    mocked.getQaAudit.mockResolvedValue(detail());
    mocked.approveQaAudit.mockResolvedValue(closed);

    render(<QaApprovalPanel projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "批准" }));

    fireEvent.change(await screen.findByPlaceholderText("批准人（必填）"), {
      target: { value: "qa-lead" },
    });
    fireEvent.change(screen.getByPlaceholderText("备注（可选）"), {
      target: { value: "ok" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认批准并关闭" }));

    await waitFor(() => {
      expect(mocked.approveQaAudit).toHaveBeenCalledWith("p1", "QA-1", {
        approver: "qa-lead",
        role: "qa_lead",
        note: "ok",
      });
    });
    expect(await screen.findByText(/已于 2026-10-31T10:00:00 由 qa-lead/)).toBeInTheDocument();
    expect(screen.queryByText("确认批准并关闭")).not.toBeInTheDocument();
  });

  it("后端 400 原文透出，审计保持待批准", async () => {
    mocked.getQaAudit.mockResolvedValue(detail());
    mocked.approveQaAudit.mockRejectedValue(
      new Error("approver is required"),
    );

    render(<QaApprovalPanel projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "批准" }));

    fireEvent.change(await screen.findByPlaceholderText("批准人（必填）"), {
      target: { value: "qa-lead" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认批准并关闭" }));

    expect(await screen.findByText("approver is required")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("待批准");
  });

  it("空审计提示「不代表质量合格」且仍需显式批准人", async () => {
    mocked.getQaAudit.mockResolvedValue(detail({ findings: [] }));

    render(<QaApprovalPanel projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "批准" }));

    expect(await screen.findByText(/不代表质量合格/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认批准并关闭" })).toBeDisabled();
  });
});

/**
 * ProjectWizardDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载模板清单（GET /desktop/project-templates）
 *  - 第 1 步：名称为空时不能进入下一步
 *  - 第 2 步：展示模板卡片，切换模板后摘要同步更新
 *  - 创建时提交 name / description / template，并把 project + template 结果回调出去
 *  - 创建失败展示后端错误且不关闭弹窗
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ProjectWizardDialog } from "@/components/desktop/project-wizard-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const TEMPLATES = {
  templates: [
    {
      id: "blank",
      name: "空白工程",
      tag: "自定义",
      description: "只创建标准产出物目录。",
      doc_templates: [],
      has_requirements_seed: false,
    },
    {
      id: "automotive",
      name: "汽车电子",
      tag: "ISO 26262",
      description: "完整 ASPICE 文档骨架 + 功能安全需求模板。",
      doc_templates: ["project-plan", "risk-register"],
      has_requirements_seed: true,
    },
  ],
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderWizard(over: Partial<React.ComponentProps<typeof ProjectWizardDialog>> = {}) {
  const onOpenChange = jest.fn();
  const onCreated = jest.fn();
  render(
    <ProjectWizardDialog
      open
      onOpenChange={onOpenChange}
      onCreated={onCreated}
      {...over}
    />,
  );
  return { onOpenChange, onCreated };
}

describe("ProjectWizardDialog", () => {
  it("打开时加载模板，名称填写后可进入第 2 步", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(TEMPLATES));
    renderWizard();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/project-templates",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    const next = screen.getByTestId("wizard-next") as HTMLButtonElement;
    expect(next).toBeDisabled();

    fireEvent.change(screen.getByTestId("wizard-name"), {
      target: { value: "智能车灯控制器" },
    });
    expect(next).not.toBeDisabled();

    fireEvent.click(next);
    expect(screen.getByText("第 2 / 2 步")).toBeInTheDocument();
    expect(await screen.findByTestId("wizard-template-blank")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-template-automotive")).toBeInTheDocument();
  });

  it("切换模板后摘要更新", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(TEMPLATES));
    renderWizard();

    fireEvent.change(screen.getByTestId("wizard-name"), { target: { value: "P" } });
    fireEvent.click(screen.getByTestId("wizard-next"));

    expect(await screen.findByTestId("wizard-summary")).toHaveTextContent("无（空白工程）");

    fireEvent.click(screen.getByTestId("wizard-template-automotive"));
    const summary = screen.getByTestId("wizard-summary");
    expect(summary).toHaveTextContent("project-plan、risk-register");
    expect(summary).toHaveTextContent("需求模板：是");
  });

  it("创建时提交模板并把结果回调出去", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(TEMPLATES));
    const created = {
      project: { id: "p1", name: "车灯", description: "desc" },
      template: {
        template: "automotive",
        created_docs: ["docs/project-plan.md"],
        requirements_saved: true,
      },
    };
    fetchMock.mockReturnValueOnce(jsonResponse(created, 201));
    const { onCreated } = renderWizard();

    fireEvent.change(screen.getByTestId("wizard-name"), { target: { value: " 车灯 " } });
    fireEvent.change(screen.getByTestId("wizard-description"), {
      target: { value: " 控制器 " },
    });
    fireEvent.click(screen.getByTestId("wizard-next"));
    await screen.findByTestId("wizard-template-automotive");
    fireEvent.click(screen.getByTestId("wizard-template-automotive"));
    fireEvent.click(screen.getByTestId("wizard-create"));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created.project, created.template));

    const [path, options] = fetchMock.mock.calls[1];
    expect(path).toBe("/api/v1/desktop/projects");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({
      name: "车灯",
      description: "控制器",
      template: "automotive",
    });
  });

  it("创建失败时展示错误且不关闭弹窗", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(TEMPLATES));
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: false, error: "模板不可用" }, 400));
    const { onOpenChange, onCreated } = renderWizard();

    fireEvent.change(screen.getByTestId("wizard-name"), { target: { value: "P" } });
    fireEvent.click(screen.getByTestId("wizard-next"));
    await screen.findByTestId("wizard-template-blank");
    fireEvent.click(screen.getByTestId("wizard-create"));

    expect(await screen.findByTestId("wizard-error")).toHaveTextContent("模板不可用");
    expect(onCreated).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

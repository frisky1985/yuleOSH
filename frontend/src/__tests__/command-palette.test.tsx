/**
 * CommandPalette 单元测试：搜索过滤、键盘导航与选择回调。
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { CommandPalette } from "@/components/desktop/command-palette";

const PROJECTS = [
  { id: "p1", name: "自动驾驶域控制器" },
  { id: "p2", name: "座舱语音助手" },
];

function renderPalette(open = true, activeId: string | null = "p1") {
  const onClose = jest.fn();
  const onSelectProject = jest.fn();
  const onGovernance = jest.fn();
  const onAction = jest.fn();
  render(
    <CommandPalette
      open={open}
      onClose={onClose}
      projects={PROJECTS}
      activeId={activeId}
      onSelectProject={onSelectProject}
      onGovernance={onGovernance}
      onAction={onAction}
    />,
  );
  return { onClose, onSelectProject, onGovernance, onAction };
}

describe("CommandPalette", () => {
  it("打开后按「操作 / 工程 / 治理分组」展示命令", () => {
    renderPalette();

    expect(screen.getByTestId("cmd-palette")).toBeInTheDocument();
    expect(screen.getByText("操作")).toBeInTheDocument();
    expect(screen.getByText("工程")).toBeInTheDocument();
    expect(screen.getByText("追溯与变更")).toBeInTheDocument();
    expect(screen.getByText("质量与合规")).toBeInTheDocument();
    expect(screen.getByText("问题与审计")).toBeInTheDocument();
    expect(screen.getByText("项目管理")).toBeInTheDocument();
    expect(screen.getByTestId("cmd-item-action-new-project")).toBeInTheDocument();
    expect(screen.getAllByText("自动驾驶域控制器")).toHaveLength(1);
    expect(screen.getAllByText("追溯矩阵").length).toBeGreaterThan(0);
  });

  it("未打开时不渲染任何内容", () => {
    renderPalette(false);
    expect(screen.queryByTestId("cmd-palette")).toBeNull();
  });

  it("搜索按标签过滤，Enter 执行唯一结果", () => {
    const { onGovernance } = renderPalette();

    fireEvent.change(screen.getByTestId("cmd-input"), {
      target: { value: "合规" },
    });

    expect(screen.queryByTestId("cmd-item-action-new-project")).toBeNull();
    fireEvent.keyDown(screen.getByTestId("cmd-input"), { key: "Enter" });

    expect(onGovernance).toHaveBeenCalledWith("compliance");
  });

  it("ArrowDown 移动光标，Enter 执行选中项", () => {
    const { onAction } = renderPalette();

    const input = screen.getByTestId("cmd-input");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onAction).toHaveBeenCalledWith("run-pipeline");
  });

  it("点击工程项切换工程并关闭面板", () => {
    const { onSelectProject, onClose } = renderPalette();

    fireEvent.click(screen.getByTestId("cmd-item-project-p2"));

    expect(onSelectProject).toHaveBeenCalledWith("p2");
    expect(onClose).toHaveBeenCalled();
  });

  it("搜索关键字可命中治理工具描述", () => {
    renderPalette();
    fireEvent.change(screen.getByTestId("cmd-input"), {
      target: { value: "红黄绿" },
    });
    expect(screen.getByTestId("cmd-item-gov-compliance")).toBeInTheDocument();
    expect(screen.queryByTestId("cmd-item-gov-traceability")).toBeNull();
  });

  it("无匹配时展示空态", () => {
    renderPalette();
    fireEvent.change(screen.getByTestId("cmd-input"), {
      target: { value: "zzzz" },
    });
    expect(screen.getByText("没有匹配的命令")).toBeInTheDocument();
  });

  it("Esc 关闭面板", () => {
    const { onClose } = renderPalette();
    fireEvent.keyDown(screen.getByTestId("cmd-input"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

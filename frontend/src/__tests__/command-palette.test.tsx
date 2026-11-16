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

const FILES = ["requirements/requirements.md", "code/self_test.c"];

function renderPalette(open = true, activeId: string | null = "p1", files = FILES) {
  const onClose = jest.fn();
  const onSelectProject = jest.fn();
  const onOpenFile = jest.fn();
  const onGovernance = jest.fn();
  const onAction = jest.fn();
  render(
    <CommandPalette
      open={open}
      onClose={onClose}
      projects={PROJECTS}
      activeId={activeId}
      files={files}
      onSelectProject={onSelectProject}
      onOpenFile={onOpenFile}
      onGovernance={onGovernance}
      onAction={onAction}
    />,
  );
  return { onClose, onSelectProject, onOpenFile, onGovernance, onAction };
}

describe("CommandPalette", () => {
  it("打开后按「操作 / 工程 / 治理分组」展示命令", () => {
    renderPalette();

    expect(screen.getByTestId("cmd-palette")).toBeInTheDocument();
    expect(screen.getByText("操作")).toBeInTheDocument();
    expect(screen.getByText("工程")).toBeInTheDocument();
    expect(screen.getByText("产物文件")).toBeInTheDocument();
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

  it("按文件名搜索并快速打开产物文件", () => {
    const { onOpenFile, onClose } = renderPalette();

    fireEvent.change(screen.getByTestId("cmd-input"), {
      target: { value: "self_test" },
    });
    fireEvent.keyDown(screen.getByTestId("cmd-input"), { key: "Enter" });

    expect(onOpenFile).toHaveBeenCalledWith("code/self_test.c");
    expect(onClose).toHaveBeenCalled();
  });

  it("无产物文件时不展示文件分组", () => {
    renderPalette(true, "p1", []);
    expect(screen.queryByText("产物文件")).toBeNull();
  });

  it("展示最近打开文件并置顶打开", () => {
    const onOpenFile = jest.fn();
    render(
      <CommandPalette
        open
        onClose={jest.fn()}
        projects={PROJECTS}
        activeId="p1"
        files={FILES}
        recentFiles={["code/self_test.c", "code/missing.c"]}
        onSelectProject={jest.fn()}
        onOpenFile={onOpenFile}
        onGovernance={jest.fn()}
        onAction={jest.fn()}
      />,
    );

    expect(screen.getByText("最近打开")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("cmd-item-recent-code/self_test.c"));
    expect(onOpenFile).toHaveBeenCalledWith("code/self_test.c");
  });

  it("运行中展示取消、选中文件时展示复制路径与缺口入口", () => {
    const onAction = jest.fn();
    render(
      <CommandPalette
        open
        onClose={jest.fn()}
        projects={PROJECTS}
        activeId="p1"
        files={FILES}
        canCancel
        hasSelection
        notificationsOn={false}
        onSelectProject={jest.fn()}
        onOpenFile={jest.fn()}
        onGovernance={jest.fn()}
        onAction={onAction}
      />,
    );

    fireEvent.click(screen.getByTestId("cmd-item-action-cancel-run"));
    expect(onAction).toHaveBeenCalledWith("cancel-run");
    fireEvent.click(screen.getByTestId("cmd-item-action-copy-path"));
    expect(onAction).toHaveBeenCalledWith("copy-path");
    fireEvent.click(screen.getByTestId("cmd-item-action-open-gaps"));
    expect(onAction).toHaveBeenCalledWith("open-gaps");
    // notificationsOn=false → 菜单项文案应是「开启桌面通知」
    expect(screen.getByText("开启桌面通知")).toBeInTheDocument();
  });
});

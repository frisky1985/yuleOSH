/**
 * GovernanceMenu 单元测试：分组菜单的展开、选择回调与关闭行为。
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { GovernanceMenu, GOVERNANCE_GROUPS } from "@/components/desktop/governance-menu";

function renderMenu(disabled = false) {
  const onSelect = jest.fn();
  render(<GovernanceMenu disabled={disabled} onSelect={onSelect} />);
  return { onSelect };
}

describe("GovernanceMenu", () => {
  it("默认折叠，点击后按关注点分组展示 9 个入口", () => {
    renderMenu();
    expect(screen.queryByTestId("gov-menu")).toBeNull();

    fireEvent.click(screen.getByTestId("gov-trigger"));

    expect(screen.getByTestId("gov-menu")).toBeInTheDocument();
    expect(screen.getByText("追溯与变更")).toBeInTheDocument();
    expect(screen.getByText("质量与合规")).toBeInTheDocument();
    expect(screen.getByText("问题与审计")).toBeInTheDocument();
    expect(screen.getByText("项目管理")).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem")).toHaveLength(9);
  });

  it("选择入口后回调对应 key 并收起菜单", () => {
    const { onSelect } = renderMenu();
    fireEvent.click(screen.getByTestId("gov-trigger"));

    fireEvent.click(screen.getByTestId("gov-item-traceability"));

    expect(onSelect).toHaveBeenCalledWith("traceability");
    expect(screen.queryByTestId("gov-menu")).toBeNull();
  });

  it("每个 key 都能正确回调", () => {
    const { onSelect } = renderMenu();
    const keys = GOVERNANCE_GROUPS.flatMap((g) => g.items.map((i) => i.key));
    for (const key of keys) {
      fireEvent.click(screen.getByTestId("gov-trigger"));
      fireEvent.click(screen.getByTestId(`gov-item-${key}`));
    }
    expect(onSelect.mock.calls.map(([k]) => k)).toEqual(keys);
  });

  it("Esc 关闭菜单", () => {
    renderMenu();
    fireEvent.click(screen.getByTestId("gov-trigger"));
    expect(screen.getByTestId("gov-menu")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByTestId("gov-menu")).toBeNull();
  });

  it("点击外部关闭菜单", () => {
    renderMenu();
    fireEvent.click(screen.getByTestId("gov-trigger"));

    fireEvent.mouseDown(document.body);

    expect(screen.queryByTestId("gov-menu")).toBeNull();
  });

  it("禁用时不能展开", () => {
    renderMenu(true);
    const trigger = screen.getByTestId("gov-trigger");
    expect(trigger).toBeDisabled();

    fireEvent.click(trigger);

    expect(screen.queryByTestId("gov-menu")).toBeNull();
  });
});

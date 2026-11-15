/**
 * ProjectActionsMenu 单元测试。
 *
 * 覆盖点：
 *  - 点击「⋯」打开菜单，展示重命名 / 同步 / 删除
 *  - 重命名提交 PATCH，成功后回调 onUpdated
 *  - 删除确认后调用 DELETE，并回调 onDeleted
 *  - 菜单中的「立即同步」转调 onSync，同步中禁用
 *  - 接口失败时展示错误
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ProjectActionsMenu } from "@/components/desktop/project-actions-menu";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const fetchMock = jest.fn();
const PROJECT = { id: "p1", name: "旧名字", description: "旧描述" };

beforeAll(() => {
  if (!("ResizeObserver" in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderMenu(over: Partial<React.ComponentProps<typeof ProjectActionsMenu>> = {}) {
  const handlers = {
    onSync: jest.fn(),
    onUpdated: jest.fn(),
    onDeleted: jest.fn(),
  };
  render(
    <ProjectActionsMenu
      project={PROJECT}
      syncing={false}
      {...handlers}
      {...over}
    />,
  );
  return handlers;
}

describe("ProjectActionsMenu", () => {
  it("打开菜单并展示三项操作", () => {
    renderMenu();
    expect(screen.queryByTestId("project-actions-menu")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("project-actions-trigger"));

    expect(screen.getByTestId("project-actions-menu")).toBeInTheDocument();
    expect(screen.getByTestId("project-action-rename")).toBeInTheDocument();
    expect(screen.getByTestId("project-action-sync")).toBeInTheDocument();
    expect(screen.getByTestId("project-action-delete")).toBeInTheDocument();
  });

  it("重命名提交 PATCH 并回调 onUpdated", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({ project: { id: "p1", name: "新名字", description: "新描述" } }),
    );
    const { onUpdated } = renderMenu();

    fireEvent.click(screen.getByTestId("project-actions-trigger"));
    fireEvent.click(screen.getByTestId("project-action-rename"));

    const nameInput = screen.getByTestId("project-rename-name") as HTMLInputElement;
    expect(nameInput.value).toBe("旧名字");
    fireEvent.change(nameInput, { target: { value: " 新名字 " } });
    fireEvent.change(screen.getByTestId("project-rename-description"), {
      target: { value: " 新描述 " },
    });
    fireEvent.click(screen.getByTestId("project-rename-confirm"));

    await waitFor(() =>
      expect(onUpdated).toHaveBeenCalledWith({
        id: "p1",
        name: "新名字",
        description: "新描述",
      }),
    );
    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/v1/desktop/projects/p1");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body)).toEqual({ name: "新名字", description: "新描述" });
    expect(screen.queryByTestId("project-rename-dialog")).not.toBeInTheDocument();
  });

  it("删除工程调用 DELETE 并回调 onDeleted", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: true }));
    const { onDeleted } = renderMenu();

    fireEvent.click(screen.getByTestId("project-actions-trigger"));
    fireEvent.click(screen.getByTestId("project-action-delete"));
    expect(screen.getByTestId("project-delete-dialog")).toHaveTextContent("旧名字");
    fireEvent.click(screen.getByTestId("project-delete-confirm"));

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("p1"));
    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/v1/desktop/projects/p1");
    expect(options.method).toBe("DELETE");
  });

  it("同步入口转调 onSync", () => {
    const { onSync } = renderMenu();
    fireEvent.click(screen.getByTestId("project-actions-trigger"));
    fireEvent.click(screen.getByTestId("project-action-sync"));
    expect(onSync).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("project-actions-menu")).not.toBeInTheDocument();
  });

  it("同步中禁用同步入口", () => {
    renderMenu({ syncing: true });
    fireEvent.click(screen.getByTestId("project-actions-trigger"));
    expect(screen.getByTestId("project-action-sync")).toBeDisabled();
  });

  it("重命名失败时展示后端错误", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ ok: false, error: "名称重复" }, 400));
    const { onUpdated } = renderMenu();

    fireEvent.click(screen.getByTestId("project-actions-trigger"));
    fireEvent.click(screen.getByTestId("project-action-rename"));
    fireEvent.click(screen.getByTestId("project-rename-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("project-rename-dialog")).toHaveTextContent("名称重复"),
    );
    expect(onUpdated).not.toHaveBeenCalled();
  });
});

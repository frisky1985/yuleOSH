/**
 * BaselineDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载基线列表并默认选择「次新 → 最新」用于比对
 *  - 创建基线（POST 载荷）与同名冲突（409）错误提示
 *  - 展开行按需加载文件清单
 *  - 基线比对请求与差异渲染（新增 / 删除 / 修改 + 证据路径）
 *  - 少于两个基线时禁用比对
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BaselineDialog } from "@/components/desktop/baseline-dialog";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response);
}

const B2 = {
  name: "B2",
  label: "R1.1",
  author: "local",
  pipeline_run: null,
  created_at: "2026-11-15T10:00:00",
  file_count: 3,
  manifest_sha256: "b2hash",
};
const B1 = {
  name: "B1",
  label: "R1.0",
  author: "local",
  pipeline_run: "job-123456789",
  created_at: "2026-11-14T10:00:00",
  file_count: 2,
  manifest_sha256: "b1hash",
};

const DIFF = {
  from: "B1",
  to: "B2",
  generated_at: "2026-11-15T10:05:00",
  added: ["tests/test_main.c"],
  removed: ["code/old.c"],
  modified: [{ path: "requirements/requirements.md", sha256_from: "a", sha256_to: "b" }],
  summary: { added: 1, removed: 1, modified: 1, total_changes: 3 },
  evidence_path: ".osh/evidence/baseline-diff-B1--B2.json",
};

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

function renderDialog(projectId: string | null = "p1") {
  render(<BaselineDialog open onOpenChange={jest.fn()} projectId={projectId} />);
}

describe("BaselineDialog", () => {
  it("加载基线列表并默认选择次新→最新", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ baselines: [B2, B1] }));
    renderDialog();

    expect(await screen.findByTestId("baseline-table")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/baselines",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByTestId("baseline-row-B2")).toHaveTextContent("R1.1");

    expect((screen.getByTestId("baseline-diff-from") as HTMLSelectElement).value).toBe("B1");
    expect((screen.getByTestId("baseline-diff-to") as HTMLSelectElement).value).toBe("B2");
  });

  it("创建基线时提交名称/标签/备注并刷新列表", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ baselines: [] }));
    renderDialog();
    await screen.findByTestId("baseline-empty");

    fetchMock.mockReturnValueOnce(jsonResponse({ baseline: { ...B1, name: "B1" } }, 201));
    fetchMock.mockReturnValueOnce(jsonResponse({ baselines: [B1] }));

    fireEvent.change(screen.getByTestId("baseline-name"), { target: { value: "B1" } });
    fireEvent.change(screen.getByTestId("baseline-label"), { target: { value: "R1.0" } });
    fireEvent.click(screen.getByTestId("baseline-create"));

    expect(await screen.findByTestId("baseline-notice")).toHaveTextContent("已创建基线 B1");
    const [path, opts] = fetchMock.mock.calls[1];
    expect(path).toBe("/api/v1/desktop/projects/p1/baselines");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ name: "B1", label: "R1.0", notes: "" });
    expect(await screen.findByTestId("baseline-row-B1")).toBeInTheDocument();
  });

  it("同名基线冲突时展示后端错误", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ baselines: [B1] }));
    renderDialog();
    await screen.findByTestId("baseline-table");

    fetchMock.mockReturnValueOnce(
      jsonResponse({ ok: false, error: "Baseline already exists: B1" }, 409),
    );
    fireEvent.change(screen.getByTestId("baseline-name"), { target: { value: "B1" } });
    fireEvent.click(screen.getByTestId("baseline-create"));

    expect(await screen.findByTestId("baseline-error")).toHaveTextContent(
      "Baseline already exists: B1",
    );
  });

  it("展开行按需加载基线文件清单", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ baselines: [B2, B1] }));
    renderDialog();
    await screen.findByTestId("baseline-table");

    fetchMock.mockReturnValueOnce(
      jsonResponse({
        baseline: {
          ...B1,
          files: [
            { path: "requirements/requirements.md", sha256: "abcdef012345", size: 10 },
            { path: "code/main.c", sha256: "fedcba987654", size: 20 },
          ],
        },
      }),
    );

    fireEvent.click(screen.getByTestId("baseline-row-B1"));

    expect(await screen.findByText("requirements/requirements.md")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/baselines/B1",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.getByText("abcdef01")).toBeInTheDocument();
  });

  it("比对两个基线并渲染差异", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ baselines: [B2, B1] }));
    renderDialog();
    await screen.findByTestId("baseline-table");

    fetchMock.mockReturnValueOnce(jsonResponse({ diff: DIFF }));
    fireEvent.click(screen.getByTestId("baseline-diff-run"));

    const result = await screen.findByTestId("baseline-diff-result");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/desktop/projects/p1/baselines/diff?from=B1&to=B2",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(result).toHaveTextContent("新增 1");
    expect(result).toHaveTextContent("删除 1");
    expect(result).toHaveTextContent("修改 1");
    expect(result).toHaveTextContent("tests/test_main.c");
    expect(result).toHaveTextContent(".osh/evidence/baseline-diff-B1--B2.json");
  });

  it("只有一个基线时禁用比对", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ baselines: [B1] }));
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("baseline-row-B1")).toBeInTheDocument());

    expect(screen.getByTestId("baseline-diff-run")).toBeDisabled();
    expect(screen.getByText("至少需要两个基线")).toBeInTheDocument();
  });
});

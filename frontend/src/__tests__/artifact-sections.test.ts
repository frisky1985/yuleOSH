import { flattenFiles } from "@/lib/artifact-sections";
import type { TreeNode } from "@/lib/artifact-sections";

describe("flattenFiles", () => {
  it("空树返回空数组", () => {
    expect(flattenFiles(null)).toEqual([]);
    expect(flattenFiles(undefined)).toEqual([]);
  });

  it("文件节点返回自身路径", () => {
    const node: TreeNode = { name: "a.c", path: "code/a.c", type: "file" };
    expect(flattenFiles(node)).toEqual(["code/a.c"]);
  });

  it("按 dfs 前序展平嵌套目录", () => {
    const tree: TreeNode = {
      name: "root",
      path: "",
      type: "dir",
      children: [
        {
          name: "requirements",
          path: "requirements",
          type: "dir",
          children: [
            { name: "requirements.md", path: "requirements/requirements.md", type: "file" },
          ],
        },
        {
          name: "code",
          path: "code",
          type: "dir",
          children: [
            { name: "a.c", path: "code/a.c", type: "file" },
            {
              name: "drivers",
              path: "code/drivers",
              type: "dir",
              children: [{ name: "can.c", path: "code/drivers/can.c", type: "file" }],
            },
          ],
        },
      ],
    };

    expect(flattenFiles(tree)).toEqual([
      "requirements/requirements.md",
      "code/a.c",
      "code/drivers/can.c",
    ]);
  });
});

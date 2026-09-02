import { loadGapSelection, saveGapSelection, gapSelKey } from "@/lib/gap-selection";

// 头脑风暴项①「持久化选择」：差距批量勾选跨刷新保留，按项目隔离。
describe("gap-selection 持久化", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("默认无选择时返回空数组", () => {
    expect(loadGapSelection("proj-1")).toEqual([]);
  });

  it("保存后可按同一项目读回，且与当前可用项求交集由调用方负责", () => {
    saveGapSelection("proj-1", ["g1", "g2", "g3"]);
    expect(loadGapSelection("proj-1")).toEqual(["g1", "g2", "g3"]);
  });

  it("按项目隔离：proj-2 不受影响", () => {
    saveGapSelection("proj-1", ["g1"]);
    saveGapSelection("proj-2", ["x9"]);
    expect(loadGapSelection("proj-1")).toEqual(["g1"]);
    expect(loadGapSelection("proj-2")).toEqual(["x9"]);
    expect(gapSelKey("proj-1")).not.toEqual(gapSelKey("proj-2"));
  });

  it("空数组保存等价于清除键", () => {
    saveGapSelection("proj-1", ["g1"]);
    expect(window.localStorage.getItem(gapSelKey("proj-1"))).not.toBeNull();
    saveGapSelection("proj-1", []);
    expect(window.localStorage.getItem(gapSelKey("proj-1"))).toBeNull();
    expect(loadGapSelection("proj-1")).toEqual([]);
  });

  it("去重：重复 id 仅保留一个", () => {
    saveGapSelection("proj-1", ["g1", "g1", "g2"]);
    expect(loadGapSelection("proj-1")).toEqual(["g1", "g2"]);
  });

  it("损坏数据降级为空数组而非抛错", () => {
    window.localStorage.setItem(gapSelKey("proj-1"), "{not-json");
    expect(loadGapSelection("proj-1")).toEqual([]);
  });
});

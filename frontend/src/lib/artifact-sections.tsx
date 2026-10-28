"use client";

import { AlertTriangle, BookOpen, Sparkles, Code2, TestTube2, ShieldCheck, type LucideIcon } from "lucide-react";

export interface TreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  size?: number;
  children?: TreeNode[];
}

export interface SectionMeta {
  label: string;
  icon: LucideIcon;
  /** 需要人工处理的异常分区（如后端归不了类的产物）。 */
  warn?: boolean;
  hint?: string;
}

export const UNCLASSIFIED_SECTION = "_unclassified";

const SECTION_META: Record<string, SectionMeta> = {
  requirements: { label: "需求", icon: BookOpen },
  design: { label: "设计", icon: Sparkles },
  code: { label: "代码", icon: Code2 },
  tests: { label: "测试用例", icon: TestTube2 },
  evidence: { label: "证据", icon: ShieldCheck },
  [UNCLASSIFIED_SECTION]: {
    label: "待归类",
    icon: AlertTriangle,
    warn: true,
    hint: "未能自动判定分区，需人工移入对应目录",
  },
};

const SECTION_ORDER = ["requirements", "design", "code", "tests", "evidence"];

export function sectionMeta(name: string): SectionMeta {
  return SECTION_META[name] || { label: name, icon: Code2 };
}

/** 取文件路径所属的分区（路径第一段）。 */
export function sectionOf(path: string): string {
  return path.split("/")[0] || "";
}

/** 统计节点下（含自身）的文件数。 */
export function countFiles(node: TreeNode | null | undefined): number {
  if (!node) return 0;
  if (node.type === "file") return 1;
  let n = 0;
  for (const c of node.children || []) n += countFiles(c);
  return n;
}

/** 返回子树里第一个文件的相对路径（dfs 前序）。 */
export function firstFile(node: TreeNode | null | undefined): string | null {
  if (!node) return null;
  if (node.type === "file") return node.path;
  for (const c of node.children || []) {
    const hit = firstFile(c);
    if (hit) return hit;
  }
  return null;
}

/** 递归过滤文件树：路径含 query 则保留，否则剪掉。 */
export function filterTree(node: TreeNode | null | undefined, query: string): TreeNode | null {
  if (!node) return null;
  const q = query.trim().toLowerCase();
  if (!q) return node;
  if (node.type === "file") return node.path.toLowerCase().includes(q) ? node : null;
  const children = (node.children || [])
    .map((c) => filterTree(c, q))
    .filter((c): c is TreeNode => c !== null);
  if (children.length > 0 || node.path.toLowerCase().includes(q)) {
    return { ...node, children };
  }
  return null;
}

/** 把顶层目录按 SECTION_ORDER 排列，末尾追加"其他"。始终保证 requirements 在前。 */
export function buildSections(tree: TreeNode | null): TreeNode[] {
  const dirs = (tree?.children || []).filter((c) => c.type === "dir" && c.name !== "pipeline");
  const byName = new Map(dirs.map((d) => [d.name, d]));
  const ordered = SECTION_ORDER.filter((n) => byName.has(n)).map((n) => byName.get(n)!);
  const others = dirs.filter((d) => !SECTION_ORDER.includes(d.name));
  const result = [...ordered, ...others];
  if (!result.some((d) => d.name === "requirements")) {
    result.unshift({ name: "requirements", path: "requirements", type: "dir", children: [] });
  }
  return result;
}

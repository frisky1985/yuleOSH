"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Folder,
  File as FileIcon,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  Cloud,
  BookOpen,
  Code2,
  TestTube2,
  ShieldCheck,
} from "lucide-react";
import { apiFetch } from "@/lib/api-fetch";

interface SyncedProject {
  id: string;
  name: string;
  description?: string;
  synced_at: string;
  pipeline_runs?: number;
  last_pipeline_status?: string | null;
}

interface TreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  children?: TreeNode[];
}

export default function DesktopSyncPage() {
  const [projects, setProjects] = useState<SyncedProject[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<{ projects: SyncedProject[] }>("/api/v1/desktop-sync");
      const list = (data.projects || []).sort(
        (a, b) => (b.synced_at || "").localeCompare(a.synced_at || ""),
      );
      setProjects(list);
    } catch (e) {
      console.error("Failed to load synced projects", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Auto-select the first project so the page shows real content on load.
  useEffect(() => {
    if (!activeId && projects.length > 0) setActiveId(projects[0].id);
  }, [projects, activeId]);

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setTree(null);
    setSelectedFile(null);
    setFileContent("");
    (async () => {
      try {
        const data = await apiFetch<{ artifacts: TreeNode }>(
          `/api/v1/desktop-sync/${activeId}`,
        );
        if (cancelled) return;
        const t = data.artifacts || null;
        if (t) t.name = projects.find((p) => p.id === activeId)?.name || t.name;
        setTree(t);
        // Auto-open the first available text artifact for immediate review.
        const first = firstFile(t);
        if (first) await selectFile(activeId, first);
      } catch (e) {
        console.error("Failed to load synced project", e);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  const selectFile = async (projectId: string, relPath: string) => {
    setSelectedFile(relPath);
    try {
      const res = await apiFetch<{ content: string | null; binary: boolean; message?: string }>(
        `/api/v1/desktop-sync/${projectId}/files/${relPath}`,
      );
      setFileContent(res.binary ? res.message || "(二进制文件)" : res.content || "");
    } catch (e) {
      setFileContent(`读取失败: ${(e as Error).message}`);
    }
  };

  const handleSelectFile = async (relPath: string) => {
    if (!activeId) return;
    await selectFile(activeId, relPath);
  };

  return (
    <div className="flex flex-col h-screen bg-[#0a0e17] text-[#e2e8f0] overflow-hidden">
      <header className="flex items-center justify-between px-6 py-4 border-b border-[#1e293b] bg-[#0d111f] shrink-0">
        <div className="flex items-center gap-3">
          <Cloud className="w-6 h-6 text-[#1677ff]" />
          <div>
            <h1 className="text-lg font-bold">桌面工程 · 云端视图</h1>
            <p className="text-xs text-[#64748b]">查看从 yuleOSH Desktop 同步到云端的工程与产出物</p>
          </div>
        </div>
        <button
          onClick={loadProjects}
          className="flex items-center gap-1.5 text-sm text-[#94a3b8] hover:text-white px-3 py-1.5 rounded-md border border-[#1e293b]"
        >
          <RefreshCw className="w-4 h-4" /> 刷新
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Project list */}
        <aside className="w-64 border-r border-[#1e293b] bg-[#0d111f] overflow-y-auto shrink-0">
          <div className="px-3 py-2 text-xs font-semibold text-[#64748b] uppercase tracking-wider">
            同步的工程 ({projects.length})
          </div>
          {loading ? (
            <div className="px-3 py-4 text-xs text-[#64748b]">加载中...</div>
          ) : projects.length === 0 ? (
            <div className="px-3 py-4 text-xs text-[#475569]">
              暂无同步的工程。请在桌面端点击「同步云端」上传工程。
            </div>
          ) : (
            <ul className="space-y-1 px-2">
              {projects.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => setActiveId(p.id)}
                    className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                      activeId === p.id ? "bg-[#1e293b] text-white" : "text-[#94a3b8] hover:bg-[#1e293b]/50"
                    }`}
                  >
                    <div className="font-medium truncate">{p.name}</div>
                    <div className="text-xs text-[#475569] truncate">
                      {p.synced_at ? new Date(p.synced_at).toLocaleString() : "—"}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* Artifact tree + content */}
        <main className="flex flex-1 overflow-hidden">
          <div className="w-60 border-r border-[#1e293b] bg-[#0d111f] overflow-y-auto shrink-0">
            <div className="px-3 py-2 text-xs font-semibold text-[#64748b] uppercase tracking-wider">
              产出物
            </div>
            {tree ? (
              <ArtifactTree node={tree} onSelect={handleSelectFile} selectedFile={selectedFile} />
            ) : (
              <div className="px-3 py-4 text-xs text-[#64748b]">选择一个工程查看产出物</div>
            )}
          </div>
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="px-4 py-2 border-b border-[#1e293b] text-xs text-[#64748b] flex items-center justify-between">
              <span>{selectedFile || "从左侧选择文件查看内容"}</span>
              {selectedFile && <FileIconBadge path={selectedFile} />}
            </div>
            <pre className="flex-1 overflow-auto p-4 text-sm text-[#cbd5e1] font-mono whitespace-pre-wrap leading-relaxed">
              {fileContent || "暂无内容"}
            </pre>
          </div>
        </main>
      </div>
    </div>
  );
}

function firstFile(node: TreeNode | null): string | null {
  if (!node) return null;
  if (node.type === "file") return node.path;
  for (const child of node.children || []) {
    const found = firstFile(child);
    if (found) return found;
  }
  return null;
}

function FileIconBadge({ path }: { path: string }) {
  const lower = path.toLowerCase();
  let Icon = FileIcon;
  if (lower.endsWith(".md") || lower.includes("requirements")) Icon = BookOpen;
  else if (lower.endsWith(".c") || lower.endsWith(".h")) Icon = Code2;
  else if (lower.includes("test")) Icon = TestTube2;
  else if (lower.includes("evidence") || lower.includes("trace")) Icon = ShieldCheck;
  return <Icon className="w-3.5 h-3.5 text-[#64748b]" />;
}

function ArtifactTree({
  node,
  onSelect,
  selectedFile,
  depth = 0,
}: {
  node: TreeNode;
  onSelect: (path: string) => void;
  selectedFile: string | null;
  depth?: number;
}) {
  const [open, setOpen] = useState(depth < 2);
  const isDir = node.type === "dir";
  const hasChildren = isDir && node.children && node.children.length > 0;

  if (depth === 1 && isDir && (!node.children || node.children.length === 0)) {
    return null;
  }

  return (
    <div>
      <div
        className={`flex items-center gap-1 px-2 py-1 rounded cursor-pointer text-xs hover:bg-[#1e293b] ${
          selectedFile === node.path ? "bg-[#1e293b] text-white" : "text-[#94a3b8]"
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={() => {
          if (isDir) setOpen(!open);
          else onSelect(node.path);
        }}
      >
        {isDir ? (
          open ? <ChevronDown className="w-3.5 h-3.5 text-[#64748b]" /> : <ChevronRight className="w-3.5 h-3.5 text-[#64748b]" />
        ) : (
          <span className="w-3.5" />
        )}
        {isDir ? (
          <Folder className="w-3.5 h-3.5 text-[#f59e0b]" />
        ) : (
          <FileIcon className="w-3.5 h-3.5 text-[#64748b]" />
        )}
        <span className="truncate">{node.name}</span>
      </div>
      {isDir && open && hasChildren && (
        <div>
          {node.children!.map((child) => (
            <ArtifactTree
              key={child.path}
              node={child}
              onSelect={onSelect}
              selectedFile={selectedFile}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

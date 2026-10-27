"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  FolderOpen,
  FolderPlus,
  FileText,
  Code2,
  TestTube2,
  Send,
  Play,
  UploadCloud,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  File as FileIcon,
  Folder,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Sparkles,
  Terminal,
  BookOpen,
  ShieldCheck,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { apiFetch } from "@/lib/api-fetch";

// ─── Types ────────────────────────────────────────────────────────────────

interface ProjectMeta {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  pipeline_runs: number;
  last_pipeline_status: string | null;
  cloud_synced: boolean;
  last_synced_at: string | null;
  artifacts?: Record<string, { path: string; exists: boolean; file_count: number }>;
}

interface TreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  size?: number;
  children?: TreeNode[];
}

interface PipelineRun {
  job_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────

const isDesktop = typeof window !== "undefined" && !!(window as any).electronAPI?.isDesktop;

function timeAgo(iso?: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} 小时前`;
  return `${Math.floor(hrs / 24)} 天前`;
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function DesktopWorkspacePage() {
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeProject, setActiveProject] = useState<ProjectMeta | null>(null);
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [activeTab, setActiveTab] = useState<"requirements" | "code" | "tests">("requirements");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [requirements, setRequirements] = useState<string>("");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "你好！我是 yuleOSH 助手。请输入需求（支持自然语言或 OpenSpec 格式），我会帮你导入并自动运行流水线。", timestamp: new Date().toISOString() },
  ]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [running, setRunning] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [showNewProject, setShowNewProject] = useState(false);
  const [loading, setLoading] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // ── Load projects ──────────────────────────────────────────────────────
  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<{ projects: ProjectMeta[] }>("/api/v1/desktop/projects");
      setProjects(data.projects || []);
      if (!activeId && data.projects?.length) {
        setActiveId(data.projects[0].id);
      }
    } catch (e) {
      console.error("Failed to load projects", e);
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // ── Load active project details + tree + requirements ──────────────────
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    (async () => {
      try {
        const proj = await apiFetch<{ project: ProjectMeta }>(`/api/v1/desktop/projects/${activeId}`);
        if (cancelled) return;
        setActiveProject(proj.project);

        const t = await apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`);
        if (cancelled) return;
        setTree(t.tree);

        const req = await apiFetch<{ content: string }>(`/api/v1/desktop/projects/${activeId}/requirements`);
        if (cancelled) return;
        setRequirements(req.content || "");

        const r = await apiFetch<{ runs: PipelineRun[] }>(`/api/v1/desktop/projects/${activeId}/pipeline/runs`);
        if (cancelled) return;
        setRuns(r.runs || []);
      } catch (e) {
        console.error("Failed to load project", e);
      }
    })();
    return () => { cancelled = true; };
  }, [activeId]);

  // ── Auto-scroll chat ───────────────────────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // ── Create project ─────────────────────────────────────────────────────
  const handleCreateProject = async () => {
    const name = newProjectName.trim();
    if (!name) return;
    try {
      const data = await apiFetch<{ project: ProjectMeta }>("/api/v1/desktop/projects", {
        method: "POST",
        body: JSON.stringify({ name, description: "" }),
      });
      setProjects((p) => [data.project, ...p]);
      setActiveId(data.project.id);
      setNewProjectName("");
      setShowNewProject(false);
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: `已创建工程「${name}」。现在可以输入需求了。`,
        timestamp: new Date().toISOString(),
      }]);
    } catch (e) {
      alert(`创建工程失败: ${(e as Error).message}`);
    }
  };

  // ── Import requirements (chatbot / CLI) ────────────────────────────────
  const handleSendChat = async () => {
    const text = chatInput.trim();
    if (!text || !activeId) return;

    // CLI-style commands
    if (text.startsWith("/")) {
      handleCliCommand(text);
      setChatInput("");
      return;
    }

    setChatMessages((m) => [...m, { role: "user", content: text, timestamp: new Date().toISOString() }]);
    setChatInput("");

    try {
      await apiFetch(`/api/v1/desktop/projects/${activeId}/requirements`, {
        method: "POST",
        body: JSON.stringify({ content: text, source: "chatbot" }),
      });
      setRequirements(text);
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: "需求已导入到 requirements/requirements.md。点击「运行流水线」开始生成代码与测试。",
        timestamp: new Date().toISOString(),
      }]);
    } catch (e) {
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: `导入失败: ${(e as Error).message}`,
        timestamp: new Date().toISOString(),
      }]);
    }
  };

  const handleCliCommand = (cmd: string) => {
    const [name, ...args] = cmd.slice(1).split(/\s+/);
    if (name === "run" || name === "pipeline") {
      handleRunPipeline();
    } else if (name === "sync") {
      handleSync();
    } else if (name === "import") {
      handleImportFile();
    } else if (name === "help") {
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: "可用命令:\n  /run          — 运行流水线\n  /sync         — 同步到云端\n  /import       — 从文件导入需求\n  /help         — 显示帮助",
        timestamp: new Date().toISOString(),
      }]);
    } else {
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: `未知命令: /${name}。输入 /help 查看可用命令。`,
        timestamp: new Date().toISOString(),
      }]);
    }
  };

  // ── Import requirements from file (native dialog) ──────────────────────
  const handleImportFile = async () => {
    if (!isDesktop) {
      alert("文件导入仅在桌面端可用。");
      return;
    }
    const path = await (window as any).electronAPI.openFile({ title: "导入需求文档" });
    if (!path) return;
    const res = await (window as any).electronAPI.readFile(path);
    if (!res.ok) {
      alert(`读取失败: ${res.error}`);
      return;
    }
    setChatInput(res.content);
    setChatMessages((m) => [...m, {
      role: "assistant",
      content: `已加载文件内容，点击发送即可导入到工程。`,
      timestamp: new Date().toISOString(),
    }]);
  };

  // ── Run pipeline ───────────────────────────────────────────────────────
  const handleRunPipeline = async () => {
    if (!activeId || running) return;
    setRunning(true);
    setChatMessages((m) => [...m, {
      role: "assistant",
      content: "🚀 开始运行流水线，产出物将写入工程的 design/、code/、tests/、evidence/ 文件夹...",
      timestamp: new Date().toISOString(),
    }]);
    try {
      const res = await apiFetch<{ job_id: string; status: string }>(
        `/api/v1/desktop/projects/${activeId}/pipeline/run`,
        { method: "POST", body: JSON.stringify({ type: "full" }) },
      );
      // Poll for completion (stub job finishes immediately; real jobs poll status).
      const poll = setInterval(async () => {
        try {
          const r = await apiFetch<{ runs: PipelineRun[] }>(
            `/api/v1/desktop/projects/${activeId}/pipeline/runs`,
          );
          setRuns(r.runs || []);
          const latest = r.runs?.[0];
          if (latest && latest.status === "passed") {
            clearInterval(poll);
            setRunning(false);
            // Reload artifacts tree to show generated files.
            const t = await apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`);
            setTree(t.tree);
            setChatMessages((m) => [...m, {
              role: "assistant",
              content: `✅ 流水线完成 (${res.job_id})。产出物已保存到工程文件夹，可在左侧文件树查看。`,
              timestamp: new Date().toISOString(),
            }]);
          } else if (latest && latest.status === "failed") {
            clearInterval(poll);
            setRunning(false);
            setChatMessages((m) => [...m, {
              role: "assistant",
              content: `❌ 流水线失败 (${res.job_id})。`,
              timestamp: new Date().toISOString(),
            }]);
          }
        } catch {
          // ignore poll errors
        }
      }, 1500);
      // Safety timeout: stop polling after 120s.
      setTimeout(() => { clearInterval(poll); setRunning(false); }, 120000);
    } catch (e) {
      setRunning(false);
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: `流水线启动失败: ${(e as Error).message}`,
        timestamp: new Date().toISOString(),
      }]);
    }
  };

  // ── Sync to cloud ──────────────────────────────────────────────────────
  const handleSync = async () => {
    if (!activeId || syncing) return;
    setSyncing(true);
    try {
      const res = await apiFetch<{ ok: boolean; synced?: boolean; pending?: boolean; error?: string }>(
        `/api/v1/desktop/projects/${activeId}/sync`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (res.synced) {
        setChatMessages((m) => [...m, {
          role: "assistant",
          content: "☁️ 已同步到云端。现在可以通过 Web UI 登录查看相同的产出物。",
          timestamp: new Date().toISOString(),
        }]);
      } else if (res.pending) {
        setChatMessages((m) => [...m, {
          role: "assistant",
          content: `⚠️ 尚未配置云端地址。请在桌面设置中填入 YULEOSH_CLOUD_URL 后重试。\n${res.error || ""}`,
          timestamp: new Date().toISOString(),
        }]);
      } else {
        setChatMessages((m) => [...m, {
          role: "assistant",
          content: `同步失败: ${res.error || "未知错误"}`,
          timestamp: new Date().toISOString(),
        }]);
      }
      // Reload project to refresh sync status.
      const proj = await apiFetch<{ project: ProjectMeta }>(`/api/v1/desktop/projects/${activeId}`);
      setActiveProject(proj.project);
    } catch (e) {
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: `同步失败: ${(e as Error).message}`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setSyncing(false);
    }
  };

  // ── Read artifact file ─────────────────────────────────────────────────
  const handleSelectFile = async (relPath: string) => {
    if (!activeId) return;
    setSelectedFile(relPath);
    try {
      const res = await apiFetch<{ content: string | null; binary: boolean; message?: string }>(
        `/api/v1/desktop/projects/${activeId}/artifacts/${relPath}`,
      );
      setFileContent(res.binary ? res.message || "(二进制文件)" : res.content || "");
    } catch (e) {
      setFileContent(`读取失败: ${(e as Error).message}`);
    }
  };

  // ── Derive the active tab's root folder name ───────────────────────────
  const tabRoot = activeTab; // requirements | code | tests

  return (
    <div className="flex flex-col h-screen bg-[#0a0e17] text-[#e2e8f0] overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-[#1e293b] bg-[#0d111f] shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-xl font-black">
            <span className="text-[#10b981]">yule</span>
            <span className="text-[#1677ff]">OSH</span>
            <span className="text-xs text-[#64748b] ml-2 font-normal">Desktop</span>
          </span>
          <div className="h-6 w-px bg-[#1e293b]" />
          <select
            value={activeId || ""}
            onChange={(e) => setActiveId(e.target.value)}
            className="bg-[#111827] border border-[#1e293b] rounded-md px-3 py-1.5 text-sm text-[#e2e8f0] focus:outline-none focus:border-[#1677ff]"
          >
            {projects.length === 0 && <option value="">（无工程）</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <Button variant="outline" size="sm" onClick={() => setShowNewProject(true)} className="border-[#1e293b] text-[#94a3b8] hover:text-white">
            <FolderPlus className="w-4 h-4 mr-1" /> 新建
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSync}
            disabled={!activeId || syncing}
            className="border-[#1e293b] text-[#94a3b8] hover:text-white"
          >
            {syncing ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <UploadCloud className="w-4 h-4 mr-1" />}
            同步云端
          </Button>
          <Button size="sm" onClick={handleRunPipeline} disabled={!activeId || running}
            className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white">
            {running ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Play className="w-4 h-4 mr-1" />}
            运行流水线
          </Button>
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: artifact tree */}
        <aside className="w-60 border-r border-[#1e293b] bg-[#0d111f] overflow-y-auto shrink-0">
          <div className="px-3 py-2 text-xs font-semibold text-[#64748b] uppercase tracking-wider flex items-center justify-between">
            <span>产出物</span>
            <button onClick={() => activeId && apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`).then(d => setTree(d.tree))}
              className="text-[#64748b] hover:text-white">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
          {tree ? (
            <ArtifactTree node={tree} onSelect={handleSelectFile} selectedFile={selectedFile} />
          ) : (
            <div className="px-3 py-4 text-xs text-[#64748b]">选择一个工程以查看产出物</div>
          )}

          {/* Pipeline runs */}
          <div className="px-3 py-2 mt-2 border-t border-[#1e293b]">
            <div className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-2">流水线记录</div>
            {runs.length === 0 ? (
              <div className="text-xs text-[#475569]">暂无运行记录</div>
            ) : (
              <ul className="space-y-1">
                {runs.slice(0, 8).map((r) => (
                  <li key={r.job_id} className="flex items-center gap-2 text-xs">
                    {r.status === "passed" ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#10b981] shrink-0" />
                    ) : r.status === "failed" ? (
                      <XCircle className="w-3.5 h-3.5 text-[#ef4444] shrink-0" />
                    ) : (
                      <Clock className="w-3.5 h-3.5 text-[#f59e0b] shrink-0" />
                    )}
                    <span className="truncate text-[#94a3b8]">{r.job_id.slice(0, 10)}</span>
                    <span className="text-[#475569] ml-auto">{timeAgo(r.completed_at || r.started_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        {/* Center: three-pane view */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-[#1e293b] bg-[#0d111f] shrink-0">
            {([
              { key: "requirements", label: "需求", icon: BookOpen },
              { key: "code", label: "代码", icon: Code2 },
              { key: "tests", label: "测试用例", icon: TestTube2 },
            ] as const).map((t) => (
              <button
                key={t.key}
                onClick={() => { setActiveTab(t.key); setSelectedFile(null); setFileContent(""); }}
                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === t.key
                    ? "border-[#1677ff] text-white"
                    : "border-transparent text-[#94a3b8] hover:text-white"
                }`}
              >
                <t.icon className="w-4 h-4" />
                {t.label}
              </button>
            ))}
            <div className="ml-auto flex items-center gap-3 px-4 text-xs text-[#64748b]">
              {activeProject && (
                <>
                  <span>运行: {activeProject.pipeline_runs || 0}</span>
                  {activeProject.last_pipeline_status && (
                    <Badge variant="outline" className={
                      activeProject.last_pipeline_status === "passed"
                        ? "border-[#10b981]/40 text-[#10b981]"
                        : "border-[#ef4444]/40 text-[#ef4444]"
                    }>
                      {activeProject.last_pipeline_status}
                    </Badge>
                  )}
                  {activeProject.cloud_synced ? (
                    <span className="flex items-center gap-1 text-[#10b981]"><UploadCloud className="w-3 h-3" />已同步</span>
                  ) : null}
                </>
              )}
            </div>
          </div>

          {/* Content pane */}
          <div className="flex-1 overflow-hidden">
            {activeTab === "requirements" ? (
              <div className="h-full flex flex-col">
                <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e293b]">
                  <span className="text-xs text-[#64748b]">requirements/requirements.md</span>
                  <span className="text-xs text-[#475569]">{requirements.length} 字符</span>
                </div>
                <pre className="flex-1 overflow-auto p-4 text-sm text-[#cbd5e1] font-mono whitespace-pre-wrap leading-relaxed">
                  {requirements || "暂无需求。在下方对话框输入需求，或使用 /import 从文件导入。"}
                </pre>
              </div>
            ) : (
              <div className="h-full flex flex-col">
                <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e293b]">
                  <span className="text-xs text-[#64748b]">{selectedFile || `从左侧选择 ${activeTab}/ 下的文件`}</span>
                </div>
                <pre className="flex-1 overflow-auto p-4 text-sm text-[#cbd5e1] font-mono whitespace-pre-wrap leading-relaxed">
                  {fileContent || `展开左侧 ${activeTab}/ 文件夹，点击文件查看内容。`}
                </pre>
              </div>
            )}
          </div>

          {/* Chatbot / CLI input */}
          <div className="border-t border-[#1e293b] bg-[#0d111f] shrink-0">
            <div className="max-h-48 overflow-y-auto px-4 py-2 space-y-2">
              {chatMessages.slice(-6).map((m, i) => (
                <div key={i} className={`text-xs flex gap-2 ${m.role === "user" ? "text-[#93c5fd]" : "text-[#94a3b8]"}`}>
                  <span className="font-semibold shrink-0">{m.role === "user" ? "你:" : "助手:"}</span>
                  <span className="whitespace-pre-wrap">{m.content}</span>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
            <div className="flex items-center gap-2 px-4 py-3 border-t border-[#1e293b]">
              <Terminal className="w-4 h-4 text-[#64748b] shrink-0" />
              <Input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSendChat()}
                placeholder="输入需求，或 /run 运行流水线、/import 导入文件、/sync 同步云端、/help 帮助"
                className="bg-[#111827] border-[#1e293b] text-sm"
              />
              <Button size="sm" onClick={handleSendChat} disabled={!activeId}
                className="bg-gradient-to-r from-[#10b981] to-[#059669] text-white">
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </main>
      </div>

      {/* ── New project dialog ─────────────────────────────────────────── */}
      {showNewProject && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setShowNewProject(false)}>
          <Card className="w-[400px] bg-[#0d111f] border-[#1e293b]" onClick={(e) => e.stopPropagation()}>
            <CardHeader>
              <CardTitle className="text-[#e2e8f0] flex items-center gap-2">
                <FolderPlus className="w-5 h-5 text-[#1677ff]" /> 新建工程
              </CardTitle>
              <CardDescription className="text-[#64748b]">创建一个本地工程，产出物将保存在独立文件夹中。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                autoFocus
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
                placeholder="工程名称，如：智能车灯控制器"
                className="bg-[#111827] border-[#1e293b] text-[#e2e8f0]"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setShowNewProject(false)}
                  className="border-[#1e293b] text-[#94a3b8]">取消</Button>
                <Button size="sm" onClick={handleCreateProject} disabled={!newProjectName.trim()}
                  className="bg-gradient-to-r from-[#10b981] to-[#059669] text-white">
                  <Plus className="w-4 h-4 mr-1" /> 创建
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ─── Artifact tree component ──────────────────────────────────────────────

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

  // Hide empty top-level artifact dirs that have no files.
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

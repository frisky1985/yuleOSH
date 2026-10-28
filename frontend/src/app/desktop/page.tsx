"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
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
  Terminal,
  BookOpen,
  ShieldCheck,
  Sparkles,
  Plus,
  Search,
  Filter,
  ChevronsUpDown,
  ChevronsDownUp,
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
import {
  buildSections,
  countFiles,
  filterTree,
  firstFile,
  sectionMeta,
  sectionOf,
  type TreeNode,
} from "@/lib/artifact-sections";
import { CodeBlock } from "@/components/code-block";

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
  const [query, setQuery] = useState("");
  const [onlyWithFiles, setOnlyWithFiles] = useState(false);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    requirements: true, design: false, code: false, tests: false, evidence: false,
  });
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [reviewComment, setReviewComment] = useState("");
  const [reviews, setReviews] = useState<Array<{
    id: string; artifact: string; status: string; comment: string; author: string; created_at: string;
  }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "你好！我是 yuleOSH 助手。请输入需求（支持自然语言或 OpenSpec 格式），我会帮你导入并自动运行流水线。", timestamp: new Date().toISOString() },
  ]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [running, setRunning] = useState(false);
  const [pollProgress, setPollProgress] = useState(0);
  const [pollStage, setPollStage] = useState<string | null>(null);
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

  // ── Load active project details + tree + auto-select first file ────────
  const findArtifactPath = useCallback((node: TreeNode | null | undefined, target: string): string | null => {
    if (!node) return null;
    if (node.type === "file" && node.path === target) return node.path;
    for (const c of node.children || []) {
      const hit = findArtifactPath(c, target);
      if (hit) return hit;
    }
    return null;
  }, []);

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

        // 需求只有一份数据源：requirements/requirements.md。加载后直接选中它。
        // 若该文件还不存在（工程刚创建），则让右侧展示空态。
        setSelectedFile(null);
        setFileContent("");
        const reqPath = findArtifactPath(t.tree, "requirements/requirements.md");
        if (reqPath) {
          try {
            const f = await apiFetch<{ content: string }>(
              `/api/v1/desktop/projects/${activeId}/artifacts/${encodeURIComponent(reqPath).replace(/%2F/g, "/")}`,
            );
            if (cancelled) return;
            setSelectedFile(reqPath);
            setFileContent(f.content || "");
            setOpenSections((s) => ({ ...s, requirements: true }));
          } catch { /* 读不到内容也没关系，文件路径存在就够了 */ }
        }

        const r = await apiFetch<{ runs: PipelineRun[] }>(`/api/v1/desktop/projects/${activeId}/pipeline/runs`);
        if (cancelled) return;
        setRuns(r.runs || []);
      } catch (e) {
        console.error("Failed to load project", e);
      }
    })();
    return () => { cancelled = true; };
  }, [activeId, findArtifactPath]);

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

  // ── Error feedback via chatbot (no alert() breaking the flow) ──────────
  const pushAssistant = useCallback((content: string) => {
    setChatMessages((m) => [...m, { role: "assistant", content, timestamp: new Date().toISOString() }]);
  }, []);

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
      // 刷新产物树 + 直接打开刚落盘的 requirements.md
      const t = await apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`);
      setTree(t.tree);
      setSelectedFile("requirements/requirements.md");
      setFileContent(text);
      setOpenSections((s) => ({ ...s, requirements: true }));
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

  // ── Review helpers ──────────────────────────────────────────────────────
  const loadReviews = useCallback(async () => {
    if (!activeId) return;
    try {
      const r = await apiFetch<{ reviews: typeof reviews }>(
        `/api/v1/desktop/projects/${activeId}/review`,
      );
      setReviews(r.reviews || []);
    } catch { /* evidence/review.json 不存在时 404，正常 */ }
  }, [activeId]);

  const submitReview = async (status: "approved" | "rejected" | "needs_revision") => {
    if (!activeId || !selectedFile) return;
    try {
      await apiFetch<{ review: typeof reviews[number] }>(
        `/api/v1/desktop/projects/${activeId}/review`,
        {
          method: "POST",
          body: JSON.stringify({
            artifact: selectedFile,
            status,
            comment: reviewComment.trim() || undefined,
          }),
        },
      );
      setReviewComment("");
      await loadReviews();
    } catch (e) {
      pushAssistant(`评审提交失败: ${(e as Error).message}`);
    }
  };

  const bulkReview = async (scope: "section" | "all", section?: string,
                            status: "approved" | "rejected" | "needs_revision" = "approved") => {
    if (!activeId) return;
    try {
      const payload: any = { scope, status };
      if (scope === "section" && section) payload.section = section;
      const r = await apiFetch<{ created: number; updated: number }>(
        `/api/v1/desktop/projects/${activeId}/review/bulk`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      await loadReviews();
      pushAssistant(`✅ 批量评审完成：创建 ${r.created} 条，更新 ${r.updated} 条。`);
    } catch (e) {
      pushAssistant(`批量评审失败: ${(e as Error).message}`);
    }
  };

  const exportReviews = async () => {
    if (!activeId) return;
    try {
      const r = await apiFetch<{ content: string; path: string; total: number; summary: any }>(
        `/api/v1/desktop/projects/${activeId}/review/export`,
      );
      pushAssistant(`📄 评审报告已导出到 \`${r.path}\`（${r.total} 条评审）。可在 evidence 分区查看。`);
      // 刷新产物树，让 review-report.md 出现
      const t = await apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`);
      setTree(t.tree);
    } catch (e) {
      pushAssistant(`导出评审失败: ${(e as Error).message}`);
    }
  };

  // 切换工程时自动加载评审记录
  useEffect(() => {
    if (activeId) loadReviews();
  }, [activeId, loadReviews]);

  // ── Run pipeline ───────────────────────────────────────────────────────
  const handleRunPipeline = async () => {
    if (!activeId || running) return;
    setRunning(true);
    setPollProgress(0);
    setPollStage(null);
    setChatMessages((m) => [...m, {
      role: "assistant",
      content: "🚀 开始运行流水线，产出物将写入工程的 design/、code/、tests/、evidence/ 文件夹...",
      timestamp: new Date().toISOString(),
    }]);
    try {
      const res = await apiFetch<{ job_id: string; status: string; poll_url: string }>(
        `/api/v1/desktop/projects/${activeId}/pipeline/run`,
        { method: "POST", body: JSON.stringify({ type: "full" }) },
      );

      // 用 poll_url（来自后端）拿真实状态，不再用 /pipeline/runs 磁盘记录。
      const pollUrl = res.poll_url || `/api/v1/desktop/projects/${activeId}/pipeline/status/${res.job_id}`;
      const pollTimer = window.setInterval(async () => {
        try {
          const s = await apiFetch<{
            status: string; progress: number; current_stage?: string;
            stages?: Array<{ key: string; name?: string; status: string }>;
            logs?: string[]; result?: any;
          }>(pollUrl);
          setPollProgress(s.progress ?? 0);
          const currentStage = s.stages?.find((st) => st.status === "running");
          setPollStage(currentStage?.name || currentStage?.key || s.current_stage || null);

          // 把最新日志追加到对话里（每 3 秒最多一条，避免刷屏）
          if (s.logs && s.logs.length > 0 && Math.random() < 0.3) {
            const tail = s.logs[s.logs.length - 1];
            setChatMessages((m) => m.length > 0 && m[m.length - 1].content.includes(tail)
              ? m
              : [...m, { role: "assistant", content: `📋 ${tail}`, timestamp: new Date().toISOString() }]);
          }

          if (s.status === "passed" || s.status === "failed") {
            window.clearInterval(pollTimer);
            setRunning(false);
            setPollProgress(0);
            setPollStage(null);
            // 刷新 runs 列表和产物树
            const [, runList] = await Promise.all([
              apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`).then((t) => setTree(t.tree)).catch(() => {}),
              apiFetch<{ runs: PipelineRun[] }>(`/api/v1/desktop/projects/${activeId}/pipeline/runs`).then((r) => setRuns(r.runs || [])).catch(() => {}),
            ]);
            if (s.status === "passed") {
              setChatMessages((m) => [...m, {
                role: "assistant",
                content: `✅ 流水线完成 (${res.job_id})。产出物已保存到工程文件夹，可在左侧文件树查看。`,
                timestamp: new Date().toISOString(),
              }]);
            } else {
              const err = s.result?.error || s.result?.summary || "未知错误";
              setChatMessages((m) => [...m, {
                role: "assistant",
                content: `❌ 流水线失败 (${res.job_id})：${err}`,
                timestamp: new Date().toISOString(),
              }]);
            }
          }
        } catch { /* 轮询中途报错忽略，下一轮继续 */ }
      }, 1500);

      // Safety timeout: stop polling after 5 min.
      window.setTimeout(() => {
        window.clearInterval(pollTimer);
        setRunning(false);
        setPollProgress(0);
        setPollStage(null);
      }, 300000);
    } catch (e) {
      setRunning(false);
      setPollProgress(0);
      setPollStage(null);
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
      const res = await apiFetch<{
        ok: boolean; synced?: boolean; pending?: boolean; error?: string;
        changed_files?: number; removed_files?: number; total_files?: number; skipped?: boolean;
      }>(
        `/api/v1/desktop/projects/${activeId}/sync`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (res.synced) {
        const changed = res.changed_files ?? 0;
        const removed = res.removed_files ?? 0;
        const total = res.total_files ?? 0;
        const skipped = res.skipped;
        let msg = "☁️ 已同步到云端。";
        if (skipped) {
          msg += ` 产物无变化，跳过上传。`;
        } else {
          msg += ` 变更 ${changed} 个文件，删除 ${removed} 个，共 ${total} 个产物文件。`;
        }
        msg += ` 现在可以通过 Web UI 登录查看相同的产出物。`;
        setChatMessages((m) => [...m, {
          role: "assistant", content: msg, timestamp: new Date().toISOString(),
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
    // 展开该文件所属分区（若未展开）
    const section = sectionOf(relPath);
    if (section && !openSections[section]) {
      setOpenSections((s) => ({ ...s, [section]: true }));
    }
    try {
      const res = await apiFetch<{ content: string | null; binary: boolean; message?: string }>(
        `/api/v1/desktop/projects/${activeId}/artifacts/${encodeURIComponent(relPath).replace(/%2F/g, "/")}`,
      );
      setFileContent(res.binary ? res.message || "(二进制文件)" : res.content || "");
    } catch (e) {
      setFileContent(`读取失败: ${(e as Error).message}`);
    }
  };

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
          {running && (
            <div className="flex items-center gap-2 min-w-[180px]">
              <div className="h-1.5 w-24 bg-[#1e293b] rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-[#722ed1] to-[#1677ff] transition-all duration-500"
                  style={{ width: `${pollProgress}%` }} />
              </div>
              <span className="text-xs text-[#f59e0b] tabular-nums">
                {pollProgress}% {pollStage ? `· ${pollStage}` : ""}
              </span>
            </div>
          )}
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: 5-section artifact tree */}
        <aside className="w-64 border-r border-[#1e293b] bg-[#0d111f] overflow-y-auto shrink-0 flex flex-col">
          <div className="px-3 py-2 text-xs font-semibold text-[#64748b] uppercase tracking-wider flex items-center justify-between shrink-0">
            <span>产出物分区</span>
            <button onClick={() => activeId && apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`).then(d => setTree(d.tree))}
              className="text-[#64748b] hover:text-white" title="刷新">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* 工具栏：搜索 + 展开/折叠 + 过滤 */}
          <div className="px-3 pb-2 space-y-1.5 shrink-0">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#475569]" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索文件..."
                className="bg-[#111827] border-[#1e293b] text-xs h-7 pl-7"
              />
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-[#64748b]">
              <button
                onClick={() => setOpenSections(Object.fromEntries(Object.keys(openSections).map(k => [k, true])))}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-[#1e293b]"
                title="全部展开">
                <ChevronsDownUp className="w-3 h-3" /> 展开
              </button>
              <button
                onClick={() => setOpenSections(Object.fromEntries(Object.keys(openSections).map(k => [k, false])))}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-[#1e293b]"
                title="全部折叠">
                <ChevronsUpDown className="w-3 h-3" /> 折叠
              </button>
              <button
                onClick={() => setOnlyWithFiles((v) => !v)}
                className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${onlyWithFiles ? "text-[#93c5fd] bg-[#1e293b]" : "hover:bg-[#1e293b]"}`}>
                <Filter className="w-3 h-3" /> 有产物
              </button>
            </div>
          </div>

          {/* 5 大固定分区 */}
          <div className="flex-1 overflow-y-auto px-1 pb-2">
            {(() => {
              const sections = buildSections(tree).map((sec) => {
                const filtered = filterTree(sec, query);
                return { sec, filtered, count: countFiles(filtered) };
              }).filter(({ count }) => !onlyWithFiles || count > 0);
              if (sections.length === 0) return <div className="px-2 py-4 text-xs text-[#475569] text-center">暂无产物</div>;

              return sections.map(({ sec, filtered, count }) => {
                const isOpen = query.trim() ? true : (openSections[sec.name] ?? true);
                const meta = sectionMeta(sec.name);
                const Icon = meta.icon;
                return (
                  <div key={sec.name} className="mb-1">
                    <button
                      onClick={() => {
                        const willOpen = !isOpen;
                        setOpenSections((s) => ({ ...s, [sec.name]: willOpen }));
                        // 点击分区标题：若展开且当前文件不属于该分区，自动打开首个文件
                        if (willOpen && (!selectedFile || sectionOf(selectedFile) !== sec.name)) {
                          const first = firstFile(filtered);
                          if (first) {
                            handleSelectFile(first);
                          } else {
                            setSelectedFile(null);
                            setFileContent("");
                          }
                        }
                      }}
                      className={`w-full flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium rounded transition-colors ${
                        selectedFile && sectionOf(selectedFile) === sec.name
                          ? "bg-[#1e293b] text-white"
                          : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]/60"
                      }`}>
                      {isOpen ? <ChevronDown className="w-3 h-3 shrink-0" /> : <ChevronRight className="w-3 h-3 shrink-0" />}
                      <Icon className={`w-3.5 h-3.5 shrink-0 ${meta.warn ? "text-[#f59e0b]" : ""}`} />
                      <span className={`flex-1 text-left ${meta.warn ? "text-[#fbbf24]" : ""}`}>{meta.label}</span>
                      <span className={`text-[10px] tabular-nums ${count === 0 ? "text-[#475569]" : meta.warn ? "text-[#f59e0b]" : "text-[#64748b]"}`}>{count}</span>
                    </button>
                    {meta.hint && isOpen && count > 0 && (
                      <div className="px-2 pb-1 text-[10px] leading-relaxed text-[#f59e0b]/70">{meta.hint}</div>
                    )}
                    {isOpen && filtered && filtered.children && filtered.children.length > 0 && (
                      <ArtifactTreeLite
                        nodes={filtered.children}
                        depth={0}
                        onSelect={handleSelectFile}
                        selectedFile={selectedFile}
                      />
                    )}
                  </div>
                );
              });
            })()}
          </div>

          {/* Pipeline runs */}
          <div className="px-3 py-2 border-t border-[#1e293b] shrink-0">
            <div className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-2">流水线记录</div>
            {runs.length === 0 ? (
              <div className="text-xs text-[#475569]">暂无运行记录</div>
            ) : (
              <ul className="space-y-1">
                {runs.slice(0, 6).map((r) => (
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

        {/* Center: unified code view */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Breadcrumb */}
          <div className="flex border-b border-[#1e293b] bg-[#0d111f] shrink-0 items-center justify-between px-4 py-2">
            <div className="flex items-center gap-2 text-xs text-[#64748b]">
              {selectedFile ? (
                <>
                  <span className="text-[#94a3b8]">{sectionOf(selectedFile)}</span>
                  <span className="text-[#334155]">/</span>
                  <span className="text-[#cbd5e1] truncate max-w-[360px]">{selectedFile}</span>
                  {(() => {
                    const rev = [...reviews].reverse().find((r) => r.artifact === selectedFile);
                    if (!rev) return null;
                    return (
                      <Badge variant="outline" className={
                        rev.status === "approved" ? "border-[#10b981]/40 text-[#10b981]"
                          : rev.status === "rejected" ? "border-[#ef4444]/40 text-[#ef4444]"
                          : "border-[#f59e0b]/40 text-[#fbbf24]"
                      }>
                        {rev.status === "approved" ? "已通过" : rev.status === "rejected" ? "已退回" : "待修改"}
                      </Badge>
                    );
                  })()}
                </>
              ) : (
                <span className="text-[#475569]">从左侧选择文件查看</span>
              )}
            </div>
            {activeProject && (
              <div className="flex items-center gap-3 text-xs text-[#64748b]">
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
              </div>
            )}
          </div>

          {/* Content pane — unified */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {selectedFile ? (
              <CodeBlock content={fileContent} path={selectedFile} />
            ) : (
              <div className="flex-1 flex items-center justify-center text-center px-8">
                <div className="space-y-2">
                  <div className="text-5xl">📂</div>
                  <div className="text-[#64748b] text-sm">展开左侧「{(() => {
                    const sections = buildSections(tree);
                    return sections[0] ? sectionMeta(sections[0].name).label : "需求";
                  })()}」分区，点击文件查看内容</div>
                </div>
              </div>
            )}

            {/* Review panel —挂在底部，与文件内容解耦 */}
            {selectedFile && (
              <div className="border-t border-[#1e293b] bg-[#0d111f] shrink-0 px-4 py-3 space-y-2">
                {(() => {
                  const mine = reviews.filter((r) => r.artifact === selectedFile);
                  if (mine.length === 0) return null;
                  const shown = mine.slice(-4);
                  return (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {mine.length > shown.length && (
                        <span className="text-[10px] text-[#475569]">共 {mine.length} 条 ·</span>
                      )}
                      {shown.map((r) => (
                        <span key={r.id} className={
                          `inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border ${
                            r.status === "approved" ? "border-[#10b981]/40 text-[#10b981] bg-[#10b981]/10" :
                            r.status === "rejected" ? "border-[#ef4444]/40 text-[#ef4444] bg-[#ef4444]/10" :
                            "border-[#f59e0b]/40 text-[#fbbf24] bg-[#f59e0b]/10"
                          }`}>
                          {r.status === "approved" ? "✅ 通过" : r.status === "rejected" ? "❌ 退回" : "🔍 修改"}
                          {r.comment && <span className="truncate max-w-[120px] text-[#94a3b8]">· {r.comment}</span>}
                        </span>
                      ))}
                    </div>
                  );
                })()}

                {/* 批量操作栏 */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] text-[#475569] uppercase tracking-wider mr-1">批量：</span>
                  {(["requirements", "design", "code", "tests", "evidence"] as const).map((sec) => {
                    const meta = sectionMeta(sec);
                    const Icon = meta.icon;
                    return (
                      <button key={sec}
                        onClick={() => bulkReview("section", sec, "approved")}
                        className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border border-[#10b981]/30 text-[#6ee7b7] hover:bg-[#10b981]/15">
                        <Icon className="w-3 h-3" /> 全过 {meta.label}
                      </button>
                    );
                  })}
                  <button
                    onClick={() => bulkReview("all", undefined, "approved")}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border border-[#10b981]/30 text-[#6ee7b7] hover:bg-[#10b981]/15">
                    ✅ 全过全部
                  </button>
                  <button
                    onClick={exportReviews}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border border-[#64748b]/40 text-[#94a3b8] hover:bg-[#1e293b] ml-auto">
                    📄 导出评审报告
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <Input
                    value={reviewComment}
                    onChange={(e) => setReviewComment(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.metaKey || e.ctrlKey)}
                    placeholder="批注（可选，Ctrl+Enter 提交）"
                    className="bg-[#111827] border-[#1e293b] text-xs flex-1 h-8"
                  />
                  <button onClick={() => submitReview("approved")}
                    className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded border border-[#10b981]/40 text-[#10b981] hover:bg-[#10b981]/15">
                    ✅ 通过
                  </button>
                  <button onClick={() => submitReview("needs_revision")}
                    className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded border border-[#f59e0b]/40 text-[#fbbf24] hover:bg-[#f59e0b]/15">
                    🔍 修改
                  </button>
                  <button onClick={() => submitReview("rejected")}
                    className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded border border-[#ef4444]/40 text-[#ef4444] hover:bg-[#ef4444]/15">
                    ❌ 退回
                  </button>
                </div>
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

// ─── Lightweight artifact tree (used under each section) ────────────────

function ArtifactTreeLite({
  nodes,
  depth = 0,
  onSelect,
  selectedFile,
}: {
  nodes: TreeNode[];
  depth?: number;
  onSelect: (path: string) => void;
  selectedFile: string | null;
}) {
  // 目录默认不展开（分区已展开后，再逐层展开文件）
  const [openDirs, setOpenDirs] = useState<Record<string, boolean>>({});

  return (
    <div>
      {nodes.map((node) => {
        const isDir = node.type === "dir";
        const isOpen = openDirs[node.path] ?? false;
        const hasChildren = isDir && (node.children?.length ?? 0) > 0;
        return (
          <div key={node.path}>
            <div
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded cursor-pointer text-[11px] hover:bg-[#1e293b] ${
                selectedFile === node.path ? "bg-[#1e293b] text-white" : "text-[#94a3b8]"
              }`}
              style={{ paddingLeft: `${depth * 10 + 10}px` }}
              onClick={() => {
                if (isDir && hasChildren) {
                  setOpenDirs((s) => ({ ...s, [node.path]: !s[node.path] }));
                } else if (!isDir) {
                  onSelect(node.path);
                }
              }}
            >
              {isDir && hasChildren ? (
                isOpen ? <ChevronDown className="w-3 h-3 text-[#64748b]" /> : <ChevronRight className="w-3 h-3 text-[#64748b]" />
              ) : (
                <span className="w-3" />
              )}
              {isDir ? (
                <Folder className="w-3 h-3 text-[#f59e0b]" />
              ) : (
                <FileIcon className="w-3 h-3 text-[#64748b]" />
              )}
              <span className="truncate">{node.name}</span>
            </div>
            {isDir && isOpen && hasChildren && (
              <ArtifactTreeLite
                nodes={node.children!}
                depth={depth + 1}
                onSelect={onSelect}
                selectedFile={selectedFile}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

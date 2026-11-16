"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import type { DragEvent } from "react";
import { useRouter } from "next/navigation";
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
  Sparkles,
  Search,
  Filter,
  Copy,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Inbox,
  Bell,
  BellOff,
  ChevronsUpDown,
  ChevronsDownUp,
  Settings,
  LogOut,
  LogIn,
  UserRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api-fetch";
import {
  buildSections,
  countFiles,
  filterTree,
  filterTreeByPaths,
  firstFile,
  flattenFiles,
  sectionMeta,
  sectionOf,
  type TreeNode,
} from "@/lib/artifact-sections";
import {
  REVIEW_TONES,
  REVIEW_TONE_META,
  aggregateReviewTone,
  countReviewTones,
  latestReviewByArtifact,
  matchesReviewFilter,
  reviewCoverage,
  reviewToneByArtifact,
  staleArtifactsByTree,
  type ReviewFilter,
  type ReviewTone,
} from "@/lib/review-status";
import { CodeBlock } from "@/components/code-block";
import { AccountInfoDialog } from "@/components/account/account-info-dialog";
import { UserSettingsDialog } from "@/components/account/user-settings-dialog";
import { DesktopLLMSettingsDialog } from "@/components/account/desktop-llm-settings-dialog";
import { LogoutConfirmDialog } from "@/components/account/logout-confirm-dialog";
import { PipelineRunDialog } from "@/components/desktop/pipeline-run-dialog";
import { ProjectWizardDialog } from "@/components/desktop/project-wizard-dialog";
import type { ProjectLite, TemplateApplyResult } from "@/components/desktop/project-wizard-dialog";
import { ProjectActionsMenu } from "@/components/desktop/project-actions-menu";
import type { ProjectRef } from "@/components/desktop/project-actions-menu";
import { TraceabilityDialog } from "@/components/desktop/traceability-dialog";
import { BaselineDialog } from "@/components/desktop/baseline-dialog";
import { ChangeRequestDialog } from "@/components/desktop/change-request-dialog";
import { ComplianceDialog } from "@/components/desktop/compliance-dialog";
import { QualityGatesDialog } from "@/components/desktop/quality-gates-dialog";
import { IssueTrackerDialog } from "@/components/desktop/issue-tracker-dialog";
import { QaAuditDialog } from "@/components/desktop/qa-audit-dialog";
import { ProjectMgmtDialog } from "@/components/desktop/project-mgmt-dialog";
import { ReviewCenterDialog } from "@/components/desktop/review-center-dialog";
import { GovernanceMenu } from "@/components/desktop/governance-menu";
import type { GovernanceKey } from "@/components/desktop/governance-menu";
import { CommandPalette } from "@/components/desktop/command-palette";
import type { CommandActionKey } from "@/components/desktop/command-palette";

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

interface SyncStatus {
  configured: boolean;
  cloud_url: string | null;
  synced: boolean;
  last_synced_at: string | null;
  changed_files: number;
  removed_files: number;
  total_files: number;
  pending: boolean;
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

// ─── Workspace persistence ────────────────────────────────────────────────

const WORKSPACE_STATE_KEY = "yuleosh.desktop.workspace.v1";

interface PersistedWorkspaceState {
  activeId?: string | null;
  openSections?: Record<string, boolean>;
  selectedFile?: string | null;
  query?: string;
  onlyWithFiles?: boolean;
  reviewFilter?: ReviewFilter;
  /** 最近打开的文件（按时间倒序，最多 8 个）。 */
  recentFiles?: string[];
  /** 桌面通知开关。 */
  notificationsOn?: boolean;
}

const NOTIFY_STATE_KEY = "yuleosh.desktop.notify.v1";

function loadWorkspaceState(): PersistedWorkspaceState {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(WORKSPACE_STATE_KEY);
    return raw ? (JSON.parse(raw) as PersistedWorkspaceState) : {};
  } catch {
    return {};
  }
}

function saveWorkspaceState(state: PersistedWorkspaceState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(WORKSPACE_STATE_KEY, JSON.stringify(state));
  } catch {
    /* 隐私模式 / 配额不足时静默忽略 */
  }
}

/** 读取桌面通知开关（默认开启）。 */
function notificationsEnabled(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(NOTIFY_STATE_KEY) !== "off";
  } catch {
    return true;
  }
}

/** 长任务完成后弹桌面通知；在 Electron 里由主进程负责（窗口聚焦时跳过）。 */
function notifyDesktop(title: string, body: string) {
  if (typeof window === "undefined") return;
  if (!notificationsEnabled()) return;
  const api = (window as any).electronAPI;
  if (api?.notify) {
    api.notify({ title, body }).catch(() => {});
    return;
  }
  try {
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      new Notification(title, { body });
    }
  } catch {
    /* 浏览器不支持时忽略 */
  }
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function DesktopWorkspacePage() {
  const router = useRouter();
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
  const [fileNotice, setFileNotice] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState(false);
  const [reviewComment, setReviewComment] = useState("");
  const [lineStart, setLineStart] = useState("");
  const [lineEnd, setLineEnd] = useState("");
  const [highlightLine, setHighlightLine] = useState<number | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  // 最近打开 / 前进后退
  const [recentFiles, setRecentFiles] = useState<string[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const historyRef = useRef<{ list: string[]; index: number }>({ list: [], index: -1 });
  const goHistoryRef = useRef<(delta: number) => void>(() => {});
  // 证据缺口收件箱
  const [showGaps, setShowGaps] = useState(false);
  const [openIssues, setOpenIssues] = useState<Array<{
    id: string; title: string; status: string; severity?: string;
  }>>([]);
  // 桌面通知 / 拖拽导入
  const [notificationsOn, setNotificationsOn] = useState(true);
  const [dragActive, setDragActive] = useState(false);
  // 流水线预检
  const [preflight, setPreflight] = useState<{
    ready: boolean;
    checks: Array<{ key: string; label: string; status: string; detail: string; hint: string }>;
  } | null>(null);
  const [pendingRun, setPendingRun] = useState<string | null>(null);
  const loggedLogsRef = useRef<Set<string>>(new Set());
  // 桌面深链接（yuleosh://open?project=&file=&line=）与托盘工程切换
  const [deepLink, setDeepLink] = useState<{
    projectId: string; file: string | null; line: number | null;
  } | null>(null);
  const [searchResults, setSearchResults] = useState<Array<{
    path: string; line: number; text: string;
  }>>([]);
  const [reviews, setReviews] = useState<Array<{
    id: string; artifact: string; status: string; comment: string; author: string; created_at: string;
    line_start?: number | null; line_end?: number | null;
  }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "你好！我是 yuleOSH 助手。请输入需求（支持自然语言或 OpenSpec 格式），我会帮你导入并自动运行流水线。", timestamp: new Date().toISOString() },
  ]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [runDetailJob, setRunDetailJob] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runJobId, setRunJobId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [pollProgress, setPollProgress] = useState(0);
  const [pollStage, setPollStage] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const restoredRef = useRef<PersistedWorkspaceState>({});
  const [persistReady, setPersistReady] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);
  const [showTraceability, setShowTraceability] = useState(false);
  const [showBaselines, setShowBaselines] = useState(false);
  const [showChangeRequests, setShowChangeRequests] = useState(false);
  const [showCompliance, setShowCompliance] = useState(false);
  const [showQualityGates, setShowQualityGates] = useState(false);
  const [showIssues, setShowIssues] = useState(false);
  const [showQa, setShowQa] = useState(false);
  const [showPm, setShowPm] = useState(false);
  const [showReviews, setShowReviews] = useState(false);
  const [showPalette, setShowPalette] = useState(false);
  const [loading, setLoading] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // ── 工作现场恢复 / 持久化 ────────────────────────────────────────────
  // 首帧后再读取 localStorage，避免 Next.js 预渲染水合不一致。
  useEffect(() => {
    const saved = loadWorkspaceState();
    restoredRef.current = saved;
    if (saved.activeId) setActiveId(saved.activeId);
    if (saved.query) setQuery(saved.query);
    if (typeof saved.onlyWithFiles === "boolean") setOnlyWithFiles(saved.onlyWithFiles);
    if (saved.openSections) setOpenSections(saved.openSections);
    if (saved.reviewFilter) setReviewFilter(saved.reviewFilter);
    if (saved.recentFiles) setRecentFiles(saved.recentFiles);
    if (typeof saved.notificationsOn === "boolean") {
      setNotificationsOn(saved.notificationsOn);
      try {
        window.localStorage.setItem(
          NOTIFY_STATE_KEY,
          saved.notificationsOn ? "on" : "off",
        );
      } catch {
        /* 忽略存储异常 */
      }
    }
    setPersistReady(true);
  }, []);

  useEffect(() => {
    if (!persistReady) return;
    saveWorkspaceState({
      activeId,
      openSections,
      selectedFile,
      query,
      onlyWithFiles,
      reviewFilter,
      recentFiles,
      notificationsOn,
    });
  }, [
    persistReady,
    activeId,
    openSections,
    selectedFile,
    query,
    onlyWithFiles,
    reviewFilter,
    recentFiles,
    notificationsOn,
  ]);

  // ── Python 后端健康状态（Electron） ─────────────────────────────────
  useEffect(() => {
    const api = (window as Window & {
      electronAPI?: {
        getBackendStatus?: () => Promise<{ running?: boolean }>;
        onBackendReady?: (cb: () => void) => () => void;
        onBackendError?: (cb: (msg?: string) => void) => () => void;
      };
    }).electronAPI;
    if (!api?.getBackendStatus) return;
    let alive = true;
    api.getBackendStatus()
      .then((s) => { if (alive) setBackendUp(Boolean(s?.running)); })
      .catch(() => {});
    const offReady = api.onBackendReady?.(() => setBackendUp(true));
    const offError = api.onBackendError?.(() => setBackendUp(false));
    return () => {
      alive = false;
      offReady?.();
      offError?.();
    };
  }, []);

  // ── 左下角用户区（参考 Trae 桌面版） ─────────────────────────────────
  // 桌面端多数场景是本地离线工作区，不强制登录；这里用裸 fetch 探测会话，
  // 避免 lib/api.ts 对 401 的「跳转登录页」副作用把工作台顶掉。
  const [session, setSession] = useState<{
    email: string;
    org_name?: string | null;
    user_id?: number | string;
  } | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [llmSettingsOpen, setLlmSettingsOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [appVersion, setAppVersion] = useState("");
  const userDockRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/auth/session", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => {
        if (alive && s?.email) {
          setSession({ email: s.email, org_name: s.org_name, user_id: s.user_id });
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const api = (window as Window & {
      electronAPI?: { getVersion?: () => Promise<string> };
    }).electronAPI;
    if (api?.getVersion) {
      api.getVersion().then((v) => setAppVersion(v)).catch(() => {});
    }
  }, []);

  // outside-click / Esc 关闭用户菜单
  useEffect(() => {
    if (!userMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!userDockRef.current?.contains(e.target as Node)) setUserMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setUserMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [userMenuOpen]);

  const userName = session?.email ? session.email.split("@")[0] : "本地用户";
  const userSub = session?.org_name || (session ? "已登录" : "离线工作区");

  // ── Load projects ──────────────────────────────────────────────────────
  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<{ projects: ProjectMeta[] }>("/api/v1/desktop/projects");
      const list = data.projects || [];
      setProjects(list);
      // 上次选中的工程可能已被删除：此时回落到第一个工程。
      setActiveId((prev) => (
        prev && list.some((p) => p.id === prev) ? prev : (list[0]?.id ?? null)
      ));
    } catch (e) {
      console.error("Failed to load projects", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // ── Cloud sync status ──────────────────────────────────────────────────
  const loadSyncStatus = useCallback(async (id: string) => {
    try {
      const s = await apiFetch<SyncStatus>(`/api/v1/desktop/projects/${id}/sync`);
      setSyncStatus(s);
    } catch {
      setSyncStatus(null);
    }
  }, []);

  useEffect(() => {
    if (!activeId) {
      setSyncStatus(null);
      return;
    }
    loadSyncStatus(activeId);
  }, [activeId, loadSyncStatus]);

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
    // 切换工程时重置当前工程的文件前进/后退栈
    historyRef.current = { list: [], index: -1 };
    setHistory([]);
    setHistoryIndex(-1);
    (async () => {
      try {
        const proj = await apiFetch<{ project: ProjectMeta }>(`/api/v1/desktop/projects/${activeId}`);
        if (cancelled) return;
        setActiveProject(proj.project);

        const t = await apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`);
        if (cancelled) return;
        setTree(t.tree);

        // 需求只有一份数据源：requirements/requirements.md。
        // 若上次退出时选中的文件仍存在，优先恢复到该文件；否则回落到需求文档。
        setSelectedFile(null);
        setFileContent("");
        setFileNotice(null);
        setHighlightLine(null);
        setLineStart("");
        setLineEnd("");
        const preferred = restoredRef.current.activeId === activeId
          ? restoredRef.current.selectedFile
          : null;
        const preferredPath = preferred ? findArtifactPath(t.tree, preferred) : null;
        const targetPath = preferredPath || findArtifactPath(t.tree, "requirements/requirements.md");
        if (targetPath) {
          try {
            const f = await apiFetch<{ content: string; message?: string }>(
              `/api/v1/desktop/projects/${activeId}/artifacts/${encodeURIComponent(targetPath).replace(/%2F/g, "/")}`,
            );
            if (cancelled) return;
            setSelectedFile(targetPath);
            // 初始文件也进入历史栈，保证「后退」在打开工程后立即可用。
            historyRef.current = { list: [targetPath], index: 0 };
            setHistory([targetPath]);
            setHistoryIndex(0);
            setRecentFiles((prev) =>
              [targetPath, ...prev.filter((p) => p !== targetPath)].slice(0, 8),
            );
            setFileContent(f.content || "");
            setFileNotice(f.message ?? null);
            setOpenSections((s) => ({ ...s, [sectionOf(targetPath)]: true }));
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

  // ── Create project (from the wizard) ───────────────────────────────────
  const handleProjectCreated = (project: ProjectLite, template: TemplateApplyResult | null) => {
    setProjects((p) => [project as ProjectMeta, ...p]);
    setActiveProject(project as ProjectMeta);
    setActiveId(project.id);
    setShowNewProject(false);
    let extra = "";
    if (template) {
      const docs = template.created_docs.length;
      if (docs) extra += ` 已按模板生成 ${docs} 份文档。`;
      if (template.requirements_saved) extra += " 已预置需求模板。";
    }
    setChatMessages((m) => [...m, {
      role: "assistant",
      content: `已创建工程「${project.name}」。${extra}现在可以输入需求了。`,
      timestamp: new Date().toISOString(),
    }]);
    loadSyncStatus(project.id);
  };

  // ── Rename / re-describe project ───────────────────────────────────────
  const handleProjectUpdated = (updated: ProjectRef) => {
    setProjects((list) => list.map((p) => (p.id === updated.id
      ? { ...p, name: updated.name, description: updated.description ?? p.description }
      : p)));
    setActiveProject((p) => (p && p.id === updated.id
      ? { ...p, name: updated.name, description: updated.description ?? p.description }
      : p));
  };

  // ── Delete project ─────────────────────────────────────────────────────
  const handleProjectDeleted = (id: string) => {
    const next = projects.filter((p) => p.id !== id);
    setProjects(next);
    if (id !== activeId) return;

    const fallback = next[0]?.id ?? null;
    setActiveId(fallback);
    if (!fallback) {
      setActiveProject(null);
      setTree(null);
      setSelectedFile(null);
      setFileContent("");
      setRuns([]);
    }
  };

  // ── Governance menu routing ────────────────────────────────────────────
  const handleGovernanceSelect = useCallback((key: GovernanceKey) => {
    const open: Record<GovernanceKey, () => void> = {
      traceability: () => setShowTraceability(true),
      baselines: () => setShowBaselines(true),
      "change-requests": () => setShowChangeRequests(true),
      "quality-gates": () => setShowQualityGates(true),
      compliance: () => setShowCompliance(true),
      reviews: () => setShowReviews(true),
      issues: () => setShowIssues(true),
      qa: () => setShowQa(true),
      "project-mgmt": () => setShowPm(true),
    };
    open[key]?.();
  }, []);

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
      pushAssistant("文件导入仅在桌面端可用。");
      return;
    }
    const path = await (window as any).electronAPI.openFile({ title: "导入需求文档" });
    if (!path) return;
    const res = await (window as any).electronAPI.readFile(path);
    if (!res.ok) {
      pushAssistant(`读取失败: ${res.error}`);
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
    const start = parseInt(lineStart, 10);
    const end = parseInt(lineEnd, 10);
    const hasRange = Number.isFinite(start) && start > 0;
    try {
      await apiFetch<{ review: typeof reviews[number] }>(
        `/api/v1/desktop/projects/${activeId}/review`,
        {
          method: "POST",
          body: JSON.stringify({
            artifact: selectedFile,
            status,
            comment: reviewComment.trim() || undefined,
            line_start: hasRange ? start : undefined,
            line_end: hasRange
              ? (Number.isFinite(end) && end >= start ? end : start)
              : undefined,
          }),
        },
      );
      setReviewComment("");
      setLineStart("");
      setLineEnd("");
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

  // 产物树评审标记：每个文件取最新一条评审结果，映射成状态色。
  const reviewTones = useMemo(() => reviewToneByArtifact(reviews), [reviews]);
  const reviewCounts = useMemo(() => countReviewTones(reviewTones), [reviewTones]);
  const reviewedTotal = REVIEW_TONES.reduce((n, t) => n + reviewCounts[t], 0);
  const latestReviews = useMemo(() => latestReviewByArtifact(reviews), [reviews]);
  // 文件在评审后被修改 → 评审结论过期；筛选「待修订」时也会带上这些文件。
  const stalePaths = useMemo(
    () => staleArtifactsByTree(tree, latestReviews),
    [tree, latestReviews],
  );

  // 窗口重新获得焦点 / 切回标签页时自动刷新产物树与评审，避免外部改动不可见。
  useEffect(() => {
    if (!activeId) return;
    let last = 0;
    const refresh = () => {
      const now = Date.now();
      if (now - last < 1500) return;
      last = now;
      apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`)
        .then((t) => setTree(t.tree))
        .catch(() => {});
      loadReviews();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [activeId, loadReviews]);

  // 全文搜索：防抖 300ms，只在查询词 ≥ 2 字符时请求后端扫描产物。
  useEffect(() => {
    const q = query.trim();
    if (!activeId || q.length < 2) {
      setSearchResults([]);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      apiFetch<{ matches: Array<{ path: string; line: number; text: string }> }>(
        `/api/v1/desktop/projects/${activeId}/artifacts/search?q=${encodeURIComponent(q)}`,
      )
        .then((r) => { if (alive) setSearchResults(r.matches || []); })
        .catch(() => { if (alive) setSearchResults([]); });
    }, 300);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [activeId, query]);

  // ── Run pipeline ───────────────────────────────────────────────────────
  // 先跑环境预检：阻塞项（磁盘/权限/Python）直接拦下并展示修复建议；
  // 降级项（cppcheck/模型 Key）只提示，不阻断运行。
  const handleRunPipeline = async (resumeFrom?: string) => {
    if (!activeId || running) return;
    try {
      const pf = await apiFetch<{
        ready: boolean;
        checks: Array<{ key: string; label: string; status: string; detail: string; hint: string }>;
      }>(`/api/v1/desktop/projects/${activeId}/pipeline/preflight`);
      const checks = pf.checks || [];
      const blocking = checks.filter((c) => c.status === "fail");
      if (blocking.length > 0) {
        setPreflight({ ready: false, checks });
        setPendingRun(resumeFrom ?? null);
        pushAssistant(
          `⛔ 运行前检查未通过：${blocking.map((c) => `${c.label}（${c.detail}）`).join("、")}。\n`
          + blocking.filter((c) => c.hint).map((c) => `· ${c.hint}`).join("\n"),
        );
        return;
      }
      const warns = checks.filter((c) => c.status === "warn");
      if (warns.length > 0) {
        pushAssistant(
          `⚠️ 运行前提示：${warns.map((c) => `${c.label}（${c.detail}）`).join("、")}。流水线将降级继续。`,
        );
      }
    } catch {
      /* 预检失败不阻塞运行 */
    }
    await startPipeline(resumeFrom);
  };

  const startPipeline = async (resumeFrom?: string) => {
    if (!activeId || running) return;
    setRunning(true);
    setCancelling(false);
    setPollProgress(0);
    setPollStage(null);
    loggedLogsRef.current = new Set();
    const resumed = Boolean(resumeFrom);
    setChatMessages((m) => [...m, {
      role: "assistant",
      content: resumed
        ? `🔁 从失败阶段「${resumeFrom}」重试流水线...`
        : "🚀 开始运行流水线，产出物将写入工程的 design/、code/、tests/、evidence/ 文件夹...",
      timestamp: new Date().toISOString(),
    }]);
    try {
      const res = await apiFetch<{ job_id: string; status: string; poll_url: string }>(
        `/api/v1/desktop/projects/${activeId}/pipeline/run`,
        { method: "POST", body: JSON.stringify({ type: "full", resume_from: resumeFrom }) },
      );
      setRunJobId(res.job_id);

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

          // 增量日志：只追加本次运行中尚未展示过的行（最多 3 条/轮询），
          // 比随机抽样更及时，也不会重复刷屏。
          if (s.logs && s.logs.length > 0) {
            const seen = loggedLogsRef.current;
            const fresh = s.logs.filter((line) => line && !seen.has(line)).slice(-3);
            if (fresh.length > 0) {
              fresh.forEach((line) => seen.add(line));
              setChatMessages((m) => [
                ...m,
                ...fresh.map((line) => ({
                  role: "assistant" as const,
                  content: `📋 ${line}`,
                  timestamp: new Date().toISOString(),
                })),
              ]);
            }
          }

          if (s.status === "passed" || s.status === "failed" || s.status === "cancelled") {
            window.clearInterval(pollTimer);
            setRunning(false);
            setCancelling(false);
            setRunJobId(null);
            setPollProgress(0);
            setPollStage(null);
            // 刷新 runs 列表、产物树和评审标记
            await Promise.all([
              apiFetch<{ tree: TreeNode }>(`/api/v1/desktop/projects/${activeId}/artifacts`)
                .then((t) => setTree(t.tree)).catch(() => {}),
              apiFetch<{ runs: PipelineRun[] }>(`/api/v1/desktop/projects/${activeId}/pipeline/runs`)
                .then((r) => setRuns(r.runs || [])).catch(() => {}),
            ]);
            loadReviews();
            if (s.status === "passed") {
              const content = `✅ 流水线完成 (${res.job_id})。产出物已保存到工程文件夹，可在左侧文件树查看。`;
              setChatMessages((m) => [...m, {
                role: "assistant", content, timestamp: new Date().toISOString(),
              }]);
              notifyDesktop("yuleOSH 流水线完成", `工程 ${activeProject?.name || activeId} 已全部通过`);
            } else if (s.status === "cancelled") {
              setChatMessages((m) => [...m, {
                role: "assistant",
                content: `⏹ 流水线已取消 (${res.job_id})。已完成的阶段产物保留在工程目录。`,
                timestamp: new Date().toISOString(),
              }]);
              notifyDesktop("yuleOSH 流水线已取消", `工程 ${activeProject?.name || activeId}`);
            } else {
              const err = s.result?.error || s.result?.summary || "未知错误";
              const failedStage = s.stages?.find((st) => st.status === "failed")?.key;
              setChatMessages((m) => [...m, {
                role: "assistant",
                content: `❌ 流水线失败 (${res.job_id})：${err}`
                  + (failedStage ? `\n可在运行详情里从阶段「${failedStage}」重试。` : ""),
                timestamp: new Date().toISOString(),
              }]);
              notifyDesktop("yuleOSH 流水线失败", `工程 ${activeProject?.name || activeId}：${err}`);
            }
          }
        } catch { /* 轮询中途报错忽略，下一轮继续 */ }
      }, 1000);

      // Safety timeout: stop polling after 5 min.
      window.setTimeout(() => {
        window.clearInterval(pollTimer);
        setRunning(false);
        setCancelling(false);
        setRunJobId(null);
        setPollProgress(0);
        setPollStage(null);
      }, 300000);
    } catch (e) {
      setRunning(false);
      setCancelling(false);
      setRunJobId(null);
      setPollProgress(0);
      setPollStage(null);
      setChatMessages((m) => [...m, {
        role: "assistant",
        content: `流水线启动失败: ${(e as Error).message}`,
        timestamp: new Date().toISOString(),
      }]);
    }
  };

  // ── Cancel running pipeline ────────────────────────────────────────────
  const handleCancelPipeline = async () => {
    if (!activeId || !runJobId || cancelling) return;
    setCancelling(true);
    try {
      await apiFetch(`/api/v1/desktop/projects/${activeId}/pipeline/cancel`, {
        method: "POST",
        body: JSON.stringify({ job_id: runJobId }),
      });
      pushAssistant("⏹ 已请求取消流水线，将在当前阶段结束后停止。");
    } catch (e) {
      setCancelling(false);
      pushAssistant(`取消失败: ${(e as Error).message}`);
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
      await loadSyncStatus(activeId);
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

  // ── Command palette (Ctrl/Cmd+K) ───────────────────────────────────────
  const handlePaletteAction = useCallback((action: CommandActionKey) => {
    if (action === "new-project") setShowNewProject(true);
    if (action === "run-pipeline") void handleRunPipeline();
    if (action === "cancel-run") void handleCancelPipeline();
    if (action === "sync") handleSync();
    if (action === "open-gaps") setShowGaps(true);
    if (action === "copy-path") void copySelectedPath();
    if (action === "toggle-notifications") {
      setNotificationsOn((v) => {
        const next = !v;
        try {
          window.localStorage.setItem(NOTIFY_STATE_KEY, next ? "on" : "off");
        } catch { /* 忽略存储异常 */ }
        return next;
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleRunPipeline, handleSync]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setShowPalette((v) => !v);
        return;
      }
      // Alt+←/→ 在最近打开的文件之间前进/后退
      if (e.altKey && !e.ctrlKey && !e.metaKey
        && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        e.preventDefault();
        goHistoryRef.current(e.key === "ArrowLeft" ? -1 : 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ── Read artifact file ─────────────────────────────────────────────────
  const handleSelectFile = async (
    relPath: string,
    opts?: { pushHistory?: boolean },
  ) => {
    if (!activeId) return;
    const currentEntry = historyRef.current.list[historyRef.current.index];
    if (opts?.pushHistory !== false && currentEntry !== relPath) {
      const cur = historyRef.current;
      const next = [...cur.list.slice(0, cur.index + 1), relPath].slice(-50);
      historyRef.current = { list: next, index: next.length - 1 };
      setHistory(next);
      setHistoryIndex(next.length - 1);
      setRecentFiles((prev) => [relPath, ...prev.filter((p) => p !== relPath)].slice(0, 8));
    }
    setSelectedFile(relPath);
    setHighlightLine(null);
    setLineStart("");
    setLineEnd("");
    // 展开该文件所属分区（若未展开）
    const section = sectionOf(relPath);
    if (section && !openSections[section]) {
      setOpenSections((s) => ({ ...s, [section]: true }));
    }
    try {
      const res = await apiFetch<{
        content: string | null; binary: boolean; message?: string; truncated?: boolean;
      }>(
        `/api/v1/desktop/projects/${activeId}/artifacts/${encodeURIComponent(relPath).replace(/%2F/g, "/")}`,
      );
      setFileContent(res.binary ? res.message || "(二进制文件)" : res.content || "");
      setFileNotice(res.truncated ? (res.message || "文件过大，仅显示部分内容") : null);
    } catch (e) {
      setFileContent(`读取失败: ${(e as Error).message}`);
      setFileNotice(null);
    }
  };

  const copySelectedPath = async () => {
    if (!selectedFile) return;
    try {
      await navigator.clipboard.writeText(selectedFile);
      setCopiedPath(true);
      window.setTimeout(() => setCopiedPath(false), 1500);
    } catch {
      pushAssistant("复制路径失败：当前环境不允许访问剪贴板。");
    }
  };

  const revealSelectedFile = async () => {
    if (!activeId || !selectedFile) return;
    const api = (window as any).electronAPI;
    if (!api?.revealArtifact) {
      pushAssistant("「在文件管理器中显示」仅在桌面端可用。");
      return;
    }
    const res = await api.revealArtifact(activeId, selectedFile);
    if (!res?.ok) {
      pushAssistant(`无法在文件管理器中显示: ${res?.error || "未知错误"}`);
    }
  };

  const artifactFiles = useMemo(() => flattenFiles(tree), [tree]);

  // 预览行高亮：优先使用评审行范围，其次是全文搜索命中行。
  const reviewLineRange = (() => {
    const start = parseInt(lineStart, 10);
    const end = parseInt(lineEnd || lineStart, 10);
    if (!Number.isFinite(start) || start <= 0) return null;
    return { start, end: Number.isFinite(end) && end >= start ? end : start };
  })();
  const previewLineRange = reviewLineRange
    ?? (highlightLine ? { start: highlightLine, end: highlightLine } : null);

  // 最近打开 / 前进后退
  const goHistory = (delta: number) => {
    const cur = historyRef.current;
    const next = cur.index + delta;
    if (next < 0 || next >= cur.list.length) return;
    historyRef.current = { ...cur, index: next };
    setHistoryIndex(next);
    void handleSelectFile(cur.list[next], { pushHistory: false });
  };
  goHistoryRef.current = goHistory;

  // 证据缺口：未评审 + 过期评审 + 未闭环问题
  const gapFiles = useMemo(() => {
    const reviewed = new Set(latestReviews.keys());
    return {
      unreviewed: artifactFiles.filter((p) => !reviewed.has(p)),
      stale: Array.from(stalePaths),
    };
  }, [artifactFiles, latestReviews, stalePaths]);
  const gapCount = gapFiles.unreviewed.length + gapFiles.stale.length + openIssues.length;

  // 未闭环问题（closed/rejected 之外都算未闭环）
  useEffect(() => {
    if (!activeId) { setOpenIssues([]); return; }
    let alive = true;
    apiFetch<{ issues: Array<{ id: string; title: string; status: string; severity?: string }> }>(
      `/api/v1/desktop/projects/${activeId}/issues`,
    )
      .then((r) => {
        if (!alive) return;
        setOpenIssues((r.issues || []).filter((i) => !["closed", "rejected"].includes(i.status)));
      })
      .catch(() => { if (alive) setOpenIssues([]); });
    return () => { alive = false; };
  }, [activeId, showGaps, showIssues]);

  // 托盘：最近工程 + 运行状态
  useEffect(() => {
    const api = (window as any).electronAPI;
    if (!api?.updateTray) return;
    api.updateTray({
      recentProjects: projects.map((p) => ({ id: p.id, name: p.name })),
      pipeline: { running, progress: pollProgress, stage: pollStage },
    }).catch(() => {});
  }, [projects, running, pollProgress, pollStage]);

  // 托盘「最近工程」点击 + 深链接入口
  useEffect(() => {
    const api = (window as any).electronAPI;
    if (!api) return;
    const offOpen = api.onOpenProject?.((pid: string) => setActiveId(pid));
    const offLink = api.onDeepLink?.((url: string) => {
      try {
        const u = new URL(url);
        const pid = u.searchParams.get("project") || "";
        const line = parseInt(u.searchParams.get("line") || "", 10);
        if (pid) setActiveId(pid);
        setDeepLink({
          projectId: pid,
          file: u.searchParams.get("file"),
          line: Number.isFinite(line) && line > 0 ? line : null,
        });
      } catch { /* 非法深链接忽略 */ }
    });
    return () => { offOpen?.(); offLink?.(); };
  }, []);

  // 产物树加载后消费深链接：打开目标文件并定位到行
  useEffect(() => {
    if (!deepLink || !tree || !activeId) return;
    if (deepLink.projectId && deepLink.projectId !== activeId) return;
    const target = deepLink.file ? findArtifactPath(tree, deepLink.file) : null;
    if (target) {
      void handleSelectFile(target).then(() => {
        if (deepLink.line) setHighlightLine(deepLink.line);
      });
    }
    setDeepLink(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLink, tree, activeId]);

  // 评审快捷键：Alt+A 通过 / Alt+R 退回（输入框内不生效）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = !!target && (
        target.tagName === "INPUT"
        || target.tagName === "TEXTAREA"
        || target.isContentEditable
      );
      if (!typing && e.altKey && !e.ctrlKey && !e.metaKey) {
        const k = e.key.toLowerCase();
        if (k === "a") { e.preventDefault(); void submitReview("approved"); }
        if (k === "r") { e.preventDefault(); void submitReview("needs_revision"); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFile, activeId, reviewComment, lineStart, lineEnd]);

  // 拖拽导入：把 Markdown/文本内容载入输入框，确认后发送即可导入需求
  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    const dropped = e.dataTransfer.files?.[0];
    if (!dropped || !activeId) return;
    const isText = /\.(md|markdown|txt)$/i.test(dropped.name)
      || dropped.type.startsWith("text/");
    if (!isText) {
      pushAssistant(`暂不支持拖入 ${dropped.name}：请拖入 Markdown 或文本文件。`);
      return;
    }
    if (dropped.size > 1024 * 1024) {
      pushAssistant(`文件 ${dropped.name} 超过 1 MB，请先精简后再导入。`);
      return;
    }
    try {
      const text = await dropped.text();
      setChatInput(text);
      pushAssistant(`已载入 ${dropped.name}（${text.length} 字符），确认后点击发送即可导入需求。`);
    } catch {
      pushAssistant("读取拖入的文件失败。");
    }
  };

  return (
    <div
      className="relative flex flex-col h-screen bg-[#0a0e17] text-[#e2e8f0] overflow-hidden"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setDragActive(true);
        }
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragActive(false);
      }}
      onDrop={handleDrop}
    >
      {dragActive && (
        <div
          data-testid="drop-overlay"
          className="absolute inset-0 z-50 flex items-center justify-center bg-[#0a0e17]/85 border-2 border-dashed border-[#38bdf8] pointer-events-none"
        >
          <div className="text-center">
            <Inbox className="w-10 h-10 mx-auto text-[#38bdf8]" />
            <p className="mt-3 text-sm text-[#e2e8f0]">松开以导入需求文档</p>
            <p className="mt-1 text-xs text-[#64748b]">支持 .md / .txt，≤ 1 MB</p>
          </div>
        </div>
      )}
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
          <ProjectActionsMenu
            project={activeProject}
            syncing={syncing}
            onSync={handleSync}
            onUpdated={handleProjectUpdated}
            onDeleted={handleProjectDeleted}
          />
        </div>
        <div className="flex items-center gap-2">
          {backendUp === false && (
            <span
              data-testid="backend-offline"
              title="Python 后端未就绪，请点击「重试启动」或稍候"
              className="flex items-center gap-1 rounded-full border border-[#ef4444]/40 bg-[#ef4444]/10 px-2 py-0.5 text-[11px] text-[#f87171]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#ef4444]" />
              后端离线
            </span>
          )}
          <SyncStatusChip status={syncStatus} onSync={handleSync} disabled={!activeId || syncing} />
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
          <button
            type="button"
            onClick={() => setShowPalette(true)}
            data-testid="palette-trigger"
            aria-label="命令面板"
            title="命令面板 (Ctrl+K)"
            className="rounded-md border border-[#1e293b] p-1.5 text-[#94a3b8] transition-colors hover:text-white"
          >
            <Search className="h-4 w-4" />
          </button>
          <GovernanceMenu disabled={!activeId} onSelect={handleGovernanceSelect} />
          <Button size="sm" onClick={() => handleRunPipeline()} disabled={!activeId || running}
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
              <button
                type="button"
                data-testid="cancel-run"
                onClick={() => void handleCancelPipeline()}
                disabled={cancelling || !runJobId}
                title="取消运行（在当前阶段结束后停止）"
                className="rounded border border-[#7f1d1d] px-1.5 py-0.5 text-[11px] text-[#f87171] transition-colors hover:bg-[#7f1d1d]/30 disabled:opacity-50"
              >
                {cancelling ? "取消中…" : "取消"}
              </button>
            </div>
          )}
        </div>
      </header>

      {/* 运行前环境预检：阻塞项可见并可修复后重跑 */}
      {preflight && (
        <div
          data-testid="pipeline-preflight"
          className="shrink-0 border-b border-[#7f1d1d] bg-[#1f1214] px-4 py-2"
        >
          <div className="flex items-center gap-2 text-xs text-[#fca5a5]">
            <AlertTriangle className="h-3.5 w-3.5" />
            运行前检查未通过
            <button
              type="button"
              onClick={() => { setPreflight(null); setPendingRun(null); }}
              className="ml-auto rounded border border-[#334155] px-2 py-0.5 text-[11px] text-[#94a3b8] hover:text-white"
            >
              取消
            </button>
            <button
              type="button"
              data-testid="preflight-continue"
              onClick={() => {
                const resume = pendingRun;
                setPreflight(null);
                setPendingRun(null);
                void startPipeline(resume ?? undefined);
              }}
              className="rounded border border-[#7f1d1d] px-2 py-0.5 text-[11px] text-[#f87171] hover:bg-[#7f1d1d]/30"
            >
              仍然运行
            </button>
          </div>
          <ul className="mt-1 space-y-0.5 text-[11px]">
            {preflight.checks.map((c) => (
              <li
                key={c.key}
                className={
                  c.status === "fail"
                    ? "text-[#f87171]"
                    : c.status === "warn"
                      ? "text-[#fbbf24]"
                      : "text-[#64748b]"
                }
              >
                {c.label}：{c.detail}
                {c.hint ? ` — ${c.hint}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

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
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-[#64748b] shrink-0">评审</span>
              <select
                data-testid="review-filter"
                value={reviewFilter}
                onChange={(e) => setReviewFilter(e.target.value as ReviewFilter)}
                className="min-w-0 flex-1 rounded border border-[#1e293b] bg-[#111827] px-1.5 py-0.5 text-[11px] text-[#94a3b8] focus:border-[#1677ff] focus:outline-none"
              >
                <option value="all">全部状态</option>
                <option value="needs_revision">待修订 / 已过期</option>
                <option value="unreviewed">未评审</option>
                <option value="approved">已通过</option>
              </select>
            </div>
            {reviewedTotal > 0 && (
              <div
                data-testid="review-legend"
                className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-[#64748b]"
                title={`${reviewedTotal} 个产物已有评审结论`}
              >
                {REVIEW_TONES.filter((tone) => reviewCounts[tone] > 0).map((tone) => (
                  <span key={tone} className="flex items-center gap-1">
                    <span className={`h-1.5 w-1.5 rounded-full ${REVIEW_TONE_META[tone].dot}`} />
                    {REVIEW_TONE_META[tone].label}
                    <span className="tabular-nums text-[#475569]">{reviewCounts[tone]}</span>
                  </span>
                ))}
                {stalePaths.size > 0 && (
                  <span data-testid="stale-summary" className="flex items-center gap-1 text-[#f59e0b]">
                    <AlertTriangle className="h-3 w-3" />
                    过期 <span className="tabular-nums">{stalePaths.size}</span>
                  </span>
                )}
              </div>
            )}
            {/* 证据缺口收件箱：未评审 / 过期评审 / 未闭环问题 */}
            <div className="pt-0.5">
              <button
                type="button"
                data-testid="gap-inbox-toggle"
                onClick={() => setShowGaps((v) => !v)}
                className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-[11px] text-[#94a3b8] hover:bg-[#1e293b]"
                title="聚合未评审、过期评审与未闭环问题"
              >
                <Inbox className="h-3 w-3" />
                证据缺口
                <span
                  className={`ml-auto rounded-full px-1.5 text-[10px] tabular-nums ${
                    gapCount > 0 ? "bg-[#7c2d12] text-[#fdba74]" : "bg-[#1e293b] text-[#64748b]"
                  }`}
                >
                  {gapCount}
                </span>
              </button>
              {showGaps && (
                <div
                  data-testid="gap-inbox"
                  className="mt-1 max-h-56 overflow-y-auto rounded border border-[#1e293b] bg-[#111827] py-1"
                >
                  {gapCount === 0 && (
                    <div className="px-2 py-1.5 text-[10px] text-[#64748b]">暂无缺口，评审与问题均已闭环。</div>
                  )}
                  {gapFiles.unreviewed.length > 0 && (
                    <div className="px-2 py-1 text-[10px] text-[#64748b]">
                      未评审 <span className="tabular-nums">{gapFiles.unreviewed.length}</span>
                    </div>
                  )}
                  {gapFiles.unreviewed.slice(0, 8).map((p) => (
                    <button
                      key={`unrev-${p}`}
                      type="button"
                      data-testid={`gap-unreviewed-${p}`}
                      onClick={() => {
                        setShowGaps(false);
                        setReviewFilter("unreviewed");
                        void handleSelectFile(p);
                      }}
                      className="block w-full truncate px-2 py-0.5 text-left font-mono text-[10px] text-[#93c5fd] hover:bg-[#1e293b]/60"
                      title={p}
                    >
                      {p}
                    </button>
                  ))}
                  {gapFiles.stale.length > 0 && (
                    <div className="px-2 py-1 text-[10px] text-[#f59e0b]">
                      过期评审 <span className="tabular-nums">{gapFiles.stale.length}</span>
                    </div>
                  )}
                  {gapFiles.stale.slice(0, 8).map((p) => (
                    <button
                      key={`stale-${p}`}
                      type="button"
                      data-testid={`gap-stale-${p}`}
                      onClick={() => {
                        setShowGaps(false);
                        setReviewFilter("needs_revision");
                        void handleSelectFile(p);
                      }}
                      className="block w-full truncate px-2 py-0.5 text-left font-mono text-[10px] text-[#fbbf24] hover:bg-[#1e293b]/60"
                      title={p}
                    >
                      {p}
                    </button>
                  ))}
                  {openIssues.length > 0 && (
                    <div className="px-2 py-1 text-[10px] text-[#f87171]">
                      未闭环问题 <span className="tabular-nums">{openIssues.length}</span>
                    </div>
                  )}
                  {openIssues.slice(0, 6).map((issue) => (
                    <button
                      key={`issue-${issue.id}`}
                      type="button"
                      data-testid={`gap-issue-${issue.id}`}
                      onClick={() => { setShowGaps(false); setShowIssues(true); }}
                      className="block w-full truncate px-2 py-0.5 text-left text-[10px] text-[#fca5a5] hover:bg-[#1e293b]/60"
                      title={`${issue.title}（${issue.status}）`}
                    >
                      {issue.title}
                      <span className="ml-1 text-[#64748b]">{issue.status}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {searchResults.length > 0 && (
              <div
                data-testid="artifact-search-results"
                className="overflow-hidden rounded border border-[#1e293b] bg-[#111827]"
              >
                <div className="border-b border-[#1e293b] px-2 py-1 text-[10px] text-[#64748b]">
                  内容命中 {searchResults.length} 条 · 点击跳转
                </div>
                <div className="max-h-40 overflow-y-auto">
                  {searchResults.slice(0, 20).map((hit, i) => (
                    <button
                      key={`${hit.path}:${hit.line}:${i}`}
                      type="button"
                      onClick={async () => {
                        setQuery("");
                        await handleSelectFile(hit.path);
                        setHighlightLine(hit.line);
                      }}
                      className="block w-full px-2 py-1 text-left hover:bg-[#1e293b]/60"
                    >
                      <div className="truncate font-mono text-[10px] text-[#93c5fd]">
                        {hit.path}:{hit.line}
                      </div>
                      <div className="truncate text-[10px] text-[#64748b]">{hit.text}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 5 大固定分区 */}
          <div className="flex-1 overflow-y-auto px-1 pb-2">
            {(() => {
              const sections = buildSections(tree).map((sec) => {
                const allFiles = flattenFiles(sec);
                const coverage = reviewCoverage(allFiles, reviewTones);
                const aggregate = aggregateReviewTone(allFiles.map((p) => reviewTones[p]));
                const filtered = filterTreeByPaths(
                  filterTree(sec, query),
                  (path) => matchesReviewFilter(path, reviewTones, reviewFilter, stalePaths),
                );
                return { sec, filtered, count: countFiles(filtered), coverage, aggregate };
              }).filter(({ count }) => (reviewFilter !== "all" ? count > 0 : (!onlyWithFiles || count > 0)));
              if (sections.length === 0) {
                return (
                  <div className="px-2 py-4 text-xs text-[#475569] text-center">
                    {reviewFilter !== "all" ? "没有符合评审筛选的产物" : "暂无产物"}
                  </div>
                );
              }

              return sections.map(({ sec, filtered, count, coverage, aggregate }) => {
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
                      {aggregate && (
                        <span
                          data-testid={`section-review-dot-${sec.name}`}
                          title={`分区评审：${REVIEW_TONE_META[aggregate].label}`}
                          className={`h-1.5 w-1.5 shrink-0 rounded-full ${REVIEW_TONE_META[aggregate].dot}`}
                        />
                      )}
                      {coverage.reviewed > 0 && (
                        <span
                          data-testid={`section-review-coverage-${sec.name}`}
                          className="shrink-0 text-[10px] tabular-nums text-[#64748b]"
                          title={`已评审 ${coverage.reviewed} / ${coverage.total} 个产物`}
                        >
                          {coverage.reviewed}/{coverage.total}
                        </span>
                      )}
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
                        reviewTones={reviewTones}
                        stalePaths={stalePaths}
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
              <ul className="max-h-44 space-y-0.5 overflow-y-auto">
                {runs.map((r) => (
                  <li key={r.job_id}>
                    <button
                      type="button"
                      onClick={() => setRunDetailJob(r.job_id)}
                      title={`查看运行详情 ${r.job_id}`}
                      className="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-xs text-[#94a3b8] transition-colors hover:bg-[#1e293b]/60 hover:text-white"
                    >
                      {r.status === "passed" ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#10b981] shrink-0" />
                      ) : r.status === "failed" ? (
                        <XCircle className="w-3.5 h-3.5 text-[#ef4444] shrink-0" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-[#f59e0b] shrink-0" />
                      )}
                      <span className="truncate">{r.job_id.slice(0, 10)}</span>
                      <span className="ml-auto text-[#475569]">{timeAgo(r.completed_at || r.started_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 用户信息 + 设置（参考 Trae 桌面版左下角） */}
          <div ref={userDockRef} className="relative px-2 py-2 border-t border-[#1e293b] shrink-0">
            {userMenuOpen && (
              <div
                role="menu"
                aria-label="用户菜单"
                className="absolute bottom-full left-2 right-2 mb-1 z-30 rounded-lg border border-[#1e293b] bg-[#111827] text-[#e2e8f0] shadow-xl ring-1 ring-black/40 p-1"
              >
                <div className="px-2 py-1.5 mb-1 border-b border-[#1e293b]">
                  <div className="text-xs text-[#e2e8f0] truncate">
                    {session?.email ?? "未登录"}
                  </div>
                  <div className="text-[10px] text-[#64748b] truncate">
                    {session?.org_name || (session ? "已登录账号" : "数据仅保存在本机")}
                  </div>
                </div>
                {session && (
                  <DockMenuItem
                    icon={<UserRound className="w-3.5 h-3.5" />}
                    label="个人信息"
                    onClick={() => {
                      setUserMenuOpen(false);
                      setAccountOpen(true);
                    }}
                  />
                )}
                <DockMenuItem
                  icon={<Settings className="w-3.5 h-3.5" />}
                  label="用户设置"
                  onClick={() => {
                    setUserMenuOpen(false);
                    setSettingsOpen(true);
                  }}
                />
                <DockMenuItem
                  icon={<Sparkles className="w-3.5 h-3.5" />}
                  label="模型设置"
                  onClick={() => {
                    setUserMenuOpen(false);
                    setLlmSettingsOpen(true);
                  }}
                />
                <DockMenuItem
                  icon={notificationsOn
                    ? <Bell className="w-3.5 h-3.5" />
                    : <BellOff className="w-3.5 h-3.5" />}
                  label={notificationsOn ? "桌面通知：开" : "桌面通知：关"}
                  onClick={() => {
                    setNotificationsOn((v) => {
                      const next = !v;
                      try {
                        window.localStorage.setItem(NOTIFY_STATE_KEY, next ? "on" : "off");
                      } catch { /* 忽略存储异常 */ }
                      return next;
                    });
                  }}
                />
                <div className="my-1 h-px bg-[#1e293b]" />
                {session ? (
                  <DockMenuItem
                    icon={<LogOut className="w-3.5 h-3.5" />}
                    label="退出登录"
                    tone="warning"
                    onClick={() => {
                      setUserMenuOpen(false);
                      setLogoutOpen(true);
                    }}
                  />
                ) : (
                  <DockMenuItem
                    icon={<LogIn className="w-3.5 h-3.5" />}
                    label="登录账号"
                    onClick={() => {
                      setUserMenuOpen(false);
                      router.push("/login");
                    }}
                  />
                )}
                {appVersion && (
                  <div className="px-2 pt-1 pb-0.5 text-[10px] text-[#475569]">
                    yuleOSH Desktop v{appVersion}
                  </div>
                )}
              </div>
            )}

            <div
              className={`flex items-center gap-1 rounded-lg px-2 py-1.5 transition-colors ${
                userMenuOpen ? "bg-[#1e293b]" : "hover:bg-[#1e293b]"
              }`}
            >
              <button
                type="button"
                aria-haspopup="menu"
                aria-expanded={userMenuOpen}
                onClick={() => setUserMenuOpen((v) => !v)}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#722ed1]/20 text-[11px] font-bold text-[#a78bfa]">
                  {(userName[0] ?? "Y").toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs text-[#e2e8f0]">{userName}</span>
                  <span className="block truncate text-[10px] text-[#64748b]">{userSub}</span>
                </span>
              </button>
              <button
                type="button"
                title="用户设置"
                aria-label="用户设置"
                onClick={() => {
                  setUserMenuOpen(false);
                  setSettingsOpen(true);
                }}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[#64748b] hover:text-white hover:bg-[#334155]"
              >
                <Settings className="w-3.5 h-3.5" />
              </button>
            </div>
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
              <CodeBlock
                content={fileContent}
                path={selectedFile}
                notice={fileNotice}
                lineRange={previewLineRange}
                onLineClick={(line) => {
                  setHighlightLine(null);
                  setLineStart(String(line));
                  setLineEnd(String(line));
                }}
                actions={(
                  <>
                    <button
                      type="button"
                      data-testid="file-history-back"
                      onClick={() => goHistory(-1)}
                      disabled={historyIndex <= 0}
                      title="上一个文件（Alt+←）"
                      className="inline-flex items-center rounded border border-[#1e293b] p-1 text-[10px] text-[#94a3b8] hover:text-white disabled:opacity-30"
                    >
                      <ArrowLeft className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      data-testid="file-history-forward"
                      onClick={() => goHistory(1)}
                      disabled={historyIndex < 0 || historyIndex >= history.length - 1}
                      title="下一个文件（Alt+→）"
                      className="inline-flex items-center rounded border border-[#1e293b] p-1 text-[10px] text-[#94a3b8] hover:text-white disabled:opacity-30"
                    >
                      <ArrowRight className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void copySelectedPath()}
                      title="复制相对路径"
                      className="inline-flex items-center gap-1 rounded border border-[#1e293b] px-1.5 py-0.5 text-[10px] text-[#94a3b8] hover:text-white"
                    >
                      <Copy className="h-3 w-3" /> {copiedPath ? "已复制" : "复制路径"}
                    </button>
                    {isDesktop && (
                      <button
                        type="button"
                        data-testid="reveal-in-folder"
                        onClick={() => void revealSelectedFile()}
                        title="在文件管理器中显示"
                        className="inline-flex items-center gap-1 rounded border border-[#1e293b] px-1.5 py-0.5 text-[10px] text-[#94a3b8] hover:text-white"
                      >
                        <FolderOpen className="h-3 w-3" /> 定位
                      </button>
                    )}
                  </>
                )}
              />
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
                {stalePaths.has(selectedFile) && (
                  <div
                    data-testid="stale-banner"
                    className="flex items-center gap-1.5 rounded border border-[#f59e0b]/40 bg-[#f59e0b]/10 px-2 py-1 text-[11px] text-[#fbbf24]"
                  >
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                    该文件在最近一次评审后被修改，评审结论可能已过期，请重新确认。
                  </div>
                )}
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
                          {r.line_start ? (
                            <span className="text-[#93c5fd]">
                              L{r.line_start}{r.line_end && r.line_end !== r.line_start ? `-${r.line_end}` : ""}
                            </span>
                          ) : null}
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

                <div className="flex items-center gap-2 text-[11px] text-[#64748b]">
                  <span className="shrink-0">行范围</span>
                  <Input
                    value={lineStart}
                    onChange={(e) => setLineStart(e.target.value.replace(/[^\d]/g, ""))}
                    placeholder="起始"
                    inputMode="numeric"
                    aria-label="评审起始行"
                    data-testid="review-line-start"
                    className="bg-[#111827] border-[#1e293b] text-xs h-7 w-16"
                  />
                  <span>–</span>
                  <Input
                    value={lineEnd}
                    onChange={(e) => setLineEnd(e.target.value.replace(/[^\d]/g, ""))}
                    placeholder="结束"
                    inputMode="numeric"
                    aria-label="评审结束行"
                    data-testid="review-line-end"
                    className="bg-[#111827] border-[#1e293b] text-xs h-7 w-16"
                  />
                  {(lineStart || lineEnd) && (
                    <button
                      type="button"
                      onClick={() => { setLineStart(""); setLineEnd(""); }}
                      className="rounded px-1.5 py-0.5 hover:bg-[#1e293b]"
                    >
                      清除
                    </button>
                  )}
                  <span className="ml-auto text-[10px] text-[#475569]">点击预览行号可快速定位</span>
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

      {/* ── New project wizard ─────────────────────────────────────────── */}
      <ProjectWizardDialog
        open={showNewProject}
        onOpenChange={setShowNewProject}
        onCreated={handleProjectCreated}
      />

      {/* ── ASPICE traceability matrix + audit chain ───────────────────── */}
      <TraceabilityDialog
        open={showTraceability}
        onOpenChange={setShowTraceability}
        projectId={activeId}
        onOpenArtifact={(path) => {
          setShowTraceability(false);
          void handleSelectFile(path);
        }}
      />

      {/* ── Configuration baselines ────────────────────────────────────── */}
      <BaselineDialog
        open={showBaselines}
        onOpenChange={setShowBaselines}
        projectId={activeId}
      />

      {/* ── Change requests + impact analysis ──────────────────────────── */}
      <ChangeRequestDialog
        open={showChangeRequests}
        onOpenChange={setShowChangeRequests}
        projectId={activeId}
      />

      {/* ── ASPICE compliance dashboard ────────────────────────────────── */}
      <ComplianceDialog
        open={showCompliance}
        onOpenChange={setShowCompliance}
        projectId={activeId}
      />

      {/* ── Quality gate board ─────────────────────────────────────────── */}
      <QualityGatesDialog
        open={showQualityGates}
        onOpenChange={setShowQualityGates}
        projectId={activeId}
      />

      {/* ── Issue tracker (SUP.9) ──────────────────────────────────────── */}
      <IssueTrackerDialog
        open={showIssues}
        onOpenChange={setShowIssues}
        projectId={activeId}
      />

      {/* ── QA audit (SUP.1) ───────────────────────────────────────────── */}
      <QaAuditDialog
        open={showQa}
        onOpenChange={setShowQa}
        projectId={activeId}
      />

      {/* ── Project management (MAN.3) ─────────────────────────────────── */}
      <ProjectMgmtDialog
        open={showPm}
        onOpenChange={setShowPm}
        projectId={activeId}
      />

      {/* ── Review center (SUP.4 cross-artifact reviews) ───────────────── */}
      <ReviewCenterDialog
        open={showReviews}
        onOpenChange={setShowReviews}
        projectId={activeId}
      />

      {/* ── 用户区 Dialog（与 dashboard 共用） ────────────────────────── */}
      {session && (
        <AccountInfoDialog
          open={accountOpen}
          onOpenChange={setAccountOpen}
          fallbackEmail={session.email}
          fallbackOrgName={session.org_name ?? undefined}
        />
      )}
      <UserSettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        userId={session?.user_id}
        onOpenLLM={() => {
          setSettingsOpen(false);
          setLlmSettingsOpen(true);
        }}
      />
      <DesktopLLMSettingsDialog
        open={llmSettingsOpen}
        onOpenChange={setLlmSettingsOpen}
      />
      <LogoutConfirmDialog
        open={logoutOpen}
        onOpenChange={setLogoutOpen}
        emailLabel={session?.email}
      />
      <PipelineRunDialog
        key={runDetailJob ?? "none"}
        open={!!runDetailJob}
        onOpenChange={(next) => !next && setRunDetailJob(null)}
        projectId={activeId}
        jobId={runDetailJob}
        running={running}
        onRerun={(fromStage) => {
          setRunDetailJob(null);
          handleRunPipeline(fromStage);
        }}
        onInspectLayer={(layerPath) => {
          const prefix = `code/${layerPath}/`;
          setQuery(prefix);
          setOpenSections((s) => ({ ...s, code: true }));
          const first = artifactFiles.find((path) => path.startsWith(prefix));
          if (first) void handleSelectFile(first);
        }}
      />

      {/* ── 命令面板（Ctrl/Cmd+K） ─────────────────────────────────────── */}
      <CommandPalette
        open={showPalette}
        onClose={() => setShowPalette(false)}
        projects={projects.map((p) => ({ id: p.id, name: p.name }))}
        activeId={activeId}
        files={artifactFiles}
        recentFiles={recentFiles}
        canCancel={running}
        hasSelection={Boolean(selectedFile)}
        notificationsOn={notificationsOn}
        onSelectProject={setActiveId}
        onOpenFile={(path) => { void handleSelectFile(path); }}
        onGovernance={handleGovernanceSelect}
        onAction={handlePaletteAction}
      />
    </div>
  );
}

// ─── 云端同步状态 chip ────────────────────────────────────────────────────

function SyncStatusChip({
  status,
  onSync,
  disabled,
}: {
  status: SyncStatus | null;
  onSync: () => void;
  disabled: boolean;
}) {
  if (!status) return null;

  if (!status.configured) {
    return (
      <span
        title="未配置云端地址（YULEOSH_CLOUD_URL），产物目前仅保存在本地"
        data-testid="sync-status"
        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-[#1e293b] text-[#64748b]"
      >
        <UploadCloud className="w-3 h-3" /> 云端未配置
      </span>
    );
  }

  if (status.pending) {
    const count = status.changed_files + status.removed_files;
    return (
      <button
        type="button"
        onClick={onSync}
        disabled={disabled}
        title="点击立即同步到云端"
        data-testid="sync-status"
        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#f59e0b] hover:bg-[#f59e0b]/20 disabled:opacity-60"
      >
        <Clock className="w-3 h-3" />
        {status.synced ? `待同步 ${count} 个文件` : "尚未同步"}
      </button>
    );
  }

  return (
    <span
      title={status.last_synced_at ?? ""}
      data-testid="sync-status"
      className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-[#10b981]/40 bg-[#10b981]/10 text-[#10b981]"
    >
      <CheckCircle2 className="w-3 h-3" /> 已同步 · {timeAgo(status.last_synced_at)}
    </span>
  );
}

// ─── 用户菜单项 ──────────────────────────────────────────────────────────

function DockMenuItem({
  icon,
  label,
  tone = "default",
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  tone?: "default" | "warning";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={`w-full flex items-center gap-2 text-xs rounded-md px-2 py-1.5 cursor-pointer bg-transparent text-left transition-colors ${
        tone === "warning"
          ? "text-[#f59e0b] hover:bg-[#f59e0b]/10"
          : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

// ─── Lightweight artifact tree (used under each section) ────────────────

function ArtifactTreeLite({
  nodes,
  depth = 0,
  onSelect,
  selectedFile,
  reviewTones,
  stalePaths,
}: {
  nodes: TreeNode[];
  depth?: number;
  onSelect: (path: string) => void;
  selectedFile: string | null;
  /** 产物路径 → 最新评审状态色，未评审的文件不显示圆点。 */
  reviewTones?: Record<string, ReviewTone>;
  /** 评审结论已过期的文件集合（文件在评审后被修改）。 */
  stalePaths?: Set<string>;
}) {
  // 目录默认不展开（分区已展开后，再逐层展开文件）
  const [openDirs, setOpenDirs] = useState<Record<string, boolean>>({});

  return (
    <div data-tree-root={depth === 0 ? "true" : undefined}>
      {nodes.map((node) => {
        const isDir = node.type === "dir";
        const isOpen = openDirs[node.path] ?? false;
        const hasChildren = isDir && (node.children?.length ?? 0) > 0;
        const tone = isDir ? null : reviewTones?.[node.path];
        const dirTone = isDir
          ? aggregateReviewTone(flattenFiles(node).map((p) => reviewTones?.[p]))
          : null;
        const stale = !isDir && Boolean(stalePaths?.has(node.path));
        return (
          <div key={node.path}>
            <div
              data-tree-row={node.path}
              role="treeitem"
              tabIndex={0}
              aria-expanded={isDir && hasChildren ? isOpen : undefined}
              aria-selected={!isDir ? selectedFile === node.path : undefined}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded cursor-pointer text-[11px] hover:bg-[#1e293b] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#1677ff] ${
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
              onKeyDown={(e) => {
                const row = e.currentTarget;
                const root = row.closest('[data-tree-root="true"]');
                const rows = root
                  ? Array.from(root.querySelectorAll<HTMLElement>('[data-tree-row]'))
                  : [];
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  const next = rows[rows.indexOf(row) + (e.key === "ArrowDown" ? 1 : -1)];
                  next?.focus();
                  return;
                }
                if (e.key === "ArrowRight" && isDir && hasChildren) {
                  e.preventDefault();
                  setOpenDirs((s) => ({ ...s, [node.path]: true }));
                  return;
                }
                if (e.key === "ArrowLeft" && isDir && hasChildren && isOpen) {
                  e.preventDefault();
                  setOpenDirs((s) => ({ ...s, [node.path]: false }));
                  return;
                }
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  if (isDir && hasChildren) {
                    setOpenDirs((s) => ({ ...s, [node.path]: !s[node.path] }));
                  } else if (!isDir) {
                    onSelect(node.path);
                  }
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
              <span className="min-w-0 flex-1 truncate">{node.name}</span>
              {dirTone && (
                <span
                  data-testid={`dir-review-dot-${node.path}`}
                  title={`目录评审：${REVIEW_TONE_META[dirTone].label}`}
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${REVIEW_TONE_META[dirTone].dot}`}
                />
              )}
              {stale && (
                <span
                  data-testid={`review-stale-${node.path}`}
                  title="评审后文件已修改，评审结论可能过期"
                  aria-label="评审结论已过期"
                  className="shrink-0"
                >
                  <AlertTriangle className="h-3 w-3 text-[#f59e0b]" />
                </span>
              )}
              {tone && (
                <span
                  data-testid={`review-dot-${node.path}`}
                  title={`评审状态：${REVIEW_TONE_META[tone].label}`}
                  aria-label={`评审状态：${REVIEW_TONE_META[tone].label}`}
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${REVIEW_TONE_META[tone].dot}`}
                />
              )}
            </div>
            {isDir && isOpen && hasChildren && (
              <ArtifactTreeLite
                nodes={node.children!}
                depth={depth + 1}
                onSelect={onSelect}
                selectedFile={selectedFile}
                reviewTones={reviewTones}
                stalePaths={stalePaths}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

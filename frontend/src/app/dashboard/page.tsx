"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Loader2,
  Download,
  RefreshCw,
  FileText,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  BarChart3,
  Target,
  LogOut,
  User as UserIcon,
  Settings,
  Layers,
  ArrowRight,
  FileDown,
  Info,
  Search,
  ExternalLink,
  BookOpen,
  TrendingUp,
  X,
  BookMarked,
  Hash,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  getToken,
  clearToken,
  getDashboardProjects,
  getSWEStatus,
  getGapAnalysis,
  generateEvidence,
  getEvidenceStatus,
  getCoverage,
  getKBArticles,
  getFMEAEntries,
  getMISRATrend,
  type DashboardProject,
  type SWEStatus,
  type SWEStatusResponse,
  type GapItem,
  type GapSummary,
  type GapAnalysisResponse,
  type EvidenceTask,
  type CoverageResponse,
  type KbArticle,
  type KbArticlesResponse,
  type FmeaEntry,
  type FmeaResponse,
  type MisraTrendPoint,
  type MisraDistribution,
  type MisraViolationItem,
  type MisraTrendResponse,
} from "@/lib/api";
import type { UserInfo } from "@/lib/api";

// ─── Simple Markdown renderer ───────────────────────────────────────────────

function simpleMarkdown(content: string): string {
  // Very basic markdown rendering for article content
  let html = content
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-[#1e293b] rounded-lg p-3 my-2 overflow-x-auto text-xs text-[#e2e8f0] font-mono"><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-[#1e293b] px-1.5 py-0.5 rounded text-xs text-[#10b981] font-mono">$1</code>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-bold text-[#e2e8f0] mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold text-[#e2e8f0] mt-5 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold text-[#e2e8f0] mt-5 mb-3">$1</h1>')
    // Bold/italic
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-bold text-[#e2e8f0]">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em class="italic text-[#94a3b8]">$1</em>')
    // Lists
    .replace(/^- (.+)$/gm, '<li class="text-xs text-[#94a3b8] ml-4 list-disc">$1</li>')
    // Paragraphs (double newlines)
    .replace(/\n\n/g, '</p><p class="text-xs text-[#94a3b8] leading-relaxed mb-1">')
    // Single newlines within paragraphs
    .replace(/\n/g, '<br/>');

  return '<p class="text-xs text-[#94a3b8] leading-relaxed mb-1">' + html + '</p>';
}

// ─── Types ───────────────────────────────────────────────────────────────────

type Tab = "overview" | "gap-analysis" | "knowledge-base" | "misra-trends";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getInitials(name: string): string {
  return name
    .split(/[\s@]+/)
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function formatDate(dateStr: string): string {
  if (!dateStr || dateStr === "-") return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function severityColor(sev: string): string {
  switch (sev) {
    case "critical":
      return "#ff4d4f";
    case "major":
      return "#faad14";
    case "minor":
      return "#10b981";
    default:
      return "#64748b";
  }
}

function severityLabel(sev: string): string {
  switch (sev) {
    case "critical":
      return "🔴 Critical";
    case "major":
      return "🟡 Major";
    case "minor":
      return "🟢 Minor";
    default:
      return sev;
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "completed":
      return "✅ 完成";
    case "partial":
      return "⚠️ 部分";
    case "not_started":
      return "❌ 未开始";
    default:
      return status;
  }
}

function statusColor(status: string): string {
  switch (status) {
    case "completed":
      return "#10b981";
    case "partial":
      return "#faad14";
    case "not_started":
      return "#ff4d4f";
    default:
      return "#64748b";
  }
}

function gapStatusLabel(s: string): string {
  switch (s) {
    case "open":
      return "待处理";
    case "in_progress":
      return "处理中";
    case "resolved":
      return "已解决";
    default:
      return s;
  }
}

function gapStatusColor(s: string): string {
  switch (s) {
    case "open":
      return "#ff4d4f";
    case "in_progress":
      return "#1677ff";
    case "resolved":
      return "#10b981";
    default:
      return "#64748b";
  }
}

// ─── Mini Coverage Bar ───────────────────────────────────────────────────────

function MiniCoverageBar({ label, pct, color }: { label: string; pct: number; color?: string }) {
  const barColor = color || (pct >= 80 ? "#10b981" : pct >= 50 ? "#faad14" : "#ff4d4f");
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-[#94a3b8] w-16 truncate shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-[#1e293b] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(pct, 100)}%`, background: barColor }}
        />
      </div>
      <span className="text-xs font-mono font-medium w-11 text-right" style={{ color: barColor }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  );
}

// ─── SWE Status Card ─────────────────────────────────────────────────────────

function SWECard({ swe }: { swe: SWEStatus }) {
  return (
    <Link href={swe.details_url} className="group block">
      <Card
        className="h-full border-[#1e293b] bg-[#111827] hover:border-[#722ed1]/30 transition-all cursor-pointer overflow-hidden"
      >
        {/* Color top strip */}
        <div className="h-1 w-full" style={{ background: swe.color }} />
        <CardHeader className="pb-2 pt-3">
          <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center justify-between">
            <span>{swe.short}</span>
            <Badge
              variant="outline"
              className="text-[10px] px-1.5 py-0 h-5"
              style={{
                background: `${swe.color}15`,
                color: swe.color,
                borderColor: `${swe.color}30`,
              }}
            >
              {statusLabel(swe.status)}
            </Badge>
          </CardTitle>
          <CardDescription className="text-xs text-[#94a3b8] line-clamp-2 mt-1">
            {swe.name}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0 pb-3">
          <p className="text-xs text-[#64748b] line-clamp-2 mb-2 min-h-[2em]">
            {swe.description}
          </p>
          <div className="flex items-center justify-between text-[10px] text-[#64748b]">
            <span>更新: {formatDate(swe.last_updated)}</span>
            <span className="text-[#722ed1] opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
              详情 <ArrowRight className="w-2.5 h-2.5" />
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

// ─── Evidence Pack Modal ─────────────────────────────────────────────────────

function EvidenceModal({
  open,
  task,
  onClose,
}: {
  open: boolean;
  task: EvidenceTask | null;
  onClose: () => void;
}) {
  if (!open) return null;

  const isRunning = task?.status === "running";
  const isCompleted = task?.status === "completed";
  const isFailed = task?.status === "failed";
  const progress = task?.progress_pct ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <Card className="w-full max-w-md border-[#1e293b] bg-[#111827] shadow-2xl">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-bold text-[#e2e8f0] flex items-center gap-2">
            {isRunning && <Loader2 className="w-4 h-4 animate-spin text-[#722ed1]" />}
            {isCompleted && <CheckCircle2 className="w-4 h-4 text-[#10b981]" />}
            {isFailed && <AlertCircle className="w-4 h-4 text-[#ff4d4f]" />}
            {isRunning && "正在生成证据包..."}
            {isCompleted && "证据包生成完成"}
            {isFailed && "证据包生成失败"}
          </CardTitle>
          {!isRunning && (
            <CardDescription className="text-xs text-[#94a3b8]">
              {isCompleted && task?.note ? task.note : ""}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="pb-4">
          {/* Progress bar */}
          <div className="mb-4">
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-[#64748b]">进度</span>
              <span className="text-[#94a3b8] font-mono">{progress}%</span>
            </div>
            <div className="h-2 rounded-full bg-[#1e293b] overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${progress}%`,
                  background: isFailed
                    ? "#ff4d4f"
                    : `linear-gradient(90deg, #722ed1, #1677ff)`,
                }}
              />
            </div>
          </div>

          {/* Status details */}
          {isRunning && (
            <div className="rounded-lg bg-[#722ed1]/5 border border-[#722ed1]/10 px-3 py-2 text-xs text-[#94a3b8]">
              正在收集合规证据、生成审计清单...
            </div>
          )}

          {isFailed && task?.error && (
            <div className="rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-3 py-2 text-xs text-[#ff4d4f] break-words">
              {task.error}
            </div>
          )}

          {isCompleted && task?.download_url && (
            <div className="rounded-lg bg-[#10b981]/10 border border-[#10b981]/20 px-3 py-2 text-xs text-[#10b981]">
              证据包已生成，可下载使用。
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-2 mt-4">
            {isCompleted && task?.download_url && (
              <a
                href={task.download_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-xs font-medium bg-gradient-to-r from-[#10b981] to-[#1677ff] text-white shadow-lg shadow-[#10b981]/20 hover:from-[#10b981]/90 hover:to-[#1677ff]/90 transition-all"
              >
                <Download className="w-3.5 h-3.5" />
                下载证据包
              </a>
            )}
            <Button
              variant="outline"
              onClick={onClose}
              className="border-[#1e293b] text-[#94a3b8] h-9 text-xs"
            >
              {isRunning ? "后台运行" : "关闭"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Main Dashboard Component ────────────────────────────────────────────────

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  // Session / nav
  const [session, setSession] = useState<UserInfo | null>(null);

  // Projects
  const [projects, setProjects] = useState<DashboardProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [projectSearch, setProjectSearch] = useState("");
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);

  // SWE Status
  const [sweData, setSweData] = useState<SWEStatusResponse | null>(null);
  const [sweLoading, setSweLoading] = useState(true);

  // Coverage
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(true);

  // Gap analysis
  const [gapData, setGapData] = useState<GapAnalysisResponse | null>(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [gapPage, setGapPage] = useState(1);
  const [gapSeverity, setGapSeverity] = useState("");
  const [gapAllItems, setGapAllItems] = useState<GapItem[]>([]);
  const [gapShowAll, setGapShowAll] = useState(false);

  // Evidence generation
  const [evTask, setEvTask] = useState<EvidenceTask | null>(null);
  const [evGenerating, setEvGenerating] = useState(false);
  const [showEvModal, setShowEvModal] = useState(false);
  const evPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Global loading/error
  const [pageLoading, setPageLoading] = useState(true);
  const [error, setError] = useState("");
  const [datanote, setDatanote] = useState<string | null>(null);

  // ─── Load initial data ─────────────────────────────────────────────────────

  const loadProjects = useCallback(async () => {
    try {
      const res = await getDashboardProjects();
      if (res.projects && res.projects.length > 0) {
        setProjects(res.projects);
        if (!selectedProject) {
          setSelectedProject(res.projects[0].id);
        }
      }
      if (res.note) setDatanote(res.note);
    } catch (err: any) {
      // Projects not critical — use empty
      console.warn("Failed to load projects:", err);
    }
  }, [selectedProject]);

  const loadSWE = useCallback(async (projectId: string) => {
    setSweLoading(true);
    try {
      const res = await getSWEStatus(projectId);
      setSweData(res);
      if (res.note) setDatanote(res.note);
    } catch (err: any) {
      setError(err.message || "加载合规状态失败");
    } finally {
      setSweLoading(false);
    }
  }, []);

  const loadCoverage = useCallback(async (projectId: string) => {
    setCoverageLoading(true);
    try {
      const res = await getCoverage(projectId);
      setCoverage(res);
      if (res.note) setDatanote(res.note);
    } catch (err: any) {
      console.warn("Failed to load coverage:", err);
    } finally {
      setCoverageLoading(false);
    }
  }, []);

  const loadGapAnalysis = useCallback(
    async (projectId: string, page: number, severity: string) => {
      setGapLoading(true);
      try {
        const res = await getGapAnalysis({
          projectId,
          page,
          limit: 10,
          severity: severity || undefined,
        });
        setGapData(res);
        if (res.note) setDatanote(res.note);

        // Fetch all items for the "show all" mode if severity is empty
        if (!severity) {
          if (page === 1) {
            setGapAllItems(res.items);
          } else {
            setGapAllItems((prev) => [...prev, ...res.items]);
          }
        }
      } catch (err: any) {
        console.warn("Failed to load gap analysis:", err);
      } finally {
        setGapLoading(false);
      }
    },
    []
  );

  // Boot
  useEffect(() => {
    async function boot() {
      setPageLoading(true);
      setError("");

      const token = getToken();
      if (token) {
        try {
          const { api } = await import("@/lib/api");
          const s = await api.auth.session();
          setSession(s);
        } catch {
          // Token invalid — proceed without session
        }
      }

      await loadProjects();
      setPageLoading(false);
    }
    boot();
  }, []);

  // When selected project or tab changes, load relevant data
  useEffect(() => {
    if (!selectedProject) return;

    if (activeTab === "overview") {
      loadSWE(selectedProject);
      loadCoverage(selectedProject);
    } else {
      setGapPage(1);
      setGapSeverity("");
      setGapShowAll(false);
      setGapAllItems([]);
      loadGapAnalysis(selectedProject, 1, "");
    }
  }, [selectedProject, activeTab]);

  // ─── Project selector ─────────────────────────────────────────────────────

  const projectDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        projectDropdownRef.current &&
        !projectDropdownRef.current.contains(e.target as Node)
      ) {
        setShowProjectDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filteredProjects = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(projectSearch.toLowerCase()) ||
      p.description.toLowerCase().includes(projectSearch.toLowerCase())
  );

  const selectedProjectObj = projects.find((p) => p.id === selectedProject);

  // ─── Evidence generation ───────────────────────────────────────────────────

  const handleGenerateEvidence = async () => {
    if (evGenerating) return;
    setEvGenerating(true);
    setError("");

    try {
      const res = await generateEvidence(selectedProject);

      // Start polling the status
      const taskId = res.task_id;
      const pollInterval = setInterval(async () => {
        try {
          const status = await getEvidenceStatus(taskId);
          setEvTask(status);
          setShowEvModal(true);

          if (status.status === "completed" || status.status === "failed") {
            clearInterval(pollInterval);
            evPollRef.current = null;
            setEvGenerating(false);

            if (status.status === "completed") {
              // Auto-refresh SWE data
              loadSWE(selectedProject);
              loadCoverage(selectedProject);
            }
          }
        } catch {
          clearInterval(pollInterval);
          evPollRef.current = null;
          setEvGenerating(false);
        }
      }, 1500);

      evPollRef.current = pollInterval;
      setShowEvModal(true);
    } catch (err: any) {
      setError(err.message || "证据包生成失败");
      setEvGenerating(false);
    }
  };

  const handleCloseEvModal = () => {
    // Stop polling if still running
    if (evPollRef.current) {
      clearInterval(evPollRef.current);
      evPollRef.current = null;
    }
    setShowEvModal(false);
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (evPollRef.current) clearInterval(evPollRef.current);
    };
  }, []);

  // ─── Gap analysis ─────────────────────────────────────────────────────────

  const handleLoadMoreGaps = () => {
    const nextPage = gapPage + 1;
    setGapPage(nextPage);
    loadGapAnalysis(selectedProject, nextPage, gapSeverity);
  };

  const handleFilterGaps = (severity: string) => {
    setGapSeverity(severity);
    setGapPage(1);
    setGapShowAll(false);
    setGapAllItems([]);
    loadGapAnalysis(selectedProject, 1, severity);
  };

  const handleExportGaps = () => {
    if (!gapAllItems.length) return;
    const csvHeader = "ID,SWE Area,Description,Severity,Status,Suggestion\n";
    const csvRows = gapAllItems
      .map(
        (i) =>
          `"${i.id}","${i.swe_area}","${i.description.replace(/"/g, '""')}","${i.severity}","${i.status}","${i.suggestion.replace(/"/g, '""')}"`
      )
      .join("\n");
    const csv = csvHeader + csvRows;
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `gap-analysis-${selectedProject || "all"}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // ─── Logout ────────────────────────────────────────────────────────────────

  const handleLogout = async () => {
    try {
      const { api } = await import("@/lib/api");
      await api.auth.logout();
    } catch {
      // Ignore
    }
    clearToken();
    window.location.href = "/login";
  };

  // ─── Render ────────────────────────────────────────────────────────────────

  const displayGapItems = gapShowAll ? gapAllItems : (gapData?.items || []);
  const displayGapSummary = gapData?.summary || { total: 0, critical: 0, major: 0, minor: 0 };

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      {/* ── Top Nav ── */}
      <nav className="sticky top-0 z-50 border-b border-[#1e293b]/60 nav-blur" style={{ background: "rgba(10,14,23,.85)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <Link href="/" className="text-lg font-black tracking-tight shrink-0">
              <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
            </Link>

            {/* Tab navigation */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setActiveTab("overview")}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeTab === "overview"
                    ? "bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30"
                    : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
                }`}
              >
                <Layers className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
                概览
              </button>
              <button
                onClick={() => setActiveTab("gap-analysis")}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeTab === "gap-analysis"
                    ? "bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30"
                    : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
                }`}
              >
                <AlertTriangle className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
                差距分析
              </button>
              <button
                onClick={() => setActiveTab("knowledge-base")}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeTab === "knowledge-base"
                    ? "bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30"
                    : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
                }`}
              >
                <BookOpen className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
                知识库
              </button>
              <button
                onClick={() => setActiveTab("misra-trends")}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeTab === "misra-trends"
                    ? "bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30"
                    : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
                MISRA 趋势
              </button>
            </div>

            {/* User menu */}
            <div className="flex items-center gap-2">
              {getToken() ? (
                <DropdownMenu>
                  <DropdownMenuTrigger className="flex items-center gap-2 rounded-lg border border-[#1e293b] hover:border-[#722ed1]/40 px-2 py-1 transition-all cursor-pointer">
                    <Avatar className="w-7 h-7 border border-[#1e293b]">
                      <AvatarFallback className="bg-[#722ed1]/20 text-[#722ed1] text-[10px]">
                        {session ? getInitials(session.email) : "YU"}
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-xs text-[#94a3b8] hidden sm:inline max-w-[120px] truncate">
                      {session?.email || "用户"}
                    </span>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    className="w-56 border-[#1e293b] bg-[#111827] text-[#e2e8f0]"
                  >
                    <DropdownMenuLabel className="text-xs text-[#94a3b8]">
                      {session?.org_name || "账号"}
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator className="bg-[#1e293b]" />
                    <DropdownMenuItem className="text-sm text-[#94a3b8] hover:text-white hover:bg-[#1e293b] cursor-pointer gap-2">
                      <UserIcon className="w-3.5 h-3.5" />
                      个人信息
                    </DropdownMenuItem>
                    <DropdownMenuItem className="text-sm text-[#94a3b8] hover:text-white hover:bg-[#1e293b] cursor-pointer gap-2">
                      <Settings className="w-3.5 h-3.5" />
                      项目设置
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="bg-[#1e293b]" />
                    <DropdownMenuItem
                      onClick={handleLogout}
                      className="text-sm text-[#ff4d4f] hover:text-[#ff4d4f] hover:bg-[#ff4d4f]/10 cursor-pointer gap-2"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      退出登录
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Link
                  href="/login"
                  className="text-sm px-3 py-1.5 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40 transition-all"
                >
                  登录
                </Link>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* ── Main Content Area ── */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Data note banner */}
        {datanote && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{datanote}</span>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="mb-4 rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-4 py-2 text-xs text-[#ff4d4f] flex items-center justify-between">
            <span className="flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {error}
            </span>
            <button onClick={() => setError("")} className="ml-2 hover:text-white text-sm">&times;</button>
          </div>
        )}

        {/* ================================================================= */}
        {/* OVERVIEW TAB                                                        */}
        {/* ================================================================= */}
        {activeTab === "overview" && (
          <>
            {/* Top row: project selector + evidence button */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
              {/* Project selector */}
              <div className="relative" ref={projectDropdownRef}>
                <button
                  onClick={() => setShowProjectDropdown(!showProjectDropdown)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[#1e293b] bg-[#111827] hover:border-[#722ed1]/40 transition-all text-sm min-w-[200px]"
                >
                  <FileText className="w-3.5 h-3.5 text-[#64748b]" />
                  <span className="text-[#e2e8f0] flex-1 text-left">
                    {selectedProjectObj?.name || "选择项目"}
                  </span>
                  <ChevronDown className="w-3 h-3 text-[#64748b]" />
                </button>

                {showProjectDropdown && (
                  <div className="absolute top-full left-0 mt-1 w-72 rounded-lg border border-[#1e293b] bg-[#111827] shadow-xl z-40">
                    <div className="p-2">
                      <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#64748b]" />
                        <Input
                          placeholder="搜索项目..."
                          value={projectSearch}
                          onChange={(e) => setProjectSearch(e.target.value)}
                          className="pl-8 h-9 text-xs border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
                        />
                      </div>
                    </div>
                    <div className="max-h-60 overflow-y-auto">
                      {filteredProjects.map((p) => {
                        const isSelected = p.id === selectedProject;
                        return (
                          <button
                            key={p.id}
                            onClick={() => {
                              setSelectedProject(p.id);
                              setShowProjectDropdown(false);
                              setProjectSearch("");
                            }}
                            className={`w-full text-left px-3 py-2.5 text-sm transition-colors flex items-center gap-2 ${
                              isSelected
                                ? "bg-[#722ed1]/10 text-white"
                                : "text-[#94a3b8] hover:bg-[#1e293b] hover:text-white"
                            }`}
                          >
                            <div className="flex-1 min-w-0">
                              <div className="font-medium truncate">{p.name}</div>
                              <div className="text-[10px] text-[#64748b] truncate mt-0.5">
                                {p.swe_completed_count}/{p.swe_total} SWE
                              </div>
                            </div>
                            {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-[#722ed1] shrink-0" />}
                          </button>
                        );
                      })}
                      {filteredProjects.length === 0 && (
                        <div className="px-3 py-4 text-xs text-[#64748b] text-center">
                          未找到匹配的项目
                        </div>
                      )}
                    </div>
                    <div className="border-t border-[#1e293b] p-2">
                      <button className="w-full text-left px-2 py-1.5 text-xs text-[#722ed1] hover:bg-[#722ed1]/5 rounded transition-colors flex items-center gap-1.5">
                        <ExternalLink className="w-3 h-3" />
                        新建项目（CLI 指引）
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Evidence button */}
              <div className="flex items-center gap-2">
                <Button
                  onClick={handleGenerateEvidence}
                  disabled={evGenerating || !selectedProject}
                  className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 gap-2 disabled:opacity-60"
                >
                  {evGenerating ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      生成中...
                    </>
                  ) : (
                    <>
                      <Download className="w-4 h-4" />
                      生成证据包
                    </>
                  )}
                </Button>
              </div>
            </div>

            {/* Compliance Progress + Coverage side by side */}
            <div className="grid lg:grid-cols-3 gap-5 mb-6">
              {/* Overall compliance progress (spans 2 cols) */}
              <Card className="lg:col-span-2 border-[#1e293b] bg-[#111827]">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                      <Target className="w-4 h-4 text-[#722ed1]" />
                      ASPICE SWE 合规概览
                    </CardTitle>
                    {sweLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin text-[#64748b]" />
                    ) : (
                      <span className="text-xs text-[#64748b]">
                        {sweData?.completed_count || 0}/{sweData?.total_count || 6} 项完成
                      </span>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {/* Big progress bar */}
                  {!sweLoading && sweData && (
                    <>
                      <div className="mb-4">
                        <div className="flex items-center justify-between text-xs mb-1.5">
                          <span className="text-[#64748b]">总体合规进度</span>
                          <span
                            className="font-bold text-lg"
                            style={{
                              color:
                                sweData.overall_pct >= 80
                                  ? "#10b981"
                                  : sweData.overall_pct >= 50
                                  ? "#faad14"
                                  : "#ff4d4f",
                            }}
                          >
                            {sweData.overall_pct}%
                          </span>
                        </div>
                        <div className="h-3 rounded-full bg-[#1e293b] overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{
                              width: `${sweData.overall_pct}%`,
                              background: `linear-gradient(90deg, #722ed1, #1677ff)`,
                            }}
                          />
                        </div>
                      </div>

                      {/* SWE.1-SWE.6 Cards */}
                      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {Object.entries(sweData.swe).map(([key, swe]) => (
                          <SWECard key={key} swe={swe} />
                        ))}
                      </div>
                    </>
                  )}
                  {sweLoading && (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
                      <span className="ml-2 text-xs text-[#94a3b8]">加载合规数据...</span>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Coverage card */}
              <Card className="border-[#1e293b] bg-[#111827]">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-[#722ed1]" />
                    代码覆盖率
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {coverageLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
                    </div>
                  ) : coverage ? (
                    <div className="space-y-3">
                      {/* Big numbers */}
                      <div className="flex items-center gap-4 mb-3">
                        <div className="text-center">
                          <div
                            className="text-2xl font-black"
                            style={{
                              color:
                                coverage.line_pct >= 80
                                  ? "#10b981"
                                  : coverage.line_pct >= 50
                                  ? "#faad14"
                                  : "#ff4d4f",
                            }}
                          >
                            {coverage.display_mode === "trend"
                              ? `<${Math.round(coverage.line_pct)}%`
                              : `${Math.round(coverage.line_pct)}%`}
                          </div>
                          <div className="text-[10px] text-[#64748b] mt-0.5">行覆盖</div>
                        </div>
                        <div className="text-center">
                          <div
                            className="text-2xl font-black"
                            style={{
                              color:
                                coverage.branch_pct >= 80
                                  ? "#10b981"
                                  : coverage.branch_pct >= 50
                                  ? "#faad14"
                                  : "#ff4d4f",
                            }}
                          >
                            {Math.round(coverage.branch_pct)}%
                          </div>
                          <div className="text-[10px] text-[#64748b] mt-0.5">分支覆盖</div>
                        </div>
                        <div className="text-center">
                          <div
                            className="text-2xl font-black"
                            style={{
                              color:
                                coverage.function_pct >= 80
                                  ? "#10b981"
                                  : coverage.function_pct >= 50
                                  ? "#faad14"
                                  : "#ff4d4f",
                            }}
                          >
                            {Math.round(coverage.function_pct)}%
                          </div>
                          <div className="text-[10px] text-[#64748b] mt-0.5">函数覆盖</div>
                        </div>
                      </div>

                      {/* Mini bars per module */}
                      {coverage.modules && coverage.modules.length > 0 && (
                        <div className="space-y-2">
                          <div className="text-[10px] text-[#64748b] font-medium uppercase tracking-wider">
                            模块详情
                          </div>
                          {coverage.modules.map((m, i) => (
                            <MiniCoverageBar
                              key={i}
                              label={m.name}
                              pct={m.line_pct}
                            />
                          ))}
                        </div>
                      )}

                      {/* Trend: if display_mode is trend, show the trend line */}
                      {coverage.display_mode === "trend" && coverage.trend && coverage.trend.length > 0 && (
                        <div className="rounded-lg bg-[#faad14]/5 border border-[#faad14]/10 p-2.5 mt-2">
                          <div className="text-[10px] text-[#64748b] mb-1">覆盖率提升趋势</div>
                          <div className="flex items-end gap-1 h-8">
                            {coverage.trend.map((t, i) => {
                              const maxPct = Math.max(...coverage.trend.map((x) => x.line_pct));
                              const height = maxPct > 0 ? (t.line_pct / maxPct) * 100 : 0;
                              return (
                                <div
                                  key={i}
                                  className="flex-1 rounded-t"
                                  style={{
                                    height: `${Math.max(height, 5)}%`,
                                    background: `linear-gradient(to top, #722ed1, #1677ff)`,
                                    opacity: 0.4 + (i / coverage.trend.length) * 0.6,
                                  }}
                                  title={`${t.date}: ${t.line_pct}%`}
                                />
                              );
                            })}
                          </div>
                          <div className="text-[10px] text-[#64748b] mt-0.5 text-center">
                            近期增长趋势
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="py-6 text-center text-xs text-[#64748b]">
                      覆盖率数据不可用
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </>
        )}

        {/* ================================================================= */}
        {/* GAP ANALYSIS TAB                                                    */}
        {/* ================================================================= */}
        {activeTab === "gap-analysis" && (
          <>
            {/* Page header */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
              <div>
                <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-[#faad14]" />
                  差距分析
                </h1>
                <p className="text-xs text-[#64748b] mt-0.5">
                  {selectedProjectObj?.name
                    ? `项目: ${selectedProjectObj.name}`
                    : "选择项目查看差距"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  disabled={gapLoading}
                  onClick={() => loadGapAnalysis(selectedProject, 1, gapSeverity)}
                  className="border-[#1e293b] text-[#94a3b8] h-9 text-xs gap-1.5"
                  variant="outline"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${gapLoading ? "animate-spin" : ""}`} />
                  刷新
                </Button>
                <Button
                  onClick={handleExportGaps}
                  disabled={!gapAllItems.length}
                  className="bg-gradient-to-r from-[#10b981] to-[#1677ff] text-white h-9 text-xs gap-1.5 disabled:opacity-50 shadow-lg shadow-[#10b981]/20"
                >
                  <FileDown className="w-3.5 h-3.5" />
                  导出 CSV
                </Button>
              </div>
            </div>

            {/* Summary bar */}
            <div className="grid grid-cols-4 gap-3 mb-6">
              <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-3 text-center">
                <div className="text-xl font-black text-[#e2e8f0]">{displayGapSummary.total}</div>
                <div className="text-[10px] text-[#64748b] mt-0.5">总差距</div>
              </div>
              <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-3 text-center">
                <div className="text-xl font-black text-[#ff4d4f]">{displayGapSummary.critical}</div>
                <div className="text-[10px] text-[#64748b] mt-0.5">🔴 Critical</div>
              </div>
              <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-3 text-center">
                <div className="text-xl font-black text-[#faad14]">{displayGapSummary.major}</div>
                <div className="text-[10px] text-[#64748b] mt-0.5">🟡 Major</div>
              </div>
              <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-3 text-center">
                <div className="text-xl font-black text-[#10b981]">{displayGapSummary.minor}</div>
                <div className="text-[10px] text-[#64748b] mt-0.5">🟢 Minor</div>
              </div>
            </div>

            {/* Severity filter */}
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xs text-[#64748b]">筛选:</span>
              {["", "critical", "major", "minor"].map((sev) => (
                <button
                  key={sev}
                  onClick={() => handleFilterGaps(sev)}
                  className={`px-2.5 py-1 text-[11px] rounded-lg border transition-all ${
                    gapSeverity === sev
                      ? "bg-[#722ed1]/15 text-[#722ed1] border-[#722ed1]/30"
                      : "border-[#1e293b] text-[#94a3b8] hover:border-[#722ed1]/30 hover:text-white"
                  }`}
                >
                  {sev === ""
                    ? "全部"
                    : sev === "critical"
                    ? "🔴 Critical"
                    : sev === "major"
                    ? "🟡 Major"
                    : "🟢 Minor"}
                </button>
              ))}
            </div>

            {/* Gap analysis table */}
            <Card className="border-[#1e293b] bg-[#111827]">
              <CardContent className="p-0">
                {gapLoading && !gapData ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
                    <span className="ml-2 text-xs text-[#94a3b8]">加载差距分析数据...</span>
                  </div>
                ) : displayGapItems.length === 0 ? (
                  <div className="text-center py-12">
                    <CheckCircle2 className="w-8 h-8 text-[#10b981] mx-auto mb-2" />
                    <p className="text-sm text-[#94a3b8]">
                      {gapSeverity ? "没有匹配的差距项" : "暂无差距，合规状态良好"}
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-[#1e293b]">
                          <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                            SWE
                          </th>
                          <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                            差距描述
                          </th>
                          <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                            严重级别
                          </th>
                          <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                            状态
                          </th>
                          <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider hidden lg:table-cell">
                            建议
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayGapItems.map((item, idx) => (
                          <tr
                            key={item.id}
                            className={`border-b border-[#1e293b] hover:bg-[#1e293b]/50 transition-colors ${
                              idx % 2 === 0 ? "bg-[#0a0e17]/30" : ""
                            }`}
                          >
                            <td className="py-3 px-4">
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5"
                                style={{
                                  background: `${severityColor(item.severity)}10`,
                                  color: severityColor(item.severity),
                                  borderColor: `${severityColor(item.severity)}30`,
                                }}
                              >
                                {item.swe_area}
                              </Badge>
                            </td>
                            <td className="py-3 px-4 text-xs text-[#94a3b8] max-w-sm">
                              <span className="line-clamp-2">{item.description}</span>
                            </td>
                            <td className="py-3 px-4">
                              <span
                                className="text-xs font-medium"
                                style={{ color: severityColor(item.severity) }}
                              >
                                {severityLabel(item.severity)}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              <span
                                className="text-xs"
                                style={{ color: gapStatusColor(item.status) }}
                              >
                                {gapStatusLabel(item.status)}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-xs text-[#64748b] hidden lg:table-cell max-w-xs">
                              <span className="line-clamp-2">{item.suggestion || "-"}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Show more / less */}
                {!gapLoading && gapData && (
                  <div className="border-t border-[#1e293b] px-4 py-3 flex items-center justify-between">
                    <span className="text-xs text-[#64748b]">
                      共 {displayGapSummary.total} 项差距
                      {displayGapItems.length < gapData.total_items
                        ? `，显示 ${displayGapItems.length} 项`
                        : ""}
                    </span>
                    <div className="flex items-center gap-2">
                      {gapData.has_more && !gapShowAll && (
                        <Button
                          onClick={handleLoadMoreGaps}
                          variant="outline"
                          className="border-[#1e293b] text-[#94a3b8] h-8 text-xs gap-1"
                        >
                          <ChevronDown className="w-3 h-3" />
                          显示更多
                        </Button>
                      )}
                      {gapAllItems.length > 10 && (
                        <Button
                          onClick={() => setGapShowAll(!gapShowAll)}
                          variant="outline"
                          className="border-[#1e293b] text-[#94a3b8] h-8 text-xs gap-1"
                        >
                          {gapShowAll ? (
                            <>
                              <ChevronUp className="w-3 h-3" />
                              收起
                            </>
                          ) : (
                            <>
                              <ChevronDown className="w-3 h-3" />
                              展开全部
                            </>
                          )}
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}

        {/* ================================================================= */}
        {/* KNOWLEDGE BASE TAB                                                */}
        {/* ================================================================= */}
        {activeTab === "knowledge-base" && <KnowledgeBaseTab />}

        {/* ================================================================= */}
        {/* MISRA TRENDS TAB                                                  */}
        {/* ================================================================= */}
        {activeTab === "misra-trends" && <MisraTrendsTab />}

        {/* Page loading */}
        {pageLoading && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0a0e17]/80 backdrop-blur-sm">
            <div className="text-center">
              <Loader2 className="w-8 h-8 text-[#722ed1] animate-spin mx-auto mb-3" />
              <p className="text-sm text-[#94a3b8]">加载 Dashboard...</p>
            </div>
          </div>
        )}
      </div>

      {/* Evidence Modal */}
      <EvidenceModal open={showEvModal} task={evTask} onClose={handleCloseEvModal} />
    </div>
  );
}

// ─── Knowledge Base Tab Component ────────────────────────────────────────────

function KnowledgeBaseTab() {
  const [articles, setArticles] = useState<KbArticle[]>([]);
  const [articlesLoading, setArticlesLoading] = useState(true);
  const [articlesError, setArticlesError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedArticle, setExpandedArticle] = useState<number | null>(null);
  const [kbOffset, setKbOffset] = useState(0);
  const [kbTotal, setKbTotal] = useState(0);
  const [kbSearching, setKbSearching] = useState(false);
  const pageSize = 10;

  // FMEA
  const [fmeaEntries, setFmeaEntries] = useState<FmeaEntry[]>([]);
  const [fmeaLoading, setFmeaLoading] = useState(true);

  // Load KB articles
  const loadArticles = useCallback(async (search?: string, offset?: number) => {
    setArticlesLoading(true);
    setArticlesError("");
    try {
      const res = await getKBArticles({
        search: search || undefined,
        limit: pageSize,
        offset: offset ?? kbOffset,
      });
      setArticles(res.items);
      setKbTotal(res.total);
    } catch (err: any) {
      setArticlesError(err.message || "加载知识库失败");
    } finally {
      setArticlesLoading(false);
    }
  }, [kbOffset]);

  // Load FMEA entries
  const loadFmea = useCallback(async () => {
    setFmeaLoading(true);
    try {
      const res = await getFMEAEntries({ limit: 10, sort_by: "rpn", sort_desc: true });
      setFmeaEntries(res.items);
    } catch {
      // Silently fail
    } finally {
      setFmeaLoading(false);
    }
  }, []);

  useEffect(() => {
    loadArticles();
    loadFmea();
  }, []);

  // Search handler
  const handleSearch = () => {
    setKbOffset(0);
    setKbSearching(true);
    loadArticles(searchQuery || undefined, 0).then(() => setKbSearching(false));
  };

  const handleClearSearch = () => {
    setSearchQuery("");
    setKbOffset(0);
    setKbSearching(true);
    loadArticles(undefined, 0).then(() => setKbSearching(false));
  };

  const handlePrevPage = () => {
    const newOffset = Math.max(0, kbOffset - pageSize);
    setKbOffset(newOffset);
    setKbSearching(true);
    loadArticles(searchQuery || undefined, newOffset).then(() => setKbSearching(false));
  };

  const handleNextPage = () => {
    const newOffset = kbOffset + pageSize;
    setKbOffset(newOffset);
    setKbSearching(true);
    loadArticles(searchQuery || undefined, newOffset).then(() => setKbSearching(false));
  };

  const totalPages = Math.ceil(kbTotal / pageSize);
  const currentPage = Math.floor(kbOffset / pageSize) + 1;

  function rpnColor(rpn: number): string {
    if (rpn >= 100) return "#ff4d4f";
    if (rpn >= 50) return "#faad14";
    return "#10b981";
  }

  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-[#722ed1]" />
            知识库
          </h1>
          <p className="text-xs text-[#64748b] mt-0.5">
            {kbTotal > 0 ? `共 ${kbTotal} 篇文章` : "浏览知识库文章和 FMEA 条目"}
          </p>
        </div>
      </div>

      {/* Search bar */}
      <div className="mb-5">
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#64748b]" />
            <Input
              placeholder="搜索知识库文章..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
              className="pl-9 h-9 text-xs border-[#1e293b] bg-[#111827] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
            />
            {searchQuery && (
              <button
                onClick={handleClearSearch}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#64748b] hover:text-white"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
          <Button
            onClick={handleSearch}
            disabled={kbSearching || !searchQuery.trim()}
            className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white h-9 text-xs gap-1.5 disabled:opacity-50"
          >
            {kbSearching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            搜索
          </Button>
        </div>
      </div>

      {/* Article list + FMEA grid */}
      <div className="grid lg:grid-cols-3 gap-5 mb-6">
        {/* Article list (spans 2 cols) */}
        <Card className="lg:col-span-2 border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#722ed1]" />
              文章列表
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {articlesLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
                <span className="ml-2 text-xs text-[#94a3b8]">加载文章...</span>
              </div>
            ) : articlesError ? (
              <div className="px-4 py-8 text-center">
                <AlertCircle className="w-6 h-6 text-[#ff4d4f] mx-auto mb-2" />
                <p className="text-xs text-[#ff4d4f]">{articlesError}</p>
              </div>
            ) : articles.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <BookOpen className="w-6 h-6 text-[#64748b] mx-auto mb-2" />
                <p className="text-xs text-[#64748b]">
                  {searchQuery ? "没有找到匹配的文章" : "暂无知识库文章"}
                </p>
              </div>
            ) : (
              <div>
                {articles.map((article) => {
                  const isExpanded = expandedArticle === article.id;
                  const tags = article.tags ? article.tags.split(/[,\s]+/).filter(Boolean) : [];
                  return (
                    <div key={article.id} className="border-b border-[#1e293b] last:border-b-0">
                      <button
                        onClick={() => setExpandedArticle(isExpanded ? null : article.id)}
                        className="w-full text-left px-4 py-3 hover:bg-[#1e293b]/50 transition-colors flex items-start gap-3"
                      >
                        <div className="mt-0.5 shrink-0">
                          <ChevronRight
                            className={`w-3.5 h-3.5 text-[#64748b] transition-transform ${
                              isExpanded ? "rotate-90" : ""
                            }`}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium text-[#e2e8f0] truncate">
                              {article.title}
                            </span>
                            {article.source && (
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 h-5 shrink-0 border-[#722ed1]/20 text-[#722ed1]"
                              >
                                {article.source}
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-wrap">
                            {tags.slice(0, 4).map((tag, i) => (
                              <span
                                key={i}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-[#722ed1]/10 text-[#722ed1]/80"
                              >
                                {tag}
                              </span>
                            ))}
                            <span className="text-[10px] text-[#64748b]">
                              {article.created_at ? formatDate(article.created_at) : "-"}
                            </span>
                          </div>
                        </div>
                      </button>
                      {isExpanded && (
                        <div className="px-4 pb-4 pl-12 border-t border-[#1e293b]/50 pt-3">
                          <div
                            className="prose prose-invert max-w-none text-xs leading-relaxed"
                            dangerouslySetInnerHTML={{ __html: simpleMarkdown(article.content || "*无内容*") }}
                          />
                          <div className="mt-3 flex items-center gap-3 text-[10px] text-[#64748b]">
                            {article.source && <span>来源: {article.source}</span>}
                            {article.source_ref && <span>参考: {article.source_ref}</span>}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Pagination */}
            {!articlesLoading && kbTotal > pageSize && (
              <div className="border-t border-[#1e293b] px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-[#64748b]">
                  第 {currentPage}/{totalPages} 页，共 {kbTotal} 篇
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    onClick={handlePrevPage}
                    disabled={kbOffset === 0}
                    variant="outline"
                    className="border-[#1e293b] text-[#94a3b8] h-8 text-xs disabled:opacity-40"
                  >
                    上一页
                  </Button>
                  <Button
                    onClick={handleNextPage}
                    disabled={kbOffset + pageSize >= kbTotal}
                    variant="outline"
                    className="border-[#1e293b] text-[#94a3b8] h-8 text-xs disabled:opacity-40"
                  >
                    下一页
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* FMEA Panel */}
        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <Hash className="w-4 h-4 text-[#faad14]" />
              FMEA 高 RPN 条目
            </CardTitle>
            <CardDescription className="text-[10px] text-[#64748b]">
              按 RPN 降序排列
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {fmeaLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
              </div>
            ) : fmeaEntries.length === 0 ? (
              <div className="px-4 py-6 text-center">
                <p className="text-xs text-[#64748b]">暂无 FMEA 条目</p>
              </div>
            ) : (
              <div className="space-y-0">
                {fmeaEntries.map((entry) => (
                  <div
                    key={entry.id}
                    className="px-4 py-2.5 border-b border-[#1e293b] last:border-b-0 hover:bg-[#1e293b]/30 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-[#e2e8f0] truncate max-w-[160px]">
                        {entry.item}
                      </span>
                      <span
                        className="text-xs font-mono font-bold"
                        style={{ color: rpnColor(entry.rpn) }}
                      >
                        RPN {entry.rpn}
                      </span>
                    </div>
                    <p className="text-[10px] text-[#64748b] line-clamp-1 mb-1">
                      {entry.failure_mode}
                    </p>
                    <div className="flex items-center gap-2 text-[10px] text-[#64748b]">
                      <span>S:{entry.severity}</span>
                      <span>O:{entry.occurence}</span>
                      <span>D:{entry.detection}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

// ─── MISRA Trends Tab Component ─────────────────────────────────────────────

function MisraTrendsTab() {
  const [trendData, setTrendData] = useState<MisraTrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError("");
      try {
        const res = await getMISRATrend();
        setTrendData(res);
      } catch (err: any) {
        setError(err.message || "加载 MISRA 趋势失败");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 text-[#722ed1] animate-spin" />
        <span className="ml-2 text-sm text-[#94a3b8]">加载 MISRA 趋势数据...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[#ff4d4f]/20 bg-[#ff4d4f]/5 px-4 py-6 text-center">
        <AlertCircle className="w-6 h-6 text-[#ff4d4f] mx-auto mb-2" />
        <p className="text-sm text-[#ff4d4f]">{error}</p>
      </div>
    );
  }

  if (!trendData) return null;

  const { weekly_trend, distribution, recent_violations, note } = trendData;

  // Compute max values for scaling
  const maxViolations = Math.max(...weekly_trend.map((w) => w.violations), 1);
  const totalDist = distribution.required + distribution.advisory;

  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-[#722ed1]" />
            MISRA 违规趋势
          </h1>
          <p className="text-xs text-[#64748b] mt-0.5">
            MISRA 违规数量周趋势与规则分布
          </p>
        </div>
        <Button
          onClick={() => window.location.reload()}
          variant="outline"
          className="border-[#1e293b] text-[#94a3b8] h-9 text-xs gap-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          刷新
        </Button>
      </div>

      {/* Note banner */}
      {note && (
        <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
          <Info className="w-3.5 h-3.5 shrink-0" />
          <span>{note}</span>
        </div>
      )}

      {/* Trend chart + Distribution pie side by side */}
      <div className="grid lg:grid-cols-3 gap-5 mb-6">
        {/* Trend bar chart (spans 2 cols) */}
        <Card className="lg:col-span-2 border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[#722ed1]" />
              周趋势
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Bar chart */}
            <div className="flex items-end gap-3 h-48 px-2">
              {weekly_trend.map((point, i) => {
                const h = Math.max((point.violations / maxViolations) * 100, 4);
                return (
                  <div key={point.week} className="flex-1 flex flex-col items-center gap-1 h-full">
                    {/* Bar stack */}
                    <div className="flex-1 w-full flex flex-col justify-end gap-0.5">
                      {/* Advisory portion */}
                      <div
                        className="w-full rounded-t-sm transition-all duration-500"
                        style={{
                          height: `${Math.max((point.advisory / maxViolations) * 100, 2)}%`,
                          background: "#1677ff",
                          opacity: 0.6 + (i / weekly_trend.length) * 0.4,
                        }}
                        title={`Advisory: ${point.advisory}`}
                      />
                      {/* Required portion */}
                      <div
                        className="w-full rounded-t-sm transition-all duration-500"
                        style={{
                          height: `${Math.max(((point.required) / maxViolations) * 100, 2)}%`,
                          background: "#722ed1",
                          opacity: 0.5 + (i / weekly_trend.length) * 0.5,
                        }}
                        title={`Required: ${point.required}`}
                      />
                    </div>
                    {/* Label */}
                    <span className="text-[10px] text-[#64748b] whitespace-nowrap">
                      {point.week.slice(5)}
                    </span>
                    {/* Value */}
                    <span className="text-[10px] font-mono text-[#94a3b8]">
                      {point.violations}
                    </span>
                  </div>
                );
              })}
            </div>
            {/* Legend */}
            <div className="flex items-center justify-center gap-4 mt-4 text-[10px] text-[#94a3b8]">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: "#722ed1" }} />
                Required
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: "#1677ff" }} />
                Advisory
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Distribution */}
        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <Target className="w-4 h-4 text-[#722ed1]" />
              规则分布
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Simple donut-style visualization with pure CSS */}
            <div className="flex flex-col items-center">
              <div className="relative w-32 h-32 mb-4">
                {/* CSS donut: two overlapping semicircles + conic-gradient approach */}
                <svg viewBox="0 0 36 36" className="w-32 h-32 -rotate-90">
                  {/* Background ring */}
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none"
                    stroke="#1e293b"
                    strokeWidth="3.2"
                  />
                  {/* Required segment */}
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none"
                    stroke="#722ed1"
                    strokeWidth="3.2"
                    strokeDasharray={`${(distribution.required / totalDist) * 100} ${100 - (distribution.required / totalDist) * 100}`}
                    strokeLinecap="butt"
                  />
                  {/* Advisory segment */}
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none"
                    stroke="#1677ff"
                    strokeWidth="3.2"
                    strokeDasharray={`${(distribution.advisory / totalDist) * 100} ${100 - (distribution.advisory / totalDist) * 100}`}
                    strokeDashoffset={-(distribution.required / totalDist) * 100}
                    strokeLinecap="butt"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-xl font-black text-[#e2e8f0]">{totalDist}</div>
                    <div className="text-[10px] text-[#64748b]">总计</div>
                  </div>
                </div>
              </div>

              <div className="w-full space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-[#94a3b8]">
                    <span className="w-2 h-2 rounded-full" style={{ background: "#722ed1" }} />
                    Required
                  </span>
                  <span className="font-mono text-[#722ed1]">{distribution.required}</span>
                </div>
                <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(distribution.required / totalDist) * 100}%`,
                      background: "#722ed1",
                    }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs mt-2">
                  <span className="flex items-center gap-1.5 text-[#94a3b8]">
                    <span className="w-2 h-2 rounded-full" style={{ background: "#1677ff" }} />
                    Advisory
                  </span>
                  <span className="font-mono text-[#1677ff]">{distribution.advisory}</span>
                </div>
                <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(distribution.advisory / totalDist) * 100}%`,
                      background: "#1677ff",
                    }}
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent violations */}
      <Card className="border-[#1e293b] bg-[#111827]">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-[#faad14]" />
            最近违规（最近 10 条）
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {recent_violations.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <CheckCircle2 className="w-6 h-6 text-[#10b981] mx-auto mb-2" />
              <p className="text-xs text-[#94a3b8]">暂无近期违规</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                      规则
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                      类别
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider hidden sm:table-cell">
                      文件
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider hidden md:table-cell">
                      行
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider hidden lg:table-cell">
                      说明
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                      严重级别
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recent_violations.map((v, idx) => (
                    <tr
                      key={idx}
                      className={`border-b border-[#1e293b] hover:bg-[#1e293b]/50 transition-colors ${
                        idx % 2 === 0 ? "bg-[#0a0e17]/30" : ""
                      }`}
                    >
                      <td className="py-3 px-4">
                        <Badge
                          variant="outline"
                          className="text-[10px] px-1.5 font-mono border-[#722ed1]/20 text-[#722ed1]"
                        >
                          {v.rule_id}
                        </Badge>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-xs font-medium ${
                            v.category === "Required" ? "text-[#722ed1]" : "text-[#1677ff]"
                          }`}
                        >
                          {v.category === "Required" ? "🔴 Required" : "🔵 Advisory"}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-xs text-[#94a3b8] font-mono hidden sm:table-cell">
                        <span className="truncate max-w-[120px] inline-block align-bottom">{v.file}</span>
                      </td>
                      <td className="py-3 px-4 text-xs text-[#64748b] font-mono hidden md:table-cell">
                        {v.line}
                      </td>
                      <td className="py-3 px-4 text-xs text-[#64748b] hidden lg:table-cell max-w-xs">
                        <span className="line-clamp-2">{v.message}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-xs ${
                            v.severity === "high"
                              ? "text-[#ff4d4f]"
                              : v.severity === "medium"
                              ? "text-[#faad14]"
                              : "text-[#64748b]"
                          }`}
                        >
                          {v.severity === "high"
                            ? "🔴 高"
                            : v.severity === "medium"
                            ? "🟡 中"
                            : "🔵 低"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

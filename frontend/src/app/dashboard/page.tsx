"use client";

import { useState, useEffect, useCallback, useRef, ReactNode } from "react";
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
  Settings,
  ArrowRight,
  FileDown,
  Info,
  Search,
  ExternalLink,
  X,
  BookMarked,
  Hash,
  ShieldCheck,
  Activity,
  Play,
  ListChecks,
  Trash2,
  Clock,
  History,
  FolderPlus,
  Sparkles,
  Cpu,
  MessageSquare,
  Coins,
  Layers,
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
import { useDashboardShell } from "@/app/dashboard/layout";
import {
  getDashboardProjects,
  getSWEStatus,
  getGapAnalysis,
  getGapDetail,
  runGap,
  generateEvidence,
  getEvidenceStatus,
  getCoverage,
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
import { api } from "@/lib/api";
import { simpleMarkdown } from "@/lib/markdown";
import { subscribeSSE, type SSEHandle } from "@/lib/sse";
import { loadGapSelection, saveGapSelection } from "@/lib/gap-selection";
import {
  listGapRuns,
  clearGapRuns,
  type GapRunRecord,
} from "@/lib/gap-run-history";
import {
  listEvidenceHistory,
  recordEvidence,
  clearEvidenceHistory,
  type EvidenceHistoryEntry,
} from "@/lib/evidence-history";
import { MiniCoverageBar } from "@/components/dashboard/mini-coverage-bar";
import { SWECard } from "@/components/dashboard/swe-card";
import { EvidenceModal } from "@/components/dashboard/evidence-modal";
import { TaskStageProgress } from "@/components/dashboard/task-stage-progress";
import { GapDetailModal } from "@/components/dashboard/gap-detail-modal";
import { CreateProjectModal } from "@/components/dashboard/create-project-modal";
import { DemoGalleryModal, DEMO_SLUGS } from "@/components/dashboard/demo-gallery-modal";
import LLMSettingsModal from "@/components/dashboard/llm-settings-modal";
import { GapBatchModal } from "@/components/dashboard/gap-batch-modal";
import { KnowledgeBaseTab } from "@/components/dashboard/knowledge-base-tab";
import { MisraTrendsTab } from "@/components/dashboard/misra-trends-tab";
import { PipelineStageBoard } from "@/components/dashboard/pipeline-stage-board";
import { LoopEngineering } from "@/components/dashboard/loop-engineering";
import { YuleASRStatus } from "@/components/dashboard/yuleasr-status";
import { PortfolioCompliance } from "@/components/dashboard/portfolio-compliance";

// ─── Types ───────────────────────────────────────────────────────────────────

type Tab = "overview" | "gap-analysis" | "knowledge-base" | "misra-trends";

// ─── Dashboard v2 (五维合规总览) types ─────────────────────────────────────

interface ComplianceDimension {
  key: string;
  label: string;
  score: number;
  weight: number;
  status: "good" | "warning" | "critical";
  note?: string | null;
}

interface DashboardV2Overview {
  compliance_score: number;
  dimensions: ComplianceDimension[];
  coverage: number;
  test_pass_rate: number;
  misra_violations: number;
  active_pipelines: number;
  projects_count: number;
  devices_summary: Record<string, number>;
  generated_at: string;
  note: string | null;
}

interface DashboardV2OverviewResponse {
  ok: boolean;
  data: DashboardV2Overview;
  error?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

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
    case "queued":
      return "排队中";
    case "running":
      return "执行中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
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

function complianceScoreColor(score: number): string {
  if (score >= 80) return "#10b981";
  if (score >= 60) return "#faad14";
  return "#ff4d4f";
}

// 运行历史（头脑风暴项④）：运行记录的状态 / 模式 展示元信息。
function runStatusMeta(status: string): { label: string; color: string } {
  switch (status) {
    case "running":
      return { label: "执行中", color: "#722ed1" };
    case "completed":
      return { label: "已完成", color: "#10b981" };
    case "failed":
      return { label: "失败", color: "#ff4d4f" };
    default:
      return { label: status, color: "#64748b" };
  }
}

function runModeMeta(mode: string): { label: string; color: string } {
  switch (mode) {
    case "analyze":
      return { label: "批量分析", color: "#722ed1" };
    case "remediate":
      return { label: "批量修复", color: "#10b981" };
    default:
      return { label: mode, color: "#64748b" };
  }
}

function formatRunTime(epoch: number): string {
  try {
    const d = new Date(epoch);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "-";
  }
}

function clampScore(score: number): number {
  return Math.max(0, Math.min(100, score));
}

// 生成进度可视化（头脑风暴项⑧）：证据包生成的阶段定义，供常驻横幅复用
// （与 EvidenceModal 一致：准备→收集证据→生成清单→打包并写入→完成）。
const EVIDENCE_STAGES = ["准备", "收集证据", "生成清单", "打包并写入", "完成"];
const EVIDENCE_BREAKPOINTS = [0, 10, 30, 60, 95, 100];

// ─── 测试分层（四层流水线）类型 + 状态映射 ───────────────────────────────────

interface LayerOverview {
  key: "unit" | "integration" | "hil" | "qualification";
  label: string;
  subtitle: string;
  badge: string;
  in_steps: boolean;
  status: "pass" | "fail" | "mock" | "unknown";
  passed: number | null;
  failed: number | null;
  skipped: number | null;
  source: string;
  updated_at: string;
  commit?: string | null;
  mock_mode?: boolean | null;
  note?: string | null;
}

interface LayersResponse {
  project: string;
  order: LayerOverview["key"][];
  layers: LayerOverview[];
  note?: string | null;
}

function layerStatusMeta(status: string): { label: string; color: string } {
  switch ((status || "").toLowerCase()) {
    case "pass":
    case "passed":
      return { label: "PASS", color: "#10b981" };
    case "fail":
    case "failed":
      return { label: "FAIL", color: "#ff4d4f" };
    case "mock":
      return { label: "MOCK", color: "#faad14" };
    default:
      return { label: "未运行", color: "#64748b" };
  }
}

// ─── v9: 我的用量 helpers ────────────────────────────────────────────────────

function fmtTokens(n: number): string {
  if (!n || n <= 0) return "0";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function UsageStat({
  icon,
  label,
  value,
  unit,
  sub,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-[#1e293b] bg-[#0b1220] px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[10px] text-[#64748b] mb-1">
        {icon}
        <span>{label}</span>
      </div>
      <div className="text-lg font-semibold text-[#e2e8f0] leading-tight truncate">
        {value}
        {unit ? <span className="text-xs text-[#64748b] ml-0.5">{unit}</span> : null}
      </div>
      {sub ? <div className="text-[10px] text-[#475569] mt-0.5 truncate">{sub}</div> : null}
    </div>
  );
}

// ─── Mini Coverage Bar ───────────────────────────────────────────────────────




export default function DashboardPage() {
  // 顶部 tab 状态由 dashboard/layout 持有（导航渲染在 layout，避免子页重复渲染）
  const { activeTab, setActiveTab } = useDashboardShell();

  // 子页面（/dashboard/evidence 等）下点顶栏 tab 项时跳到 /dashboard?tab=<tab>，
  // 这里读 query 同步到 layout 持有的 activeTab。layout 也读了一次，这里是双保险：
  // 直接读 window.location，避免触发 useSearchParams 在静态导出下的 Suspense 要求。
  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = new URLSearchParams(window.location.search).get("tab");
    if (
      t === "overview" ||
      t === "gap-analysis" ||
      t === "misra-trends" ||
      t === "knowledge-base"
    ) {
      if (t !== activeTab) setActiveTab(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Session / nav
  const [session, setSession] = useState<UserInfo | null>(null);

  // 视角：管理视角（决策者，合规/用量优先）/ 工程视角（工程师，流水线优先）
  // 默认严格按角色（见 boot 中设置）；用户手动切换仅当前会话有效，不持久化。
  const [perspective, setPerspective] = useState<"manage" | "engineer">("manage");

  const roleLabel =
    session?.role === "admin"
      ? "Administrator"
      : session?.role === "developer"
      ? "Developer"
      : session?.role === "reviewer"
      ? "Reviewer"
      : session?.role === "auditor"
      ? "Auditor"
      : "—";

  const switchPerspective = (next: "manage" | "engineer") => {
    // 仅当前会话级覆盖，不持久化到 localStorage —— 避免同一浏览器下
    // 跨账号污染（即两角色视图趋同的根因）。刷新 / 重新登录回落角色默认值。
    setPerspective(next);
  };

  // Projects
  const [projects, setProjects] = useState<DashboardProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDemoGallery, setShowDemoGallery] = useState(false);
  const [projectSearch, setProjectSearch] = useState("");
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);

  // SWE Status
  const [sweData, setSweData] = useState<SWEStatusResponse | null>(null);
  const [sweLoading, setSweLoading] = useState(true);

  // Coverage
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(true);

  // 测试分层总览（四层流水线，含 HIL Layer 2.5）
  const [testLayers, setTestLayers] = useState<LayerOverview[]>([]);
  const [testLayersLoading, setTestLayersLoading] = useState(true);

  // Dashboard v2 compliance overview (五维合规总览)
  const [v2Overview, setV2Overview] = useState<DashboardV2Overview | null>(null);
  const [v2OverviewLoading, setV2OverviewLoading] = useState(false);

  // Gap analysis
  const [gapData, setGapData] = useState<GapAnalysisResponse | null>(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [gapPage, setGapPage] = useState(1);
  const [gapSeverity, setGapSeverity] = useState("");
  const [gapAllItems, setGapAllItems] = useState<GapItem[]>([]);
  const [gapShowAll, setGapShowAll] = useState(false);

  // Gap detail modal (per-item 分析 / 运行)
  const [showGapDetail, setShowGapDetail] = useState(false);
  const [selectedGapId, setSelectedGapId] = useState<string | null>(null);

  // 运行历史（头脑风暴项④）：前端本地记录，按项目展示，刷新/重进可回看。
  const [gapRuns, setGapRuns] = useState<GapRunRecord[]>([]);
  const [runsOpen, setRunsOpen] = useState(false);

  // Gap batch (bulk analyze / remediate)
  const [selectedGapIds, setSelectedGapIds] = useState<string[]>([]);
  // 持久化选择（头脑风暴项①）：勾选跨刷新保留，按项目隔离。
  // restoredRef 记录已为哪个项目恢复过，避免切换项目时误存旧选择；
  // skipSaveRef 跳过挂载首帧（此时 selectedGapIds=[] 会把持久化清空）。
  const restoredRef = useRef<string | null>(null);
  const skipSaveRef = useRef(true);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [batchMode, setBatchMode] = useState<"analyze" | "remediate">("remediate");

  // Evidence generation
  const [evTask, setEvTask] = useState<EvidenceTask | null>(null);
  const [evGenerating, setEvGenerating] = useState(false);
  const [showEvModal, setShowEvModal] = useState(false);
  const evPollRef = useRef<SSEHandle | null>(null);

  // 证据历史（头脑风暴项⑨）：前端本地记录，按项目展示，可回看/再次下载。
  const [evidenceHistory, setEvidenceHistory] = useState<EvidenceHistoryEntry[]>([]);
  const [evHistoryOpen, setEvHistoryOpen] = useState(false);

  // Global loading/error
  const [pageLoading, setPageLoading] = useState(true);
  const [error, setError] = useState("");
  const [datanote, setDatanote] = useState<string | null>(null);

  // v9: per-user usage panel (我的用量) + org LLM model config
  const [myUsage, setMyUsage] = useState<any>(null);
  const [usageLoading, setUsageLoading] = useState(true);
  const [showLLMSettings, setShowLLMSettings] = useState(false);
  const [llmCfg, setLlmCfg] = useState<{ provider?: string | null; model?: string | null }>({
    provider: null,
    model: null,
  });

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

  const handleDemoLoaded = async () => {
    try {
      const res = await getDashboardProjects();
      if (res?.projects?.length) {
        setProjects(res.projects);
        const uart = res.projects.find((p) => p.slug === "uart-demo");
        if (uart) setSelectedProject(uart.id);
      }
    } catch (e: any) {
      console.error("refresh projects after seed failed:", e?.message || e);
    }
  };

  const demoLoadedSlugs = projects
    .filter((p) => DEMO_SLUGS.includes(p.slug))
    .map((p) => p.slug);

  const handleCreated = async (proj: { id?: string; name: string; slug?: string }) => {
    try {
      const res = await getDashboardProjects();
      if (res?.projects?.length) {
        setProjects(res.projects);
        const match = res.projects.find((p) => p.name === proj.name);
        if (match) setSelectedProject(match.id);
      }
    } catch (e: any) {
      console.error("refresh projects failed:", e?.message || e);
    }
  };

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

  // 测试分层总览 — 仓库级数据（.osh/sessions + .osh/ci），无需 project。
  const loadTestLayers = useCallback(async () => {
    setTestLayersLoading(true);
    try {
      const resp = await fetch("/api/v1/tests/layers", { credentials: "same-origin" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body: LayersResponse & { ok?: boolean; data?: LayersResponse } = await resp.json();
      const payload = body.data ?? body;
      setTestLayers(payload.layers || []);
    } catch (err: any) {
      console.warn("Failed to load test layers:", err);
      setTestLayers([]);
    } finally {
      setTestLayersLoading(false);
    }
  }, []);

  // Dashboard v2 五维合规总览 — cookie 认证自动携带，直接 fetch 即可。
  // 信封 {ok, data}，业务数据在 resp.data；note 非空 = 无真实数据。
  const loadV2Overview = useCallback(async () => {
    setV2OverviewLoading(true);
    try {
      const resp = await fetch("/api/v1/dashboard-v2/overview", {
        credentials: "same-origin",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body: DashboardV2OverviewResponse = await resp.json();
      if (!body || body.ok === false) {
        throw new Error(body?.error || "加载合规总览失败");
      }
      setV2Overview(body.data ?? null);
    } catch (err: any) {
      console.warn("Failed to load dashboard-v2 overview:", err);
      setV2Overview(null);
    } finally {
      setV2OverviewLoading(false);
    }
  }, []);

  // v9: 我的用量 — 当前用户 pipeline 次数 / 对话次数 / token / 当前模型
  const loadMyUsage = useCallback(async () => {
    setUsageLoading(true);
    try {
      const { api } = await import("@/lib/api");
      const [usage, cfg] = await Promise.all([
        api.v1.me.usage(),
        api.v1.org.llmConfig().catch(() => null),
      ]);
      if (usage && usage.ok !== false) setMyUsage(usage.data ?? usage);
      if (cfg && cfg.ok !== false) setLlmCfg(cfg.data ?? cfg);
    } catch (err: any) {
      console.warn("Failed to load my usage:", err);
    } finally {
      setUsageLoading(false);
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

        // 持久化选择（头脑风暴项①）：page 1 整页重拉时，从 localStorage 恢复
        // 该项目已勾选的差距项（与当前可用项求交集，剔除已不存在的）。
        // 恢复后置 restoredRef 并放开保存，避免挂载首帧把持久化清空。
        if (page === 1) {
          const avail = new Set(res.items.map((i) => i.id));
          const valid = loadGapSelection(projectId).filter((id) => avail.has(id));
          restoredRef.current = projectId;
          skipSaveRef.current = false;
          setSelectedGapIds(valid);
        }
      } catch (err: any) {
        console.warn("Failed to load gap analysis:", err);
      } finally {
        setGapLoading(false);
      }
    },
    []
  );

  // 持久化选择（头脑风暴项①）：选择变更即写回 localStorage（按当前项目分桶）。
  // 跳过挂载首帧与「尚未为该项目恢复」的情况，避免清空已有持久化。
  useEffect(() => {
    if (skipSaveRef.current) return;
    if (!selectedProject || restoredRef.current !== selectedProject) return;
    saveGapSelection(selectedProject, selectedGapIds);
  }, [selectedGapIds, selectedProject]);

  // Boot
  useEffect(() => {
    async function boot() {
      setPageLoading(true);
      setError("");

      // T1 (v3.9.0): 会话由 httpOnly cookie 携带，前端无法读 token。
      // 直接探测 session 端点；未登录时 request() 会触发无感续期，
      // 续期失败则 redirectToLogin（/login）。
      try {
        const { api } = await import("@/lib/api");
        const s = await api.auth.session();
        setSession(s);
        // 视角完全由登录用户角色决定：admin -> 管理视角，其余 -> 工程视角。
        // 不读 ?view / localStorage，避免同一浏览器下预览状态跨账号污染。
        if (s?.role) {
          setPerspective(s.role === "admin" ? "manage" : "engineer");
        }
      } catch {
        // No valid session — proceed without session (redirect already fired)
      }

      await loadProjects();
      loadMyUsage();
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
      loadV2Overview();
      loadTestLayers();
    } else {
      setGapPage(1);
      setGapSeverity("");
      setGapShowAll(false);
      setGapAllItems([]);
      loadGapAnalysis(selectedProject, 1, "");
    }
    // 运行历史（头脑风暴项④）：项目切换时按项目从 localStorage 载入本地记录。
    setGapRuns(listGapRuns(selectedProject));
    // 证据历史（项⑨）：项目切换时按项目从 localStorage 载入本地记录。
    setEvidenceHistory(listEvidenceHistory(selectedProject));
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

  // 把证据任务状态应用到 UI：更新进度/弹窗，并在终态（completed/failed）
  // 时收尾（刷新 SWE/覆盖率、记证据历史）。返回 true 表示已到终态。
  const applyEvidenceStatus = (status: EvidenceTask): boolean => {
    setEvTask(status);
    setShowEvModal(true);
    if (status.status === "completed" || status.status === "failed") {
      setEvGenerating(false);
      if (status.status === "completed") {
        // 生成成功：自动刷新 SWE / 覆盖率数据
        loadSWE(selectedProject);
        loadCoverage(selectedProject);
        // 证据历史（项⑨）：成功生成，记一条可回看/下载的记录。
        recordEvidence(selectedProject, {
          taskId: status.task_id ?? null,
          download_url: status.download_url ?? null,
          note: status.note ?? null,
          status: "completed",
        });
      } else {
        // 证据历史（项⑨）：生成失败也记录，便于排查。
        recordEvidence(selectedProject, {
          taskId: status.task_id ?? null,
          note: status.error ?? null,
          status: "failed",
        });
      }
      setEvidenceHistory(listEvidenceHistory(selectedProject));
      return true;
    }
    return false;
  };

  const handleGenerateEvidence = async () => {
    if (evGenerating) return;
    setEvGenerating(true);
    setError("");

    try {
      const res = await generateEvidence(selectedProject);
      const taskId = res.task_id;
      setShowEvModal(true);

      // 项⑩：优先 SSE 推送进度（只在状态变化时来包），连接失败/不支持时
      // 自动退回指数退避轮询（getEvidenceStatus）。
      evPollRef.current = subscribeSSE<EvidenceTask>({
        url: `/api/v1/dashboard/evidence/stream?task_id=${encodeURIComponent(taskId)}`,
        onStatus: applyEvidenceStatus,
        fallbackPoll: async () =>
          applyEvidenceStatus(await getEvidenceStatus(taskId)),
        onError: () => setEvGenerating(false),
      });
    } catch (err: any) {
      setError(err.message || "证据包生成失败");
      setEvGenerating(false);
    }
  };

  const handleCloseEvModal = () => {
    // 生成进度可视化（项⑧）：关闭弹窗不中断轮询，进度转入顶部常驻横幅
    // （后台运行）。轮询在 completed/failed 时由 startExponentialPoll 自动停止。
    setShowEvModal(false);
  };

  // 关闭/清除常驻生成进度横幅（项⑧）：停止轮询并清空任务状态。
  const dismissEvBanner = () => {
    if (evPollRef.current) {
      evPollRef.current.stop();
      evPollRef.current = null;
    }
    setEvTask(null);
    setEvGenerating(false);
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (evPollRef.current) evPollRef.current.stop();
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

  // ─── Render ────────────────────────────────────────────────────────────────

  const displayGapItems = gapShowAll ? gapAllItems : (gapData?.items || []);
  const displayGapSummary = gapData?.summary || { total: 0, critical: 0, major: 0, minor: 0 };

  return (
    <>
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

        {/* 生成进度可视化（头脑风暴项⑧）：证据包生成的常驻、非阻塞横幅。
            弹窗关闭（后台运行）后仍可见；运行中可点「查看详情」回到弹窗，
            完成/失败常驻直到用户关闭。 */}
        {evTask && !showEvModal && (evTask.status === "running" || evTask.status === "completed" || evTask.status === "failed") && (
          <div
            className="mb-4 rounded-lg border px-4 py-3"
            style={{
              background:
                evTask.status === "failed"
                  ? "#ff4d4f10"
                  : evTask.status === "completed"
                  ? "#10b98110"
                  : "#722ed114",
              borderColor:
                evTask.status === "failed"
                  ? "#ff4d4f30"
                  : evTask.status === "completed"
                  ? "#10b98130"
                  : "#722ed130",
            }}
          >
            <div className="flex items-center justify-between gap-3 mb-2">
              <span
                className="text-xs font-medium flex items-center gap-1.5"
                style={{
                  color:
                    evTask.status === "failed"
                      ? "#ff4d4f"
                      : evTask.status === "completed"
                      ? "#10b981"
                      : "#a78bfa",
                }}
              >
                {evTask.status === "running" && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {evTask.status === "completed" && <CheckCircle2 className="w-3.5 h-3.5" />}
                {evTask.status === "failed" && <AlertCircle className="w-3.5 h-3.5" />}
                {evTask.status === "running" && "正在生成证据包…"}
                {evTask.status === "completed" && "证据包已生成完成"}
                {evTask.status === "failed" && "证据包生成失败"}
              </span>
              <div className="flex items-center gap-2 shrink-0">
                {evTask.status === "running" && (
                  <button
                    onClick={() => setShowEvModal(true)}
                    className="text-[11px] text-[#722ed1] hover:text-white px-2 py-1 rounded hover:bg-[#722ed1]/10"
                  >
                    查看详情
                  </button>
                )}
                {evTask.status === "completed" && evTask.download_url && (
                  <a
                    href={evTask.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-[#10b981] hover:text-white px-2 py-1 rounded hover:bg-[#10b981]/10"
                  >
                    <Download className="w-3 h-3" />
                    下载
                  </a>
                )}
                <button
                  onClick={dismissEvBanner}
                  className="text-[11px] text-[#64748b] hover:text-white px-2 py-1 rounded hover:bg-[#1e293b]/60"
                >
                  {evTask.status === "running" ? "后台运行" : "关闭"}
                </button>
              </div>
            </div>
            <TaskStageProgress
              stages={EVIDENCE_STAGES}
              breakpoints={EVIDENCE_BREAKPOINTS}
              progressPct={evTask.progress_pct ?? 0}
              isFailed={evTask.status === "failed"}
            />
            {evTask.status === "failed" && evTask.error && (
              <div className="mt-2 text-[11px] text-[#ff4d4f] break-words">{evTask.error}</div>
            )}
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
                              <div className="font-medium truncate flex items-center gap-1.5">
                                {p.name}
                                {DEMO_SLUGS.includes(p.slug) && (
                                  <span className="text-[9px] px-1 py-0.5 rounded bg-[#1677ff]/15 text-[#1677ff] shrink-0">
                                    示例
                                  </span>
                                )}
                              </div>
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
                    <div className="border-t border-[#1e293b] p-2 space-y-1">
                      <button
                        onClick={() => setShowCreateModal(true)}
                        className="w-full text-left px-2 py-1.5 text-xs text-[#722ed1] hover:bg-[#722ed1]/5 rounded transition-colors flex items-center gap-1.5"
                      >
                        <FolderPlus className="w-3 h-3" />
                        新建项目
                      </button>
                      <button
                        onClick={() => setShowDemoGallery(true)}
                        className="w-full text-left px-2 py-1.5 text-xs text-[#1677ff] hover:bg-[#1677ff]/5 rounded transition-colors flex items-center gap-1.5"
                      >
                        <Sparkles className="w-3 h-3" />
                        加载示例项目
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* 右侧动作组：运行 Pipeline + 生成证据包 紧贴靠右 */}
              <div className="flex items-center gap-2 sm:ml-auto">
                {/* Run pipeline → 运行控制面板（重跑 / 勾选某几项 / 续跑 / 停止） */}
                <Link href="/dashboard/pipeline">
                  <Button
                    variant="outline"
                    className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40 gap-2"
                  >
                    <Play className="w-4 h-4" />
                    运行 Pipeline
                  </Button>
                </Link>

                {/* Evidence button */}
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

            {/* 视角切换：管理视角（决策者）/ 工程视角（工程师，流水线优先） */}
            <div className="flex items-center gap-2 mb-6">
              <span className="text-xs text-[#64748b]">视角</span>
              <div className="inline-flex rounded-lg border border-[#1e293b] overflow-hidden">
                <button
                  onClick={() => switchPerspective("manage")}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    perspective === "manage"
                      ? "bg-[#722ed1]/15 text-[#722ed1]"
                      : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
                  }`}
                >
                  管理视角
                </button>
                <button
                  onClick={() => switchPerspective("engineer")}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    perspective === "engineer"
                      ? "bg-[#1677ff]/15 text-[#1677ff]"
                      : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
                  }`}
                >
                  工程视角
                </button>
              </div>
              <span className="text-[10px] text-[#64748b]">当前角色：{roleLabel}</span>
            </div>

            {/* 工程视角：Loop Engineering 置顶（流水线优先） */}
            {perspective === "engineer" && (
              <div className="mb-6">
                <LoopEngineering />
              </div>
            )}

            {/* Dashboard v2: 五维合规总览卡 — 管理视角 */}
            {perspective === "manage" && (
            <>
            <Card className="border-[#1e293b] bg-[#111827] mb-6">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-[#722ed1]" />
                    合规总览（五维加权）
                  </CardTitle>
                  {v2OverviewLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin text-[#64748b]" />
                  ) : v2Overview?.generated_at ? (
                    <span className="text-[10px] text-[#64748b]">
                      更新于 {formatDate(v2Overview.generated_at)}
                    </span>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent>
                {v2OverviewLoading && !v2Overview ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
                    <span className="ml-2 text-xs text-[#94a3b8]">加载合规总览...</span>
                  </div>
                ) : !v2Overview ||
                  v2Overview.compliance_score == null ||
                  (v2Overview.note && v2Overview.note.length > 0) ? (
                  <div className="py-8 text-center">
                    <Info className="w-6 h-6 text-[#64748b] mx-auto mb-2" />
                    <p className="text-sm text-[#94a3b8]">暂无数据</p>
                    {v2Overview?.note && (
                      <p className="text-xs text-[#64748b] mt-1 max-w-xl mx-auto">
                        {v2Overview.note}
                      </p>
                    )}
                  </div>
                ) : (
                  <>
                    {/* 大号合规总分圆环 + 五维横向条 */}
                    <div className="grid lg:grid-cols-3 gap-6 items-center">
                      <div className="flex flex-col items-center gap-2">
                        <div className="relative w-28 h-28">
                          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                            <circle
                              cx="50"
                              cy="50"
                              r="42"
                              fill="none"
                              stroke="#1e293b"
                              strokeWidth="8"
                            />
                            <circle
                              cx="50"
                              cy="50"
                              r="42"
                              fill="none"
                              stroke={complianceScoreColor(v2Overview.compliance_score)}
                              strokeWidth="8"
                              strokeLinecap="round"
                              strokeDasharray={`${
                                (clampScore(v2Overview.compliance_score) / 100) *
                                2 *
                                Math.PI *
                                42
                              } ${2 * Math.PI * 42}`}
                            />
                          </svg>
                          <div className="absolute inset-0 flex items-center justify-center">
                            <span
                              className="text-3xl font-black"
                              style={{
                                color: complianceScoreColor(v2Overview.compliance_score),
                              }}
                            >
                              {Math.round(v2Overview.compliance_score)}
                            </span>
                          </div>
                        </div>
                        <span className="text-xs text-[#64748b]">合规总分</span>
                      </div>

                      <div className="lg:col-span-2 space-y-3">
                        {v2Overview.dimensions.map((d) => (
                          <div key={d.key}>
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span className="text-[#94a3b8] flex items-center gap-1.5">
                                {d.label}
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#722ed1]/10 text-[#722ed1] border border-[#722ed1]/20">
                                  权重 {Math.round(d.weight * 100)}%
                                </span>
                              </span>
                              <span
                                className="font-bold"
                                style={{ color: complianceScoreColor(d.score) }}
                              >
                                {d.score}
                              </span>
                            </div>
                            <div className="h-2 rounded-full bg-[#1e293b] overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all duration-700"
                                style={{
                                  width: `${clampScore(d.score)}%`,
                                  backgroundColor: complianceScoreColor(d.score),
                                }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* 一行 4 个小指标卡 */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
                      <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-3">
                        <div className="text-[10px] text-[#64748b] flex items-center gap-1">
                          <BarChart3 className="w-3 h-3" /> 代码覆盖率
                        </div>
                        <div
                          className="text-xl font-black mt-1"
                          style={{ color: complianceScoreColor(v2Overview.coverage) }}
                        >
                          {v2Overview.coverage}%
                        </div>
                      </div>
                      <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-3">
                        <div className="text-[10px] text-[#64748b] flex items-center gap-1">
                          <Target className="w-3 h-3" /> 测试通过率
                        </div>
                        <div
                          className="text-xl font-black mt-1"
                          style={{ color: complianceScoreColor(v2Overview.test_pass_rate) }}
                        >
                          {v2Overview.test_pass_rate}%
                        </div>
                      </div>
                      <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-3">
                        <div className="text-[10px] text-[#64748b] flex items-center gap-1">
                          <Hash className="w-3 h-3" /> MISRA 违规
                        </div>
                        <div
                          className="text-xl font-black mt-1"
                          style={{
                            color:
                              v2Overview.misra_violations === 0
                                ? "#10b981"
                                : "#ff4d4f",
                          }}
                        >
                          {v2Overview.misra_violations}
                        </div>
                      </div>
                      <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-3">
                        <div className="text-[10px] text-[#64748b] flex items-center gap-1">
                          <Activity className="w-3 h-3" /> 活跃流水线
                        </div>
                        <div className="text-xl font-black mt-1 text-[#1677ff]">
                          {v2Overview.active_pipelines}
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* v9: 我的用量 — 当前用户 pipeline 次数 / 对话次数 / token / 当前模型 */}
            <Card className="border-[#1e293b] bg-[#111827]">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                    <Activity className="w-4 h-4 text-[#1677ff]" />
                    我的用量
                  </CardTitle>
                  <button
                    onClick={() => setShowLLMSettings(true)}
                    className="flex items-center gap-1 text-xs text-[#1677ff] hover:bg-[#1677ff]/5 rounded px-2 py-1 transition-colors"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    模型设置
                  </button>
                </div>
              </CardHeader>
              <CardContent>
                {usageLoading ? (
                  <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    加载用量...
                  </div>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <UsageStat
                      icon={<Play className="w-4 h-4 text-[#1677ff]" />}
                      label="Pipeline 调用"
                      value={myUsage?.pipeline_runs ?? 0}
                      unit="次"
                    />
                    <UsageStat
                      icon={<MessageSquare className="w-4 h-4 text-[#722ed1]" />}
                      label="对话请求"
                      value={myUsage?.llm_calls ?? 0}
                      unit="次"
                    />
                    <UsageStat
                      icon={<Coins className="w-4 h-4 text-[#52c41a]" />}
                      label="Token 消耗"
                      value={fmtTokens(
                        (myUsage?.tokens_in ?? 0) + (myUsage?.tokens_out ?? 0)
                      )}
                      unit=""
                      sub={`in ${(myUsage?.tokens_in ?? 0).toLocaleString()} / out ${(myUsage?.tokens_out ?? 0).toLocaleString()}`}
                    />
                    <UsageStat
                      icon={<Cpu className="w-4 h-4 text-[#faad14]" />}
                      label="当前模型"
                      value={myUsage?.current_model || llmCfg?.model || llmCfg?.provider || "默认"}
                      unit=""
                    />
                  </div>
                )}
                {!usageLoading && myUsage?.cost != null && (
                  <div className="mt-3 text-xs text-[#64748b]">
                    预估成本 ${Number(myUsage.cost || 0).toFixed(2)}（基于 LLM 调用审计日志）
                  </div>
                )}
              </CardContent>
            </Card>
            </>
            )}

            {/* Pipeline Stage Board — recreated from archived dashboard-v5.html Phase/Stage kanban */}
            <div className="mt-6">
            <PipelineStageBoard />
            </div>

            {/* 证据历史（头脑风暴项⑨）：前端本地记录，按项目展示，可回看/再次下载/清空。 */}
            <Card className="mt-6 border-[#1e293b] bg-[#111827]">
              <button
                onClick={() => setEvHistoryOpen((v) => !v)}
                className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-[#1e293b]/40 transition-colors"
              >
                <span className="flex items-center gap-2 text-sm font-bold text-[#e2e8f0]">
                  <History className="w-4 h-4 text-[#10b981]" />
                  证据历史
                  <span className="text-[10px] font-normal px-1.5 py-0.5 rounded bg-[#10b981]/15 text-[#10b981]">
                    {evidenceHistory.length} 条
                  </span>
                  <span className="text-[10px] font-normal text-[#64748b]">
                    本地记录 · 可再次下载
                  </span>
                </span>
                <div className="flex items-center gap-2">
                  {evidenceHistory.length > 0 && (
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        if (
                          window.confirm(
                            `确定清空当前项目（${selectedProjectObj?.name || selectedProject}）的证据历史吗？`,
                          )
                        ) {
                          clearEvidenceHistory(selectedProject);
                          setEvidenceHistory([]);
                        }
                      }}
                      className="flex items-center gap-1 text-[11px] text-[#94a3b8] hover:text-[#ff4d4f] px-2 py-1 rounded hover:bg-[#ff4d4f]/5 cursor-pointer"
                      title="清空当前项目证据历史"
                    >
                      <Trash2 className="w-3 h-3" />
                      清空
                    </span>
                  )}
                  {evHistoryOpen ? (
                    <ChevronUp className="w-4 h-4 text-[#64748b]" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-[#64748b]" />
                  )}
                </div>
              </button>
              {evHistoryOpen && (
                <div className="border-t border-[#1e293b] px-4 py-3">
                  {evidenceHistory.length === 0 ? (
                    <div className="text-center py-6 text-xs text-[#64748b]">
                      暂无证据记录 — 点击「生成证据包」后会出现在这里
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {evidenceHistory.map((e) => {
                        const ok = e.status === "completed";
                        const color = ok ? "#10b981" : "#ff4d4f";
                        return (
                          <div
                            key={e.id}
                            className="flex items-center justify-between gap-3 rounded-lg border border-[#1e293b] bg-[#0a0e17]/40 px-3 py-2"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className="text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0"
                                style={{
                                  color,
                                  background: `${color}14`,
                                  border: `1px solid ${color}30`,
                                }}
                              >
                                {ok ? "已生成" : "失败"}
                              </span>
                              {e.download_url ? (
                                <a
                                  href={e.download_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-xs text-[#1677ff] hover:text-white truncate flex items-center gap-1"
                                  title="下载证据包"
                                >
                                  <Download className="w-3 h-3 shrink-0" />
                                  下载
                                </a>
                              ) : (
                                <span className="text-xs text-[#94a3b8] truncate">
                                  {e.note || "无下载链接"}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-1 text-[10px] text-[#64748b] shrink-0">
                              <Clock className="w-3 h-3" />
                              {formatRunTime(e.createdAt)}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </Card>

            {/* Demo 备选2: 首页测试分层总览卡片 */}
            <Card className="mt-6 border-[#1e293b] bg-[#111827]">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                    <Layers className="w-4 h-4 text-[#722ed1]" />
                    测试分层总览
                  </CardTitle>
                  <Link
                    href="/dashboard/test-layers"
                    className="text-xs text-[#722ed1] hover:underline flex items-center gap-1"
                  >
                    查看详情
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              </CardHeader>
              <CardContent>
                {testLayersLoading ? (
                  <div className="flex items-center gap-2 text-xs text-[#94a3b8] py-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    加载中…
                  </div>
                ) : (
                  <div className="flex items-stretch gap-1.5 overflow-x-auto">
                    {testLayers.map((l, i) => {
                      const isHil = l.key === "hil";
                      const meta = layerStatusMeta(l.status);
                      return (
                        <div key={l.key} className="flex items-stretch gap-1.5">
                          <div
                            className={`flex-1 min-w-[150px] rounded-lg border px-3 py-2 ${
                              isHil
                                ? "border-[#faad14]/50 bg-[#faad14]/5"
                                : "border-[#1e293b] bg-[#0a0e17]"
                            }`}
                          >
                            <div className="flex items-center gap-1.5 mb-1">
                              <span
                                className={`text-[9px] font-bold px-1 py-0.5 rounded ${
                                  isHil
                                    ? "bg-[#faad14]/15 text-[#faad14]"
                                    : "bg-[#722ed1]/15 text-[#722ed1]"
                                }`}
                              >
                                {l.badge}
                              </span>
                              <span className="text-[11px] font-medium text-[#e2e8f0] truncate">
                                {l.label}
                              </span>
                            </div>
                            <span
                              className="text-[9px] rounded px-1.5 py-0.5 font-medium"
                              style={{
                                color: meta.color,
                                background: `${meta.color}1f`,
                                border: `1px solid ${meta.color}4d`,
                              }}
                            >
                              {meta.label}
                            </span>
                            {isHil && l.commit && (
                              <span className="ml-1 text-[9px] text-[#64748b] font-mono">
                                @{l.commit}
                              </span>
                            )}
                          </div>
                          {i < testLayers.length - 1 && (
                            <div className="flex items-center text-[#334155] text-sm shrink-0">
                              →
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="mt-2 text-[10px] text-[#64748b]">
                  HIL 为独立 CI Layer 2.5（默认 mock 模式），不在 .osh/cache/steps 步骤清单内
                </div>
              </CardContent>
            </Card>

            {/* 工程视角：yuleASR BSW 状态（工程师关注实时编译 / MISRA / 覆盖率） */}
            {perspective === "engineer" && (
              <div className="mt-6">
                <YuleASRStatus />
              </div>
            )}

            {/* Compliance Progress + Coverage side by side — 管理视角 */}
            {perspective === "manage" && (
            <div className="grid lg:grid-cols-3 gap-5 mt-6 mb-6">
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
            )}

            {/* 管理视角：组合视图 & 合规就绪评分（置顶），Loop Engineering 置底 */}
            {perspective === "manage" && (
              <>
                <div className="mt-6">
                  <PortfolioCompliance />
                </div>
                <div className="mt-6">
                  <LoopEngineering />
                </div>
              </>
            )}
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
                <div className="w-px h-5 bg-[#1e293b] mx-0.5" />
                <Button
                  disabled={!selectedGapIds.length}
                  onClick={() => {
                    setBatchMode("analyze");
                    setShowBatchModal(true);
                  }}
                  className="border-[#1e293b] text-[#94a3b8] h-9 text-xs gap-1.5 hover:text-white hover:bg-[#722ed1]/15 disabled:opacity-40"
                  variant="outline"
                >
                  <ListChecks className="w-3.5 h-3.5 text-[#722ed1]" />
                  批量分析
                </Button>
                <Button
                  disabled={!selectedGapIds.length}
                  onClick={() => {
                    setBatchMode("remediate");
                    setShowBatchModal(true);
                  }}
                  className="bg-gradient-to-r from-[#10b981] to-[#1677ff] text-white h-9 text-xs gap-1.5 disabled:opacity-50 shadow-lg shadow-[#10b981]/20"
                >
                  <Play className="w-3.5 h-3.5" />
                  批量修复
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

            {/* 运行历史（头脑风暴项④）：前端本地记录，按项目展示，可回看/清空。 */}
            <Card className="border-[#1e293b] bg-[#111827] mb-4">
              <button
                onClick={() => setRunsOpen((v) => !v)}
                className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-[#1e293b]/40 transition-colors"
              >
                <span className="flex items-center gap-2 text-sm font-bold text-[#e2e8f0]">
                  <History className="w-4 h-4 text-[#722ed1]" />
                  运行历史
                  <span className="text-[10px] font-normal px-1.5 py-0.5 rounded bg-[#722ed1]/15 text-[#a78bfa]">
                    {gapRuns.length} 条
                  </span>
                  <span className="text-[10px] font-normal text-[#64748b]">
                    本地记录 · 刷新可回看
                  </span>
                </span>
                <div className="flex items-center gap-2">
                  {gapRuns.length > 0 && (
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        if (
                          window.confirm(
                            `确定清空当前项目（${selectedProjectObj?.name || selectedProject}）的全部运行历史吗？`,
                          )
                        ) {
                          clearGapRuns(selectedProject);
                          setGapRuns([]);
                        }
                      }}
                      className="flex items-center gap-1 text-[11px] text-[#94a3b8] hover:text-[#ff4d4f] px-2 py-1 rounded hover:bg-[#ff4d4f]/5 cursor-pointer"
                      title="清空当前项目运行历史"
                    >
                      <Trash2 className="w-3 h-3" />
                      清空
                    </span>
                  )}
                  {runsOpen ? (
                    <ChevronUp className="w-4 h-4 text-[#64748b]" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-[#64748b]" />
                  )}
                </div>
              </button>
              {runsOpen && (
                <div className="border-t border-[#1e293b] px-4 py-3">
                  {gapRuns.length === 0 ? (
                    <div className="text-center py-6 text-xs text-[#64748b]">
                      暂无运行记录 — 执行「批量分析 / 批量修复」后会出现在这里
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {gapRuns.map((r) => {
                        const sm = runStatusMeta(r.status);
                        const mm = runModeMeta(r.mode);
                        return (
                          <div
                            key={r.id}
                            className="flex items-center justify-between gap-3 rounded-lg border border-[#1e293b] bg-[#0a0e17]/40 px-3 py-2"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className="text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0"
                                style={{
                                  color: mm.color,
                                  background: `${mm.color}14`,
                                  border: `1px solid ${mm.color}30`,
                                }}
                              >
                                {mm.label}
                              </span>
                              <span className="text-xs text-[#94a3b8] shrink-0">
                                {r.count} 项
                              </span>
                              <span
                                className="text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0"
                                style={{
                                  color: sm.color,
                                  background: `${sm.color}14`,
                                  border: `1px solid ${sm.color}30`,
                                }}
                              >
                                {sm.label}
                              </span>
                              {r.batchId && (
                                <span className="text-[10px] font-mono text-[#64748b] truncate">
                                  #{r.batchId.slice(0, 8)}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-1 text-[10px] text-[#64748b] shrink-0">
                              <Clock className="w-3 h-3" />
                              {formatRunTime(r.startedAt)}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </Card>

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
                          <th className="w-10 py-3 px-3 text-center">
                            <input
                              type="checkbox"
                              className="accent-[#722ed1] w-4 h-4 cursor-pointer"
                              checked={
                                displayGapItems.length > 0 &&
                                displayGapItems.every((i) => selectedGapIds.includes(i.id))
                              }
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedGapIds((prev) =>
                                    Array.from(
                                      new Set([...prev, ...displayGapItems.map((i) => i.id)])
                                    )
                                  );
                                } else {
                                  const cur = new Set(displayGapItems.map((i) => i.id));
                                  setSelectedGapIds((prev) => prev.filter((id) => !cur.has(id)));
                                }
                              }}
                              aria-label="全选"
                            />
                          </th>
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
                          <th className="text-right py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                            操作
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayGapItems.map((item, idx) => (
                          <tr
                            key={item.id}
                            className={`border-b border-[#1e293b] hover:bg-[#1e293b]/50 transition-colors cursor-pointer ${
                              idx % 2 === 0 ? "bg-[#0a0e17]/30" : ""
                            }`}
                            onClick={() => {
                              setSelectedGapId(item.id);
                              setShowGapDetail(true);
                            }}
                          >
                            <td
                              className="py-3 px-3 text-center"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                type="checkbox"
                                className="accent-[#722ed1] w-4 h-4 cursor-pointer"
                                checked={selectedGapIds.includes(item.id)}
                                onChange={(e) =>
                                  setSelectedGapIds((prev) =>
                                    e.target.checked
                                      ? Array.from(new Set([...prev, item.id]))
                                      : prev.filter((id) => id !== item.id)
                                  )
                                }
                                aria-label={`选择 ${item.id}`}
                              />
                            </td>
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
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 font-medium"
                                style={{
                                  background: `${gapStatusColor(item.status)}14`,
                                  color: gapStatusColor(item.status),
                                  borderColor: `${gapStatusColor(item.status)}30`,
                                }}
                              >
                                {gapStatusLabel(item.status)}
                              </Badge>
                            </td>
                            <td className="py-3 px-4 text-xs text-[#64748b] hidden lg:table-cell max-w-xs">
                              <span className="line-clamp-2">{item.suggestion || "-"}</span>
                            </td>
                            <td className="py-3 px-4 text-right">
                              <div className="inline-flex items-center gap-1.5">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-7 px-2 text-[11px] text-[#94a3b8] hover:text-white hover:bg-[#722ed1]/15"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedGapId(item.id);
                                    setShowGapDetail(true);
                                  }}
                                >
                                  <Search className="w-3 h-3 mr-1" />
                                  分析
                                </Button>
                                <Button
                                  size="sm"
                                  className="h-7 px-2 text-[11px] bg-gradient-to-r from-[#10b981] to-[#1677ff] text-white disabled:opacity-50"
                                  disabled={item.status === "completed"}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedGapId(item.id);
                                    setShowGapDetail(true);
                                  }}
                                >
                                  <Play className="w-3 h-3 mr-1" />
                                  运行
                                </Button>
                              </div>
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

      {/* Gap detail modal (per-item 分析 / 运行) */}
      <GapDetailModal
        open={showGapDetail}
        gapId={selectedGapId}
        onClose={() => {
          setShowGapDetail(false);
          setSelectedGapId(null);
        }}
        onRunComplete={() => {
          // Refresh the gap list so the row reflects the new status.
          // Use a tiny delay so the in-memory override is fully written
          // (the server marks the gap "in_progress" synchronously on POST
          // and "completed" inside the background thread).
          setTimeout(() => {
            void loadGapAnalysis(selectedProject, 1, gapSeverity);
          }, 300);
        }}
      />

      {/* Create project modal (方案 B: 内联创建，替代空占位的 CLI 指引按钮) */}
      <CreateProjectModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleCreated}
      />

      <DemoGalleryModal
        open={showDemoGallery}
        onClose={() => setShowDemoGallery(false)}
        existingSlugs={demoLoadedSlugs}
        onLoaded={handleDemoLoaded}
      />

      <LLMSettingsModal
        open={showLLMSettings}
        current={llmCfg}
        onClose={() => setShowLLMSettings(false)}
        onSaved={(cfg) => {
          setLlmCfg(cfg);
          // 刷新当前模型显示
          setMyUsage((prev: any) => (prev ? { ...prev, current_model: cfg.model || cfg.provider || prev.current_model } : prev));
        }}
      />

      {/* Gap batch modal (bulk analyze / remediate) */}
      <GapBatchModal
        open={showBatchModal}
        mode={batchMode}
        gapIds={selectedGapIds}
        projectId={selectedProject}
        onClose={() => {
          setShowBatchModal(false);
          // 运行历史（项④）：关闭弹窗时刷新（覆盖修复失败等 onComplete 不触发的情形）。
          setGapRuns(listGapRuns(selectedProject));
        }}
        onComplete={() => {
          void loadGapAnalysis(selectedProject, 1, gapSeverity);
          setGapRuns(listGapRuns(selectedProject));
          setSelectedGapIds([]);
        }}
      />
    </>
  );
}

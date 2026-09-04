"use client";

import { apiFetch } from "@/lib/api-fetch";

import { marked } from "marked";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookMarked,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Cpu,
  Download,
  Eye,
  FileText,
  FlaskConical,
  FolderOpen,
  Info,
  LayoutDashboard,
  ListChecks,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Square,
  Workflow,
} from "lucide-react";
// 导航（顶栏/左栏）由 dashboard/layout 统一渲染，页面只提供内容

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// ─── 勾选选择持久化（localStorage） ──────────────────────────────────────────
const LS_SELECTED_KEY = "yuleosh:pipeline:selected";

function loadSavedSelection(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LS_SELECTED_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function persistSelected(set: Set<string>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_SELECTED_KEY, JSON.stringify(Array.from(set)));
  } catch {
    /* 忽略写入失败（隐私模式等） */
  }
}

// ── Markdown 安全渲染 ─────────────────────────────────────────
// 把 ASPICE 文档 .md 转成 HTML，并剔除能触发 XSS 的危险模式（<script>/<iframe>/
// <object>/<embed>/<form>/on*= attrs/javascript: URLs/内联 <style>）。
// 内容来源是受信任的 pipeline 产物，但仍做防御性 sanitize。
function renderMarkdownSafe(content: string): string {
  const html = marked.parse(content, { gfm: false, breaks: false }) as string;
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, "")
    .replace(/<iframe\b[^>]*\/?>(?:<\/iframe>)?/gi, "")
    .replace(/<object\b[^>]*\/?>(?:<\/object>)?/gi, "")
    .replace(/<embed\b[^>]*\/?>/gi, "")
    .replace(/<form\b[^>]*\/?>(?:<\/form>)?/gi, "")
    .replace(/\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/(href|src)\s*=\s*"\s*javascript:[^"]*"/gi, '$1="#"')
    .replace(/javascript:/gi, "");
}

// ─── Types ───────────────────────────────────────────────────────────────────

interface PipelineItem {
  name: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  spec_path?: string;
  step_count?: number;
  backend?: string;
}

interface PipelineProject {
  name: string;
  path: string;
  pipelines: PipelineItem[];
  count: number;
}

interface PipelineListResponse {
  pipelines: PipelineItem[];
  projects: PipelineProject[];
  runnable_projects?: { name: string; path: string; spec: string }[];
  count: number;
  note?: string | null;
}

interface ArtifactFile {
  path: string;
  name: string;
  size: number;
  ext: string;
}

interface ArtifactRun {
  run_id: string;
  name: string;
  status: string;
  project_dir?: string;
  files: ArtifactFile[];
}

interface ArtifactsListResponse {
  runs: ArtifactRun[];
  count: number;
  total_groups?: number;
  view?: "all" | "latest-per-project";
  note?: string | null;
}

interface ArtifactPreviewResponse {
  run_id: string;
  file: string;
  name: string;
  size: number;
  ext: string;
  content: string;
  truncated: boolean;
  note?: string | null;
}

interface PreviewState {
  runId: string;
  file: string;
  data: ArtifactPreviewResponse | null;
  loading: boolean;
}

interface StepRecord {
  step_id: string;
  name: string;
  agent: string;
  status: "pending" | "running" | "passed" | "failed" | "skipped" | string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_s?: number | null;
  error?: string | null;
  output_path?: string | null;
}

interface CheckpointSnapshot {
  state?: {
    pipeline_name?: string;
    status?: string;
    updated_at?: string | null;
  } | null;
  steps: StepRecord[];
  op_active: boolean;
  count: number;
}

// ─── T9 证据包 ───────────────────────────────────────────────────────────────

interface EvidenceArtifact {
  step_id: string;
  name: string;
  status: string;
  path: string;
  size: number;
  exists: boolean;
}

interface EvidencePackage {
  run_id: string;
  op: string;
  mode: string;
  status: string;
  started_at: string;
  finished_at: string;
  step_count: number;
  step_passed: number;
  step_failed: number;
  step_skipped: number;
  artifact_count: number;
  artifact_available: number;
  total_size: number;
  artifacts: EvidenceArtifact[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────


function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function formatDate(dateStr?: string): string {
  if (!dateStr || dateStr === "-") return "-";
  try {
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return dateStr;
    return d.toLocaleString("zh-CN", {
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

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function pipelineStatusMeta(status: string): { label: string; color: string } {
  const s = (status || "").toLowerCase();
  if (["completed", "success", "done", "passed", "succeeded"].includes(s)) {
    return { label: status || "completed", color: "#10b981" };
  }
  if (["running", "in_progress", "processing", "active", "executing"].includes(s)) {
    return { label: status || "running", color: "#1677ff" };
  }
  if (["failed", "error", "cancelled", "canceled", "aborted"].includes(s)) {
    return { label: status || "failed", color: "#ff4d4f" };
  }
  if (["pending", "queued", "waiting", "paused", "stopped", "idle"].includes(s)) {
    return { label: status || "pending", color: "#faad14" };
  }
  return { label: status || "unknown", color: "#64748b" };
}

const STEP_STATUS_META: Record<
  string,
  { label: string; color: string; symbol: string; ring: string }
> = {
  pending: { label: "待运行", color: "#475569", symbol: "○", ring: "#1e293b" },
  running: { label: "运行中", color: "#1677ff", symbol: "◐", ring: "#1677ff" },
  passed: { label: "已通过", color: "#10b981", symbol: "✓", ring: "#10b981" },
  failed: { label: "失败", color: "#ff4d4f", symbol: "✗", ring: "#ff4d4f" },
  skipped: { label: "已跳过", color: "#faad14", symbol: "⊘", ring: "#faad14" },
};

function stepMeta(status: string) {
  const key = (status || "").toLowerCase();
  return STEP_STATUS_META[key] ?? STEP_STATUS_META.pending;
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

// Navigation is rendered by the shared TopNav component
// (see src/components/dashboard/top-nav.tsx).

// ─── Page ────────────────────────────────────────────────────────────────────

export default function PipelinePage() {

  const [pipelines, setPipelines] = useState<PipelineItem[]>([]);
  const [projects, setProjects] = useState<PipelineProject[]>([]);
  const [listNote, setListNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [artifactData, setArtifactData] = useState<Record<string, ArtifactsListResponse | null>>({});
  const [artifactLoading, setArtifactLoading] = useState<Record<string, boolean>>({});
  const [artifactError, setArtifactError] = useState<Record<string, string>>({});

  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [previewError, setPreviewError] = useState("");

  // ── .md 文件就地展开渲染（在左侧 run 的文件列表里直接看 markdown 渲染）──
  // key = `${runId}::${filePath}`；与右侧 "产出物预览"（预览纯文本/JSON 等）共用
  // 同一个 /api/v1/artifacts/preview 端点，但走不同 state，避免覆盖用户当前打开
  // 的右侧面板大视图。
  const [expandedMdKeys, setExpandedMdKeys] = useState<Set<string>>(new Set());
  const [mdPreviewCache, setMdPreviewCache] = useState<Record<string, ArtifactPreviewResponse>>({});
  const [mdPreviewLoading, setMdPreviewLoading] = useState<Set<string>>(new Set());
  const [mdPreviewError, setMdPreviewError] = useState<Record<string, string>>({});

  // ── Pipeline 运行控制（重跑 / 选中某几项 / 续跑 / 停止）──
  const [steps, setSteps] = useState<{ index: number; key: string; agent: string; name: string }[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [allChecked, setAllChecked] = useState(true);
  const [opRunning, setOpRunning] = useState(false);
  const [opMsg, setOpMsg] = useState("");
  const [stepPanelOpen, setStepPanelOpen] = useState(true);

  // ── 运行过程看板（轮询 checkpoint）──
  const [checkpoint, setCheckpoint] = useState<CheckpointSnapshot | null>(null);
  const [checkpointError, setCheckpointError] = useState("");
  const [runs, setRuns] = useState<any[]>([]); // 历史运行列表
  const [activeRunId, setActiveRunId] = useState<string | null>(null); // null=最新
  // T9：证据包（每次运行一条：执行记录 + 产物，可打包下载）
  const [evidence, setEvidence] = useState<EvidencePackage[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // ── 一键运行 Demo 项目（后端编排器，真实 LLM 全链） ──
  const [runnableProjects, setRunnableProjects] = useState<{ name: string; path: string; spec: string }[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [currentRun, setCurrentRun] = useState<{ run_id: string; name: string; status: string; session_dir: string } | null>(null);
  const [runArtifacts, setRunArtifacts] = useState<ArtifactsListResponse | null>(null);
  const [runArtifactsLoading, setRunArtifactsLoading] = useState(false);
  // 视图模式：默认「按项目最新一次」, 取消勾选切换到「全部历史」(向后兼容)
  const [showAllRuns, setShowAllRuns] = useState(false);
  const runPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasRunRef = useRef(false); // 用户曾经点过运行/续跑/停止才轮询
  const [isPolling, setIsPolling] = useState(false); // 看板是否正在轮询（用于锁定勾选）
  // T10：SSE 长连接（服务端只在状态变化时推 event）；不可用时自动退回轮询
  const esRef = useRef<EventSource | null>(null);
  const sseFailedRef = useRef(false);

  // pipeline 运行中：提交中 / 正在轮询 / 后端 op_active
  const pipelineRunning = opRunning || isPolling || (checkpoint?.op_active ?? false);

  // T10：关闭 SSE 长连接
  const stopStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    stopStream(); // 同时收掉 SSE（切历史运行 / 组件卸载时）
    setIsPolling(false);
  }, [stopStream]);

  // 看板所有端点都必须带上当前选中项目的 project_dir：
  // CheckpointEngine 把状态写到 <project_dir>/.yuleosh/checkpoint-state.db，
  // 不带该参数时后端回退 OSH_HOME 根目录 → 读到仓库根的 checkpoint-state.db
  // （陈旧），表现为「点了运行但看板一直是上一次的旧状态」。
  const pdq = useMemo(
    () => (selectedProject ? `&project_dir=${encodeURIComponent(selectedProject)}` : ""),
    [selectedProject]
  );

  // 拉取历史运行列表（看板「运行历史」下拉）
  const loadRuns = useCallback(async () => {
    try {
      const res = await apiFetch<{ runs: any[] }>(
        `/api/v1/pipeline/checkpoint/runs?pipeline=agent-pipeline${pdq}`
      );
      setRuns(res.runs || []);
    } catch {
      /* 忽略：历史列表为增强项，失败不影响看板 */
    }
  }, [pdq]);

  // T9：拉取证据包列表
  const loadEvidence = useCallback(async () => {
    setEvidenceLoading(true);
    try {
      const res = await apiFetch<{ packages: EvidencePackage[] }>(
        `/api/v1/pipeline/evidence?pipeline=agent-pipeline${pdq}`
      );
      setEvidence(res.packages || []);
    } catch {
      setEvidence([]);
    } finally {
      setEvidenceLoading(false);
    }
  }, [pdq]);

  const fetchCheckpoint = useCallback(async () => {
    try {
      const res = await apiFetch<CheckpointSnapshot>(
        `/api/v1/pipeline/checkpoint?pipeline=agent-pipeline${pdq}`
      );
      setCheckpoint(res);
      setCheckpointError("");
      // 终止条件：无 op_active 且没有 running 中步骤
      const stillRunning = (res.steps || []).some((s) => (s.status || "").toLowerCase() === "running");
      if (!res.op_active && !stillRunning && pollRef.current) {
        stopPolling();
        void loadRuns(); // 运行结束 → 刷新历史列表
        void loadEvidence(); // 同步刷新证据包
      }
    } catch (err) {
      setCheckpointError(errMessage(err));
    }
  }, [pdq, stopPolling, loadRuns, loadEvidence]);

  // 切换到某次历史运行查看（静态快照，不再轮询）；null 回到最新
  const viewRun = useCallback(
    (id: string | null) => {
      setActiveRunId(id);
      stopPolling();
      if (!id) {
        void fetchCheckpoint();
        return;
      }
      void (async () => {
        try {
          const res = await apiFetch<CheckpointSnapshot>(
            `/api/v1/pipeline/checkpoint?run_id=${id}${pdq}`
          );
          setCheckpoint(res);
          setCheckpointError("");
        } catch (err) {
          setCheckpointError(errMessage(err));
        }
      })();
    },
    [fetchCheckpoint, stopPolling]
  );

  // 轮询兜底（SSE 不可用时使用）
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    setIsPolling(true);
    void fetchCheckpoint();
    pollRef.current = setInterval(() => {
      void fetchCheckpoint();
    }, 1500);
  }, [fetchCheckpoint]);

  // T10：优先用 SSE 接收服务端推送（只在状态变化时来包），失败才退回轮询
  const startStream = useCallback(() => {
    if (esRef.current || pollRef.current) return;
    if (sseFailedRef.current || typeof EventSource === "undefined") {
      startPolling();
      return;
    }
    setIsPolling(true);
    try {
      const es = new EventSource(
        `/api/v1/pipeline/checkpoint/stream?pipeline=agent-pipeline${pdq}`
      );
      esRef.current = es;

      es.addEventListener("checkpoint", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data) as CheckpointSnapshot;
          if (!data || (data as unknown as { ok?: boolean }).ok === false) return;
          setCheckpoint(data);
          setCheckpointError("");
          const stillRunning = (data.steps || []).some(
            (s) => (s.status || "").toLowerCase() === "running"
          );
          if (!data.op_active && !stillRunning) {
            // 运行结束：收流 + 刷新历史列表与证据包
            stopStream();
            setIsPolling(false);
            void loadRuns();
            void loadEvidence();
          }
        } catch {
          /* 忽略单次解析错误，等下一帧 */
        }
      });

      es.addEventListener("runs", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data) as { runs: any[] };
          if (data && Array.isArray(data.runs)) setRuns(data.runs);
        } catch {
          /* 忽略 */
        }
      });

      es.onerror = () => {
        // 连接失败 / 被代理缓冲掐断 → 关流并退回轮询（本次会话不再重试 SSE）
        stopStream();
        sseFailedRef.current = true;
        startPolling();
      };
    } catch {
      stopStream();
      sseFailedRef.current = true;
      startPolling();
    }
  }, [pdq, startPolling, stopStream, loadRuns, loadEvidence]);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // 挂载即拉一次 checkpoint + 历史列表 + 证据包：刷新后也能看到上次运行结果
  useEffect(() => {
    void fetchCheckpoint();
    void loadRuns();
    void loadEvidence();
  }, [fetchCheckpoint, loadRuns, loadEvidence]);

  // ── Load pipeline list ────────────────────────────────────────────────────
  const loadPipelines = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<PipelineListResponse>("/api/v1/pipeline/list");
      setPipelines(res.pipelines || []);
      setProjects(res.projects || []);
      setRunnableProjects(res.runnable_projects || []);
      setListNote(res.note ?? null);
    } catch (err) {
      setError(errMessage(err));
      setPipelines([]);
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPipelines();
  }, [loadPipelines]);

  // 拉取真实 pipeline steps（用于勾选重跑）
  useEffect(() => {
    void (async () => {
      try {
        const res = await apiFetch<any>("/api/v1/pipeline/steps");
        const list = (res?.steps || []) as { index: number; key: string; agent: string; name: string }[];
        setSteps(list);
        // 从 localStorage 恢复勾选（与当前步骤求交集），否则默认全选
        const saved = loadSavedSelection();
        const restored =
          saved.length > 0
            ? new Set(list.map((s) => s.key).filter((k) => saved.includes(k)))
            : new Set(list.map((s) => s.key));
        setSelected(restored);
        setAllChecked(restored.size === list.length);
        persistSelected(restored);
      } catch {
        /* 步骤列表不可用时静默，不阻塞页面 */
      }
    })();
  }, []);

  // ── Project name for artifacts query (fallback: pipeline name) ───────────
  const projectNameFor = useCallback(
    (pipelineName: string): string => {
      const proj = projects.find((p) => p.pipelines.some((pp) => pp.name === pipelineName));
      return proj?.name || pipelineName;
    },
    [projects]
  );

  // ── Expand row → fetch artifact tree ─────────────────────────────────────
  const toggleExpand = useCallback(
    async (pipelineName: string) => {
      const isOpen = !!expanded[pipelineName];
      setExpanded((prev) => ({ ...prev, [pipelineName]: !isOpen }));

      if (!isOpen && artifactData[pipelineName] === undefined && !artifactLoading[pipelineName]) {
        const project = projectNameFor(pipelineName);
        setArtifactLoading((prev) => ({ ...prev, [pipelineName]: true }));
        setArtifactError((prev) => ({ ...prev, [pipelineName]: "" }));
        try {
          const res = await apiFetch<ArtifactsListResponse>(
            `/api/v1/artifacts/list?project=${encodeURIComponent(project)}`
          );
          setArtifactData((prev) => ({ ...prev, [pipelineName]: res }));
        } catch (err) {
          setArtifactError((prev) => ({ ...prev, [pipelineName]: errMessage(err) }));
          setArtifactData((prev) => ({ ...prev, [pipelineName]: null }));
        } finally {
          setArtifactLoading((prev) => ({ ...prev, [pipelineName]: false }));
        }
      }
    },
    [artifactData, artifactLoading, expanded, projectNameFor]
  );

  // ── Click file → preview in right panel ──────────────────────────────────
  const handlePreview = useCallback(async (runId: string, filePath: string) => {
    setPreview({ runId, file: filePath, data: null, loading: true });
    setPreviewError("");
    try {
      const res = await apiFetch<ArtifactPreviewResponse>(
        `/api/v1/artifacts/preview?run=${encodeURIComponent(runId)}&file=${encodeURIComponent(filePath)}`
      );
      setPreview({ runId, file: filePath, data: res, loading: false });
    } catch (err) {
      setPreviewError(errMessage(err));
      setPreview({ runId, file: filePath, data: null, loading: false });
    }
  }, []);

  // ── .md 文件就地展开（点 row → 列表内 inline 渲染 markdown）──────────────
  // 与 handlePreview（右侧大面板纯文本）互不影响：.md 走这里、其他 ext 走
  // 右侧大面板。展开后若没缓存就 fetch 一次；切换折叠/再展开不会重复打。
  const toggleMdPreview = useCallback(async (runId: string, filePath: string) => {
    const key = `${runId}::${filePath}`;
    let shouldFetch = false;
    setExpandedMdKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
        shouldFetch = !mdPreviewCacheRef.current[key];
      }
      return next;
    });
    if (!shouldFetch) return;
    setMdPreviewLoading((prev) => {
      const n = new Set(prev);
      n.add(key);
      return n;
    });
    try {
      const res = await apiFetch<ArtifactPreviewResponse>(
        `/api/v1/artifacts/preview?run=${encodeURIComponent(runId)}&file=${encodeURIComponent(filePath)}`
      );
      setMdPreviewCache((prev) => ({ ...prev, [key]: res }));
      setMdPreviewError((prev) => {
        const { [key]: _drop, ...rest } = prev;
        void _drop;
        return rest;
      });
    } catch (err) {
      setMdPreviewError((prev) => ({ ...prev, [key]: errMessage(err) }));
    } finally {
      setMdPreviewLoading((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
    }
  }, []);
  // 让 callback 在不变 (==[]) 的同时仍读得到最新 cache —— 一个常规 ref 桥
  const mdPreviewCacheRef = useRef(mdPreviewCache);
  useEffect(() => {
    mdPreviewCacheRef.current = mdPreviewCache;
  }, [mdPreviewCache]);

  // ── 运行控制 ──────────────────────────────────────────────────────────────
  const toggleStep = useCallback((key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      setAllChecked(next.size === steps.length);
      persistSelected(next);
      return next;
    });
  }, [steps.length]);

  const toggleAll = useCallback(() => {
    setAllChecked((prev) => {
      const next = !prev;
      const nextSet = next ? new Set<string>(steps.map((s) => s.key)) : new Set<string>();
      setSelected(nextSet);
      persistSelected(nextSet);
      return next;
    });
  }, [steps]);

  const runControl = useCallback(
    async (action: "run-selected" | "resume" | "stop") => {
      // 看板控制操作必须绑定「一键运行 Demo 项目」下拉里选中的项目：
      // 早期实现 POST 空 body，后端 _resolve_pipeline_ctx 会 fallback 到
      // OSH_HOME（= 仓库根），导致 spec-check 校验的是仓库根的 docs/spec.md
      // （工作文档，自带 60+ issues / 12 ERROR），第一步必然失败且误导。
      if (!selectedProject) {
        setOpMsg("请先在上方「选择项目」下拉中选择一个项目");
        return;
      }
      setOpRunning(true);
      setOpMsg("");
      try {
        const body = JSON.stringify({ project_dir: selectedProject });
        if (action === "resume") {
          const res = await apiFetch<any>("/api/v1/pipeline/resume", {
            method: "POST",
            body,
          });
          setOpMsg(`已提交续跑：${res?.op || "resume"}`);
        } else if (action === "stop") {
          const res = await apiFetch<any>("/api/v1/pipeline/stop", {
            method: "POST",
            body,
          });
          setOpMsg(`已停止：${res?.op || "stop"}`);
        } else {
          const ids = steps.filter((s) => selected.has(s.key)).map((s) => s.key);
          if (ids.length === 0) {
            setOpMsg("请至少勾选一个阶段");
            return;
          }
          const res =
            ids.length === steps.length
              ? await apiFetch<any>("/api/v1/pipeline/rerun", {
                  method: "POST",
                  body: JSON.stringify({ project_dir: selectedProject }),
                })
              : await apiFetch<any>("/api/v1/pipeline/retry", {
                  method: "POST",
                  body: JSON.stringify({ step_ids: ids, project_dir: selectedProject }),
                });
          setOpMsg(`已提交：${res?.op || "ok"}（${ids.length}/${steps.length} 步）`);
        }
        // 提交成功后开始接收实时进度（T10：SSE 推送，不可用则退回轮询）
        hasRunRef.current = true;
        setActiveRunId(null); // 新运行即最新
        void loadRuns();
        void loadEvidence();
        startStream();
      } catch (err) {
        setOpMsg(errMessage(err));
      } finally {
        setOpRunning(false);
      }
    },
    [steps, selected, selectedProject, startStream, loadRuns, loadEvidence]
  );

  // ── 一键运行 Demo 项目：POST /api/v1/pipeline/run（后台编排器） + 产出物轮询 ──
  const loadRunArtifacts = useCallback(async () => {
    setRunArtifactsLoading(true);
    try {
      // 默认按项目聚合（view=latest-per-project），去掉"每一个 commit 列一行"的噪声；
      // 勾选"显示全部历史"切换到 view=all 调试模式。
      const view = showAllRuns ? "all" : "latest-per-project";
      const res = await apiFetch<ArtifactsListResponse>(
        `/api/v1/artifacts/list?view=${view}`
      );
      setRunArtifacts(res);
    } catch {
      setRunArtifacts(null);
    } finally {
      setRunArtifactsLoading(false);
    }
  }, [showAllRuns]);

  const stopRunPoll = useCallback(() => {
    if (runPollRef.current) {
      clearInterval(runPollRef.current);
      runPollRef.current = null;
    }
  }, []);

  const runDemoProject = useCallback(async () => {
    if (!selectedProject) {
      setOpMsg("请先选择一个 Demo 项目");
      return;
    }
    const proj = runnableProjects.find((p) => p.path === selectedProject);
    if (!proj) {
      setOpMsg("项目不存在");
      return;
    }
    setOpRunning(true);
    setOpMsg("");
    try {
      const res = await apiFetch<{ run_id: string; name: string; status: string; session_dir: string }>(
        "/api/v1/pipeline/run",
        { method: "POST", body: JSON.stringify({ spec: proj.spec, project_dir: proj.path, name: proj.name }) }
      );
      setCurrentRun({ run_id: res.run_id, name: res.name, status: res.status, session_dir: res.session_dir });
      setOpMsg(`已启动：${res.name}（${res.run_id}）`);
      void loadRunArtifacts();
      // 运行中每 3s 刷新产出物总览（产物按步落盘）
      stopRunPoll();
      runPollRef.current = setInterval(() => {
        void loadRunArtifacts();
      }, 3000);
    } catch (err) {
      setOpMsg(errMessage(err));
    } finally {
      setOpRunning(false);
    }
  }, [selectedProject, runnableProjects, loadRunArtifacts, stopRunPoll]);

  useEffect(() => {
    return () => stopRunPoll();
  }, [stopRunPoll]);

  const isEmpty = !loading && pipelines.length === 0;

  return (
  <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <Workflow className="w-4.5 h-4.5 text-[#722ed1]" />
              流水线管理
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              Pipeline 运行记录与阶段产出物（展开行查看产出物树，点击文件预览）
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadPipelines()}
            disabled={loading}
            className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>

        {/* ── 运行控制：重跑 / 勾选某几项 / 续跑 / 停止 ── */}
        <Card className="border-[#1e293b] bg-[#111827] mb-4">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <ListChecks className="w-4 h-4 text-[#722ed1]" />
                运行控制
              </CardTitle>
              <button
                type="button"
                onClick={() => setStepPanelOpen((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-[#94a3b8] hover:text-white transition-colors select-none"
              >
                {stepPanelOpen ? "收起" : "展开选择"}
                {stepPanelOpen ? (
                  <ChevronDown className="w-3.5 h-3.5" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
            <CardDescription className="text-xs text-[#64748b] mt-1">
              {stepPanelOpen
                ? "勾选要运行的阶段（默认全选）；可只跑选中的几项，其余标记为跳过"
                : "已收起阶段选择；展开后可勾选特定阶段，或直接点击下方按钮运行/续跑/停止"}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {stepPanelOpen && (
              <div className="mb-3 relative">
                <label
                  className={`flex items-center gap-1.5 text-xs select-none mb-2 ${
                    pipelineRunning ? "text-[#64748b] cursor-not-allowed" : "text-[#94a3b8] cursor-pointer"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={allChecked}
                    disabled={pipelineRunning}
                    onChange={() => void toggleAll()}
                    className="accent-[#722ed1] w-3.5 h-3.5"
                  />
                  全选
                </label>
                {steps.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {steps.map((s) => (
                      <label
                        key={s.key}
                        className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                          pipelineRunning ? "cursor-not-allowed opacity-60" : "cursor-pointer"
                        } ${
                          selected.has(s.key)
                            ? "border-[#722ed1]/50 bg-[#722ed1]/10 text-[#e2e8f0]"
                            : "border-[#1e293b] bg-[#0a0e17] text-[#64748b]"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selected.has(s.key)}
                          disabled={pipelineRunning}
                          onChange={() => void toggleStep(s.key)}
                          className="accent-[#722ed1] w-3.5 h-3.5 shrink-0"
                        />
                        <span className="font-mono text-[10px] opacity-60">{s.key}</span>
                        <span className="truncate">{s.name}</span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-[#64748b]">加载阶段列表…</div>
                )}
                {pipelineRunning && (
                  <div className="absolute inset-0 flex items-start justify-end rounded-md bg-[#0a0e17]/50 pointer-events-none">
                    <span className="mt-1 mr-1 text-[10px] text-[#94a3b8]">运行中 · 选择已锁定</span>
                  </div>
                )}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                className="bg-[#0a0e17] border border-[#1e293b] rounded px-2 py-1.5 text-[#e2e8f0] text-xs max-w-[320px]"
                aria-label="选择项目"
              >
                <option value="">选择项目…</option>
                {runnableProjects.map((p) => (
                  <option key={p.path} value={p.path}>{p.name}</option>
                ))}
              </select>
              <Button
                size="sm"
                onClick={() => void runDemoProject()}
                disabled={opRunning || !selectedProject}
                className="bg-[#722ed1] hover:bg-[#8b5cf6] text-white"
                title="用编排器（真实 LLM 全链）异步跑选中的项目，产物同步到下方「产出物总览」"
              >
                <Play className="w-3.5 h-3.5" />
                一键运行
              </Button>
              <Button
                size="sm"
                onClick={() => void runControl("run-selected")}
                disabled={opRunning}
                className="bg-[#722ed1] hover:bg-[#8b5cf6] text-white"
              >
                <Play className="w-3.5 h-3.5" />
                运行选中
              </Button>
              <Button
                size="sm"
                onClick={() => void runControl("resume")}
                disabled={opRunning}
                className="bg-[#faad14] hover:bg-[#ffc53d] text-[#0a0e17]"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${opRunning ? "animate-spin" : ""}`} />
                续跑
              </Button>
              <Button
                size="sm"
                onClick={() => void runControl("stop")}
                disabled={opRunning}
                className="bg-[#ff4d4f] hover:bg-[#ff7875] text-white"
              >
                <Square className="w-3.5 h-3.5" />
                停止
              </Button>
              {runnableProjects.length === 0 && (
                <span className="text-xs text-[#64748b]">未发现可运行项目（需含 docs/spec.md）</span>
              )}
              {opMsg && (
                <span
                  className={`text-xs ml-1 ${
                    opMsg.startsWith("已停止")
                      ? "text-[#ff4d4f]"
                      : opMsg.startsWith("已提交续跑")
                      ? "text-[#faad14]"
                      : opMsg.startsWith("已提交")
                      ? "text-[#722ed1]"
                      : "text-[#94a3b8]"
                  }`}
                >
                  {opMsg}
                </span>
              )}
            </div>
            {currentRun && (
              <div className="mt-2 text-xs text-[#94a3b8]">
                当前运行：<span className="text-[#e2e8f0] font-mono">{currentRun.name}</span>
                （{currentRun.run_id}）· 状态 <span className="text-[#722ed1]">{currentRun.status}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── 运行过程看板（轮询 checkpoint） ── */}
        <CheckpointPanel
          snapshot={checkpoint}
          polling={isPolling}
          error={checkpointError}
          stepDefs={steps}
          selectedKeys={selected}
          runs={runs}
          activeRunId={activeRunId}
          onSelectRun={viewRun}
        />

        {/* T9：证据包历史 + 下载 */}
        <EvidencePanel
          packages={evidence}
          loading={evidenceLoading}
          onRefresh={() => void loadEvidence()}
        />

        {/* ── 产出物总览（一键运行 / 编排器 .osh/sessions） ── */}
        <Card className="border-[#1e293b] bg-[#111827] mb-4">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <FolderOpen className="w-4 h-4 text-[#722ed1]" />
                {showAllRuns ? "产出物总览（历史全部）" : "项目最新一次运行"}
                {!runArtifactsLoading && runArtifacts && (
                  <span className="text-xs font-normal text-[#64748b]">
                    共{" "}
                    {showAllRuns
                      ? `${runArtifacts.count} 个运行`
                      : `${runArtifacts.count} 个项目`}
                    {runArtifacts.total_groups != null && runArtifacts.total_groups !== runArtifacts.count && !showAllRuns && (
                      <span className="text-[#475569]"> · 历史 {runArtifacts.total_groups} 个组</span>
                    )}
                  </span>
                )}
              </CardTitle>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1.5 text-[10px] text-[#64748b] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={showAllRuns}
                    onChange={async (e) => {
                      const v = e.target.checked;
                      setShowAllRuns(v);
                      // 切换视图后立刻重拉一次（不依赖轮询周期）
                      try {
                        setRunArtifactsLoading(true);
                        const res = await apiFetch<ArtifactsListResponse>(
                          `/api/v1/artifacts/list?view=${v ? "all" : "latest-per-project"}`
                        );
                        setRunArtifacts(res);
                      } catch {
                        /* 忽略：UI 已显示旧数据 */
                      } finally {
                        setRunArtifactsLoading(false);
                      }
                    }}
                    className="w-3 h-3 accent-[#722ed1]"
                  />
                  显示全部历史
                </label>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void loadRunArtifacts()}
                  disabled={runArtifactsLoading}
                  className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${runArtifactsLoading ? "animate-spin" : ""}`} />
                  刷新
                </Button>
              </div>
            </div>
            <CardDescription className="text-xs text-[#64748b]">
              {showAllRuns
                ? "所有编排器运行会话（.osh/sessions）历史全量列出 —— 调试模式"
                : "每个项目（按磁盘 project_dir 分组）仅显示最新一次运行的 ASPICE 文档证据"}
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {runArtifacts && runArtifacts.runs.length > 0 ? (
              <div className="divide-y divide-[#1e293b]/60">
                {runArtifacts.runs.map((run) => {
                  const pdir = run.project_dir || "";
                  const pdirName = pdir
                    ? pdir.replace(/\/+$/, "").split("/").filter(Boolean).pop() || pdir
                    : "";
                  return (
                  <div key={run.run_id} className="px-4 py-3">
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="w-3.5 h-3.5 text-[#1677ff]" />
                      <span className="text-xs text-[#e2e8f0] font-medium truncate">{run.name || run.run_id}</span>
                      {pdirName && (
                        <span
                          className="text-[10px] text-[#94a3b8] font-mono truncate max-w-[280px]"
                          title={pdir}
                        >
                          {pdirName}
                        </span>
                      )}
                      <span className="text-[10px] text-[#64748b] font-mono">{run.run_id}</span>
                      <Badge
                        variant="outline"
                        className="ml-auto border-transparent"
                        style={{
                          color: pipelineStatusMeta(run.status).color,
                          background: `${pipelineStatusMeta(run.status).color}1f`,
                          borderColor: `${pipelineStatusMeta(run.status).color}4d`,
                        }}
                      >
                        {run.status}
                      </Badge>
                    </div>
                    {run.files.length === 0 ? (
                      <div className="text-xs text-[#64748b] pl-5">该运行暂无 ASPICE 文档证据（仅产出物是 .json/.yaml 等中间产物，已过滤）</div>
                    ) : (
                      <div className="space-y-1 pl-5">
                        {run.files.map((f) => {
                          const key = `${run.run_id}::${f.path}`;
                          const expanded = expandedMdKeys.has(key);
                          const cached = mdPreviewCache[key];
                          const loading = mdPreviewLoading.has(key);
                          const errMd = mdPreviewError[key];
                          const isMd = (f.ext || "").toLowerCase() === "md";
                          return (
                            <div key={f.path} className="rounded">
                              <button
                                onClick={() => {
                                  if (isMd) void toggleMdPreview(run.run_id, f.path);
                                  else void handlePreview(run.run_id, f.path);
                                }}
                                className="w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs hover:bg-[#1e293b]/50 rounded transition-all cursor-pointer"
                                title={isMd ? "点击就地展开 markdown 渲染" : "点击右侧面板预览"}
                              >
                                {isMd ? (
                                  expanded ? (
                                    <ChevronDown className="w-3.5 h-3.5 text-[#94a3b8] shrink-0" />
                                  ) : (
                                    <ChevronRight className="w-3.5 h-3.5 text-[#94a3b8] shrink-0" />
                                  )
                                ) : (
                                  <FileText className="w-3.5 h-3.5 text-[#94a3b8] shrink-0" />
                                )}
                                <span className="text-[#e2e8f0] truncate flex-1">{f.name}</span>
                                {f.ext && (
                                  <span className="text-[10px] uppercase text-[#722ed1] border border-[#722ed1]/30 rounded px-1 py-0.5 shrink-0">
                                    {f.ext}
                                  </span>
                                )}
                                <span className="text-[#64748b] shrink-0">{formatSize(f.size)}</span>
                                <Eye className="w-3.5 h-3.5 text-[#475569] shrink-0" />
                              </button>
                              {expanded && isMd && (
                                <div className="mt-1 mb-2 ml-4 mr-2 rounded border border-[#1e293b] bg-[#0a0e17]/80 px-4 py-3 text-xs">
                                  {errMd ? (
                                    <div className="rounded bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-2 py-1 text-[11px] text-[#ff4d4f] flex items-center gap-1">
                                      <AlertCircle className="w-3 h-3 shrink-0" />
                                      {errMd}
                                    </div>
                                  ) : !cached ? (
                                    <div className="flex items-center justify-center py-6 text-[#64748b]">
                                      <Loader2 className="w-3.5 h-3.5 animate-spin mr-2" />
                                      <span>{loading ? "加载中…" : "等待获取"}</span>
                                    </div>
                                  ) : (
                                    <div className="space-y-2">
                                      <div className="flex items-center gap-2 text-[10px] text-[#64748b] border-b border-[#1e293b]/60 pb-1.5">
                                        <span className="text-[#94a3b8] font-mono">{cached.name}</span>
                                        <span>{formatSize(cached.size)}</span>
                                        {cached.truncated && (
                                          <span className="text-[#faad14]">已截断（&gt; 100KB）</span>
                                        )}
                                      </div>
                                      <div
                                        className="yuleosh-md-body text-[#cbd5e1] leading-relaxed"
                                        // marked 输出已 sanitize（renderMarkdownSafe），
                                        // 仍属受信任内部 pipeline 产物。
                                        dangerouslySetInnerHTML={{
                                          __html: renderMarkdownSafe(cached.content),
                                        }}
                                      />
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-[#64748b]">
                暂无产出物（运行一次流水线后自动出现）
              </div>
            )}
          </CardContent>
        </Card>

        {/* Data note */}
        {listNote && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{listNote}</span>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="mb-4 rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-4 py-2 text-xs text-[#ff4d4f] flex items-center justify-between">
            <span className="flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {error}
            </span>
            <button onClick={() => setError("")} className="ml-2 hover:text-white text-sm">
              &times;
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-6 items-start">
          {/* ── Left: pipeline list + artifact trees ── */}
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                  <FolderOpen className="w-4 h-4 text-[#722ed1]" />
                  Pipeline 列表
                  {!loading && (
                    <span className="text-xs font-normal text-[#64748b]">共 {pipelines.length} 条</span>
                  )}
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent className="px-0">
              {loading ? (
                <div className="flex items-center justify-center py-14 text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  加载中…
                </div>
              ) : isEmpty ? (
                <div className="py-14 text-center text-[#64748b] text-sm">
                  <div className="text-2xl mb-2">🗂️</div>
                  暂无数据
                  <div className="text-xs mt-1 text-[#475569]">未发现 pipeline 运行记录</div>
                </div>
              ) : (
                <div>
                  {/* Table header */}
                  <div className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-2 text-xs text-[#64748b] border-b border-[#1e293b]">
                    <span>流水线</span>
                    <span className="w-24">状态</span>
                    <span className="w-40 text-right">时间</span>
                  </div>

                  {pipelines.map((p) => {
                    const isOpen = !!expanded[p.name];
                    const meta = pipelineStatusMeta(p.status);
                    const arts = artifactData[p.name];
                    const artsLoading = !!artifactLoading[p.name];
                    const artsErr = artifactError[p.name] || "";
                    return (
                      <div key={p.name} className="border-b border-[#1e293b] last:border-b-0">
                        {/* Row */}
                        <div
                          onClick={() => void toggleExpand(p.name)}
                          className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-3 items-center cursor-pointer transition-all hover:bg-[#1e293b]/50"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            {isOpen ? (
                              <ChevronDown className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                            )}
                            <FileText className="w-4 h-4 text-[#722ed1] shrink-0" />
                            <span className="text-sm text-[#e2e8f0] truncate">{p.name}</span>
                            {p.backend && (
                              <span className="text-[10px] text-[#475569] border border-[#1e293b] rounded px-1.5 py-0.5 shrink-0">
                                {p.backend}
                              </span>
                            )}
                          </div>
                          <div className="w-24">
                            <Badge
                              variant="outline"
                              className="border-transparent"
                              style={{
                                color: meta.color,
                                background: `${meta.color}1f`,
                                borderColor: `${meta.color}4d`,
                              }}
                            >
                              {meta.label}
                            </Badge>
                          </div>
                          <div className="w-40 text-right text-xs text-[#94a3b8]">
                            {formatDate(p.updated_at || p.created_at)}
                          </div>
                        </div>

                        {/* Expanded: artifact tree */}
                        {isOpen && (
                          <div className="px-4 pb-4">
                            {artsLoading ? (
                              <div className="flex items-center gap-2 py-3 text-xs text-[#94a3b8] pl-5">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                加载产出物…
                              </div>
                            ) : artsErr ? (
                              <div className="py-3 pl-5 text-xs text-[#ff4d4f] flex items-center gap-1">
                                <AlertCircle className="w-3.5 h-3.5" />
                                {artsErr}
                              </div>
                            ) : arts && arts.runs.length === 0 ? (
                              <div className="py-3 pl-5 text-xs text-[#94a3b8]">
                                暂无产出物
                                {arts.note && (
                                  <span className="text-[#64748b]">（{arts.note}）</span>
                                )}
                              </div>
                            ) : arts ? (
                              <div className="space-y-3 pl-5">
                                {arts.runs.map((run) => (
                                  <div
                                    key={run.run_id}
                                    className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 overflow-hidden"
                                  >
                                    <div className="flex items-center gap-2 px-3 py-2 border-b border-[#1e293b]">
                                      <FileText className="w-3.5 h-3.5 text-[#1677ff]" />
                                      <span className="text-xs text-[#e2e8f0] font-medium truncate">
                                        {run.name}
                                      </span>
                                      <span className="text-[10px] text-[#64748b]">{run.run_id}</span>
                                      <Badge
                                        variant="outline"
                                        className="ml-auto border-transparent"
                                        style={{
                                          color: pipelineStatusMeta(run.status).color,
                                          background: `${pipelineStatusMeta(run.status).color}1f`,
                                          borderColor: `${pipelineStatusMeta(run.status).color}4d`,
                                        }}
                                      >
                                        {run.status}
                                      </Badge>
                                    </div>
                                    {run.files.length === 0 ? (
                                      <div className="px-3 py-2 text-xs text-[#64748b]">该 run 无产出物文件</div>
                                    ) : (
                                      <div className="divide-y divide-[#1e293b]/60">
                                        {run.files.map((f) => (
                                          <button
                                            key={f.path}
                                            onClick={() => void handlePreview(run.run_id, f.path)}
                                            className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs hover:bg-[#1e293b]/50 transition-all cursor-pointer"
                                          >
                                            <FileText className="w-3.5 h-3.5 text-[#94a3b8] shrink-0" />
                                            <span className="text-[#e2e8f0] truncate flex-1">{f.name}</span>
                                            {f.ext && (
                                              <span className="text-[10px] uppercase text-[#722ed1] border border-[#722ed1]/30 rounded px-1 py-0.5 shrink-0">
                                                {f.ext}
                                              </span>
                                            )}
                                            <span className="text-[#64748b] shrink-0">{formatSize(f.size)}</span>
                                            <Eye className="w-3.5 h-3.5 text-[#475569] shrink-0" />
                                          </button>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── Right: preview panel ── */}
          <Card className="border-[#1e293b] bg-[#111827] lg:sticky lg:top-20">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <Eye className="w-4 h-4 text-[#722ed1]" />
                产出物预览
              </CardTitle>
              <CardDescription className="text-xs text-[#64748b] truncate">
                {preview ? `${preview.runId} / ${preview.file}` : "点击左侧文件查看内容"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {previewError && (
                <div className="rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-3 py-2 text-xs text-[#ff4d4f] mb-3 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  {previewError}
                </div>
              )}
              {!preview ? (
                <div className="py-12 text-center text-[#64748b] text-sm">
                  <div className="text-2xl mb-2">📄</div>
                  暂无预览
                </div>
              ) : preview.loading ? (
                <div className="flex items-center justify-center py-12 text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  加载中…
                </div>
              ) : preview.data ? (
                <div>
                  <div className="flex items-center gap-2 mb-2 text-xs text-[#94a3b8]">
                    <span className="text-[#e2e8f0] font-medium">{preview.data.name}</span>
                    <span className="text-[#64748b]">{formatSize(preview.data.size)}</span>
                    {preview.data.truncated && (
                      <span className="text-[#faad14]">已截断</span>
                    )}
                  </div>
                  {preview.data.note && (
                    <div className="mb-2 rounded bg-[#faad14]/10 border border-[#faad14]/20 px-2 py-1 text-[11px] text-[#faad14]">
                      {preview.data.note}
                    </div>
                  )}
                  <pre className="max-h-[65vh] overflow-auto rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3 text-xs text-[#cbd5e1] whitespace-pre-wrap break-words leading-relaxed">
                    {preview.data.content}
                  </pre>
                </div>
              ) : (
                <div className="py-12 text-center text-[#64748b] text-sm">预览加载失败</div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
  </div>
  );
}

// ─── 运行过程看板 ────────────────────────────────────────────────────────────

/**
 * T8 生成进度可视化：把「哪些阶段在生成、耗时花在哪里」画出来。
 *
 *  - 分段流程条：每个阶段一格，按状态着色，一眼看完整条流水线的推进情况
 *  - 耗时分布：按 duration_s 归一化的横向条，找出发行里的耗时大头
 */
function GenerationProgress({ steps }: { steps: StepRecord[] }) {
  const [open, setOpen] = useState(true);
  if (steps.length === 0) return null;

  const timed = steps
    .filter((s) => typeof s.duration_s === "number" && (s.duration_s as number) > 0)
    .slice()
    .sort((a, b) => (b.duration_s as number) - (a.duration_s as number));
  const maxDur = timed.length ? (timed[0].duration_s as number) : 0;
  const totalDur = timed.reduce((acc, s) => acc + (s.duration_s as number), 0);

  return (
    <div className="mb-3 rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-2.5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between text-[11px] text-[#94a3b8] hover:text-white transition-colors"
      >
        <span className="inline-flex items-center gap-1.5">
          <Activity2 />
          生成进度
          <span className="text-[#64748b]">
            {steps.length} 阶段 · 累计耗时 {totalDur.toFixed(2)}s
          </span>
        </span>
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="mt-2.5 space-y-3">
          {/* 分段流程条：每阶段一格，状态着色 */}
          <div className="flex gap-[2px] h-2.5">
            {steps.map((s) => {
              const meta = stepMeta(s.status || "");
              return (
                <div
                  key={s.step_id}
                  title={`${s.step_id} · ${s.name} · ${meta.label}`}
                  className="flex-1 rounded-sm opacity-90 hover:opacity-100 transition-opacity"
                  style={{ background: meta.color }}
                />
              );
            })}
          </div>

          {/* 耗时分布（取最慢的 8 个阶段） */}
          {timed.length > 0 ? (
            <div className="space-y-1">
              {timed.slice(0, 8).map((s) => {
                const meta = stepMeta(s.status || "");
                const dur = s.duration_s as number;
                const width = maxDur > 0 ? Math.max(2, (dur / maxDur) * 100) : 2;
                return (
                  <div key={s.step_id} className="flex items-center gap-2 text-[10px]">
                    <span
                      className="w-24 truncate text-[#64748b] font-mono shrink-0"
                      title={s.name}
                    >
                      {s.step_id}
                    </span>
                    <div className="flex-1 h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${width}%`, background: meta.color }}
                      />
                    </div>
                    <span className="w-14 text-right text-[#94a3b8] shrink-0">
                      {dur.toFixed(2)}s
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[10px] text-[#475569] py-0.5">
              暂无耗时数据（阶段尚未执行完成）
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface CheckpointPanelProps {
  snapshot: CheckpointSnapshot | null;
  polling: boolean;
  error: string;
  stepDefs: { key: string; name: string; agent: string }[];
  selectedKeys: Set<string>;
  runs: any[];
  activeRunId: string | null;
  onSelectRun: (id: string | null) => void;
}

function CheckpointPanel({
  snapshot,
  polling,
  error,
  stepDefs,
  selectedKeys,
  runs,
  activeRunId,
  onSelectRun,
}: CheckpointPanelProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const steps = snapshot?.steps ?? [];
  const totals = steps.reduce(
    (acc, s) => {
      const k = (s.status || "").toLowerCase();
      if (k === "passed") acc.passed++;
      else if (k === "failed") acc.failed++;
      else if (k === "running") acc.running++;
      else if (k === "skipped") acc.skipped++;
      else acc.pending++;
      return acc;
    },
    { passed: 0, failed: 0, running: 0, skipped: 0, pending: 0 }
  );

  const finished = totals.passed + totals.failed;
  const total = steps.length || stepDefs.length || 24;
  const pct = total > 0 ? Math.round((finished / total) * 100) : 0;

  const overall = snapshot?.state?.status || (snapshot?.op_active ? "running" : "idle");
  const overallMeta = pipelineStatusMeta(overall);

  // Map stepId → selectedKey status (highlight勾选的列)
  const selectedByKey = new Map<string, boolean>();
  for (const d of stepDefs) selectedByKey.set(d.key, selectedKeys.has(d.key));

  // 看板默认隐藏（点击运行前不出现），有数据或有轮询时显示
  if (!polling && !snapshot) return null;

  return (
    <Card className="border-[#1e293b] bg-[#111827] mb-4">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
            <Activity2 />
            运行过程看板
            {polling && (
              <span className="text-[10px] text-[#94a3b8] inline-flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> 实时刷新
              </span>
            )}
          </CardTitle>
          <div className="flex items-center gap-3 text-[11px] text-[#94a3b8]">
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: "#10b981" }} />
              <span className="text-[#10b981] font-medium">{totals.passed}</span> 已通过
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: "#ff4d4f" }} />
              <span className="text-[#ff4d4f] font-medium">{totals.failed}</span> 失败
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: "#1677ff" }} />
              <span className="text-[#1677ff] font-medium">{totals.running}</span> 运行中
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: "#faad14" }} />
              <span className="text-[#faad14] font-medium">{totals.skipped}</span> 跳过
            </span>
            <span className="inline-flex items-center gap-1 text-[#e2e8f0]">
              <span className="text-[#94a3b8]">进度</span>
              <span className="font-mono">{finished}/{total}</span>
              <span className="text-[#722ed1] font-medium">{pct}%</span>
              <span
                className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
                style={{
                  color: overallMeta.color,
                  background: `${overallMeta.color}1f`,
                  border: `1px solid ${overallMeta.color}4d`,
                }}
              >
                {overallMeta.label}
              </span>
            </span>
          </div>
        </div>
        {/* 运行历史下拉：回看历次运行（选中后看板显示该次静态快照） */}
        {(runs.length > 0 || activeRunId) && (
          <div className="mt-2 flex items-center gap-2 text-xs">
            <span className="text-[#64748b] shrink-0">运行历史</span>
            <select
              value={activeRunId ?? ""}
              onChange={(e) => onSelectRun(e.target.value || null)}
              className="bg-[#0a0e17] border border-[#1e293b] rounded px-2 py-1 text-[#e2e8f0] text-xs max-w-[280px]"
            >
              <option value="">最新运行</option>
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {(r.started_at || "").replace("T", " ").slice(0, 19)} · {r.op}
                  {r.mode ? `(${r.mode})` : ""} · {r.status}
                </option>
              ))}
            </select>
            {activeRunId && (
              <span className="text-[10px] text-[#722ed1]">查看历史（静态快照）</span>
            )}
          </div>
        )}
        {/* 进度条 */}
        <div className="mt-2 h-1.5 rounded-full bg-[#0a0e17] overflow-hidden">
          <div
            className="h-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              background:
                totals.failed > 0
                  ? "linear-gradient(90deg, #10b981 0%, #ff4d4f 100%)"
                  : "linear-gradient(90deg, #722ed1 0%, #10b981 100%)",
            }}
          />
        </div>
        {error && (
          <div className="mt-2 rounded bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-2 py-1 text-[11px] text-[#ff4d4f]">
            轮询失败：{error}
          </div>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        {steps.length === 0 ? (
          <div className="py-6 text-center text-xs text-[#64748b]">
            等待 checkpoint 数据…（后端会写入最近一次运行的步骤状态）
          </div>
        ) : (
          <>
            {/* T8：生成进度可视化（分段流程 + 耗时分布） */}
            <GenerationProgress steps={steps} />
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
            {steps.map((s) => {
              const meta = stepMeta(s.status || "");
              const isRunning = (s.status || "").toLowerCase() === "running";
              const isSkipped = (s.status || "").toLowerCase() === "skipped";
              const isFailed = (s.status || "").toLowerCase() === "failed";
              const isSelected = selectedByKey.get(s.step_id);
              const hasError = !!(s.error && String(s.error).trim());
              const canExpand = isFailed && hasError;
              const isOpen = expanded === s.step_id;
              return (
                <Fragment key={s.step_id}>
                  <div
                    className={`flex items-center gap-2 rounded-md border px-2 py-1.5 text-[11px] transition-all ${
                      isSelected === false
                        ? "border-[#1e293b]/60 bg-[#0a0e17]/40 text-[#475569]"
                        : isRunning
                        ? "border-[#1677ff]/60 bg-[#1677ff]/10 text-[#e2e8f0] shadow-[0_0_0_1px_rgba(22,119,255,0.3)]"
                        : isSkipped
                        ? "border-[#faad14]/30 bg-[#0a0e17] text-[#faad14]"
                        : isFailed
                        ? "border-[#ff4d4f]/40 bg-[#ff4d4f]/10 text-[#ffb4b4] cursor-pointer hover:bg-[#ff4d4f]/15"
                        : "border-[#1e293b] bg-[#0a0e17] text-[#cbd5e1]"
                    }`}
                    title={
                      s.error
                        ? `${s.name} · ${meta.label} · ${s.error}`
                        : `${s.name} · ${meta.label}${
                            typeof s.duration_s === "number" ? ` · ${s.duration_s.toFixed(1)}s` : ""
                          }`
                    }
                    onClick={canExpand ? () => setExpanded(isOpen ? null : s.step_id) : undefined}
                  >
                    <span
                      className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold shrink-0 ${
                        isRunning ? "animate-pulse" : ""
                      }`}
                      style={{
                        color: meta.color,
                        background: `${meta.color}1f`,
                        border: `1px solid ${meta.ring}`,
                      }}
                    >
                      {meta.symbol}
                    </span>
                    <span className="font-mono opacity-60 shrink-0">{s.step_id}</span>
                    <span className="truncate flex-1">{s.name}</span>
                    {typeof s.duration_s === "number" && s.duration_s > 0 && (
                      <span className="text-[10px] text-[#64748b] shrink-0">
                        {s.duration_s.toFixed(1)}s
                      </span>
                    )}
                    {canExpand && (
                      <ChevronDown
                        className={`w-3 h-3 shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`}
                        style={{ color: meta.color }}
                      />
                    )}
                    <span className="text-[10px] shrink-0" style={{ color: meta.color }}>
                      {meta.label}
                    </span>
                  </div>
                  {isOpen && hasError && (
                    <div className="col-span-full rounded-md border border-[#ff4d4f]/30 bg-[#ff4d4f]/10 px-3 py-2 text-[11px] text-[#ffc9c9] whitespace-pre-wrap break-words leading-relaxed">
                      <span className="font-medium text-[#ff4d4f]">失败原因：</span>
                      {s.error}
                    </div>
                  )}
                </Fragment>
              );
            })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── T9 证据包面板 ───────────────────────────────────────────────────────────

function EvidencePanel({
  packages,
  loading,
  onRefresh,
}: {
  packages: EvidencePackage[];
  loading: boolean;
  onRefresh: () => void;
}) {
  // 默认只展示最新的 10 条，其余折叠；超出时可一键展开/收起。
  const VISIBLE = 10;
  const [expanded, setExpanded] = useState(false);
  const visiblePackages = expanded ? packages : packages.slice(0, VISIBLE);
  return (
    <Card className="border-[#1e293b] bg-[#111827] mb-4">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
            <FolderOpen className="w-4 h-4 text-[#722ed1]" />
            证据包
            {!loading && (
              <span className="text-xs font-normal text-[#64748b]">
                共 {packages.length} 个
              </span>
            )}
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={loading}
            className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>
        <CardDescription className="text-xs text-[#64748b]">
          每次运行生成一条证据包：完整执行记录（逐步状态 / 耗时 / 错误）+ 产物文件，可打包为 zip 下载
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {loading && packages.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-[#64748b]">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            加载中…
          </div>
        ) : packages.length === 0 ? (
          <div className="py-8 text-center text-xs text-[#64748b]">
            暂无证据包（运行一次流水线后自动生成）
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              {visiblePackages.map((p) => {
                const rm = pipelineStatusMeta(p.status || "");
                return (
                  <div
                    key={p.run_id}
                    className="flex items-center gap-3 rounded-md border border-[#1e293b] bg-[#0a0e17] px-3 py-2 text-xs"
                  >
                    <span className="font-mono text-[#64748b] shrink-0 w-24 truncate">
                      {p.run_id}
                    </span>
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] shrink-0"
                      style={{
                        color: rm.color,
                        background: `${rm.color}1f`,
                        border: `1px solid ${rm.color}4d`,
                      }}
                    >
                      {p.status}
                    </span>
                    <span className="text-[#94a3b8] shrink-0">
                      {p.op}
                      {p.mode ? ` · ${p.mode}` : ""}
                    </span>
                    <span className="text-[#64748b] shrink-0">
                      {p.step_count} 步（
                      <span className="text-[#10b981]">{p.step_passed}</span> /{" "}
                      <span className="text-[#ff4d4f]">{p.step_failed}</span>）
                    </span>
                    <span
                      className="text-[#64748b] shrink-0"
                      title="磁盘上仍存在的产物 / 记录到的产物"
                    >
                      产物 {p.artifact_available}/{p.artifact_count}
                    </span>
                    <span className="text-[#475569] shrink-0 ml-auto">
                      {(p.started_at || "").replace("T", " ").slice(0, 19)}
                    </span>
                    <a
                      href={`/api/v1/pipeline/evidence/download?run_id=${p.run_id}`}
                      className="inline-flex items-center gap-1 shrink-0 px-2 py-1 rounded border border-[#722ed1]/40 text-[#722ed1] hover:text-white hover:bg-[#722ed1]/10 transition-colors"
                      title="下载证据包（zip：执行记录 manifest + 产物）"
                    >
                      <Download className="w-3.5 h-3.5" />
                      下载
                    </a>
                  </div>
                );
              })}
            </div>
            {packages.length > VISIBLE && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-md border border-[#1e293b] py-2 text-xs text-[#94a3b8] transition-colors hover:border-[#722ed1]/40 hover:text-white"
              >
                {expanded ? (
                  <>
                    <ChevronUp className="w-3.5 h-3.5" />
                    收起，仅显示最新 {VISIBLE} 条
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3.5 h-3.5" />
                    展开剩余 {packages.length - VISIBLE} 条
                  </>
                )}
              </button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// Minimal Activity icon (lucide doesn't ship one in this codebase), reused as funnel
function Activity2() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-[#722ed1]"
    >
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

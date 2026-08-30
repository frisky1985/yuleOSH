"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookMarked,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
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
import { TopNav } from "@/components/dashboard/top-nav";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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
  files: ArtifactFile[];
}

interface ArtifactsListResponse {
  runs: ArtifactRun[];
  count: number;
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

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Fetch an API v1 endpoint and unwrap the {ok, data?} envelope (flat or data-wrapped). */
async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = res.headers.get("content-type") || "";
  let body: unknown = null;
  if (contentType.includes("application/json")) {
    body = await res.json();
  } else {
    const text = await res.text();
    throw new Error(`Non-JSON response (${res.status}): ${text.slice(0, 200)}`);
  }
  const record = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  if (record.ok === false) {
    throw new Error(typeof record.error === "string" ? record.error : `API error (${res.status})`);
  }
  const payload = record.data !== undefined ? record.data : body;
  return payload as T;
}

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
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasRunRef = useRef(false); // 用户曾经点过运行/续跑/停止才轮询

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchCheckpoint = useCallback(async () => {
    try {
      const res = await apiFetch<CheckpointSnapshot>(
        "/api/v1/pipeline/checkpoint?pipeline=agent-pipeline"
      );
      setCheckpoint(res);
      setCheckpointError("");
      // 终止条件：无 op_active 且没有 running 中步骤
      const stillRunning = (res.steps || []).some((s) => (s.status || "").toLowerCase() === "running");
      if (!res.op_active && !stillRunning && pollRef.current) {
        stopPolling();
      }
    } catch (err) {
      setCheckpointError(errMessage(err));
    }
  }, [stopPolling]);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    void fetchCheckpoint();
    pollRef.current = setInterval(() => {
      void fetchCheckpoint();
    }, 1500);
  }, [fetchCheckpoint]);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // 挂载即拉一次 checkpoint：刷新后也能看到上次运行结果（仅取一次，不轮询）
  useEffect(() => {
    void fetchCheckpoint();
  }, [fetchCheckpoint]);

  // ── Load pipeline list ────────────────────────────────────────────────────
  const loadPipelines = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<PipelineListResponse>("/api/v1/pipeline/list");
      setPipelines(res.pipelines || []);
      setProjects(res.projects || []);
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
        setSelected(new Set(list.map((s) => s.key)));
        setAllChecked(true);
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

  // ── 运行控制 ──────────────────────────────────────────────────────────────
  const toggleStep = useCallback((key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      setAllChecked(next.size === steps.length);
      return next;
    });
  }, [steps.length]);

  const toggleAll = useCallback(() => {
    setAllChecked((prev) => {
      const next = !prev;
      setSelected(next ? new Set(steps.map((s) => s.key)) : new Set());
      return next;
    });
  }, [steps]);

  const runControl = useCallback(
    async (action: "run-selected" | "resume" | "stop") => {
      setOpRunning(true);
      setOpMsg("");
      try {
        if (action === "resume") {
          const res = await apiFetch<any>("/api/v1/pipeline/resume", {
            method: "POST",
            body: JSON.stringify({}),
          });
          setOpMsg(`已提交续跑：${res?.op || "resume"}`);
        } else if (action === "stop") {
          const res = await apiFetch<any>("/api/v1/pipeline/stop", {
            method: "POST",
            body: JSON.stringify({}),
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
                  body: JSON.stringify({}),
                })
              : await apiFetch<any>("/api/v1/pipeline/retry", {
                  method: "POST",
                  body: JSON.stringify({ step_ids: ids }),
                });
          setOpMsg(`已提交：${res?.op || "ok"}（${ids.length}/${steps.length} 步）`);
        }
        // 提交成功后启动实时进度轮询（看板数据源）
        hasRunRef.current = true;
        startPolling();
      } catch (err) {
        setOpMsg(errMessage(err));
      } finally {
        setOpRunning(false);
      }
    },
    [steps, selected, startPolling]
  );

  const isEmpty = !loading && pipelines.length === 0;

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <TopNav mode="links" />

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
              <div className="mb-3">
                <label className="flex items-center gap-1.5 text-xs text-[#94a3b8] cursor-pointer select-none mb-2">
                  <input
                    type="checkbox"
                    checked={allChecked}
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
                        className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs cursor-pointer transition-colors ${
                          selected.has(s.key)
                            ? "border-[#722ed1]/50 bg-[#722ed1]/10 text-[#e2e8f0]"
                            : "border-[#1e293b] bg-[#0a0e17] text-[#64748b]"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selected.has(s.key)}
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
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
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
          </CardContent>
        </Card>

        {/* ── 运行过程看板（轮询 checkpoint） ── */}
        <CheckpointPanel
          snapshot={checkpoint}
          polling={pollRef.current !== null}
          error={checkpointError}
          stepDefs={steps}
          selectedKeys={selected}
        />

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

interface CheckpointPanelProps {
  snapshot: CheckpointSnapshot | null;
  polling: boolean;
  error: string;
  stepDefs: { key: string; name: string; agent: string }[];
  selectedKeys: Set<string>;
}

function CheckpointPanel({
  snapshot,
  polling,
  error,
  stepDefs,
  selectedKeys,
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
            <Badge
              variant="outline"
              className="border-transparent ml-1"
              style={{
                color: overallMeta.color,
                background: `${overallMeta.color}1f`,
                borderColor: `${overallMeta.color}4d`,
              }}
            >
              {overallMeta.label}
            </Badge>
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
            </span>
          </div>
        </div>
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

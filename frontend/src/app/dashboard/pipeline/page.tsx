"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookMarked,
  ChevronDown,
  ChevronRight,
  Cpu,
  Eye,
  FileText,
  FlaskConical,
  FolderOpen,
  Info,
  LayoutDashboard,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldCheck,
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

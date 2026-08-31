"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookMarked,
  ChevronDown,
  ChevronRight,
  Cpu,
  FileText,
  FlaskConical,
  FolderOpen,
  Info,
  LayoutDashboard,
  Link2,
  ListChecks,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Target,
  Workflow,
} from "lucide-react";
import { DashboardChrome } from "@/components/dashboard/dashboard-chrome";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Scenario {
  given: string[];
  when: string[];
  then: string[];
}

interface Requirement {
  req_id: string;
  title: string;
  kind: string; // SHALL | SHOULD | MAY
  text: string;
  state: string; // PROPOSED | APPROVED | IMPLEMENTED | VERIFIED
  scenarios: Scenario[];
}

interface RequirementsResponse {
  requirements: Requirement[];
  count: number;
  note?: string | null;
}

interface TraceArtifact {
  type: string; // design | code | test | evidence
  ref: string;
}

interface TraceResponse {
  req_id: string;
  artifacts: TraceArtifact[];
  note?: string | null;
}

interface GapItem {
  req_id: string;
  missing: string[];
}

interface GapsResponse {
  total: number;
  with_test: number;
  with_evidence: number;
  gaps: GapItem[];
  note?: string | null;
}

interface ProjectItem {
  id: number | string;
  name: string;
  slug?: string;
  description?: string;
}

interface ProjectsResponse {
  projects: ProjectItem[];
  count?: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const KIND_META: Record<string, { label: string; color: string }> = {
  SHALL: { label: "SHALL", color: "#722ed1" },
  SHOULD: { label: "SHOULD", color: "#1677ff" },
  MAY: { label: "MAY", color: "#faad14" },
};

const STATE_META: Record<string, { label: string; color: string }> = {
  PROPOSED: { label: "PROPOSED", color: "#64748b" },
  APPROVED: { label: "APPROVED", color: "#1677ff" },
  IMPLEMENTED: { label: "IMPLEMENTED", color: "#10b981" },
  VERIFIED: { label: "VERIFIED", color: "#722ed1" },
};

const TRACE_TYPES: { key: string; label: string; color: string }[] = [
  { key: "design", label: "设计", color: "#1677ff" },
  { key: "code", label: "代码", color: "#10b981" },
  { key: "test", label: "测试", color: "#faad14" },
  { key: "evidence", label: "证据", color: "#722ed1" },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Fetch an API v1 endpoint and unwrap the {ok, data?} envelope. */
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

function kindMeta(kind: string): { label: string; color: string } {
  return KIND_META[kind] || { label: kind || "SHALL", color: "#722ed1" };
}

function stateMeta(state: string): { label: string; color: string } {
  return STATE_META[state] || { label: state || "PROPOSED", color: "#64748b" };
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

// Navigation is rendered by the shared TopNav component
// (see src/components/dashboard/top-nav.tsx).

// ─── Page ────────────────────────────────────────────────────────────────────

export default function RequirementsPage() {

  // Projects (context for all requirement queries)
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");

  // Requirement list
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [reqNote, setReqNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Expandable rows: scenarios + traceability
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [traces, setTraces] = useState<Record<string, TraceResponse | null>>({});
  const [traceLoading, setTraceLoading] = useState<Record<string, boolean>>({});
  const [traceError, setTraceError] = useState<Record<string, string>>({});

  // Gap analysis
  const [gaps, setGaps] = useState<GapsResponse | null>(null);
  const [gapsLoading, setGapsLoading] = useState(true);
  const [gapsError, setGapsError] = useState("");

  // ── Load project list ────────────────────────────────────────────────────
  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectsError("");
    try {
      const res = await apiFetch<ProjectsResponse>("/api/v1/project");
      const list = res.projects || [];
      setProjects(list);
      setSelectedProject((prev) => (prev && list.some((p) => p.name === prev) ? prev : list[0]?.name || ""));
    } catch (err) {
      setProjectsError(errMessage(err));
      setProjects([]);
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  // ── Load requirements + gaps for the selected project ───────────────────
  const loadAll = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError("");
    setGapsLoading(true);
    setGapsError("");
    try {
      const [reqRes, gapRes] = await Promise.all([
        apiFetch<RequirementsResponse>(
          `/api/v1/requirements?project=${encodeURIComponent(selectedProject)}`
        ),
        apiFetch<GapsResponse>(
          `/api/v1/requirements/gaps?project=${encodeURIComponent(selectedProject)}`
        ),
      ]);
      setRequirements(reqRes.requirements || []);
      setReqNote(reqRes.note ?? null);
      setGaps(gapRes);
      // Project switched → clear expand state and cached traces
      setExpanded({});
      setTraces({});
      setTraceError({});
    } catch (err) {
      const msg = errMessage(err);
      setError(msg);
      setGapsError(msg);
      setRequirements([]);
      setGaps(null);
    } finally {
      setLoading(false);
      setGapsLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (!selectedProject) return;
    void loadAll();
  }, [selectedProject, loadAll]);

  // ── Expand row → scenarios + trace ───────────────────────────────────────
  const toggleExpand = useCallback(
    async (reqId: string) => {
      const isOpen = !!expanded[reqId];
      setExpanded((prev) => ({ ...prev, [reqId]: !isOpen }));

      if (!isOpen && traces[reqId] === undefined && !traceLoading[reqId] && selectedProject) {
        setTraceLoading((prev) => ({ ...prev, [reqId]: true }));
        setTraceError((prev) => ({ ...prev, [reqId]: "" }));
        try {
          const res = await apiFetch<TraceResponse>(
            `/api/v1/requirements/${encodeURIComponent(reqId)}/trace?project=${encodeURIComponent(selectedProject)}`
          );
          setTraces((prev) => ({ ...prev, [reqId]: res }));
        } catch (err) {
          setTraceError((prev) => ({ ...prev, [reqId]: errMessage(err) }));
          setTraces((prev) => ({ ...prev, [reqId]: null }));
        } finally {
          setTraceLoading((prev) => ({ ...prev, [reqId]: false }));
        }
      }
    },
    [expanded, traces, traceLoading, selectedProject]
  );

  const isEmpty = !loading && requirements.length === 0;
  const noProjects = !projectsLoading && projects.length === 0;

  return (
  <DashboardChrome mode="links">

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <BookMarked className="w-4.5 h-4.5 text-[#722ed1]" />
              需求管理
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              需求生命周期、场景与追溯矩阵、测试/证据差距分析（展开行查看场景与追溯）
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#64748b] shrink-0">项目</span>
              {projectsLoading ? (
                <span className="text-xs text-[#64748b] flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  加载中…
                </span>
              ) : (
                <Select value={selectedProject} onValueChange={(v) => setSelectedProject(v ?? "")}>
                  <SelectTrigger size="sm" className="w-44">
                    <SelectValue placeholder="选择项目" />
                  </SelectTrigger>
                  <SelectContent align="end">
                    {projects.map((p) => (
                      <SelectItem key={String(p.id)} value={p.name}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void loadAll()}
              disabled={loading || gapsLoading || !selectedProject}
              className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              刷新
            </Button>
          </div>
        </div>

        {/* Data note */}
        {reqNote && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{reqNote}</span>
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

        {noProjects ? (
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardContent className="py-14 text-center text-[#64748b] text-sm">
              <div className="text-2xl mb-2">📂</div>
              暂无项目
              <div className="text-xs mt-1 text-[#475569]">
                {projectsError ? `项目列表加载失败：${projectsError}` : "请先在座舱中创建项目"}
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6 items-start">
            {/* ── Left: requirement list ── */}
            <Card className="border-[#1e293b] bg-[#111827]">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[#722ed1]" />
                  需求列表
                  {!loading && (
                    <span className="text-xs font-normal text-[#64748b]">
                      共 {requirements.length} 条
                    </span>
                  )}
                </CardTitle>
                <CardDescription className="text-xs text-[#64748b]">
                  展开行查看 GIVEN/WHEN/THEN 场景与设计/代码/测试/证据追溯
                </CardDescription>
              </CardHeader>
              <CardContent className="px-0">
                {loading ? (
                  <div className="flex items-center justify-center py-14 text-[#64748b]">
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    加载中…
                  </div>
                ) : isEmpty ? (
                  <div className="py-14 text-center text-[#64748b] text-sm">
                    <div className="text-2xl mb-2">📋</div>
                    暂无需求
                    <div className="text-xs mt-1 text-[#475569]">
                      {reqNote || "所选项目未解析到需求条目"}
                    </div>
                  </div>
                ) : (
                  <div>
                    {/* Table header */}
                    <div className="grid grid-cols-[1fr_auto_auto_auto] gap-3 px-4 py-2 text-xs text-[#64748b] border-b border-[#1e293b]">
                      <span>需求</span>
                      <span className="w-20">类型</span>
                      <span className="w-28">状态</span>
                      <span className="w-20 text-right">操作</span>
                    </div>

                    {requirements.map((r) => {
                      const km = kindMeta(r.kind);
                      const sm = stateMeta(r.state);
                      const isOpen = !!expanded[r.req_id];
                      const trace = traces[r.req_id];
                      const traceLoad = !!traceLoading[r.req_id];
                      const traceErr = traceError[r.req_id] || "";
                      return (
                        <div key={r.req_id} className="border-b border-[#1e293b] last:border-b-0">
                          {/* Row */}
                          <div
                            onClick={() => void toggleExpand(r.req_id)}
                            className="grid grid-cols-[1fr_auto_auto_auto] gap-3 px-4 py-3 items-center cursor-pointer transition-all hover:bg-[#1e293b]/50"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 min-w-0">
                                {isOpen ? (
                                  <ChevronDown className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                                ) : (
                                  <ChevronRight className="w-3.5 h-3.5 text-[#64748b] shrink-0" />
                                )}
                                <span className="text-xs font-mono text-[#722ed1] shrink-0">
                                  {r.req_id}
                                </span>
                                <span className="text-sm text-[#e2e8f0] truncate">
                                  {r.title || "(无标题)"}
                                </span>
                              </div>
                              {r.text && (
                                <div className="text-xs text-[#64748b] truncate pl-6 mt-0.5">
                                  {r.text}
                                </div>
                              )}
                            </div>
                            <div className="w-20">
                              <Badge
                                variant="outline"
                                className="border-transparent"
                                style={{
                                  color: km.color,
                                  background: `${km.color}1f`,
                                  borderColor: `${km.color}4d`,
                                }}
                              >
                                {km.label}
                              </Badge>
                            </div>
                            <div className="w-28">
                              <Badge
                                variant="outline"
                                className="border-transparent"
                                style={{
                                  color: sm.color,
                                  background: `${sm.color}1f`,
                                  borderColor: `${sm.color}4d`,
                                }}
                              >
                                {sm.label}
                              </Badge>
                            </div>
                            <div className="w-20 text-right">
                              <span className="text-xs text-[#64748b]">
                                {r.scenarios?.length ? `${r.scenarios.length} 场景` : "无场景"}
                              </span>
                            </div>
                          </div>

                          {/* Expanded: text + scenarios + trace */}
                          {isOpen && (
                            <div className="px-4 pb-4 space-y-3">
                              {r.text && (
                                <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-3 py-2 text-xs text-[#cbd5e1] leading-relaxed">
                                  {r.text}
                                </div>
                              )}

                              {/* Scenarios */}
                              <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 overflow-hidden">
                                <div className="flex items-center gap-2 px-3 py-2 border-b border-[#1e293b] text-xs text-[#94a3b8]">
                                  <ListChecks className="w-3.5 h-3.5 text-[#1677ff]" />
                                  场景（GIVEN / WHEN / THEN）
                                </div>
                                {r.scenarios.length === 0 ? (
                                  <div className="px-3 py-2 text-xs text-[#64748b]">
                                    该需求未定义场景
                                  </div>
                                ) : (
                                  <div className="divide-y divide-[#1e293b]/60">
                                    {r.scenarios.map((sc, i) => (
                                      <div key={i} className="px-3 py-2 text-xs space-y-1">
                                        {sc.given.map((g, gi) => (
                                          <div key={`g${gi}`} className="flex gap-2">
                                            <span className="text-[#10b981] font-mono shrink-0">GIVEN</span>
                                            <span className="text-[#cbd5e1]">{g}</span>
                                          </div>
                                        ))}
                                        {sc.when.map((w, wi) => (
                                          <div key={`w${wi}`} className="flex gap-2">
                                            <span className="text-[#1677ff] font-mono shrink-0">WHEN</span>
                                            <span className="text-[#cbd5e1]">{w}</span>
                                          </div>
                                        ))}
                                        {sc.then.map((t, ti) => (
                                          <div key={`t${ti}`} className="flex gap-2">
                                            <span className="text-[#faad14] font-mono shrink-0">THEN</span>
                                            <span className="text-[#cbd5e1]">{t}</span>
                                          </div>
                                        ))}
                                        {sc.given.length === 0 && sc.when.length === 0 && sc.then.length === 0 && (
                                          <div className="text-[#64748b]">空场景</div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {/* Traceability */}
                              <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 overflow-hidden">
                                <div className="flex items-center gap-2 px-3 py-2 border-b border-[#1e293b] text-xs text-[#94a3b8]">
                                  <Link2 className="w-3.5 h-3.5 text-[#722ed1]" />
                                  需求追溯
                                  <span className="text-[#64748b] font-normal">
                                    {selectedProject}
                                  </span>
                                </div>
                                {traceLoad ? (
                                  <div className="flex items-center gap-2 py-3 px-3 text-xs text-[#94a3b8]">
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    加载追溯…
                                  </div>
                                ) : traceErr ? (
                                  <div className="py-3 px-3 text-xs text-[#ff4d4f] flex items-center gap-1">
                                    <AlertCircle className="w-3.5 h-3.5" />
                                    {traceErr}
                                  </div>
                                ) : trace && trace.artifacts.length === 0 ? (
                                  <div className="py-3 px-3 text-xs text-[#64748b]">
                                    未发现引用该需求的制品
                                    {trace.note && <span className="text-[#475569]">（{trace.note}）</span>}
                                  </div>
                                ) : trace ? (
                                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-3">
                                    {TRACE_TYPES.map((tt) => {
                                      const items = trace.artifacts.filter((a) => a.type === tt.key);
                                      return (
                                        <div
                                          key={tt.key}
                                          className="rounded-lg border border-[#1e293b] bg-[#111827] p-2"
                                        >
                                          <div
                                            className="text-[11px] font-medium mb-1.5 flex items-center gap-1.5"
                                            style={{ color: tt.color }}
                                          >
                                            <span
                                              className="w-1.5 h-1.5 rounded-full inline-block"
                                              style={{ background: tt.color }}
                                            />
                                            {tt.label}
                                            <span className="text-[#64748b] font-normal">
                                              {items.length}
                                            </span>
                                          </div>
                                          {items.length === 0 ? (
                                            <div className="text-[11px] text-[#475569]">—</div>
                                          ) : (
                                            <ul className="space-y-1">
                                              {items.slice(0, 8).map((a) => (
                                                <li
                                                  key={a.ref}
                                                  className="text-[11px] text-[#94a3b8] font-mono truncate"
                                                  title={a.ref}
                                                >
                                                  {a.ref}
                                                </li>
                                              ))}
                                              {items.length > 8 && (
                                                <li className="text-[11px] text-[#475569]">
                                                  +{items.length - 8} 更多
                                                </li>
                                              )}
                                            </ul>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Right: gap analysis ── */}
            <Card className="border-[#1e293b] bg-[#111827] lg:sticky lg:top-20">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                  <Target className="w-4 h-4 text-[#722ed1]" />
                  差距分析
                </CardTitle>
                <CardDescription className="text-xs text-[#64748b]">
                  测试 / 证据覆盖缺口
                </CardDescription>
              </CardHeader>
              <CardContent>
                {gapsLoading ? (
                  <div className="flex items-center justify-center py-12 text-[#64748b]">
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    加载中…
                  </div>
                ) : gapsError ? (
                  <div className="py-8 text-center text-[#ff4d4f] text-xs flex items-center justify-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5" />
                    {gapsError}
                  </div>
                ) : gaps ? (
                  <div className="space-y-4">
                    {/* Stats */}
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-2 text-center">
                        <div className="text-lg font-bold text-[#e2e8f0]">{gaps.total}</div>
                        <div className="text-[10px] text-[#64748b] mt-0.5">总需求</div>
                      </div>
                      <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-2 text-center">
                        <div className="text-lg font-bold text-[#10b981]">{gaps.with_test}</div>
                        <div className="text-[10px] text-[#64748b] mt-0.5">有测试</div>
                      </div>
                      <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-2 text-center">
                        <div className="text-lg font-bold text-[#722ed1]">{gaps.with_evidence}</div>
                        <div className="text-[10px] text-[#64748b] mt-0.5">有证据</div>
                      </div>
                    </div>

                    {/* Coverage bar */}
                    {gaps.total > 0 && (
                      <div>
                        <div className="flex items-center justify-between text-[10px] text-[#64748b] mb-1">
                          <span>测试覆盖率</span>
                          <span>{Math.round((gaps.with_test / gaps.total) * 100)}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${(gaps.with_test / gaps.total) * 100}%`,
                              background: "#10b981",
                            }}
                          />
                        </div>
                      </div>
                    )}

                    {/* Gap list */}
                    <div>
                      <div className="text-xs text-[#94a3b8] mb-2 flex items-center gap-1.5">
                        <AlertCircle className="w-3 h-3 text-[#faad14]" />
                        缺口列表
                        <span className="text-[#64748b]">{gaps.gaps.length} 条</span>
                      </div>
                      {gaps.gaps.length === 0 ? (
                        <div className="py-4 text-center text-xs text-[#64748b]">
                          <div className="text-xl mb-1">🎉</div>
                          暂无缺口
                        </div>
                      ) : (
                        <div className="space-y-1.5">
                          {gaps.gaps.map((g) => (
                            <div
                              key={g.req_id}
                              className="flex items-center gap-2 rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-2.5 py-2"
                            >
                              <span className="text-xs font-mono text-[#722ed1] shrink-0">
                                {g.req_id}
                              </span>
                              <span className="flex gap-1 ml-auto shrink-0">
                                {g.missing.map((m) => (
                                  <Badge
                                    key={m}
                                    variant="outline"
                                    className="border-transparent text-[10px]"
                                    style={
                                      m === "test"
                                        ? { color: "#faad14", background: "#faad141f", borderColor: "#faad144d" }
                                        : { color: "#ff4d4f", background: "#ff4d4f1f", borderColor: "#ff4d4f4d" }
                                    }
                                  >
                                    缺{m === "test" ? "测试" : "证据"}
                                  </Badge>
                                ))}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="py-12 text-center text-[#64748b] text-sm">
                    <div className="text-2xl mb-2">📊</div>
                    暂无分析数据
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Footer hint */}
        <div className="mt-6 flex items-center gap-1 text-xs text-[#475569]">
          <FolderOpen className="w-3 h-3" />
          需求由 projects/&lt;项目&gt;/spec*.md 解析；追溯与差距分析扫描项目目录中引用需求编号的制品。
        </div>
      </div>
  </DashboardChrome>
  );
}

"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileDiff,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-fetch";

// ─── Types ────────────────────────────────────────────────────────────────

export interface BaselineListItem {
  name: string;
  label: string;
  author: string | null;
  pipeline_run: string | null;
  created_at: string | null;
  file_count: number;
  manifest_sha256: string | null;
}

export interface BaselineFile {
  path: string;
  sha256: string;
  size: number;
}

export interface BaselineDetail extends BaselineListItem {
  notes?: string;
  files: BaselineFile[];
}

export interface BaselineDiff {
  from: string;
  to: string;
  generated_at: string;
  added: string[];
  removed: string[];
  modified: Array<{ path: string; sha256_from: string; sha256_to: string }>;
  summary: { added: number; removed: number; modified: number; total_changes: number };
  evidence_path?: string;
}

interface BaselineDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端基线管理：创建配置基线、查看文件清单、比对两个基线的差异。 */
export function BaselineDialog({ open, onOpenChange, projectId }: BaselineDialogProps) {
  const [baselines, setBaselines] = useState<BaselineListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [creating, setCreating] = useState(false);

  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [diff, setDiff] = useState<BaselineDiff | null>(null);
  const [diffing, setDiffing] = useState(false);

  const [expanded, setExpanded] = useState<Record<string, BaselineDetail | "loading">>({});
  const [expandedOpen, setExpandedOpen] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ baselines: BaselineListItem[] }>(
        `/api/v1/desktop/projects/${projectId}/baselines`,
      );
      const items = data.baselines || [];
      setBaselines(items);
      // 默认对比「次新 → 最新」，没有两个基线时留空。
      setFrom((cur) => (items.some((b) => b.name === cur) ? cur : items[1]?.name ?? ""));
      setTo((cur) => (items.some((b) => b.name === cur) ? cur : items[0]?.name ?? ""));
    } catch (e) {
      setError((e as Error).message || "加载基线失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setBaselines([]);
    setDiff(null);
    setExpanded({});
    setExpandedOpen({});
    setError("");
    setNotice("");
    setName("");
    setLabel("");
    setNotes("");
    setFrom("");
    setTo("");
    load();
  }, [open, projectId, load]);

  const create = async () => {
    if (!projectId || creating) return;
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ baseline: BaselineListItem }>(
        `/api/v1/desktop/projects/${projectId}/baselines`,
        {
          method: "POST",
          body: JSON.stringify({
            ...(name.trim() ? { name: name.trim() } : {}),
            label: label.trim(),
            notes: notes.trim(),
          }),
        },
      );
      setNotice(`已创建基线 ${data.baseline.name}（${data.baseline.file_count} 个文件）`);
      setName("");
      setLabel("");
      setNotes("");
      await load();
    } catch (e) {
      // 同名基线会返回 409，直接展示后端文案
      setError((e as Error).message || "创建基线失败");
    } finally {
      setCreating(false);
    }
  };

  const compare = async () => {
    if (!projectId || diffing) return;
    if (!from || !to) {
      setError("请选择两个基线进行比对");
      return;
    }
    if (from === to) {
      setError("请选择两个不同的基线");
      return;
    }
    setDiffing(true);
    setError("");
    setNotice("");
    try {
      const qs = `from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
      const data = await apiFetch<{ diff: BaselineDiff }>(
        `/api/v1/desktop/projects/${projectId}/baselines/diff?${qs}`,
      );
      setDiff(data.diff);
    } catch (e) {
      setError((e as Error).message || "基线比对失败");
    } finally {
      setDiffing(false);
    }
  };

  const toggleDetail = async (b: BaselineListItem) => {
    if (!projectId) return;
    const isOpen = !!expandedOpen[b.name];
    setExpandedOpen((s) => ({ ...s, [b.name]: !isOpen }));
    if (isOpen || expanded[b.name]) return;
    setExpanded((s) => ({ ...s, [b.name]: "loading" }));
    try {
      const data = await apiFetch<{ baseline: BaselineDetail }>(
        `/api/v1/desktop/projects/${projectId}/baselines/${encodeURIComponent(b.name)}`,
      );
      setExpanded((s) => ({ ...s, [b.name]: data.baseline }));
    } catch (e) {
      setExpanded((s) => {
        const next = { ...s };
        delete next[b.name];
        return next;
      });
      setError((e as Error).message || "加载基线详情失败");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(94vw,980px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-[#1677ff]" /> 配置基线
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            对需求 / 设计 / 代码 / 测试等配置项做快照，并比对两个基线之间的变更。
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 space-y-3 overflow-y-auto scrollbar-dark pr-1" data-testid="baseline-dialog">
          {/* ── 新建基线 ─────────────────────────────────────────────── */}
          <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[#94a3b8]">
              <Plus className="w-3.5 h-3.5" /> 新建基线
            </div>
            <div className="grid gap-2 sm:grid-cols-[1fr_1fr_1.4fr_auto]">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="名称（留空自动生成）"
                data-testid="baseline-name"
                className="h-8 border-[#1e293b] bg-[#111827] text-xs"
              />
              <Input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="标签，如 R1.0"
                data-testid="baseline-label"
                className="h-8 border-[#1e293b] bg-[#111827] text-xs"
              />
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="备注（可选）"
                data-testid="baseline-notes"
                className="h-8 border-[#1e293b] bg-[#111827] text-xs"
              />
              <Button
                size="sm"
                onClick={create}
                disabled={!projectId || creating}
                data-testid="baseline-create"
                className="h-8 bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
              >
                {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "创建"}
              </Button>
            </div>
          </section>

          {error && (
            <div
              className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
              data-testid="baseline-error"
            >
              {error}
            </div>
          )}
          {notice && (
            <div
              className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]"
              data-testid="baseline-notice"
            >
              {notice}
            </div>
          )}

          {/* ── 基线列表 ─────────────────────────────────────────────── */}
          <section>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                基线列表（{baselines.length}）
              </span>
              <button
                type="button"
                onClick={load}
                disabled={!projectId || loading}
                title="刷新"
                className="text-[#64748b] hover:text-white disabled:opacity-50"
                data-testid="baseline-reload"
              >
                {loading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5" />
                )}
              </button>
            </div>

            {loading && baselines.length === 0 && (
              <div className="flex items-center justify-center gap-2 py-6 text-xs text-[#64748b]">
                <Loader2 className="w-4 h-4 animate-spin" /> 正在加载基线…
              </div>
            )}

            {!loading && baselines.length === 0 && (
              <div
                className="rounded-md border border-[#1e293b] px-3 py-6 text-center text-xs text-[#64748b]"
                data-testid="baseline-empty"
              >
                还没有基线。输入名称或留空后点「创建」，即可为当前配置项生成快照。
              </div>
            )}

            {baselines.length > 0 && (
              <table className="w-full text-left text-xs" data-testid="baseline-table">
                <thead>
                  <tr className="text-[11px] text-[#64748b]">
                    <th className="py-1.5 pr-2 font-medium">基线</th>
                    <th className="py-1.5 pr-2 font-medium">文件数</th>
                    <th className="py-1.5 pr-2 font-medium">作者 / 流水线</th>
                    <th className="py-1.5 pr-2 font-medium">创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {baselines.map((b) => {
                    const openRow = !!expandedOpen[b.name];
                    const detail = expanded[b.name];
                    return (
                      <Fragment key={b.name}>
                        <tr
                          data-testid={`baseline-row-${b.name}`}
                          onClick={() => toggleDetail(b)}
                          className="cursor-pointer border-t border-[#1e293b] hover:bg-[#111827]"
                        >
                          <td className="py-1.5 pr-2">
                            <div className="flex items-center gap-1">
                              {openRow ? (
                                <ChevronDown className="w-3 h-3 text-[#64748b]" />
                              ) : (
                                <ChevronRight className="w-3 h-3 text-[#64748b]" />
                              )}
                              <span className="font-mono text-[#e2e8f0]">{b.name}</span>
                              {b.label && (
                                <span className="rounded bg-[#1e293b] px-1.5 py-0.5 text-[10px] text-[#94a3b8]">
                                  {b.label}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-1.5 pr-2 tabular-nums text-[#94a3b8]">{b.file_count}</td>
                          <td className="py-1.5 pr-2 text-[#94a3b8]">
                            {b.author || "—"}
                            {b.pipeline_run ? ` · ${b.pipeline_run.slice(0, 8)}` : ""}
                          </td>
                          <td className="py-1.5 pr-2 text-[#64748b]">{fmtTime(b.created_at)}</td>
                        </tr>
                        {openRow && (
                          <tr key={`${b.name}-detail`} className="border-t border-[#1e293b] bg-[#0b1020]">
                            <td colSpan={4} className="px-3 py-2">
                              {detail === "loading" || detail === undefined ? (
                                <span className="text-[11px] text-[#64748b]">正在加载文件清单…</span>
                              ) : (
                                <div className="max-h-40 space-y-0.5 overflow-y-auto scrollbar-dark text-[11px]">
                                  {detail.files.length === 0 && (
                                    <span className="text-[#475569]">该基线没有配置文件。</span>
                                  )}
                                  {detail.files.map((f) => (
                                    <div key={f.path} className="flex items-center gap-2">
                                      <span className="font-mono text-[#94a3b8]">{f.path}</span>
                                      <span className="text-[#475569]">{f.sha256.slice(0, 8)}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </section>

          {/* ── 差异比对 ─────────────────────────────────────────────── */}
          <section className="rounded-md border border-[#1e293b] p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[#94a3b8]">
              <FileDiff className="w-3.5 h-3.5" /> 基线比对
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                data-testid="baseline-diff-from"
                className="h-8 rounded-md border border-[#1e293b] bg-[#111827] px-2 text-xs text-[#e2e8f0]"
              >
                <option value="">选择起点基线</option>
                {baselines.map((b) => (
                  <option key={b.name} value={b.name}>{b.name}</option>
                ))}
              </select>
              <ArrowRight className="w-3.5 h-3.5 text-[#64748b]" />
              <select
                value={to}
                onChange={(e) => setTo(e.target.value)}
                data-testid="baseline-diff-to"
                className="h-8 rounded-md border border-[#1e293b] bg-[#111827] px-2 text-xs text-[#e2e8f0]"
              >
                <option value="">选择终点基线</option>
                {baselines.map((b) => (
                  <option key={b.name} value={b.name}>{b.name}</option>
                ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                onClick={compare}
                disabled={!projectId || diffing || baselines.length < 2}
                data-testid="baseline-diff-run"
                className="h-8 border-[#1e293b] text-[#94a3b8] hover:text-white"
              >
                {diffing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : null}
                比对差异
              </Button>
              {baselines.length < 2 && (
                <span className="text-[11px] text-[#475569]">至少需要两个基线</span>
              )}
            </div>

            {diff && (
              <div className="mt-3 space-y-2" data-testid="baseline-diff-result">
                <div className="flex flex-wrap items-center gap-3 text-[11px]">
                  <span className="text-[#e2e8f0]">
                    {diff.from} <ArrowRight className="inline w-3 h-3 mx-1 text-[#64748b]" /> {diff.to}
                  </span>
                  <span className="rounded bg-[#10b981]/15 px-1.5 py-0.5 text-[#34d399]">
                    新增 {diff.summary.added}
                  </span>
                  <span className="rounded bg-[#ef4444]/15 px-1.5 py-0.5 text-[#f87171]">
                    删除 {diff.summary.removed}
                  </span>
                  <span className="rounded bg-[#f59e0b]/15 px-1.5 py-0.5 text-[#fbbf24]">
                    修改 {diff.summary.modified}
                  </span>
                  <span className="text-[#64748b]">共 {diff.summary.total_changes} 处变更</span>
                </div>

                {diff.summary.total_changes === 0 ? (
                  <div className="flex items-center gap-1 text-[11px] text-[#34d399]">
                    <CheckCircle2 className="w-3.5 h-3.5" /> 两个基线完全一致。
                  </div>
                ) : (
                  <div className="space-y-1 text-[11px]">
                    <DiffGroup title="新增" tone="add" items={diff.added} />
                    <DiffGroup title="删除" tone="remove" items={diff.removed} />
                    <DiffGroup
                      title="修改"
                      tone="modify"
                      items={diff.modified.map((m) => m.path)}
                    />
                  </div>
                )}

                {diff.evidence_path && (
                  <div className="text-[11px] text-[#475569]">
                    差异证据已归档：{diff.evidence_path}
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function DiffGroup({
  title,
  tone,
  items,
}: {
  title: string;
  tone: "add" | "remove" | "modify";
  items: string[];
}) {
  if (items.length === 0) return null;
  const color =
    tone === "add" ? "text-[#34d399]" : tone === "remove" ? "text-[#f87171]" : "text-[#fbbf24]";
  return (
    <div>
      <div className={`mb-0.5 ${color}`}>{title}（{items.length}）</div>
      <div className="max-h-32 space-y-0.5 overflow-y-auto scrollbar-dark pl-2 font-mono text-[#94a3b8]">
        {items.map((p) => (
          <div key={p}>{p}</div>
        ))}
      </div>
    </div>
  );
}

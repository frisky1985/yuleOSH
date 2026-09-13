"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Play, ChevronDown, Check, Loader2, ArrowRight } from "lucide-react";
import { apiFetch } from "@/lib/api-fetch";

interface RunnableProject {
  id?: string | number;
  name: string;
  path: string;
  spec: string;
}

interface SelectedProjectLite {
  id: string;
  name: string;
  slug: string;
}

/**
 * 主 dashboard 顶部「运行 Pipeline」按钮：
 *  - 主按钮：直接触发「当前选中项目」的 LLM 流水线（POST /api/v1/pipeline/run）。
 *    触发后我们已建的项目索引（1s 轮询 + ActiveProjectsCard / LiveSyncBar）会
 *    立即实时回显「后台运行中」，无需离开概览页。
 *  - 下拉箭头：列出全部可运行项目（demo/template + 用户自建），可换一个跑；
 *    底部保留「高级运行控制」入口（/dashboard/pipeline 的重跑/勾选/续跑/停止）。
 *
 * 与既有「CLI 后台跑」统一：无论 UI 触发还是 CLI 跑，session 都落在
 * project_dir/.osh/sessions，被 discover_project_sessions 聚合到同一项目索引。
 */
export function RunPipelineButton({
  project,
  onStarted,
}: {
  project?: SelectedProjectLite | null;
  onStarted?: (info: { name: string; run_id: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [list, setList] = useState<RunnableProject[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch<{
        runnable_projects?: RunnableProject[];
        user_projects?: RunnableProject[];
      }>("/api/v1/pipeline/list");
      const merged = [
        ...(res.user_projects || []),
        ...(res.runnable_projects || []),
      ];
      setList(merged);
    } catch {
      setFlash({ kind: "err", text: "无法获取可运行项目列表" });
    } finally {
      setLoading(false);
    }
  }, []);

  const run = useCallback(
    async (p: RunnableProject) => {
      setRunning(true);
      setFlash(null);
      try {
        const res = await apiFetch<{
          run_id: string;
          name: string;
          status: string;
        }>("/api/v1/pipeline/run", {
          method: "POST",
          body: JSON.stringify({
            spec: p.spec || undefined,
            project_dir: p.path,
            name: p.name,
          }),
        });
        setFlash({
          kind: "ok",
          text: `已启动：${res.name}（${res.run_id}）· 看板实时刷新中`,
        });
        onStarted?.({ name: res.name, run_id: res.run_id });
        setOpen(false);
      } catch (e) {
        setFlash({
          kind: "err",
          text: (e as Error)?.message || "启动失败",
        });
      } finally {
        setRunning(false);
      }
    },
    [onStarted],
  );

  // 当前选中项目是否能在可运行列表里匹配上（用户项目按 id，demo 按 slug/目录名）
  const match = project
    ? list.find(
        (p) =>
          (p.id != null && String(p.id) === String(project.id)) ||
          p.name === project.slug ||
          p.path.endsWith("/" + project.slug) ||
          p.path.endsWith(project.slug),
      )
    : undefined;

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && list.length === 0) void load();
  };

  // 点击外部关闭
  useEffect(() => {
    const h = (ev: MouseEvent) => {
      if (ref.current && !ref.current.contains(ev.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  // flash 自动消失
  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 5000);
    return () => clearTimeout(t);
  }, [flash]);

  // 选中项目后预载可运行列表（仅一次），让主按钮首次点击即可直接触发当前项目，
  // 不必先弹下拉等待加载。
  useEffect(() => {
    if (project && list.length === 0 && !loading) void load();
  }, [project, list.length, loading, load]);

  const isSel = (p: RunnableProject) =>
    (p.id != null && String(p.id) === String(project?.id)) ||
    p.path.endsWith("/" + (project?.slug || "__none__")) ||
    p.path.endsWith(project?.slug || "__none__");

  return (
    <div className="relative" ref={ref}>
      <div className="flex items-stretch rounded-md overflow-hidden border border-[#1e293b]">
        <button
          type="button"
          disabled={running || !project}
          onClick={() => {
            if (match) void run(match);
            else toggle();
          }}
          title={
            project
              ? `运行「${project.name}」的 LLM 流水线`
              : "请先在上方选择项目"
          }
          className="flex items-center gap-2 px-3 py-1.5 text-xs text-[#94a3b8] hover:text-white hover:bg-[#1e293b] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {running ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          运行 Pipeline
        </button>
        <button
          type="button"
          onClick={toggle}
          aria-label="选择要运行的项目"
          className="px-1.5 text-[#64748b] hover:text-white hover:bg-[#1e293b] border-l border-[#1e293b] transition-colors"
        >
          <ChevronDown className="w-3.5 h-3.5" />
        </button>
      </div>

      {open && (
        <div className="absolute right-0 mt-1 w-80 max-h-80 overflow-auto z-50 rounded-lg border border-[#1e293b] bg-[#0b1220] shadow-xl">
          <div className="px-3 py-2 text-[10px] text-[#64748b] border-b border-[#1e293b]">
            选择要运行 LLM 流水线的项目
          </div>
          {loading && (
            <div className="p-3 text-xs text-[#64748b] flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" /> 加载项目…
            </div>
          )}
          {!loading && list.length === 0 && (
            <div className="p-3 text-xs text-[#64748b]">
              无可运行项目（需含 docs/spec.md）
            </div>
          )}
          {!loading &&
            list.map((p) => (
              <button
                key={p.path}
                type="button"
                disabled={running}
                onClick={() => void run(p)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs text-[#cbd5e1] hover:bg-[#1e293b] disabled:opacity-50 transition-colors"
              >
                <span className="truncate">
                  {p.name}
                  {!p.spec && (
                    <span className="text-[#64748b]">（无 spec，将惰性创建）</span>
                  )}
                </span>
                {isSel(p) && <Check className="w-3 h-3 text-[#10b981] flex-shrink-0" />}
              </button>
            ))}
          <Link
            href="/dashboard/pipeline"
            className="flex items-center justify-between gap-2 px-3 py-2 text-xs text-[#1677ff] hover:bg-[#1677ff]/5 border-t border-[#1e293b]"
          >
            高级运行控制（重跑 / 勾选 / 续跑 / 停止）
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      )}

      {flash && (
        <div
          className={`absolute right-0 mt-1 w-80 z-50 rounded-md border px-3 py-2 text-[10px] ${
            flash.kind === "ok"
              ? "border-[#10b981]/30 bg-[#10b981]/10 text-[#95de64]"
              : "border-[#ff4d4f]/30 bg-[#ff4d4f]/10 text-[#ff7875]"
          }`}
        >
          {flash.text}
        </div>
      )}
    </div>
  );
}

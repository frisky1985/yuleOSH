"use client";

import { AlertCircle, CheckCircle2, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { TaskStageProgress } from "@/components/dashboard/task-stage-progress";
import type { EvidenceTask } from "@/lib/api";

// 证据生成任务阶段（前端按 progressPct 自动映射；真实 CLI 路径只在 10%/100%
// 跳变，因此阶段 2-4 在真实路径下会一直停在「进行中」等子进程返回）。
const EVIDENCE_STAGES = [
  "准备",
  "收集证据",
  "生成清单",
  "打包并写入",
  "完成",
];
const EVIDENCE_BREAKPOINTS = [0, 10, 30, 60, 95, 100];

export function EvidenceModal({
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
          {/* 阶段进度：准备→收集→生成清单→打包→完成 */}
          <div className="mb-4">
            <TaskStageProgress
              stages={EVIDENCE_STAGES}
              breakpoints={EVIDENCE_BREAKPOINTS}
              progressPct={progress}
              isFailed={isFailed}
            />
          </div>

          {/* 状态详情 */}
          {isCompleted && task?.note && (
            <div className="rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-3 py-2 text-xs text-[#faad14] mb-3">
              {task.note}
            </div>
          )}

          {isFailed && task?.error && (
            <div className="rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-3 py-2 text-xs text-[#ff4d4f] break-words mb-3">
              {task.error}
            </div>
          )}

          {isCompleted && task?.download_url && (
            <div className="rounded-lg bg-[#10b981]/10 border border-[#10b981]/20 px-3 py-2 text-xs text-[#10b981] mb-3">
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


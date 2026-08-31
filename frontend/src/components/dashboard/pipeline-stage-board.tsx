// Pipeline Stage Board — recreated from the archived dashboard-v5.html Phase/Stage kanban.
// Design reference: src/yuleosh/ui/pages/_archive/dashboard-v5.html
//
// The old page rendered the yuleOSH ASPICE SWE automation pipeline as a 3-phase ×
// 3-stage gated board (质量预检 / 代码与测试 / 构建与交付). That page was a
// self-contained file with broken nav links, so it was archived. This component
// reproduces the SAME board as a real Next.js dashboard widget, keeping the unique
// visualization while living inside the unified /dashboard app (no more dead links).
import {
  Activity,
  BarChart3,
  ClipboardList,
  Cpu,
  FlaskConical,
  Hammer,
  MonitorPlay,
  Package,
  Search,
  Zap,
  type LucideIcon,
} from "lucide-react";

interface PipelineStage {
  num: number;
  icon: LucideIcon;
  title: string;
  meta: string;
  gated: boolean;
}

interface PipelinePhase {
  key: string;
  label: string;
  enName: string;
  accent: {
    labelBg: string;
    labelText: string;
    labelBorder: string;
    borderHex: string;
  };
  stages: PipelineStage[];
}

// Pipeline definition mirrors dashboard-v5.html stages 0–8.
const PHASES: PipelinePhase[] = [
  {
    key: "preflight",
    label: "质量预检",
    enName: "Pre-flight Coverage & Parsing",
    accent: {
      labelBg: "bg-[#722ed1]/12",
      labelText: "text-[#722ed1]",
      labelBorder: "border-[#722ed1]/25",
      borderHex: "#722ed1",
    },
    stages: [
      { num: 0, icon: BarChart3, title: "Spec Validation", meta: "需求覆盖率 100%", gated: true },
      { num: 1, icon: ClipboardList, title: "Plan Lint", meta: "Sprint 计划合规", gated: false },
      { num: 2, icon: Search, title: "Clang-Tidy", meta: "C 代码静态检查", gated: false },
    ],
  },
  {
    key: "codetest",
    label: "代码与测试",
    enName: "Unit Tests & Coverage",
    accent: {
      labelBg: "bg-[#1677ff]/12",
      labelText: "text-[#1677ff]",
      labelBorder: "border-[#1677ff]/25",
      borderHex: "#1677ff",
    },
    stages: [
      { num: 3, icon: FlaskConical, title: "Unit Tests", meta: "1020+ tests", gated: true },
      { num: 4, icon: BarChart3, title: "Coverage Check", meta: "≥ 85% 门禁", gated: true },
      { num: 5, icon: MonitorPlay, title: "SIL Tests", meta: "QEMU 仿真验证", gated: false },
    ],
  },
  {
    key: "build",
    label: "构建与交付",
    enName: "Build, HIL & Evidence",
    accent: {
      labelBg: "bg-[#10b981]/12",
      labelText: "text-[#10b981]",
      labelBorder: "border-[#10b981]/25",
      borderHex: "#10b981",
    },
    stages: [
      { num: 6, icon: Hammer, title: "Cross-Compile", meta: "ARM / RISC-V", gated: false },
      { num: 7, icon: Cpu, title: "HIL Tests", meta: "OpenOCD / JLink", gated: true },
      { num: 8, icon: Package, title: "Evidence Pack", meta: "追溯矩阵 + 验收报告", gated: true },
    ],
  },
];

export function PipelineStageBoard() {
  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#722ed1]" />
          合规流水线 · 阶段看板
        </h2>
        <span className="text-[10px] text-[#64748b] hidden sm:inline">
          ASPICE SWE 自动化流水线 · 9 阶段
        </span>
      </div>

      <div className="space-y-5">
        {PHASES.map((phase) => (
          <div key={phase.key}>
            <div
              className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 mb-3 text-xs font-semibold border ${phase.accent.labelBg} ${phase.accent.labelText} ${phase.accent.labelBorder}`}
            >
              <span>{phase.label}</span>
              <span className="opacity-60 font-normal">{phase.enName}</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {phase.stages.map((stage) => {
                const Icon = stage.icon;
                return (
                  <div
                    key={stage.num}
                    className={`relative rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3.5 hover:border-[#722ed1]/40 transition-colors border-l-[3px] ${
                      stage.gated
                        ? "border-l-[#faad14] bg-[#faad14]/[0.04]"
                        : ""
                    }`}
                    style={
                      stage.gated
                        ? undefined
                        : { borderLeftColor: phase.accent.borderHex }
                    }
                  >
                    {stage.gated && (
                      <span
                        className="absolute top-2.5 right-2.5 inline-flex items-center gap-1 text-[10px] font-medium text-[#faad14] bg-[#faad14]/10 border border-[#faad14]/20 rounded px-1.5 py-0.5"
                        title="带门禁：未通过则阻断后续阶段"
                      >
                        <Zap className="w-3 h-3" />
                        门禁
                      </span>
                    )}
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-md bg-[#1e293b] flex items-center justify-center shrink-0">
                        <Icon className="w-4 h-4 text-[#94a3b8]" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-[#64748b] font-mono">
                            #{stage.num}
                          </span>
                          <span className="text-sm font-medium text-[#e2e8f0] truncate">
                            {stage.title}
                          </span>
                        </div>
                        <div className="text-[11px] text-[#64748b] mt-0.5 truncate">
                          {stage.meta}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

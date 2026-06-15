'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';

// ── Mock pipeline data (no backend API needed) ──────────────────────────
interface Step {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  output_summary: string;
  duration_ms: number;
  artifacts: Record<string, number | string>;
}

interface FinalReport {
  summary: string;
  coverage_prediction: string;
  review_score: string;
  compliance_gates: {
    aspice: string;
    misra: string;
    unit_test: string;
  };
}

interface PipelineData {
  status: string;
  pipeline_id: string;
  total_steps: number;
  current_step: number;
  steps: Step[];
  final_report: FinalReport | null;
  evidence_pack_url: string;
}

const DEMO_STEPS: Step[] = [
  {
    id: 'spec-parse',
    name: 'Spec Parsing',
    status: 'pending',
    output_summary: 'Parsed OpenSpec document: 5 requirements, 3 scenarios detected.',
    duration_ms: 0,
    artifacts: { requirements_count: 5, scenarios_count: 3 },
  },
  {
    id: 'requirements-analysis',
    name: 'Requirements Analysis',
    status: 'pending',
    output_summary: 'Analysis complete: 5 SHALL statements, 0 conflicts, 2 dependencies.',
    duration_ms: 0,
    artifacts: { requirements_analyzed: 5, dependencies: 2 },
  },
  {
    id: 'sdd',
    name: 'System Design Document',
    status: 'pending',
    output_summary: 'Generated SDD: 3 modules, 8 interfaces, 12 data flows.',
    duration_ms: 0,
    artifacts: { modules: 3, interfaces: 8, data_flows: 12 },
  },
  {
    id: 'code-gen',
    name: 'Code Generation',
    status: 'pending',
    output_summary: 'Generated 4 source files, 2 header files, 1 CMakeLists.txt.',
    duration_ms: 0,
    artifacts: { source_files: 4, header_files: 2, build_files: 1 },
  },
  {
    id: 'internal-review',
    name: 'Internal Review',
    status: 'pending',
    output_summary: '52 issues found: 3 errors, 12 warnings, 37 suggestions.',
    duration_ms: 0,
    artifacts: { errors: 3, warnings: 12, suggestions: 37 },
  },
  {
    id: 'test-plan',
    name: 'Test Plan Generation',
    status: 'pending',
    output_summary: 'Generated 18 test cases across 4 test suites.',
    duration_ms: 0,
    artifacts: { test_cases: 18, test_suites: 4 },
  },
  {
    id: 'code-review',
    name: 'Code Review (4-Agent Matrix)',
    status: 'pending',
    output_summary: '4 agents reviewed: quality 8.4/10, security 9.1/10, style 7.8/10, safety 8.9/10.',
    duration_ms: 0,
    artifacts: {
      quality_score: 8.4,
      security_score: 9.1,
      style_score: 7.8,
      safety_score: 8.9,
    },
  },
  {
    id: 'ci-layer1',
    name: 'CI Layer 1 — Unit Test',
    status: 'pending',
    output_summary: '18/20 tests passed, 83.7% line coverage.',
    duration_ms: 0,
    artifacts: { tests_passed: 18, tests_total: 20, coverage_pct: 83.7 },
  },
  {
    id: 'ci-layer2',
    name: 'CI Layer 2 — Cross-Compile + Static Analysis',
    status: 'pending',
    output_summary: 'ARM GCC cross-compile: PASS. MISRA: 3 warnings, 0 errors.',
    duration_ms: 0,
    artifacts: { cross_compile: 'pass', misra_warnings: 3, misra_errors: 0 },
  },
  {
    id: 'ci-layer3',
    name: 'CI Layer 3 — System Verification + Evidence Pack',
    status: 'pending',
    output_summary: 'All verification gates passed. Evidence pack generated.',
    duration_ms: 0,
    artifacts: { gates_passed: 5, evidence_files: 6 },
  },
];

const FINAL_REPORT: FinalReport = {
  summary:
    '## Demo Pipeline Results\n\n' +
    'The yuleOSH pipeline completed successfully for the embedded C project.\n\n' +
    '### Key Metrics\n' +
    '- **Spec Coverage**: 100% (5/5 requirements covered by scenarios)\n' +
    '- **Code Quality**: 8.4/10 (4-agent matrix review)\n' +
    '- **Test Coverage**: 83.7% line coverage (18/20 tests passing)\n' +
    '- **MISRA Compliance**: 3 warnings, 0 errors\n' +
    '- **Cross-Compile**: ARM GCC target build passed\n\n' +
    '### Pipeline Summary\n' +
    'All 10 pipeline steps completed in approximately 39.8 seconds (simulated).\n' +
    'The evidence pack is ready for download.\n',
  coverage_prediction: '72%',
  review_score: '8.4/10',
  compliance_gates: {
    aspice: 'passed',
    misra: '3 warnings',
    unit_test: '18/20 passed',
  },
};

const SIMULATED_DURATIONS = [1200, 2400, 3800, 5100, 2900, 1600, 6200, 4100, 8800, 3500];

const STEP_COLORS: Record<string, string> = {
  pending: 'border-gray-700 text-gray-500',
  running: 'border-blue-500 text-blue-400',
  completed: 'border-green-500 text-green-400',
  failed: 'border-red-500 text-red-400',
};

const STEP_BG: Record<string, string> = {
  pending: 'bg-gray-800',
  running: 'bg-blue-900/20',
  completed: 'bg-green-900/20',
  failed: 'bg-red-900/20',
};

const AGENT_ICONS: Record<string, string> = {
  'spec-parse': '📋',
  'requirements': '🤖',
  'sdd': '🏗️',
  'code-gen': '💻',
  'internal-review': '👁️',
  'test-plan': '🧪',
  'code-review': '👁️',
  'ci-layer1': '🧪',
  'ci-layer2': '🔧',
  'ci-layer3': '📦',
};

function getAgentIcon(id: string): string {
  for (const [key, icon] of Object.entries(AGENT_ICONS)) {
    if (id.includes(key)) return icon;
  }
  return '⚡';
}

/** Generate a unique pipeline ID locally (no server). */
function generatePipelineId(): string {
  const rand = Math.random().toString(36).substring(2, 14);
  return `demo-${rand}`;
}

export default function DemoPage() {
  const [pipeline, setPipeline] = useState<PipelineData | null>(null);
  const [started, setStarted] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stepIndexRef = useRef(0);
  const pipelineIdRef = useRef(generatePipelineId());

  const startDemo = useCallback(() => {
    // Reset state
    stepIndexRef.current = 0;
    pipelineIdRef.current = generatePipelineId();

    const initialSteps = DEMO_STEPS.map((s) => ({ ...s, status: 'pending' as const, duration_ms: 0 }));
    const initialPipeline: PipelineData = {
      status: 'running',
      pipeline_id: pipelineIdRef.current,
      total_steps: DEMO_STEPS.length,
      current_step: 0,
      steps: initialSteps,
      final_report: null,
      evidence_pack_url: '',
    };

    setPipeline(initialPipeline);
    setStarted(true);

    // Clear any previous interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }

    // Simulate progress with a timer (advance one step per tick)
    intervalRef.current = setInterval(() => {
      const idx = stepIndexRef.current;

      if (idx >= DEMO_STEPS.length) {
        // All done
        if (intervalRef.current) clearInterval(intervalRef.current);
        return;
      }

      // Mark current step as running
      setPipeline((prev) => {
        if (!prev) return prev;
        const updated = prev.steps.map((s, i) => {
          if (i === idx) return { ...s, status: 'running' as const };
          return s;
        });
        return { ...prev, steps: updated, current_step: idx };
      });

      // After a realistic delay, mark step as completed and advance
      const delay = SIMULATED_DURATIONS[idx] || 2000;
      stepIndexRef.current = idx + 1;

      setTimeout(() => {
        setPipeline((prev) => {
          if (!prev) return prev;
          const newIdx = idx;
          const isLast = newIdx + 1 >= DEMO_STEPS.length;
          const updated = prev.steps.map((s, i) => {
            if (i === newIdx) {
              return { ...s, status: 'completed' as const, duration_ms: SIMULATED_DURATIONS[newIdx] || 0 };
            }
            return s;
          });

          return {
            ...prev,
            status: isLast ? 'completed' : 'running',
            current_step: newIdx + 1,
            steps: updated,
            final_report: isLast ? FINAL_REPORT : null,
            evidence_pack_url: isLast ? `/api/v1/demo/evidence/${prev.pipeline_id}.zip` : '',
          };
        });
      }, delay);
    }, 200); // Check every 200ms — the actual step timing is in setTimeout
  }, []);

  // Auto-start on mount
  useEffect(() => {
    if (!started && !pipeline) {
      startDemo();
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const progress = pipeline
    ? Math.round((pipeline.current_step / pipeline.total_steps) * 100)
    : 0;

  return (
    <main className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-950 to-black text-white">
      <div className="max-w-4xl mx-auto px-4 py-12">
        <header className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-3 bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            yuleOSH Pipeline Demo
          </h1>
          <p className="text-gray-400">
            AI 驱动的嵌入式开发全流程 — 从需求到证据包，一键自动化
          </p>
        </header>

        {/* Initial loading state */}
        {!pipeline && (
          <div className="text-center py-20">
            <div className="inline-block w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-gray-400">启动 Pipeline...</p>
          </div>
        )}

        {pipeline && (
          <>
            {/* Progress bar */}
            <div className="bg-gray-800 rounded-full h-3 mb-8 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-purple-600 transition-all duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="flex justify-between text-sm text-gray-500 mb-8">
              <span>{pipeline.current_step}/{pipeline.total_steps} 步骤完成</span>
              <span className={pipeline.status === 'completed' ? 'text-green-400' : 'text-blue-400'}>
                {pipeline.status === 'completed' ? '✅ 已完成' : '⏳ 运行中...'}
              </span>
            </div>

            {/* Steps */}
            <div className="space-y-3 mb-12">
              {pipeline.steps.map((step) => (
                <div
                  key={step.id}
                  className={`rounded-xl border p-4 transition-all duration-500 ${STEP_BG[step.status]} ${STEP_COLORS[step.status]}`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{getAgentIcon(step.id)}</span>
                    <div className="flex-1">
                      <div className="font-semibold">{step.name}</div>
                      {step.output_summary && (
                        <div className="text-sm mt-1 opacity-70">{step.output_summary}</div>
                      )}
                    </div>
                    <div className="text-right">
                      <div className="text-xs opacity-50">
                        {step.duration_ms ? `${(step.duration_ms / 1000).toFixed(1)}s` : ''}
                      </div>
                      <div className="text-xs mt-1">
                        {step.status === 'completed' ? '✅' : step.status === 'running' ? '⏳' : step.status === 'failed' ? '❌' : '⏸️'}
                      </div>
                    </div>
                  </div>
                  {step.artifacts && Object.keys(step.artifacts).length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-700/50 text-xs flex gap-3 flex-wrap">
                      {Object.entries(step.artifacts).map(([key, val]) => (
                        <span key={key} className="bg-gray-700/50 px-2 py-1 rounded">
                          {key}: {String(val)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* CTA */}
            {pipeline.status === 'completed' && (
              <div className="text-center bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-800/50 rounded-2xl p-8">
                <h2 className="text-2xl font-bold mb-2">🎉 Pipeline 运行完成！</h2>
                <p className="text-gray-400 mb-6">
                  从 Spec 到 Evidence Pack，全流程 AI 自动化。
                  注册即可解锁完整功能。
                </p>
                <div className="flex gap-4 justify-center">
                  <Link
                    href="/pricing"
                    className="px-8 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 rounded-xl font-semibold transition"
                  >
                    查看定价 →
                  </Link>
                  <button
                    onClick={startDemo}
                    className="px-8 py-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-xl font-semibold transition"
                  >
                    重新运行
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

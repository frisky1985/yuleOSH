'use client';

import { useReducer, useEffect, useCallback, useState } from 'react';

/* ─── Types ─── */

interface StepDef {
  index: number;
  key: string;
  agent: string;
  name: string;
}

interface Step extends StepDef {
  status: 'pending' | 'running' | 'completed';
  summary: string;
  duration: number;
}

type Phase = 'idle' | 'running' | 'complete';

/* ─── Constants ─── */

const STEP_ICONS: Record<string, string> = {
  'spec-check':         '📋',
  'super-analysis':     '🤖',
  'prd':                '📄',
  'prd-review':         '👁️',
  'architecture':       '🏗️',
  'arch-review':        '🔎',
  'development':        '💻',
  'devplan-review':     '📝',
  'internal-code-review':'🔍',
  'test-planning':      '🧪',
  'self-test':          '✅',
  'self-test-review':   '📊',
  'c-unit-test':        '⚙️',
  'integration-test':   '🔗',
  'code-review':        '👓',
  'misra-review':       '📏',
  'coverage-review':    '🎯',
  'review-linker':      '🔗',
  'review-startup':     '🚀',
  'review-rtos':        '⚡',
  'review-memory':      '🧠',
  'review-bsp':         '🔌',
  'review-build':       '🛠️',
  'review-power':       '🔋',
  'review-stack':       '📐',
  'review-mmio':        '🔢',
  'test-qualification': '🏁',
  'final-report':       '📊',
};

const OUTRO_SUMMARIES: Record<string, string> = {
  'spec-check':         'Parsed OpenSpec document: all requirements and scenarios detected.',
  'super-analysis':     'S.U.P.E.R analysis: Strengths=4, Weaknesses=2, Opportunities=3.',
  'prd':                'PRD generated with user stories and acceptance criteria.',
  'prd-review':         'PRD review passed: all requirements clear and testable.',
  'architecture':       'C4 L2 diagram: components and interfaces defined.',
  'arch-review':        'Architecture review passed: no design flaws found.',
  'development':        'Implemented source files, 100% lint pass.',
  'devplan-review':     'Development plan review: milestones and deliverables confirmed.',
  'internal-code-review':'Code pre-review: 2 style suggestions, 0 blockers.',
  'test-planning':      'Test plan: unit, integration, and qualification test suites defined.',
  'self-test':          'All self-tests passed. Coverage targets met.',
  'self-test-review':   'Self-test review: results verified and documented.',
  'c-unit-test':        'C unit tests (Unity): all test cases passed.',
  'integration-test':   'Integration tests: all interface tests passed.',
  'code-review':        'Code review: approved with minor suggestions.',
  'misra-review':       'MISRA compliance: all mandatory rules checked.',
  'coverage-review':    'Coverage review: above threshold for all modules.',
  'review-linker':      'Linker script review: memory layout verified.',
  'review-startup':     'Startup code review: boot sequence validated.',
  'review-rtos':        'RTOS config review: task priorities and stack sizes correct.',
  'review-memory':      'Memory safety review: no buffer overflows detected.',
  'review-bsp':         'BSP review: board support package verified.',
  'review-build':       'Build verification: no warnings, reproducible build.',
  'review-power':       'Power review: low-power modes and consumption OK.',
  'review-stack':       'Stack analysis: worst-case usage within limits.',
  'review-mmio':        'MMIO review: memory-mapped IO registers validated.',
  'test-qualification': 'Qualification tests: all pass criteria met.',
  'final-report':       'Evidence pack generated: artifacts and reports compiled.',
};

/* ─── Step duration: faster for simpler steps, slower for complex ones ─── */
function getDefaultDuration(stepKey: string): number {
  // Simpler steps
  if (['spec-check', 'prd-review', 'arch-review', 'devplan-review',
       'self-test-review', 'review-linker', 'review-startup',
       'review-rtos', 'review-memory', 'review-bsp', 'review-build',
       'review-power', 'review-stack', 'review-mmio'].includes(stepKey)) {
    return 400;
  }
  // Medium steps
  if (['super-analysis', 'internal-code-review', 'test-planning',
       'self-test', 'coverage-review', 'misra-review'].includes(stepKey)) {
    return 700;
  }
  // Complex steps
  if (['prd', 'architecture', 'development', 'code-review',
       'c-unit-test', 'integration-test', 'test-qualification'].includes(stepKey)) {
    return 1000;
  }
  // Final report
  if (stepKey === 'final-report') return 500;
  return 600;
}

/* ─── Reducer ─── */

interface State {
  phase: Phase;
  stepDefs: StepDef[];
  steps: Step[];
}

type Action =
  | { type: 'SET_DEFS'; stepDefs: StepDef[] }
  | { type: 'START' }
  | { type: 'MARK_RUNNING'; index: number }
  | { type: 'MARK_COMPLETED'; index: number; summary: string }
  | { type: 'FINISH' };

function initState(): State {
  return { phase: 'idle', stepDefs: [], steps: [] };
}

function steplize(defs: StepDef[]): Step[] {
  return defs.map((d) => ({
    ...d,
    status: 'pending' as const,
    summary: '',
    duration: getDefaultDuration(d.key),
  }));
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_DEFS':
      return { ...state, stepDefs: action.stepDefs, steps: steplize(action.stepDefs) };

    case 'START':
      return { ...state, phase: 'running', steps: steplize(state.stepDefs) };

    case 'MARK_RUNNING':
      return {
        ...state,
        phase: 'running',
        steps: state.steps.map((s, i) =>
          i === action.index
            ? { ...s, status: 'running' as const }
            : i < action.index
              ? { ...s, status: 'completed' as const }
              : { ...s, status: 'pending' as const }
        ),
      };

    case 'MARK_COMPLETED':
      return {
        ...state,
        steps: state.steps.map((s, i) =>
          i === action.index ? { ...s, status: 'completed' as const, summary: action.summary } : s
        ),
      };

    case 'FINISH':
      return { ...state, phase: 'complete' as const };

    default:
      return state;
  }
}

/* ─── Component ─── */

export default function DemoPage() {
  const [state, dispatch] = useReducer(reducer, undefined, initState);
  const [error, setError] = useState<string | null>(null);
  const { phase, steps } = state;
  const stepDefs = state.stepDefs;

  /* ── Fetch pipeline steps from backend ── */
  useEffect(() => {
    fetch('/api/v1/pipeline/steps')
      .then((r) => r.json())
      .then((data) => {
        if (data.ok && data.data) {
          dispatch({ type: 'SET_DEFS', stepDefs: data.data.steps });
        } else {
          // Fallback: use hardcoded list
          dispatch({ type: 'SET_DEFS', stepDefs: FALLBACK_STEPS });
        }
      })
      .catch(() => {
        dispatch({ type: 'SET_DEFS', stepDefs: FALLBACK_STEPS });
      });
  }, []);

  /* ── Pipeline runner ── */
  useEffect(() => {
    if (phase !== 'running' || steps.length === 0) return;

    let currentStep = 0;
    let runningTimer: ReturnType<typeof setTimeout>;
    let gapTimer: ReturnType<typeof setTimeout>;

    function scheduleNext() {
      if (currentStep >= steps.length) {
        dispatch({ type: 'FINISH' });
        return;
      }

      dispatch({ type: 'MARK_RUNNING', index: currentStep });

      const dur = steps[currentStep].duration;

      runningTimer = setTimeout(() => {
        dispatch({
          type: 'MARK_COMPLETED',
          index: currentStep,
          summary: OUTRO_SUMMARIES[steps[currentStep].key] || '',
        });
        currentStep++;
        gapTimer = setTimeout(scheduleNext, 200);
      }, dur);
    }

    scheduleNext();
    return () => {
      clearTimeout(runningTimer);
      clearTimeout(gapTimer);
    };
  }, [phase, steps.length]);

  const handleStart = useCallback(() => {
    dispatch({ type: 'START' });
  }, []);

  const completed = steps.filter((s) => s.status === 'completed').length;
  const currentlyRunning = steps.filter((s) => s.status === 'running').length;
  const progress = steps.length > 0
    ? Math.round(((completed + currentlyRunning) / steps.length) * 100)
    : 0;

  return (
    <main className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-950 to-black text-white">
      <div className="max-w-4xl mx-auto px-4 py-12">
        <header className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-3 bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            yuleOSH Pipeline Demo
          </h1>
          <p className="text-gray-400">
            AI 驱动的嵌入式开发全流程 — 从需求到证据包，{steps.length} 步一键自动化
          </p>
        </header>

        {phase === 'idle' && steps.length === 0 && (
          <div className="text-center py-10">
            <div className="animate-pulse text-gray-500">加载步骤定义中...</div>
          </div>
        )}

        {phase === 'idle' && steps.length > 0 && (
          <div className="text-center py-20">
            <div className="text-6xl mb-6">🚀</div>
            <h2 className="text-2xl font-bold mb-4">准备好体验了吗？</h2>
            <p className="text-gray-400 mb-2">共 {steps.length} 步全流程，AI 自动编排</p>
            <p className="text-gray-500 text-sm mb-8">点击下方按钮启动模拟 Pipeline</p>
            <button
              onClick={handleStart}
              className="px-8 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 rounded-xl font-semibold text-lg transition shadow-lg shadow-purple-500/20"
            >
              🎮 启动 Demo
            </button>
          </div>
        )}

        {(phase === 'running' || phase === 'complete') && (
          <>
            <div className="bg-gray-800 rounded-full h-3 mb-4 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-purple-600 transition-all duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="flex justify-between text-sm text-gray-500 mb-8">
              <span>{completed}/{steps.length} 步骤完成</span>
              <span className={phase === 'complete' ? 'text-green-400' : 'text-blue-400'}>
                {phase === 'complete' ? '✅ 已完成' : '⏳ 运行中...'}
              </span>
            </div>

            <div className="space-y-2 mb-12">
              {steps.map((step) => (
                <div
                  key={step.key}
                  className={`rounded-xl border p-3 transition-all duration-500 ${
                    step.status === 'completed'
                      ? 'bg-green-900/20 border-green-700/50 text-green-300'
                      : step.status === 'running'
                      ? 'bg-blue-900/20 border-blue-500 text-blue-300'
                      : 'bg-gray-800/30 border-gray-700/30 text-gray-500'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{getIcon(step.key)}</span>
                    <div className="flex-1">
                      <div className="font-medium text-sm flex items-center gap-2">
                        <span className="text-gray-400">#{step.index}</span>
                        <span>{step.name}</span>
                        <span className="text-xs text-gray-500">({step.agent})</span>
                      </div>
                      {step.summary && (
                        <div className="text-xs mt-1 opacity-70">{step.summary}</div>
                      )}
                    </div>
                    <div className="text-right text-sm">
                      {step.status === 'completed' && '✅'}
                      {step.status === 'running' && (
                        <span className="inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                      )}
                      {step.status === 'pending' && '⏸️'}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {phase === 'complete' && (
              <>
                <div className="text-center mb-6">
                  <button
                    onClick={handleStart}
                    className="px-6 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm transition"
                  >
                    🔄 重新播放
                  </button>
                </div>
                <div className="text-center bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-800/50 rounded-2xl p-8">
                  <h2 className="text-2xl font-bold mb-2">🎉 全流程自动化完成！</h2>
                  <p className="text-gray-400 mb-6">
                    {steps.length} 步全自动 AI 编排完成。注册即可解锁完整功能。
                  </p>
                  <div className="flex gap-4 justify-center">
                    <a
                      href="/pricing"
                      className="px-8 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 rounded-xl font-semibold transition"
                    >
                      查看定价 →
                    </a>
                    <button
                      onClick={handleStart}
                      className="px-8 py-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-xl font-semibold transition"
                    >
                      重新运行
                    </button>
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </main>
  );
}

/* ─── Helpers ─── */

function getIcon(stepKey: string): string {
  return STEP_ICONS[stepKey] || '📌';
}

/* ─── Fallback steps (used when backend unavailable) ─── */

const FALLBACK_STEPS: StepDef[] = [
  { index: 1,  key: 'spec-check',          agent: '小明', name: 'OpenSpec 合规检查' },
  { index: 2,  key: 'super-analysis',      agent: '小明', name: 'S.U.P.E.R 启动分析' },
  { index: 3,  key: 'prd',                 agent: 'Hermes', name: '产品需求分析' },
  { index: 4,  key: 'prd-review',          agent: '小马', name: 'PRD 质量审查' },
  { index: 5,  key: 'architecture',        agent: 'Claude', name: '架构设计' },
  { index: 6,  key: 'arch-review',         agent: '小克', name: '架构审查' },
  { index: 7,  key: 'development',         agent: 'Claude', name: '开发计划与代码实现' },
  { index: 8,  key: 'devplan-review',      agent: '小克', name: '开发计划审查' },
  { index: 9,  key: 'internal-code-review',agent: '小克', name: '代码实现预审' },
  { index: 10, key: 'test-planning',       agent: 'Claude', name: '测试规划' },
  { index: 11, key: 'self-test',           agent: 'Claude', name: '自测验证' },
  { index: 12, key: 'self-test-review',    agent: '小克', name: '自测结果审查' },
  { index: 13, key: 'c-unit-test',         agent: '小克', name: 'C 单元测试 (Unity)' },
  { index: 14, key: 'integration-test',    agent: '小克', name: '接口集成测试' },
  { index: 15, key: 'code-review',         agent: 'Hermes', name: '集成代码审查' },
  { index: 16, key: 'misra-review',        agent: '小马', name: 'MISRA 合规审查' },
  { index: 17, key: 'coverage-review',     agent: '小马', name: '测试覆盖审查' },
  { index: 18, key: 'review-linker',       agent: '小克', name: '链接脚本审查' },
  { index: 19, key: 'review-startup',      agent: '小克', name: '启动代码审查' },
  { index: 20, key: 'review-rtos',         agent: '小克', name: 'RTOS 配置审查' },
  { index: 21, key: 'review-memory',       agent: '小克', name: '内存安全审查' },
  { index: 22, key: 'review-bsp',          agent: '小克', name: 'BSP 板级支持包验证' },
  { index: 23, key: 'review-build',        agent: '小克', name: '编译输出验证' },
  { index: 24, key: 'review-power',        agent: '小克', name: '低功耗审查' },
  { index: 25, key: 'review-stack',        agent: '小克', name: '堆栈使用分析' },
  { index: 26, key: 'review-mmio',         agent: '小克', name: 'MMIO 配置审查' },
  { index: 27, key: 'test-qualification',  agent: '小明', name: '合格性测试' },
  { index: 28, key: 'final-report',        agent: '小明', name: '最终报告' },
];

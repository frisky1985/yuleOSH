'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

/* ─────────────────────── Client-side Mock Data ─────────────────────── */

const STEP_DEFS = [
  { id: 'spec-parse',    name: 'Spec Parsing',               icon: '📋', duration: 800  },
  { id: 'ai-analysis',   name: 'AI Super Analysis',          icon: '🤖', duration: 1200 },
  { id: 'prd',           name: 'PRD Generation',              icon: '📄', duration: 1000 },
  { id: 'internal-review',name: 'Internal Review',            icon: '👁️', duration: 600  },
  { id: 'architecture',  name: 'Architecture Design',         icon: '🏗️', duration: 1400 },
  { id: 'development',   name: 'Development',                 icon: '💻', duration: 2000 },
  { id: 'test-planning', name: 'Test Planning',               icon: '🧪', duration: 900  },
  { id: 'self-test',     name: 'Self-Test',                   icon: '✅', duration: 1100 },
  { id: 'code-review',   name: 'Code Review',                 icon: '🔍', duration: 700  },
  { id: 'final-report',  name: 'Final Report & Evidence Pack', icon: '📊', duration: 500  },
];

const OUTRO_SUMMARIES: Record<string, string> = {
  'spec-parse':       'Parsed OpenSpec document: 5 requirements, 3 scenarios detected.',
  'ai-analysis':      'S.U.P.E.R analysis: Strengths=4, Weaknesses=2, Opportunities=3.',
  'prd':              'PRD generated with 12 user stories, 5 acceptance criteria.',
  'internal-review':  'Review passed: 3 minor issues found, 0 blockers.',
  'architecture':     'C4 L2 diagram: 4 components, 6 interfaces defined.',
  'development':      'Implemented 12 source files, 4 header files, 100% lint pass.',
  'test-planning':    'Test plan: 45 unit tests, 8 integration tests, 3 E2E scenarios.',
  'self-test':        '45/45 passed. Coverage: 82.4% line, 76.1% branch.',
  'code-review':      'Reviewed 1800 LOC. Findings: 2 style, 1 performance hint.',
  'final-report':     'Evidence pack generated: 12 artifacts, 3 CI reports, 5 reviews.',
};

/* ─────────────────────── Types ─────────────────────── */

interface Step {
  id: string;
  name: string;
  icon: string;
  status: 'pending' | 'running' | 'completed';
  summary: string;
  duration: number;
}

type Phase = 'idle' | 'running' | 'complete' | 'error';

/* ─────────────────────── Component ─────────────────────── */

export default function DemoPage() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [steps, setSteps] = useState<Step[]>(() =>
    STEP_DEFS.map((s) => ({
      ...s,
      status: 'pending' as const,
      summary: '',
    }))
  );
  const [currentIdx, setCurrentIdx] = useState(-1);
  const idxRef = useRef(0);

  const runPipeline = useCallback(() => {
    idxRef.current = 0;
    setPhase('running');
    setCurrentIdx(-1);
    setSteps(STEP_DEFS.map((s) => ({
      ...s,
      status: 'pending' as const,
      summary: '',
    })));
  }, []);

  useEffect(() => {
    if (phase !== 'running') return;

    const tick = () => {
      const idx = idxRef.current;
      if (idx >= STEP_DEFS.length) {
        setPhase('complete');
        return;
      }

      setCurrentIdx(idx);

      // Mark current as running
      setSteps((prev) => prev.map((s, i) => ({
        ...s,
        status: i === idx ? 'running' as const : s.status,
      })));

      // Mark completed after duration
      const dur = STEP_DEFS[idx].duration;
      setTimeout(() => {
        setSteps((prev) =>
          prev.map((s, i) =>
            i === idx
              ? { ...s, status: 'completed' as const, summary: OUTRO_SUMMARIES[s.id] || '' }
              : s
          )
        );
        idxRef.current = idx + 1;
        setTimeout(tick, 300);
      }, dur);
    };

    tick();
  }, [phase]);

  const completed = steps.filter((s) => s.status === 'completed').length;
  const running = steps.filter((s) => s.status === 'running').length;
  const progress =
    steps.length > 0
      ? Math.round(((completed + running) / steps.length) * 100)
      : 0;

  /* ────── Render ────── */

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

        {/* Idle state */}
        {phase === 'idle' && (
          <div className="text-center py-20">
            <div className="text-6xl mb-6">🚀</div>
            <h2 className="text-2xl font-bold mb-4">准备好体验了吗？</h2>
            <p className="text-gray-400 mb-8">点击下方按钮启动模拟 Pipeline，看看 AI 如何全流程自动编排。</p>
            <button
              onClick={runPipeline}
              className="px-8 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 rounded-xl font-semibold text-lg transition shadow-lg shadow-purple-500/20"
            >
              🎮 启动 Demo
            </button>
          </div>
        )}

        {/* Running state */}
        {(phase === 'running' || phase === 'complete') && (
          <>
            {/* Progress bar */}
            <div className="bg-gray-800 rounded-full h-3 mb-4 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-purple-600 transition-all duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="flex justify-between text-sm text-gray-500 mb-8">
              <span>{steps.filter((s) => s.status === 'completed').length}/{steps.length} 步骤完成</span>
              <span className={phase === 'complete' ? 'text-green-400' : 'text-blue-400'}>
                {phase === 'complete' ? '✅ 已完成' : '⏳ 运行中...'}
              </span>
            </div>

            {/* Steps */}
            <div className="space-y-3 mb-12">
              {steps.map((step) => (
                <div
                  key={step.id}
                  className={`rounded-xl border p-4 transition-all duration-500 ${
                    step.status === 'completed'
                      ? 'bg-green-900/20 border-green-700/50 text-green-300'
                      : step.status === 'running'
                      ? 'bg-blue-900/20 border-blue-500 text-blue-300'
                      : 'bg-gray-800/30 border-gray-700/30 text-gray-500'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{step.icon}</span>
                    <div className="flex-1">
                      <div className="font-semibold">{step.name}</div>
                      {step.summary && (
                        <div className="text-sm mt-1 opacity-70">{step.summary}</div>
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

            {/* Rewind button */}
            {phase === 'complete' && (
              <div className="text-center mb-6">
                <button
                  onClick={runPipeline}
                  className="px-6 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm transition"
                >
                  🔄 重新播放
                </button>
              </div>
            )}

            {/* CTA */}
            {phase === 'complete' && (
              <div className="text-center bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-800/50 rounded-2xl p-8">
                <h2 className="text-2xl font-bold mb-2">🎉 全流程自动化完成！</h2>
                <p className="text-gray-400 mb-6">
                  从需求到 Evidence Pack，10 步全自动 AI 编排。<br />
                  注册即可解锁完整功能，在真实项目上跑起来。
                </p>
                <div className="flex gap-4 justify-center">
                  <a
                    href="/pricing"
                    className="px-8 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 rounded-xl font-semibold transition"
                  >
                    查看定价 →
                  </a>
                  <button
                    onClick={runPipeline}
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

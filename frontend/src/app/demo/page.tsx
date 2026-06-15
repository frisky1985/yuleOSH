'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';

interface Step {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  output_summary?: string;
  duration_ms?: number;
  artifacts?: Record<string, number>;
}

interface PipelineData {
  status: string;
  pipeline_id: string;
  total_steps: number;
  current_step: number;
  steps: Step[];
}

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
  'ai-analysis': '🤖',
  'architecture': '🏗️',
  'development': '💻',
  'testing': '🧪',
  'review': '👁️',
  'report': '📊',
};

function getAgentIcon(id: string): string {
  for (const [key, icon] of Object.entries(AGENT_ICONS)) {
    if (id.includes(key)) return icon;
  }
  return '⚡';
}

export default function DemoPage() {
  const [pipeline, setPipeline] = useState<PipelineData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const startDemo = useCallback(async () => {
    setLoading(true);
    setError(null);
    setStarted(true);

    try {
      const res = await fetch('/api/v1/demo', { method: 'POST' });
      if (!res.ok) throw new Error('Demo service unavailable');
      const data = await res.json();
      setPipeline(data.data);
    } catch (e) {
      setError('Demo 服务暂不可用，请稍后再试。');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!started && !pipeline && !loading) {
      startDemo();
    }
  }, [started, pipeline, loading, startDemo]);

  // Auto-poll progress
  useEffect(() => {
    if (!pipeline || pipeline.status === 'completed' || pipeline.status === 'failed') return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/v1/demo/pipeline/${pipeline.pipeline_id}`);
        const data = await res.json();
        setPipeline(data.data);
      } catch {
        // ignore polling errors
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [pipeline?.pipeline_id, pipeline?.status]);

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

        {error && (
          <div className="bg-red-900/30 border border-red-800 rounded-xl p-6 text-center mb-8">
            <p className="text-red-400 mb-4">{error}</p>
            <button
              onClick={startDemo}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition"
            >
              重试
            </button>
          </div>
        )}

        {loading && !pipeline && (
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
                    <div className="mt-2 pt-2 border-t border-gray-700/50 text-xs flex gap-3">
                      {Object.entries(step.artifacts).map(([key, val]) => (
                        <span key={key} className="bg-gray-700/50 px-2 py-1 rounded">
                          {key}: {val}
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

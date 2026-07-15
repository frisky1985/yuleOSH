"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Timer, Code, CheckCircle, Zap, Clock, ArrowRight,
  AlertTriangle, GitPullRequest, Users, Cpu, Menu, X,
  BarChart3, Sparkles, Layers, FolderOpen,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

export default function ReviewBottleneckPage() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative min-h-screen bg-[#0a0e17] text-[#e2e8f0] overflow-x-hidden">

      {/* ─── NAV ─── */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[#1e293b]/60 nav-blur"
           style={{background:"rgba(10,14,23,.85)", backdropFilter:"blur(16px)"}}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link href="/" className="flex items-center gap-2.5 group">
              <span className="text-2xl font-black tracking-tight">
                <span className="text-[#10b981]">yule</span><span className="text-[#3b82f6]">OSH</span>
              </span>
            </Link>
            <div className="flex items-center gap-8">
              <div className="hidden md:flex items-center gap-6">
                <Link href="/scenarios/audit-emergency" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">审计突击</Link>
                <Link href="/scenarios/budget-friendly" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">预算困境</Link>
                <Link href="/scenarios/review-bottleneck" className="text-sm text-[#3b82f6] font-medium">审查瓶颈</Link>
              </div>
              <div className="flex items-center gap-3">
                <Link href="/login"
                   className="text-sm px-3 py-1.5 rounded-lg border border-[#1e293b] text-[#e2e8f0] hover:border-[#1677ff]/40 transition-all">登录</Link>
                <Link href="/dashboard"
                   className="text-sm flex items-center gap-1.5 px-4 py-1.5 rounded-lg font-semibold bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white transition-all">Dashboard →</Link>
              </div>
            </div>
            <button className="md:hidden p-2 rounded-lg border border-[#1e293b] text-[#94a3b8]"
                    onClick={() => setMobileOpen(!mobileOpen)}>
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
        {mobileOpen && (
          <div className="md:hidden border-t border-[#1e293b] bg-[#0a0e17]/95 px-4 py-4 space-y-3">
            <Link href="/scenarios/audit-emergency" className="block text-sm text-[#94a3b8]">审计突击</Link>
            <Link href="/scenarios/budget-friendly" className="block text-sm text-[#94a3b8]">预算困境</Link>
            <Link href="/scenarios/review-bottleneck" className="block text-sm text-[#3b82f6]">审查瓶颈</Link>
            <Link href="/dashboard" className="block text-sm px-4 py-2 rounded-lg font-semibold bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white text-center">Dashboard →</Link>
          </div>
        )}
      </nav>

      {/* ─── HERO ─── */}
      <section className="relative pt-28 pb-16 bg-grid overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[#3b82f6]/5 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-[#722ed1]/5 rounded-full blur-[100px]"></div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-4xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#3b82f6]/30 bg-[#3b82f6]/5 text-[#3b82f6] text-xs font-medium mb-6">
              <span className="w-2 h-2 rounded-full bg-[#3b82f6] animate-pulse"></span>
              Tier 2 真实场景 · 代码审查瓶颈
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight leading-[1.1] mb-6">
              <span className="gradient-blue-purple">Code Review 卡 3 天？</span>
              <br />
              <span className="text-[#e2e8f0]">30 分钟 AI 辅助搞定</span>
            </h1>
            <p className="text-lg sm:text-xl text-[#94a3b8] max-w-3xl mx-auto mb-8 leading-relaxed">
              嵌入式开发者提了 PR 后等 Code Review 等 3 天？
              yuleOSH AI 辅助审查流水线 <span className="text-[#3b82f6] font-semibold">30 分钟完成</span>，
              不阻塞开发进度，不降低审查质量。
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/demo"
                 className="group inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#3b82f6] to-[#722ed1] text-white shadow-lg shadow-[#3b82f6]/20 hover:opacity-90 transition-all">
                <PlayIcon className="w-4 h-4" />
                观看流水线演示
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <button onClick={() => document.getElementById('pipeline')?.scrollIntoView({behavior:'smooth'})}
                 className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm border border-[#1e293b] text-[#94a3b8] hover:border-[#3b82f6]/40 hover:text-white transition-all">
                查看流水线
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto">
            {[
              { label: "审查耗时", value: "30 分钟", sub: "vs 传统 3 天", color: "text-[#10b981]" },
              { label: "审查覆盖率", value: "100%", sub: "代码 & 设计 & 测试", color: "text-[#3b82f6]" },
              { label: "开发满意度", value: "+67%", sub: "减少等待焦虑", color: "text-[#722ed1]" },
              { label: "缺陷捕获率", value: "92%", sub: "AI + 人工双保险", color: "text-[#f59e0b]" },
            ].map((s, i) => (
              <div key={i} className="text-center p-4 rounded-xl border border-[#1e293b] bg-[#111827]/60">
                <div className={`text-3xl font-black ${s.color}`}>{s.value}</div>
                <div className="text-xs text-[#64748b] mt-0.5">{s.sub}</div>
                <div className="text-[10px] text-[#94a3b8] mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── PROBLEM ─── */}
      <section className="py-20 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#ef4444]">痛点</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">Code Review 瓶颈，嵌入式团队的隐形杀手</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {[
              {
                icon: <Timer className="w-6 h-6 text-[#ef4444]" />,
                title: "等待 3 天",
                desc: "PR 提了之后，资深工程师忙自己的开发任务，Code Review 排到 3 天后。期间开发者被阻塞，无事可做。",
              },
              {
                icon: <AlertTriangle className="w-6 h-6 text-[#f59e0b]" />,
                title: "质量不可控",
                desc: "赶时间的人肉审查容易遗漏关键问题：MISRA 违规、内存泄露、竞态条件。事后修复成本呈指数级增长。",
              },
              {
                icon: <Users className="w-6 h-6 text-[#3b82f6]" />,
                title: "资深工程师稀缺",
                desc: "团队里能做好 Code Review 的就那么几个人，他们同时还要做架构设计、技术决策，瓶颈无法避免。",
              },
            ].map((item, i) => (
              <div key={i} className="rounded-xl border border-[#1e293b] bg-[#111827] p-6 feature-card">
                <div className="w-11 h-11 rounded-lg bg-[#ef4444]/10 flex items-center justify-center mb-4">{item.icon}</div>
                <h3 className="text-base font-bold text-[#e2e8f0] mb-2">{item.title}</h3>
                <p className="text-sm text-[#94a3b8] leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── PIPELINE ─── */}
      <section id="pipeline" className="py-20 bg-[#0a0e17]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#3b82f6]">流水线</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">30 分钟 AI 辅助审查流水线</h2>
            <p className="text-[#94a3b8] mt-3 max-w-xl mx-auto">自动化不替代人工判断，但做 80% 的重复工作</p>
          </div>

          <div className="max-w-4xl mx-auto">
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-7 top-0 bottom-0 w-0.5 bg-gradient-to-b from-[#3b82f6] via-[#722ed1] to-[#10b981] opacity-30"></div>

              {[
                { icon: <GitPullRequest className="w-5 h-5" />, color: "#3b82f6", title: "PR 提交触发", desc: "开发者提交 Pull Request，自动触发 yuleOSH 审查流水线。无需手动操作。", time: "0 min" },
                { icon: <Code className="w-5 h-5" />, color: "#722ed1", title: "静态分析 + MISRA 检查", desc: "cppcheck 自动扫描：MISRA C:2023 规则检查、空指针、越界、未初始化变量。", time: "5 min" },
                { icon: <Layers className="w-5 h-5" />, color: "#3b82f6", title: "AI 差异分析", desc: "AI 对比变更代码与项目规范，识别架构违例、设计漂移、命名不一致。", time: "8 min" },
                { icon: <FolderOpen className="w-5 h-5" />, color: "#722ed1", title: "追溯一致性检查", desc: "检查变更是否影响已有需求追溯链，更新追溯矩阵和测试覆盖报告。", time: "5 min" },
                { icon: <BarChart3 className="w-5 h-5" />, color: "#10b981", title: "测试运行", desc: "自动运行受影响的单元测试和集成测试，验证变更未破坏已有功能。", time: "10 min" },
                { icon: <CheckCircle className="w-5 h-5" />, color: "#10b981", title: "审查摘要生成", desc: "汇总所有结果：问题列表、建议修改、合规状态。人工审查只需关注 AI 标记项。", time: "2 min" },
              ].map((item, i) => (
                <div key={i} className="relative flex items-start gap-6 pb-8 pl-0">
                  <div className="relative z-10 w-14 h-14 rounded-2xl flex items-center justify-center shrink-0"
                       style={{background:`linear-gradient(135deg, ${item.color}20, ${item.color}05)`, border:`1px solid ${item.color}40`}}>
                    <div style={{color: item.color}}>{item.icon}</div>
                  </div>
                  <div className="flex-1 pt-2">
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-sm font-bold text-[#e2e8f0]">{item.title}</h3>
                      <span className="text-[10px] font-mono text-[#64748b] bg-[#1e293b] px-2 py-0.5 rounded">{item.time}</span>
                    </div>
                    <p className="text-xs text-[#94a3b8] leading-relaxed">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Time summary */}
            <div className="mt-6 gradient-border">
              <div className="bg-[#111827] rounded-2xl p-6 text-center">
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <div className="text-xs text-[#ef4444] font-semibold mb-1">传统 Code Review</div>
                    <div className="text-3xl font-black text-[#ef4444]">3 天</div>
                    <div className="text-xs text-[#64748b] mt-1">等资深工程师空闲</div>
                  </div>
                  <div>
                    <div className="text-xs text-[#10b981] font-semibold mb-1">yuleOSH 流水线</div>
                    <div className="text-3xl font-black text-[#10b981]">30 分钟</div>
                    <div className="text-xs text-[#64748b] mt-1">AI 辅助 + 人工确认</div>
                  </div>
                </div>
                <div className="mt-4 text-sm text-[#94a3b8]">
                  速度提升 <span className="text-[#10b981] font-bold">144x</span> · 人工审查时间减少 <span className="text-[#3b82f6] font-bold">75%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── DEVELOPER EXPERIENCE ─── */}
      <section className="py-20 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#722ed1]">开发者体验</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">开发者怎么说</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {[
              {
                quote: "以前提 PR 后要等 2-3 天才有 Review。现在 30 分钟出结果，我可以在同一天内完成修改和合并。",
                name: "陈工",
                role: "嵌入式 C 开发 · 5 年经验",
              },
              {
                quote: "AI 帮我提前拦截了 MISRA 违规和潜在的内存问题，资深工程师只需要确认少数真正需要人工判断的点。",
                name: "李工",
                role: "嵌入式 C++ 开发 · 3 年经验",
              },
              {
                quote: "审查报告非常清晰，每个问题都标了严重等级和代码位置。开发者自审就能解决大部分低级问题。",
                name: "王工",
                role: "技术负责人 · 10 年经验",
              },
            ].map((item, i) => (
              <div key={i} className="rounded-xl border border-[#1e293b] bg-[#111827] p-6 feature-card">
                <div className="text-[#10b981] text-2xl mb-3">"</div>
                <p className="text-sm text-[#94a3b8] leading-relaxed mb-4">{item.quote}</p>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#722ed1] to-[#3b82f6] flex items-center justify-center text-white text-xs font-bold">
                    {item.name[0]}
                  </div>
                  <div>
                    <div className="text-xs font-medium text-[#e2e8f0]">{item.name}</div>
                    <div className="text-[10px] text-[#64748b]">{item.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section className="py-20 bg-[#0a0e17] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">别再让 Code Review 阻塞开发</h2>
          <p className="text-[#94a3b8] mb-8">30 分钟 AI 辅助审查，开发者体验和代码质量双赢</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/demo"
               className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-[#3b82f6] to-[#722ed1] text-white font-semibold text-sm shadow-lg shadow-[#3b82f6]/20 hover:opacity-90 transition-all">
              <PlayIcon className="w-4 h-4" />
              观看流水线演示
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/dashboard"
               className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl border border-[#1e293b] text-[#94a3b8] hover:border-white/20 hover:text-white text-sm font-medium transition-all">
              免费试用
            </Link>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="py-12 border-t border-[#1e293b] bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <Link href="/" className="text-lg font-black tracking-tight">
                <span className="text-[#10b981]">yule</span><span className="text-[#3b82f6]">OSH</span>
              </Link>
              <span className="text-xs text-[#64748b]">v0.1.0 · MIT License</span>
            </div>
            <div className="flex items-center gap-6">
              <Link href="/scenarios/audit-emergency" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">审计突击</Link>
              <Link href="/scenarios/budget-friendly" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">预算困境</Link>
              <Link href="/scenarios/review-bottleneck" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">审查瓶颈</Link>
              <Link href="https://github.com/stefanji/yuleOSH" target="_blank" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">GitHub</Link>
            </div>
          </div>
        </div>
      </footer>

      <style jsx>{`
        .nav-blur { backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); }
        .feature-card { transition: all .3s cubic-bezier(.4,0,.2,1); }
        .feature-card:hover { transform: translateY(-4px); }
        .gradient-blue-purple {
          background: linear-gradient(135deg, #3b82f6 0%, #722ed1 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .gradient-border { position: relative; border-radius: 16px; overflow: hidden; }
        .gradient-border::before {
          content: ''; position: absolute; inset: 0; border-radius: 16px; padding: 1px;
          background: linear-gradient(135deg, #3b82f6, #722ed1, #10b981, #3b82f6);
          background-size: 300% 300%;
          -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          -webkit-mask-composite: xor;
          mask-composite: exclude;
          animation: border-shimmer 4s ease infinite;
        }
        @keyframes border-shimmer {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        .bg-grid {
          background-image:
            linear-gradient(rgba(16,185,129,.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(16,185,129,.03) 1px, transparent 1px);
          background-size: 60px 60px;
        }
      `}</style>
    </div>
  );
}

/* Inline PlayIcon since lucide-react doesn't have it */
function PlayIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

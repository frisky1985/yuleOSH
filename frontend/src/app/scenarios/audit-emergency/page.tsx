"use client";

import Link from "next/link";
import { useState } from "react";
import {
  AlertTriangle, CheckCircle, Clock, FileText, Shield, ArrowRight,
  Download, Search, BarChart3, Zap, Menu, X, FileSearch, Users,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

export default function AuditEmergencyPage() {
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
                <Link href="/scenarios/audit-emergency" className="text-sm text-[#10b981] font-medium">审计突击</Link>
                <Link href="/scenarios/budget-friendly" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">预算困境</Link>
                <Link href="/scenarios/review-bottleneck" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">审查瓶颈</Link>
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
            <Link href="/scenarios/audit-emergency" className="block text-sm text-[#10b981]">审计突击</Link>
            <Link href="/scenarios/budget-friendly" className="block text-sm text-[#94a3b8]">预算困境</Link>
            <Link href="/scenarios/review-bottleneck" className="block text-sm text-[#94a3b8]">审查瓶颈</Link>
            <Link href="/dashboard" className="block text-sm px-4 py-2 rounded-lg font-semibold bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white text-center">Dashboard →</Link>
          </div>
        )}
      </nav>

      {/* ─── HERO ─── */}
      <section className="relative pt-28 pb-16 bg-grid overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[#f59e0b]/5 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-[#ef4444]/5 rounded-full blur-[100px]"></div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-4xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#f59e0b]/30 bg-[#f59e0b]/5 text-[#f59e0b] text-xs font-medium mb-6">
              <span className="w-2 h-2 rounded-full bg-[#f59e0b] animate-pulse"></span>
              Tier 2 真实场景 · 审计突击
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight leading-[1.1] mb-6">
              <span style={{background:"linear-gradient(135deg, #f59e0b 0%, #ef4444 50%, #f59e0b 100%)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent", backgroundClip:"text"}}>
                审计通知来了
              </span>
              <br />
              <span className="text-[#e2e8f0]">别慌，yuleOSH 帮你 5 分钟搞定</span>
            </h1>
            <p className="text-lg sm:text-xl text-[#94a3b8] max-w-3xl mx-auto mb-8 leading-relaxed">
              Tier 1 客户突然通知 ASPICE 审计？传统准备需要 2 周甚至更久。
              yuleOSH 一键生成合规证据包，<span className="text-[#f59e0b] font-semibold">从 2 周准备到 5 分钟一键生成</span>。
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/dashboard"
                 className="group inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#f59e0b] to-[#ef4444] text-white shadow-lg shadow-[#f59e0b]/20 hover:opacity-90 transition-all">
                <Zap className="w-4 h-4" />
                立即体验一键合规
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <button onClick={() => document.getElementById('problem')?.scrollIntoView({behavior:'smooth'})}
                 className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm border border-[#1e293b] text-[#94a3b8] hover:border-[#f59e0b]/40 hover:text-white transition-all">
                了解详情
              </button>
            </div>
          </div>

          {/* Stats bar */}
          <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto">
            {[
              { label: "审计准备时间", value: "5 分钟", sub: "vs 传统 2 周", color: "text-[#10b981]" },
              { label: "证据项覆盖", value: "100%", sub: "ASPICE SWE.1-6", color: "text-[#3b82f6]" },
              { label: "合规模板", value: "47 项", sub: "预置审计模板", color: "text-[#f59e0b]" },
              { label: "通过率", value: "96%", sub: "首次提审通过", color: "text-[#ef4444]" },
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
      <section id="problem" className="py-20 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#ef4444]">问题</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">审计突击，传统团队的真实困境</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {[
              {
                icon: <Clock className="w-6 h-6 text-[#ef4444]" />,
                title: "时间紧迫",
                desc: "Tier 1 客户突然通知 2 周后审计。团队加班加点整理文档、追溯矩阵、测试报告，身心俱疲。",
              },
              {
                icon: <FileSearch className="w-6 h-6 text-[#f59e0b]" />,
                title: "文档散落",
                desc: "需求在 Confluence，设计在 Wiki，测试在 Jira，代码在 GitLab。跨系统追溯全靠人工，遗漏风险极高。",
              },
              {
                icon: <AlertTriangle className="w-6 h-6 text-[#ef4444]" />,
                title: "证据缺失",
                desc: "ASPICE 要求需求↔测试双向追溯、覆盖率证明、审查日志。大多数 Tier 2 团队根本没有系统化的证据管理。",
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

      {/* ─── SOLUTION ─── */}
      <section className="py-20 bg-[#0a0e17]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#10b981]">yuleOSH 方案</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">三步走，5 分钟完成审计准备</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {[
              {
                step: "1",
                icon: <Search className="w-7 h-7 text-[#f59e0b]" />,
                title: "差距分析",
                desc: "yuleOSH 自动扫描项目所有文档和代码，识别 ASPICE SWE.1~SWE.6 各个环节的合规差距。一键生成差距分析报告。",
                color: "from-[#f59e0b]/20 to-[#f59e0b]/5",
                border: "#f59e0b/30",
              },
              {
                step: "2",
                icon: <FileText className="w-7 h-7 text-[#3b82f6]" />,
                title: "证据包生成",
                desc: "自动生成：需求追溯矩阵、测试覆盖率报告、审查日志、CI/CD 执行记录。涵盖 ASPICE 要求的全部关键证据。",
                color: "from-[#3b82f6]/20 to-[#3b82f6]/5",
                border: "#3b82f6/30",
              },
              {
                step: "3",
                icon: <Shield className="w-7 h-7 text-[#10b981]" />,
                title: "审计通过",
                desc: "一键打包下载标准合规证据包。ASPICE 审计师可直接查阅的格式，减少来回沟通时间。首次通过率 96%。",
                color: "from-[#10b981]/20 to-[#10b981]/5",
                border: "#10b981/30",
              },
            ].map((item, i) => (
              <div key={i} className="relative text-center p-6 rounded-xl border feature-card"
                   style={{borderColor: item.border, background:`linear-gradient(135deg, ${item.color})`}}>
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-black"
                     style={{background: `linear-gradient(135deg, ${item.step === "1" ? "#f59e0b" : item.step === "2" ? "#3b82f6" : "#10b981"}, ${item.step === "1" ? "#d97706" : item.step === "2" ? "#2563eb" : "#059669"})`}}>
                  {item.step}
                </div>
                <div className="mt-6 mb-4 flex justify-center">
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                       style={{background:`linear-gradient(135deg, ${item.color})`, border:`1px solid ${item.border}`}}>
                    {item.icon}
                  </div>
                </div>
                <h3 className="text-lg font-bold text-[#e2e8f0] mb-2">{item.title}</h3>
                <p className="text-sm text-[#94a3b8] leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>

          <div className="mt-12 gradient-border max-w-3xl mx-auto">
            <div className="bg-[#111827] rounded-2xl p-6 sm:p-8 text-center">
              <h3 className="text-xl font-bold text-[#e2e8f0] mb-4">📊 数据对比</h3>
              <div className="grid grid-cols-2 gap-6 text-center">
                <div className="p-4 rounded-xl border border-[#ef4444]/30 bg-[#ef4444]/5">
                  <div className="text-xs text-[#ef4444] font-semibold mb-2">传统方式</div>
                  <div className="text-2xl font-black text-[#ef4444]">2 周</div>
                  <div className="text-xs text-[#94a3b8] mt-1">团队加班整理</div>
                  <div className="text-xs text-[#94a3b8]">多系统手动追溯</div>
                </div>
                <div className="p-4 rounded-xl border border-[#10b981]/30 bg-[#10b981]/5">
                  <div className="text-xs text-[#10b981] font-semibold mb-2">yuleOSH</div>
                  <div className="text-2xl font-black text-[#10b981]">5 分钟</div>
                  <div className="text-xs text-[#94a3b8] mt-1">一键差距分析</div>
                  <div className="text-xs text-[#94a3b8]">自动证据包生成</div>
                </div>
              </div>
              <div className="mt-4 text-sm text-[#94a3b8]">
                效率提升 <span className="text-[#10b981] font-bold">4000%+</span> · 减少人工错误 <span className="text-[#3b82f6] font-bold">95%</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── HOW IT WORKS ─── */}
      <section className="py-20 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#3b82f6]">工作流</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">审计准备全流程</h2>
          </div>

          <div className="max-w-4xl mx-auto space-y-4">
            {[
              { step: "01", icon: "🔗", title: "连接项目数据源", desc: "连接 GitLab、Jira、Confluence 等工具，yuleOSH 自动抓取需求、代码、测试数据。" },
              { step: "02", icon: "🔍", title: "自动差距分析", desc: "比对 ASPICE SWE.1~SWE.6 标准要求，识别缺失证据项，生成优先级排序的差距报告。" },
              { step: "03", icon: "📋", title: "生成追溯矩阵", desc: "自动建立需求↔代码↔测试的双向追溯关系，覆盖缺口一目了然。" },
              { step: "04", icon: "📊", title: "生成覆盖率报告", desc: "统计测试覆盖率（行/分支/函数），生成符合 ASPICE 格式的覆盖率报告。" },
              { step: "05", icon: "📦", title: "打包合规证据", desc: "所有证据统一格式打包，可直接提交给审计师。一键下载 ZIP 文件。" },
              { step: "06", icon: "✅", title: "审计支持", desc: "审计进行中如有补充需求，可增量更新。历史版本自动存档。" },
            ].map((item, i) => (
              <div key={i} className="flex items-start gap-4 p-4 rounded-xl border border-[#1e293b] bg-[#111827] feature-card hover:border-[#10b981]/30 transition-all">
                <div className="text-3xl shrink-0 mt-0.5">{item.icon}</div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-mono text-[#64748b]">{item.step}</span>
                    <h3 className="text-sm font-bold text-[#e2e8f0]">{item.title}</h3>
                  </div>
                  <p className="text-xs text-[#94a3b8] leading-relaxed">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── TESTIMONIAL ─── */}
      <section className="py-20 bg-[#0a0e17]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-4xl mx-auto">
            <div className="rounded-xl border border-[#f59e0b]/20 bg-gradient-to-br from-[#f59e0b]/5 to-transparent p-8 text-center relative">
              <div className="text-4xl mb-4">💬</div>
              <blockquote className="text-lg sm:text-xl text-[#e2e8f0] font-medium leading-relaxed mb-6">
                "甲方突然通知两周后 ASPICE 审计。以前这种情况至少要加班一个月。
                用 yuleOSH 一键生成证据包，5 分钟就搞定了。审计一次通过。"
              </blockquote>
              <div className="flex items-center justify-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#f59e0b] to-[#ef4444] flex items-center justify-center text-white font-bold text-sm">张</div>
                <div className="text-left">
                  <div className="text-sm font-semibold text-[#e2e8f0]">张工 · 嵌入式软件负责人</div>
                  <div className="text-xs text-[#64748b]">某 Tier 2 汽车电子供应商</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section className="py-20 bg-[#0d111f] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">再也不怕审计突击</h2>
          <p className="text-[#94a3b8] mb-8">5 分钟搞定合规证据，让审计变得简单</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/dashboard"
               className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-[#f59e0b] to-[#ef4444] text-white font-semibold text-sm shadow-lg shadow-[#f59e0b]/20 hover:opacity-90 transition-all">
              <Zap className="w-4 h-4" />
              立即体验一键合规
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/pricing"
               className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl border border-[#1e293b] text-[#94a3b8] hover:border-white/20 hover:text-white text-sm font-medium transition-all">
              查看定价
            </Link>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="py-12 border-t border-[#1e293b] bg-[#0a0e17]">
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
        .gradient-border { position: relative; border-radius: 16px; overflow: hidden; }
        .gradient-border::before {
          content: ''; position: absolute; inset: 0; border-radius: 16px; padding: 1px;
          background: linear-gradient(135deg, #f59e0b, #ef4444, #f59e0b);
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

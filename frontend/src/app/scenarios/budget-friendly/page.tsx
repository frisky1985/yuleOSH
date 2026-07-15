"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Coins, Wallet, TrendingDown, CheckCircle, ArrowRight,
  Users, Cpu, GitBranch, FileText, Menu, X, Zap, DollarSign,
  BarChart3,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

export default function BudgetFriendlyPage() {
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
                <Link href="/scenarios/budget-friendly" className="text-sm text-[#10b981] font-medium">预算困境</Link>
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
            <Link href="/scenarios/audit-emergency" className="block text-sm text-[#94a3b8]">审计突击</Link>
            <Link href="/scenarios/budget-friendly" className="block text-sm text-[#10b981]">预算困境</Link>
            <Link href="/scenarios/review-bottleneck" className="block text-sm text-[#94a3b8]">审查瓶颈</Link>
            <Link href="/dashboard" className="block text-sm px-4 py-2 rounded-lg font-semibold bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white text-center">Dashboard →</Link>
          </div>
        )}
      </nav>

      {/* ─── HERO ─── */}
      <section className="relative pt-28 pb-16 bg-grid overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[#10b981]/5 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-[#3b82f6]/5 rounded-full blur-[100px]"></div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-4xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#10b981]/30 bg-[#10b981]/5 text-[#10b981] text-xs font-medium mb-6">
              <span className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse"></span>
              Tier 2 真实场景 · 预算困境
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight leading-[1.1] mb-6">
              <span className="gradient-green-blue">¥5,000 预算</span>
              <br />
              <span className="text-[#e2e8f0]">干 ¥500,000 团队的活</span>
            </h1>
            <p className="text-lg sm:text-xl text-[#94a3b8] max-w-3xl mx-auto mb-8 leading-relaxed">
              15 人嵌入式团队，只有 ¥50,000 工具预算。用 yuleOSH + Jira + GitLab，
              <span className="text-[#10b981] font-semibold">¥5,999/年 vs ¥500,000+</span>，覆盖同样的全流程需求。
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/dashboard"
                 className="group inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#10b981] to-[#059669] text-white shadow-lg shadow-[#10b981]/20 hover:opacity-90 transition-all">
                <Wallet className="w-4 h-4" />
                查看 Team 方案
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <button onClick={() => document.getElementById('comparison')?.scrollIntoView({behavior:'smooth'})}
                 className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm border border-[#1e293b] text-[#94a3b8] hover:border-[#10b981]/40 hover:text-white transition-all">
                成本对比
              </button>
            </div>
          </div>

          {/* Quick stats */}
          <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto">
            {[
              { label: "年费", value: "¥5,999", sub: "vs ¥500,000+", color: "text-[#10b981]" },
              { label: "团队规模", value: "15 人", sub: "嵌入式团队", color: "text-[#3b82f6]" },
              { label: "工具覆盖", value: "100%", sub: "SWE.1-6 全流程", color: "text-[#f59e0b]" },
              { label: "年节省", value: "¥494K+", sub: "直接成本节约", color: "text-[#10b981]" },
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
            <span className="text-xs font-semibold tracking-widest uppercase text-[#f59e0b]">困境</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">预算有限，但客户要求不能降</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {[
              {
                icon: <Coins className="w-6 h-6 text-[#f59e0b]" />,
                title: "高昂的商业工具",
                desc: "IBM Rational / VectorCAST / LDRA 等传统工具年费动辄数十万。对于 Tier 2 供应商，这就占了全年工具预算的一半。",
              },
              {
                icon: <Users className="w-6 h-6 text-[#3b82f6]" />,
                title: "小团队大压力",
                desc: "15 人的嵌入式团队要面对 ASPICE 合规、多层 CI/CD、自动化测试等全部要求。开源方案维护成本高。",
              },
              {
                icon: <GitBranch className="w-6 h-6 text-[#ef4444]" />,
                title: "工具链碎片化",
                desc: "需求工具、测试工具、CI 工具、合规工具各买一套，相互之间不通。集成又要额外成本。",
              },
            ].map((item, i) => (
              <div key={i} className="rounded-xl border border-[#1e293b] bg-[#111827] p-6 feature-card">
                <div className="w-11 h-11 rounded-lg bg-[#f59e0b]/10 flex items-center justify-center mb-4">{item.icon}</div>
                <h3 className="text-base font-bold text-[#e2e8f0] mb-2">{item.title}</h3>
                <p className="text-sm text-[#94a3b8] leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── COST COMPARISON ─── */}
      <section id="comparison" className="py-20 bg-[#0a0e17]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#10b981]">成本对比</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">yuleOSH 方案 vs 传统商业方案</h2>
          </div>

          <div className="max-w-5xl mx-auto overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e293b]">
                  <th className="text-left py-3 px-4 text-[#94a3b8] font-medium">类别</th>
                  <th className="text-center py-3 px-4 text-[#ef4444] font-semibold">传统商业方案</th>
                  <th className="text-center py-3 px-4 text-[#10b981] font-semibold">yuleOSH + 开源</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["需求管理", "DOORS / Polarion ¥80,000+/年", "OpenSpec (内置) ¥0"],
                  ["代码审查", "Collaborator / CodeBeamer ¥60,000+/年", "AI 辅助审查 ¥0"],
                  ["CI/CD 平台", "Jenkins Enterprise ¥40,000+/年", "GitLab CI (已有) ¥0"],
                  ["测试管理", "VectorCAST / LDRA ¥150,000+/年", "pytest + Unity ¥0"],
                  ["合规工具", "MethodPark / PREEvision ¥120,000+/年", "yuleOSH ¥5,999/年"],
                  ["集成费用", "各工具间集成 ¥50,000+", "原生集成 ¥0"],
                ].map((row, i) => (
                  <tr key={i} className="border-b border-[#1e293b]/60 hover:bg-[#111827]/50 transition-colors">
                    <td className="py-3.5 px-4 text-[#e2e8f0] font-medium">{row[0]}</td>
                    <td className="py-3.5 px-4 text-center text-[#ef4444]/80">{row[1]}</td>
                    <td className="py-3.5 px-4 text-center text-[#10b981]/80">{row[2]}</td>
                  </tr>
                ))}
                <tr className="border-t-2 border-[#10b981]/30 bg-[#10b981]/5">
                  <td className="py-4 px-4 text-[#e2e8f0] font-bold">总计</td>
                  <td className="py-4 px-4 text-center text-[#ef4444] font-bold text-lg">¥500,000+/年</td>
                  <td className="py-4 px-4 text-center text-[#10b981] font-bold text-lg">¥5,999/年</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="mt-8 text-center">
            <div className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-[#10b981]/30 bg-[#10b981]/5 text-[#10b981] text-sm font-semibold">
              <DollarSign className="w-4 h-4" />
              节省 <span className="text-xl font-black">98.8%</span> 的工具成本
            </div>
          </div>
        </div>
      </section>

      {/* ─── SOLUTION ─── */}
      <section className="py-20 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#3b82f6]">方案</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">yuleOSH + 已有工具，零成本衔接</h2>
          </div>

          <div className="max-w-4xl mx-auto">
            {/* Integration flow */}
            <div className="flex flex-col gap-3">
              {[
                { icon: "📋", title: "Jira 看板", desc: "导入已有需求 / 任务。yuleOSH 自动同步，无需迁移。" },
                { icon: "💻", title: "GitLab 仓库", desc: "连接 GitLab 仓库，自动分析代码覆盖率、MISRA 合规状态。" },
                { icon: "🤖", title: "yuleOSH Pipeline", desc: "AI 辅助流水线自动推进：需求审查→设计→编码→测试→合规审计证据。" },
                { icon: "📊", title: "证据包输出", desc: "一键导出 ASPICE 合规证据包，追溯矩阵 / 覆盖率报告 / 审查日志全包含。" },
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-4 p-4 rounded-xl border border-[#1e293b] bg-[#111827] feature-card">
                  <div className="text-2xl shrink-0 mt-0.5">{item.icon}</div>
                  <div className="flex-1">
                    <h3 className="text-sm font-bold text-[#e2e8f0] mb-1">{item.title}</h3>
                    <p className="text-xs text-[#94a3b8]">{item.desc}</p>
                  </div>
                  <div className="w-8 h-8 rounded-full border border-[#1e293b] flex items-center justify-center text-xs text-[#64748b] font-mono">{i + 1}</div>
                </div>
              ))}
            </div>

            <div className="mt-8 p-5 rounded-xl bg-gradient-to-r from-[#10b981]/10 via-[#3b82f6]/5 to-transparent border border-[#10b981]/20">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-[#10b981]/20 flex items-center justify-center shrink-0">
                  <CheckCircle className="w-5 h-5 text-[#10b981]" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-[#e2e8f0]">零额外基础设施</h4>
                  <p className="text-xs text-[#94a3b8]">yuleOSH 可 Docker 自托管部署在已有服务器上，不依赖专有硬件或云服务。</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section className="py-20 bg-[#0a0e17] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">预算不够，不是代码写不好的理由</h2>
          <p className="text-[#94a3b8] mb-8">从 ¥5,999/年起步，覆盖嵌入式开发全流程</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/pricing"
               className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-[#10b981] to-[#059669] text-white font-semibold text-sm shadow-lg shadow-[#10b981]/20 hover:opacity-90 transition-all">
              <Wallet className="w-4 h-4" />
              查看定价方案
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
        .gradient-green-blue {
          background: linear-gradient(135deg, #10b981 0%, #3b82f6 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
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

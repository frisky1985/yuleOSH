"use client";

import Link from "next/link";
import { useState } from "react";
import {
  FileText,
  Cpu,
  GitBranch,
  Shield,
  Container,
  ArrowRight,
  Menu,
  X,
  ChevronDown,
  Layers,
  Play,
  Sparkles,
  BarChart3,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

export default function LandingPage() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative min-h-screen bg-[#0a0e17] text-[#e2e8f0] overflow-x-hidden">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[#1e293b]/60 nav-blur" style={{ background: "rgba(10,14,23,.85)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link href="/" className="flex items-center gap-2.5 group">
              <span className="text-2xl font-black tracking-tight">
                <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
              </span>
            </Link>
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">功能</a>
              <a href="#how-it-works" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">工作流</a>
              <Link href="/pricing" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">定价</Link>
              <Link href="/login" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">登录</Link>
              <Link href="/dashboard"
                className="text-sm flex items-center gap-1.5 px-4 py-2 rounded-lg font-semibold
                  bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white
                  hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 transition-all"
              >
                Dashboard
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
            <div className="md:hidden">
              <button onClick={() => setMobileOpen(!mobileOpen)}
                className="p-2 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white transition-all"
              >
                {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
        {mobileOpen && (
          <div className="md:hidden border-t border-[#1e293b] bg-[#0a0e17]/95 nav-blur">
            <div className="px-4 py-4 space-y-3">
              <a href="#features" onClick={() => setMobileOpen(false)} className="block text-sm text-[#94a3b8] hover:text-white transition-colors">功能</a>
              <a href="#how-it-works" onClick={() => setMobileOpen(false)} className="block text-sm text-[#94a3b8] hover:text-white transition-colors">工作流</a>
              <Link href="/pricing" onClick={() => setMobileOpen(false)} className="block text-sm text-[#94a3b8] hover:text-white transition-colors">定价</Link>
              <Link href="/login" onClick={() => setMobileOpen(false)} className="block text-sm text-[#94a3b8] hover:text-white transition-colors">登录</Link>
              <Link href="/dashboard" onClick={() => setMobileOpen(false)}
                className="block text-sm px-4 py-2 rounded-lg font-semibold bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white text-center"
              >
                进入 Dashboard
              </Link>
            </div>
          </div>
        )}
      </nav>

      {/* Hero */}
      <section className="relative min-h-screen flex items-center bg-grid pt-16 overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[#722ed1]/5 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-[#1677ff]/5 rounded-full blur-[120px]"></div>
        <div className="absolute top-1/3 right-1/3 w-64 h-64 bg-[#10b981]/5 rounded-full blur-[100px]"></div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 sm:py-32">
          <div className="text-center max-w-4xl mx-auto">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#722ed1]/30 bg-[#722ed1]/5 text-[#722ed1] text-xs font-medium mb-8">
              <span className="w-2 h-2 rounded-full bg-[#722ed1] animate-pulse"></span>
              v0.1.0 · 开源 · Docker 自托管
            </div>

            <h1 className="text-4xl sm:text-5xl md:text-7xl font-black tracking-tight leading-[1.1] mb-6">
              <span className="gradient-text">AI 驱动的嵌入式</span><br />
              <span className="text-[#e2e8f0]">开发全流程平台</span>
            </h1>

            <p className="text-lg sm:text-xl text-[#94a3b8] max-w-2xl mx-auto mb-10 leading-relaxed">
              From natural language requirements to hardware-tested firmware.
            </p>

            <p className="text-sm text-[#64748b] max-w-lg mx-auto mb-10">
              No NDA. No Sales Call. No License Negotiation.<br />
              Just <code className="text-[#10b981] bg-[#10b981]/10 px-1.5 py-0.5 rounded text-xs">pip install yuleosh</code> and you&apos;re running in 5 minutes.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/dashboard"
                className="group relative inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm
                  bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white
                  hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 transition-all"
              >
                <Sparkles className="w-4 h-4" />
                <span>立即体验 Dashboard</span>
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <a href="#how-it-works"
                className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm
                  border border-[#1e293b] text-[#94a3b8] hover:border-[#1677ff]/40 hover:text-white transition-all"
              >
                <Play className="w-4 h-4" />
                看它如何工作
              </a>
            </div>

            {/* Stats */}
            <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-6 max-w-3xl mx-auto">
              <div className="text-center">
                <div className="text-2xl font-black text-[#722ed1]">3</div>
                <div className="text-xs text-[#64748b] mt-1">AI Agents 编排</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-black text-[#1677ff]">3</div>
                <div className="text-xs text-[#64748b] mt-1">CI/CD 流水线层</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-black text-[#f59e0b]">1</div>
                <div className="text-xs text-[#64748b] mt-1">键生成审计包</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-black text-[#10b981]">100%</div>
                <div className="text-xs text-[#64748b] mt-1">Docker 自托管</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#722ed1]">核心功能</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">
              嵌入式开发，一个平台搞定
            </h2>
            <p className="text-[#94a3b8] mt-4 max-w-xl mx-auto">
              从需求定义到审计合规，yuleOSH 覆盖嵌入式开发全生命周期
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[
              { icon: <FileText className="w-5 h-5 text-[#722ed1]" />, color: "#722ed1", title: "OpenSpec 需求管理", desc: "基于 SHALL/SHOULD/MAY 语法的结构化需求定义。自动追溯矩阵，从需求到代码、测试的双向覆盖，支持增量变更（Delta）管理。" },
              { icon: <Cpu className="w-5 h-5 text-[#1677ff]" />, color: "#1677ff", title: "AI 编排流水线", desc: "AI Agent 自动编排全流程：审查需求→生成设计→编写代码→自我测试→代码审查→生成报告。全过程无需人工介入。" },
              { icon: <GitBranch className="w-5 h-5 text-[#f59e0b]" />, color: "#f59e0b", title: "SDD → DDD → TDD 管线", desc: "从软件设计文档到详细设计文档再到测试驱动开发，逐层自动化推进。设计即代码，测试即文档，确保全过程可追溯。" },
              { icon: <Shield className="w-5 h-5 text-[#10b981]" />, color: "#10b981", title: "三层 CI/CD 流水线", desc: "Layer 1 开发验证 → Layer 2 集成验证 → Layer 3 系统验证。逐层推进，与 ASPICE 标准对齐（SWE.4 / SWE.5 / SWE.6）。" },
              { icon: <BarChart3 className="w-5 h-5 text-[#1677ff]" />, color: "#1677ff", title: "一键 ASPICE 合规包", desc: "自动生成合规审计证据包：追溯矩阵、覆盖率报告、审查日志。一键打包下载，直接用于 ASPICE 评估或客户审计。" },
              { icon: <Container className="w-5 h-5 text-[#10b981]" />, color: "#10b981", title: "Docker 自托管 / SaaS", desc: "一行命令 Docker 部署，数据完全掌控在您手中。同时提供 SaaS 云版本，零部署成本，快速上手体验。" },
            ].map((f, i) => (
              <div key={i} className="feature-card rounded-xl border border-[#1e293b] bg-[#111827] p-6">
                <div
                  className="w-11 h-11 rounded-lg flex items-center justify-center mb-4"
                  style={{ background: `${f.color}10` }}
                >
                  {f.icon}
                </div>
                <h3 className="text-base font-bold text-[#e2e8f0] mb-2">{f.title}</h3>
                <p className="text-sm text-[#94a3b8] leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-24 bg-[#0a0e17]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#1677ff]">工作流程</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">
              从需求到交付，<span className="gradient-text">全自动</span>
            </h2>
            <p className="text-[#94a3b8] mt-4 max-w-xl mx-auto">
              配置好项目，剩下的交给 AI Agent 流水线
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 relative">
            {[
              { icon: <FileText className="w-7 h-7 text-[#10b981]" />, color: "#10b981", num: "1", title: "定义需求", desc: "编写 OpenSpec 格式的需求文档。SHALL/SHOULD/MAY 语法清晰定义功能与验收标准，AI 自动评审需求质量。" },
              { icon: <Cpu className="w-7 h-7 text-[#1677ff]" />, color: "#1677ff", num: "2", title: "AI 自动开发", desc: "Agent 编排流水线自动执行：SDD 设计 → DDD 细化 → TDD 测试先行 → 代码实现 → 自我测试 → 代码审查。全过程无需人工介入。" },
              { icon: <Shield className="w-7 h-7 text-[#10b981]" />, color: "#10b981", num: "3", title: "交付与合规", desc: "三层 CI/CD 流水线验证。可追溯矩阵自动生成，一键导出 ASPICE 合规审计包。快速交付，轻松通过客户审计。" },
            ].map((s, i) => (
              <div key={i} className="relative text-center p-6">
                <div
                  className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5"
                  style={{ background: `${s.color}15`, border: `1px solid ${s.color}30` }}
                >
                  {s.icon}
                </div>
                <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-3 w-8 h-8 rounded-full text-white text-xs font-black flex items-center justify-center"
                  style={{ background: s.color }}
                >{s.num}</div>
                <h3 className="text-lg font-bold text-[#e2e8f0] mb-2">{s.title}</h3>
                <p className="text-sm text-[#94a3b8] leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>

          {/* V-Model Pipeline — Three-phase vertical */}
          <div className="mt-16 gradient-border">
            <div className="bg-[#111827] rounded-2xl p-6 sm:p-8">
              <h3 className="text-sm font-semibold text-[#94a3b8] mb-8 text-center tracking-wider uppercase">
                AI Pipeline 全流程 — ASPICE V-Model
              </h3>
              <div className="flex flex-col gap-6">
                {/* Phase 1: Design */}
                <div className="relative overflow-hidden rounded-xl"
                  style={{ background: "linear-gradient(135deg, rgba(114,46,209,.08), rgba(114,46,209,.02))", border: "1px solid rgba(114,46,209,.15)" }}>
                  <div className="absolute top-0 left-0 w-1 h-full" style={{ background: "linear-gradient(180deg, #722ed1, rgba(114,46,209,.3))" }} />
                  <div className="p-5">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ background: "#722ed1" }} />
                        <span className="text-xs font-semibold text-[#722ed1] tracking-wider uppercase">Phase 1 · 设计层</span>
                      </div>
                      <span className="text-[10px] text-[#64748b]">Layer 1 · SWE.4</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(114,46,209,.12)", color: "#c084fc", border: "1px solid rgba(114,46,209,.2)" }}>需求分析</span>
                      <ArrowRight className="w-3 h-3 text-[#334155]" />
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(114,46,209,.12)", color: "#c084fc", border: "1px solid rgba(114,46,209,.2)" }}>架构设计</span>
                      <ArrowRight className="w-3 h-3 text-[#334155]" />
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(114,46,209,.12)", color: "#c084fc", border: "1px solid rgba(114,46,209,.2)" }}>详细设计</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(114,46,209,.06)", color: "#64748b" }}>Spec.md</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(114,46,209,.06)", color: "#64748b" }}>Architecture.md</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(114,46,209,.06)", color: "#64748b" }}>验收矩阵</span>
                    </div>
                  </div>
                </div>

                {/* Phase 2: Verification */}
                <div className="relative overflow-hidden rounded-xl"
                  style={{ background: "linear-gradient(135deg, rgba(22,119,255,.08), rgba(22,119,255,.02))", border: "1px solid rgba(22,119,255,.15)" }}>
                  <div className="absolute top-0 left-0 w-1 h-full" style={{ background: "linear-gradient(180deg, #1677ff, rgba(22,119,255,.3))" }} />
                  <div className="p-5">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ background: "#1677ff" }} />
                        <span className="text-xs font-semibold text-[#1677ff] tracking-wider uppercase">Phase 2 · 验证层</span>
                      </div>
                      <span className="text-[10px] text-[#64748b]">Layer 2 · SWE.5</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(22,119,255,.12)", color: "#60a5fa", border: "1px solid rgba(22,119,255,.2)" }}>代码实现</span>
                      <ArrowRight className="w-3 h-3 text-[#334155]" />
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(22,119,255,.12)", color: "#60a5fa", border: "1px solid rgba(22,119,255,.2)" }}>单元测试</span>
                      <ArrowRight className="w-3 h-3 text-[#334155]" />
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(22,119,255,.12)", color: "#60a5fa", border: "1px solid rgba(22,119,255,.2)" }}>静态分析</span>
                      <ArrowRight className="w-3 h-3 text-[#334155]" />
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(22,119,255,.12)", color: "#60a5fa", border: "1px solid rgba(22,119,255,.2)" }}>集成测试</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(22,119,255,.06)", color: "#64748b" }}>Code</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(22,119,255,.06)", color: "#64748b" }}>Test Report</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(22,119,255,.06)", color: "#64748b" }}>Coverage</span>
                    </div>
                  </div>
                </div>

                {/* Phase 3: Delivery */}
                <div className="relative overflow-hidden rounded-xl"
                  style={{ background: "linear-gradient(135deg, rgba(16,185,129,.08), rgba(16,185,129,.02))", border: "1px solid rgba(16,185,129,.15)" }}>
                  <div className="absolute top-0 left-0 w-1 h-full" style={{ background: "linear-gradient(180deg, #10b981, rgba(16,185,129,.3))" }} />
                  <div className="p-5">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ background: "#10b981" }} />
                        <span className="text-xs font-semibold text-[#10b981] tracking-wider uppercase">Phase 3 · 交付层</span>
                      </div>
                      <span className="text-[10px] text-[#64748b]">Layer 3 · SWE.6</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(16,185,129,.12)", color: "#34d399", border: "1px solid rgba(16,185,129,.2)" }}>系统测试</span>
                      <ArrowRight className="w-3 h-3 text-[#334155]" />
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(16,185,129,.12)", color: "#34d399", border: "1px solid rgba(16,185,129,.2)" }}>验收</span>
                      <ArrowRight className="w-3 h-3 text-[#334155]" />
                      <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                        style={{ background: "rgba(16,185,129,.12)", color: "#34d399", border: "1px solid rgba(16,185,129,.2)" }}>证据包</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(16,185,129,.06)", color: "#64748b" }}>合规审计包</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(16,185,129,.06)", color: "#64748b" }}>追溯矩阵</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(16,185,129,.06)", color: "#64748b" }}>审查日志</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="text-center mt-8">
            <Link href="/dashboard/projects/1"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-sm"
              style={{ background: "linear-gradient(135deg,#722ed1,#1677ff)", color: "#fff", boxShadow: "0 0 20px rgba(114,46,209,.2)" }}
            >
              <Layers className="w-4 h-4" />
              查看完整 Pipeline 流水线
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-[#0d111f] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">
            准备好了吗？
          </h2>
          <p className="text-[#94a3b8] mb-8">
            无需注册，立即体验嵌入式AI开发全流程自动化
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/dashboard"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white font-semibold text-sm shadow-lg shadow-[#722ed1]/20 hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 transition-all"
            >
              立即体验
              <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="https://github.com/stefanji/yuleOSH" target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl border border-[#1e293b] text-[#94a3b8] hover:border-white/20 hover:text-white text-sm font-medium transition-all"
            >
              <GithubIcon className="w-4 h-4" />
              GitHub
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-[#1e293b] bg-[#0a0e17]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <Link href="/" className="text-lg font-black tracking-tight">
                <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
              </Link>
              <span className="text-xs text-[#64748b]">v0.1.0 · MIT License</span>
            </div>
            <div className="flex items-center gap-6">
              <a href="#features" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">功能</a>
              <Link href="/pricing" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">定价</Link>
              <Link href="/login" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">登录</Link>
              <a href="https://github.com/stefanji/yuleOSH" target="_blank" rel="noreferrer" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">GitHub</a>
            </div>
          </div>
          <div className="mt-6 text-center text-xs text-[#393e4a]">
            Built for embedded developers. Open source and community driven.
          </div>
        </div>
      </footer>
    </div>
  );
}

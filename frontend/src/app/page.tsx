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
  Layers,
  Play,
  Sparkles,
  BarChart3,
  Star,
  Users,
  Zap,
  CheckCircle,
  ChevronRight,
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
              <Link href="/register"
                className="text-sm inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg font-semibold min-h-[48px] bg-gradient-to-r from-[#10b981] to-[#059669] text-white shadow-lg shadow-[#10b981]/20 hover:from-[#10b981]/90 hover:to-[#059669]/90 transition-all"
              >
                <Sparkles className="w-4 h-4" />
                免费试用
              </Link>
              <Link href="/demo"
                className="text-sm inline-flex items-center gap-1.5 px-4 py-2 rounded-lg font-semibold border border-[#1e293b] text-[#94a3b8] hover:border-[#10b981]/40 hover:text-white transition-all"
              >
                🎮 Try Demo
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
              <Link href="/register" onClick={() => setMobileOpen(false)}
                className="block text-sm px-4 py-3 rounded-lg font-semibold bg-gradient-to-r from-[#10b981] to-[#059669] text-white text-center"
              >
                <Sparkles className="w-4 h-4 inline-block mr-1" />
                免费试用
              </Link>
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
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#10b981]/30 bg-[#10b981]/5 text-[#10b981] text-xs font-medium mb-8">
              <span className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse"></span>
              🚗 ASPICE Compliant · 开源 · 14天免费试用 · Docker 自托管
            </div>

            <h1 className="text-4xl sm:text-5xl md:text-7xl font-black tracking-tight leading-[1.1] mb-6">
              <span className="gradient-text">一站式 ASPICE 合规</span><br />
              <span className="text-[#e2e8f0]">AI 嵌入式开发平台</span>
            </h1>

            <p className="text-lg sm:text-xl text-[#94a3b8] max-w-3xl mx-auto mb-6 leading-relaxed">
              <strong className="text-[#10b981]">Automotive SPICE compliant out of the box.</strong><br />
              从自然语言需求到硬件测试固件，<strong className="text-[#e2e8f0]">AI Agent 全自动编排</strong>。
              一站式覆盖需求管理、架构设计、代码生成、CI/CD 到 ASPICE 合规审计。
            </p>

            <p className="text-sm text-[#64748b] max-w-lg mx-auto mb-10">
              无需 NDA · 无需销售沟通 · 无需 License 谈判<br />
              <code className="text-[#10b981] bg-[#10b981]/10 px-1.5 py-0.5 rounded text-xs">pip install yuleosh</code> 5 分钟即可开始
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/register"
                className="group relative inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm min-h-[48px] bg-gradient-to-r from-[#10b981] to-[#059669] text-white shadow-lg shadow-[#10b981]/30 hover:from-[#10b981]/90 hover:to-[#059669]/90 transition-all"
              >
                <Sparkles className="w-4 h-4" />
                <span>开始免费试用</span>
                <span className="text-xs ml-1 opacity-80">(14天 Pro 全功能)</span>
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <Link href="/login"
                className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 transition-all"
              >
                <Zap className="w-4 h-4" />
                已有账号？立即登录
              </Link>
              <a href="#how-it-works"
                className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm border border-[#1e293b] text-[#94a3b8] hover:border-[#1677ff]/40 hover:text-white transition-all"
              >
                <Play className="w-4 h-4" />
                看它如何工作
              </a>
            </div>

            {/* Social Proof */}
            <div className="mt-12 max-w-3xl mx-auto">
              <div className="flex items-center justify-center gap-2 text-xs text-[#64748b] mb-4">
                <Star className="w-3 h-3 text-[#f59e0b] fill-[#f59e0b]" />
                <Star className="w-3 h-3 text-[#f59e0b] fill-[#f59e0b]" />
                <Star className="w-3 h-3 text-[#f59e0b] fill-[#f59e0b]" />
                <Star className="w-3 h-3 text-[#f59e0b] fill-[#f59e0b]" />
                <Star className="w-3 h-3 text-[#f59e0b] fill-[#f59e0b]" />
                <span className="ml-1">5.0 · 社区驱动 · MIT 开源</span>
              </div>
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
                <div className="text-2xl font-black text-[#f59e0b">1</div>
                <div className="text-xs text-[#64748b] mt-1">键生成审计包</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-black text-[#10b981]">100%</div>
                <div className="text-xs text-[#64748b] mt-1">Docker 自托管</div>
              </div>
            </div>

            {/* Registration funnel */}
            <div className="mt-10">
              <Link href="/register"
                className="inline-flex items-center gap-1.5 text-sm text-[#10b981] hover:text-[#10b981]/80 transition-colors group"
              >
                免费注册，无需信用卡
                <ChevronRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Trust Bar */}
      <section className="py-10 border-y border-[#1e293b] bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-xs text-center text-[#64748b] uppercase tracking-widest mb-6">
            被全球嵌入式开发团队信赖
          </p>
          <div className="flex flex-wrap items-center justify-center gap-8 md:gap-16 text-[#39404e]">
            <span className="text-lg font-bold tracking-wider">STM32</span>
            <span className="text-lg font-bold tracking-wider">ESP32</span>
            <span className="text-lg font-bold tracking-wider">ARM CMSIS</span>
            <span className="text-lg font-bold tracking-wider">FreeRTOS</span>
            <span className="text-lg font-bold tracking-wider">Zephyr</span>
            <span className="text-lg font-bold tracking-wider">AUTOSAR</span>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="text-xs font-semibold tracking-widest uppercase text-[#722ed1]">核心功能</span>
            <h2 className="text-3xl sm:text-4xl font-black mt-3 text-[#e2e8f0]">
              嵌入式开发，<span className="gradient-text">AI 一个平台搞定</span>
            </h2>
            <p className="text-[#94a3b8] mt-4 max-w-2xl mx-auto">
              从需求定义到审计合规，yuleOSH 覆盖嵌入式开发全生命周期。
              <strong> 注册即可免费使用全部 Pro 功能 14 天。</strong>
            </p>
            <Link href="/register"
              className="inline-flex items-center gap-1.5 mt-6 text-sm font-semibold text-[#10b981] hover:text-[#10b981]/80 transition-colors group"
            >
              <Sparkles className="w-4 h-4" />
              免费开始试用
              <ChevronRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
            </Link>
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
              从需求到交付，<span className="gradient-text">全自动 AI 流水线</span>
            </h2>
            <p className="text-[#94a3b8] mt-4 max-w-2xl mx-auto">
              配置好项目，剩下的交给 AI Agent 流水线。
              <strong> 注册后一键创建示例项目，立即体验全流程。</strong>
            </p>
            <Link href="/register"
              className="inline-flex items-center gap-1.5 mt-6 text-sm font-semibold text-[#1677ff] hover:text-[#1677ff]/80 transition-colors group"
            >
              免费开始
              <ChevronRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
            </Link>
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

          {/* Pipeline visualization */}
          <div className="mt-16 gradient-border">
            <div className="bg-[#111827] rounded-2xl p-6 sm:p-8">
              <h3 className="text-sm font-semibold text-[#94a3b8] mb-8 text-center tracking-wider uppercase">
                AI Pipeline 全流程 — ASPICE V-Model
              </h3>
              <div className="flex flex-col gap-6">
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
                  </div>
                </div>
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
                        style={{ background: "rgba(22,119,255,.12)", color: "#60a5fa", border: "1px solid rgba(22,119,255,.2)" }}>集成测试</span>
                    </div>
                  </div>
                </div>
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
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Pipeline Demo CTA */}
          <div className="mt-8 text-center">
            <Link
              href="/demo"
              className="inline-flex items-center gap-2.5 px-8 py-4 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 transition-all group"
            >
              <Play className="w-4 h-4" />
              查看 Pipeline 演示
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <p className="text-xs text-[#64748b] mt-3">
              无需注册，直接体验 AI Agent 全自动流水线的完整运行过程。
            </p>
          </div>
        </div>
      </section>

      {/* Pricing Snapshot */}
      <section className="py-24 bg-[#0a0e17] border-t border-[#1e293b]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#722ed1]/30 bg-[#722ed1]/5 text-[#722ed1] text-xs font-medium mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-[#722ed1]"></span>
            透明定价 · 即用即省
          </span>
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">
            找到适合你的<span className="gradient-text">方案</span>
          </h2>
          <p className="text-[#94a3b8] mb-12 max-w-xl mx-auto">
            从个人开发者到企业团队，免费起步，按需升级。无需 NDA，无需销售对接。
          </p>

          <div className="grid md:grid-cols-4 gap-4 text-left max-w-5xl mx-auto">
            {/* Free */}
            <div className="rounded-2xl border border-[#1e293b] bg-[#111827] p-6 flex flex-col">
              <h3 className="text-lg font-bold text-[#e2e8f0]">Free</h3>
              <div className="mt-2 mb-4">
                <span className="text-3xl font-black text-[#e2e8f0]">¥0</span>
                <span className="text-xs text-[#64748b] ml-1">永久免费</span>
              </div>
              <ul className="space-y-2 text-xs text-[#94a3b8] flex-1">
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  1-3 人 · 基础 Pipeline · 3 项目
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  AI Code Review 基础
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  ESP32/STM32 + QEMU
                </li>
              </ul>
              <a href="/register" className="mt-4 block w-full text-center py-2 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#1677ff]/40 text-xs font-semibold transition-all">免费开始</a>
            </div>

            {/* Team */}
            <div className="rounded-2xl border border-[#1e293b] bg-[#111827] p-6 flex flex-col">
              <h3 className="text-lg font-bold text-[#e2e8f0]">Team</h3>
              <div className="mt-2 mb-4">
                <span className="text-3xl font-black text-[#e2e8f0]">¥199</span>
                <span className="text-xs text-[#64748b] ml-1">/月</span>
                <div className="text-[10px] text-[#64748b] mt-0.5">年付 ¥1,999</div>
              </div>
              <ul className="space-y-2 text-xs text-[#94a3b8] flex-1">
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  无限项目 · 10 人团队
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  SDD→DDD→TDD 全管线
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  ASPICE 合规包（基础）
                </li>
              </ul>
              <a href="/register" className="mt-4 block w-full text-center py-2 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#1677ff]/40 text-xs font-semibold transition-all">选择 Team</a>
            </div>

            {/* Pro (Featured) */}
            <div className="rounded-2xl border-2 border-[#722ed1]/40 bg-[#111827] p-6 flex flex-col relative scale-[1.03]">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white text-[10px] font-bold shadow-lg whitespace-nowrap">
                最受欢迎
              </div>
              <h3 className="text-lg font-bold text-[#e2e8f0]">Pro</h3>
              <div className="mt-2 mb-4">
                <span className="text-3xl font-black text-[#e2e8f0]">¥999</span>
                <span className="text-xs text-[#64748b] ml-1">/月</span>
                <div className="text-[10px] text-[#64748b] mt-0.5">年付 ¥9,999</div>
              </div>
              <ul className="space-y-2 text-xs text-[#94a3b8] flex-1">
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  无限项目 · 无限成员
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  硬件在环 + 并行 4-Agent
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#10b981] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  一键 ASPICE 完整合规包
                </li>
              </ul>
              <a href="/register" className="mt-4 block w-full text-center py-2 rounded-lg bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 text-xs font-semibold shadow-lg shadow-[#722ed1]/20 transition-all">免费试用 Pro</a>
            </div>

            {/* Enterprise */}
            <div className="rounded-2xl border border-[#1e293b] bg-[#111827] p-6 flex flex-col">
              <h3 className="text-lg font-bold text-[#e2e8f0]">Enterprise</h3>
              <div className="mt-2 mb-4">
                <span className="text-3xl font-black text-[#e2e8f0]">定制</span>
                <span className="text-xs text-[#64748b] ml-1">/月起</span>
                <div className="text-[10px] text-[#64748b] mt-0.5">+ ASPICE 咨询 ¥298K/年</div>
              </div>
              <ul className="space-y-2 text-xs text-[#94a3b8] flex-1">
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#f59e0b] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  私有化部署 (K8s Helm)
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#f59e0b] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  SLA 99.95% + 专属 CSM
                </li>
                <li className="flex items-start gap-2">
                  <svg className="w-3.5 h-3.5 text-[#f59e0b] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
                  ASPICE 现场检查 CL1-CL3
                </li>
              </ul>
              <a href="mailto:sales@yuleosh.com" className="mt-4 block w-full text-center py-2 rounded-lg border border-[#f59e0b]/30 bg-[#f59e0b]/5 text-[#f59e0b] hover:bg-[#f59e0b]/10 text-xs font-semibold transition-all">联系销售</a>
            </div>
          </div>

          <div className="mt-10">
            <Link href="/pricing" className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-[#1e293b] text-[#94a3b8] hover:border-white/20 hover:text-white text-sm font-medium transition-all">
              查看完整定价对比
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>
            </Link>
          </div>
        </div>
      </section>

      {/* CTA - Main */}
      <section className="py-20 bg-[#0d111f] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">
            准备好了吗？<span className="gradient-text">14 天免费试用</span>
          </h2>
          <p className="text-[#94a3b8] mb-8 max-w-lg mx-auto">
            无需信用卡。注册即获得全部 Pro 功能访问权限。
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/register"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-[#10b981] to-[#059669] text-white font-semibold text-sm shadow-lg shadow-[#10b981]/20 hover:from-[#10b981]/90 hover:to-[#059669]/90 transition-all"
            >
              <Sparkles className="w-4 h-4" />
              免费开始试用
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/login"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 transition-all"
            >
              已有账号？登录
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
            <a href="https://github.com/frisky1985/yuleOSH" target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl border border-[#1e293b] text-[#94a3b8] hover:border-white/20 hover:text-white text-sm font-medium transition-all"
            >
              <GithubIcon className="w-4 h-4" />
              GitHub
            </a>
          </div>
          <div className="mt-8 flex items-center justify-center gap-6 text-xs text-[#64748b]">
            <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-[#10b981]" /> 无需信用卡</span>
            <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-[#10b981]" /> 随时取消</span>
            <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-[#10b981]" /> 数据安全</span>
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
              <Link href="/register" className="text-xs text-[#10b981] hover:text-[#10b981]/80 transition-colors font-medium">免费开始试用</Link>
              <a href="https://github.com/frisky1985/yuleOSH" target="_blank" rel="noreferrer" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">GitHub</a>
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

"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  Check,
  Menu,
  X,
  Sparkles,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const plans = [
  {
    name: "Free",
    price: "¥0",
    period: "forever",
    description: "个人开发者入门首选。适合 1-3 人独立探索嵌入式 AI 开发与 ASPICE 合规。",
    highlight: false,
    features: [
      "基础 Pipeline（Spec → Code → Test → CI）",
      "3 个项目限制",
      "AI Code Review 基础规则",
      "ESP32 / STM32 模板 + QEMU SIL",
      "社区支持（GitHub Issues）",
    ],
    cta: "免费开始",
    ctaHref: "/register",
    ctaVariant: "outline" as const,
  },
  {
    name: "Pro",
    price: "¥999",
    period: "/月",
    annual: "年付 ¥9,999 · 首月免费试用",
    description: "团队全功能版，面向需要 ASPICE 合规与 CI/CD 自动化的嵌入式团队。",
    highlight: true,
    badge: "首月免费试用",
    features: [
      "无限项目 · 无限成员",
      "SDD → DDD → TDD 全管线",
      "三层 CI/CD 流水线 + SIL 集成",
      "全部 AI Code Review + 并行 4-Agent 矩阵",
      "硬件在环（OpenOCD / JLink / esptool）",
      "多租户隔离 + 插件市场",
      "一键 ASPICE 合规包（追溯矩阵 + 验收矩阵）",
      "高级证据包 + 自定义审计报告",
      "共享工作空间 + 团队仪表盘",
      "技术邮件支持 48h 响应",
    ],
    cta: "免费开始试用 Pro",
    ctaHref: "/register?plan=pro",
    ctaVariant: "default" as const,
  },
];

const enterprise = {
  name: "Enterprise",
  price: "¥99,800",
  period: "/月起",
  description: "面向需要私有化部署 + ASPICE 认证咨询的企业级团队。",
  features: [
    "私有化部署（Docker / K8s + Helm）",
    "SAML / LDAP SSO + RBAC",
    "SLA 99.95% 可用性保障",
    "专属客户成功经理",
    "HIL 适配器定制（Vector/dSPACE/自定义）",
    "SOC 2 / ISO 27001 合规",
  ],
  cta: "咨询 Enterprise",
  ctaHref: "mailto:sales@yuleosh.com?subject=yuleOSH%20Enterprise%20咨询",
};

export default function PricingPage() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative min-h-screen bg-[#0a0e17] text-[#e2e8f0] overflow-x-hidden">
      {/* Nav (same as landing page) */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[#1e293b]/60 nav-blur" style={{ background: "rgba(10,14,23,.85)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link href="/" className="flex items-center gap-2.5 group">
              <span className="text-2xl font-black tracking-tight">
                <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
              </span>
            </Link>
            <div className="hidden md:flex items-center gap-8">
              <Link href="/" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">首页</Link>
              <Link href="/pricing" className="text-sm text-[#e2e8f0] font-medium transition-colors">定价</Link>
              <Link href="/register" className="text-sm inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg font-semibold min-h-[42px] bg-gradient-to-r from-[#10b981] to-[#059669] text-white shadow-lg shadow-[#10b981]/20 hover:from-[#10b981]/90 hover:to-[#059669]/90 transition-all">
                <Sparkles className="w-3.5 h-3.5" />
                开始免费试用
              </Link>
              <Link href="/login" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">登录</Link>
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
              <Link href="/" onClick={() => setMobileOpen(false)} className="block text-sm text-[#94a3b8] hover:text-white transition-colors">首页</Link>
              <Link href="/pricing" onClick={() => setMobileOpen(false)} className="block text-sm text-white font-medium transition-colors">定价</Link>
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
      <section className="relative pt-32 pb-16 bg-grid overflow-hidden">
        <div className="absolute top-1/3 left-1/4 w-96 h-96 bg-[#722ed1]/5 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-[#1677ff]/5 rounded-full blur-[120px]"></div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <Badge variant="outline" className="mb-6 border-[#722ed1]/30 text-[#722ed1] bg-[#722ed1]/5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#722ed1] mr-1.5"></span>
            Simple. Transparent. No surprises.
          </Badge>
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight leading-[1.1] mb-6">
            <span className="gradient-text">Choose the plan</span><br />
            <span className="text-[#e2e8f0]">that fits your team</span>
          </h1>
          <p className="text-lg text-[#94a3b8] max-w-2xl mx-auto mb-4">
            Start with Free. Upgrade when you outgrow it.
          </p>
          <p className="text-sm text-[#64748b] max-w-xl mx-auto">
            No NDA. No Sales Call. No License Negotiation.
            Just <code className="text-[#10b981] bg-[#10b981]/10 px-1.5 py-0.5 rounded text-xs">pip install yuleosh</code> and you're running in 5 minutes.
          </p>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="py-16 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-3 gap-6 lg:gap-8 max-w-5xl mx-auto">
            {plans.map((plan) => (
              <Card
                key={plan.name}
                className={`relative flex flex-col bg-[#111827] border ${
                  plan.highlight
                    ? "border-[#722ed1]/50 shadow-lg shadow-[#722ed1]/10 scale-[1.02] md:scale-[1.05]"
                    : "border-[#1e293b]"
                }`}
              >
                {plan.badge && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
                    <Badge className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white border-none px-4 py-1 text-xs font-semibold shadow-lg shadow-[#722ed1]/30">
                      <Sparkles className="w-3 h-3 mr-1" />
                      {plan.badge}
                    </Badge>
                  </div>
                )}

                <CardHeader className="pt-8 pb-0">
                  <CardTitle className="text-lg font-bold text-[#e2e8f0]">{plan.name}</CardTitle>
                  <div className="mt-3 flex items-baseline gap-1">
                    <span className="text-4xl font-black text-[#e2e8f0]">{plan.price}</span>
                    <span className="text-sm text-[#94a3b8]">{plan.period}</span>
                  </div>
                  <CardDescription className="mt-3 text-sm text-[#94a3b8] leading-relaxed">
                    {plan.description}
                  </CardDescription>
                </CardHeader>

                <CardContent className="flex-1 pt-6">
                  <ul className="space-y-3">
                    {plan.features.map((feature, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-[#cbd5e1]">
                        <Check className="w-4 h-4 mt-0.5 shrink-0 text-[#10b981]" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>

                <CardFooter className="border-t border-[#1e293b] bg-transparent pt-4 pb-6">
                  <Link
                    href={plan.ctaHref}
                    className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all ${
                      plan.ctaVariant === "default"
                        ? "bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20"
                        : "border border-[#1e293b] text-[#94a3b8] hover:border-[#1677ff]/40 hover:text-white"
                    }`}
                  >
                    {plan.cta}
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </CardFooter>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Enterprise */}
      <section className="py-20 bg-[#0a0e17] border-t border-[#1e293b]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="gradient-border rounded-2xl">
            <div className="bg-[#111827] rounded-2xl p-8 sm:p-12 text-center">
              <Badge variant="outline" className="mb-4 border-[#f59e0b]/30 text-[#f59e0b] bg-[#f59e0b]/5">
                Enterprise + ASPICE Consulting
              </Badge>
              <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">
                Need something <span className="gradient-text">more powerful</span>?
              </h2>
              <p className="text-[#94a3b8] max-w-2xl mx-auto mb-4 leading-relaxed">
                Custom pricing for organizations that need private deployment, advanced security,
                dedicated support, and end-to-end ASPICE certification readiness.
              </p>
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#f59e0b]/10 border border-[#f59e0b]/20 text-[#f59e0b] text-sm font-semibold mb-8">
                <span className="w-2 h-2 rounded-full bg-[#f59e0b] animate-pulse"></span>
                Option: <strong>¥298K/年</strong> ASPICE Consulting Package — 现场检查 + 定制证据包
              </div>
              <div className="grid sm:grid-cols-2 gap-4 max-w-2xl mx-auto mb-10 text-left">
                {[
                  "私有化部署（On-Premise + K8s Helm）",
                  "SAML / LDAP SSO + RBAC",
                  "SLA 保障（99.95% uptime）",
                  "专属客户成功经理 + 现场支持",
                  "SOC 2 / ISO 27001 合规",
                  "HIL 适配器定制（Vector/dSPACE 等）",
                  "ASPICE 现场检查（CL1-CL3）",
                  "定制合规证据包（客户审计就绪）",
                ].map((feature, i) => (
                  <div key={i} className="flex items-start gap-2.5 text-sm text-[#cbd5e1]">
                    <Check className="w-4 h-4 mt-0.5 shrink-0 text-[#f59e0b]" />
                    <span>{feature}</span>
                  </div>
                ))}
              </div>
              <a
                href="mailto:sales@yuleosh.com"
                className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm
                  bg-gradient-to-r from-[#f59e0b] to-[#f97316] text-white
                  hover:from-[#f59e0b]/90 hover:to-[#f97316]/90 shadow-lg shadow-[#f59e0b]/20 transition-all"
              >
                Contact Us
                <ArrowRight className="w-4 h-4" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-20 bg-[#0d111f] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl sm:text-3xl font-black text-center text-[#e2e8f0] mb-12">
            Frequently Asked Questions
          </h2>
          <div className="space-y-5">
            {[
              {
                q: "Can I try Pro before buying?",
                a: "Yes! Start with Free — no credit card required. Upgrade to Pro anytime via the dashboard.",
              },
              {
                q: "What hardware adapters does Pro support?",
                a: "OpenOCD (STM32), JLink (ARM Cortex-M), esptool (ESP32), Vector CANoe/dSPACE for automotive. More on the way.",
              },
              {
                q: "How does Team pricing work?",
                a: "Pro 版 ¥299/月（¥2,999/年）锁定 5-15 人团队，不按人头计费。超出 15 人请联系 Enterprise 方案。包含共享工作空间和团队仪表盘。",
              },
              {
                q: "Can I cancel anytime?",
                a: "Yes. No lock-in, no cancellation fees. Your data stays accessible on the Free tier after cancellation.",
              },
              {
                q: "Do you offer educational / open-source discounts?",
                a: "Yes! Contact us at edu@yuleosh.com for academic pricing and open-source project sponsorships.",
              },
            ].map((faq, i) => (
              <details
                key={i}
                className="group rounded-xl border border-[#1e293b] bg-[#111827] p-5 cursor-pointer transition-all hover:border-[#1e293b]/80"
              >
                <summary className="text-sm font-semibold text-[#e2e8f0] list-none flex items-center justify-between">
                  {faq.q}
                  <span className="text-[#64748b] transition-transform group-open:rotate-180">▾</span>
                </summary>
                <p className="mt-3 text-sm text-[#94a3b8] leading-relaxed pr-8">
                  {faq.a}
                </p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-[#0a0e17] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">
            Start building in <span className="gradient-text">5 minutes</span>
          </h2>
          <p className="text-[#94a3b8] mb-8">
            No NDA. No Sales Call. No License Negotiation.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/register"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-[#10b981] to-[#059669] text-white font-semibold text-sm shadow-lg shadow-[#10b981]/20 hover:from-[#10b981]/90 hover:to-[#059669]/90 transition-all"
            >
              <Sparkles className="w-4 h-4" />
              免费开始试用
              <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="https://github.com/stefanji/yuleOSH" target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl border border-[#1e293b] text-[#94a3b8] hover:border-white/20 hover:text-white text-sm font-medium transition-all"
            >
              <GithubIcon className="w-4 h-4" />
              View on GitHub
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
              <Link href="/register" className="text-xs text-[#10b981] hover:text-[#10b981]/80 transition-colors font-medium">免费试用</Link>
              <Link href="/" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">首页</Link>
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

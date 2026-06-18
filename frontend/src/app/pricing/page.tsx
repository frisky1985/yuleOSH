"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Check, Menu, X, Sparkles, Globe } from "lucide-react";
import { GithubIcon } from "@/components/github-icon";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

/* ===== i18n ===== */
type Locale = "zh-CN" | "en";
const LOCALE_KEY = "yuleOSH_locale";

function useLocale(): [Locale, () => void] {
  const [locale, setLocale] = useState<Locale>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem(LOCALE_KEY) as Locale) || "zh-CN";
    }
    return "zh-CN";
  });
  const toggle = () => setLocale((l) => {
    const next: Locale = l === "zh-CN" ? "en" : "zh-CN";
    if (typeof window !== "undefined") {
      localStorage.setItem(LOCALE_KEY, next);
    }
    return next;
  });
  return [locale, toggle];
}

/* ===== 中文文案 ===== */
const zh = {
  nav: { home: "首页", pricing: "定价", freeTrial: "免费试用", login: "登录" },
  hero: {
    badge: "透明定价 · 无隐藏费用",
    title: "选择适合团队的方案",
    sub: "免费起步，按需升级。",
    desc: "无需 NDA，无需销售对接。",
    code: "pip install yuleosh",
    codeAfter: "5 分钟即可开始。",
  },
  plans: [
    {
      name: "Free",
      price: "¥0",
      period: "永久免费",
      description: "个人开发者入门首选，适合 1-3 人独立探索嵌入式 AI 开发。",
      features: [
        "基础 Pipeline（Spec → Code → Test → CI）",
        "1-3 人 · 3 个项目限制",
        "AI Code Review 基础规则",
        "ESP32 / STM32 模板 + QEMU SIL",
        "社区支持（GitHub Issues）",
      ],
      cta: "免费开始",
    },
    {
      name: "Team",
      price: "¥199",
      period: "/月",
      annual: "年付 ¥1,999（省 16%）",
      description: "小型团队协作版，适合 3-10 人嵌入式团队日常开发。",
      highlight: false,
      features: [
        "无限项目 · 10 人团队",
        "SDD → DDD → TDD 全管线",
        "三层 CI/CD 流水线 + SIL 集成",
        "AI Code Review（8 种检测）",
        "一键 ASPICE 合规包（基础）",
        "共享工作空间 + 团队仪表盘",
        "技术邮件支持 72h 响应",
      ],
      cta: "选择 Team",
    },
    {
      name: "Pro",
      price: "¥999",
      period: "/月",
      annual: "年付 ¥9,999（省 17%）",
      description: "全功能版，面向需要完整 ASPICE 合规与自动化的嵌入式团队。",
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
      cta: "免费试用 Pro",
    },
  ],
  enterprise: {
    badge: "Enterprise + ASPICE 咨询",
    title: "需要更强大的方案？",
    desc: "面向需要私有化部署、高级安全、专属支持及端到端 ASPICE 认证的企业团队。",
    option: "可选 ¥298,000/年 ASPICE 咨询包（含现场检查 + 定制证据包）",
    features: [
      "私有化部署（On-Premise + K8s Helm）",
      "SAML / LDAP SSO + RBAC",
      "SLA 保障（99.95% uptime）",
      "专属客户成功经理 + 现场支持",
      "SOC 2 / ISO 27001 合规",
      "HIL 适配器定制（Vector/dSPACE 等）",
      "ASPICE 现场检查（CL1-CL3）",
      "定制合规证据包（客户审计就绪）",
    ],
    cta: "联系销售",
  },
  faq: {
    title: "常见问题",
    items: [
      {
        q: "可以先试用 Pro 再付费吗？",
        a: "当然！Pro 首月免费试用，无需绑定信用卡。随时可通过 Dashboard 升级，不满意在第一个月内取消即可，无任何费用。",
      },
      {
        q: "Pro 支持哪些硬件适配器？",
        a: "OpenOCD（STM32）、JLink（ARM Cortex-M）、esptool（ESP32）、Vector CANoe/dSPACE（汽车电子）。更多适配器持续更新中。",
      },
      {
        q: "Team 版和 Pro 版有什么区别？",
        a: "Team 版 ¥199/月（年付 ¥1,999），适合 3-10 人团队日常协作，包含全 Pipeline 和基础合规包。Pro 版 ¥999/月（年付 ¥9,999），增加硬件在环、多租户隔离、插件市场、高级证据包和 48h 技术支持。",
      },
      {
        q: "可以随时取消订阅吗？",
        a: "可以。无合约绑定，无取消费用。取消后数据在 Free 版中依然可访问。",
      },
      {
        q: "提供教育 / 开源项目优惠吗？",
        a: "提供。请联系 edu@yuleosh.com 了解学术定价和开源项目赞助。",
      },
    ],
  },
  cta: {
    title: "5 分钟开始构建",
    desc: "无需 NDA，无需销售对接，无需许可谈判。",
    freeTrial: "免费开始试用",
    viewGitHub: "查看 GitHub",
  },
  footer: {
    v: "v0.1.0 · MIT License",
    freeTrial: "免费开始试用",
    home: "首页",
    login: "登录",
    tagline: "为嵌入式开发者而生 · 开源社区驱动",
  },
  switchLang: "English",
};

/* ===== 英文文案 ===== */
const en: typeof zh = {
  nav: { home: "Home", pricing: "Pricing", freeTrial: "Free Trial", login: "Login" },
  hero: {
    badge: "Simple. Transparent. No surprises.",
    title: "Choose the plan",
    sub: "that fits your team",
    desc: "Start with Free. Upgrade when you outgrow it.",
    code: "pip install yuleosh",
    codeAfter: "and you're running in 5 minutes.",
  },
  plans: [
    {
      name: "Free",
      price: "¥0",
      period: "forever",
      description: "For individual developers exploring embedded AI development with 1-3 people.",
      features: [
        "Basic Pipeline (Spec → Code → Test → CI)",
        "1-3 people · 3 project limit",
        "AI Code Review (basic rules)",
        "ESP32 / STM32 templates + QEMU SIL",
        "Community support (GitHub Issues)",
      ],
      cta: "Get Started Free",
    },
    {
      name: "Team",
      price: "¥199",
      period: "/mo",
      annual: "¥1,999/yr (save 16%)",
      description: "For small teams of 3-10 looking for daily collaboration on embedded projects.",
      highlight: false,
      features: [
        "Unlimited projects · Up to 10 members",
        "Full Pipeline (SDD → DDD → TDD)",
        "3-layer CI/CD + SIL integration",
        "AI Code Review (8 checks)",
        "ASPICE compliance pack (basic)",
        "Shared workspace + team dashboard",
        "Email support (72h response)",
      ],
      cta: "Choose Team",
    },
    {
      name: "Pro",
      price: "¥999",
      period: "/mo",
      annual: "¥9,999/yr (save 17%)",
      description: "Full-featured plan for teams needing complete ASPICE compliance and automation.",
      highlight: true,
      badge: "Free trial available",
      features: [
        "Unlimited projects · Unlimited members",
        "Full Pipeline (SDD → DDD → TDD)",
        "3-layer CI/CD + SIL integration",
        "Full AI Code Review + parallel 4-Agent",
        "Hardware-in-the-loop (OpenOCD / JLink / esptool)",
        "Multi-tenant isolation + plugin marketplace",
        "One-click ASPICE compliance (traceability + acceptance matrix)",
        "Advanced evidence pack + custom audit reports",
        "Shared workspace + team dashboard",
        "Email support (48h response)",
      ],
      cta: "Try Pro Free",
    },
  ],
  enterprise: {
    badge: "Enterprise + ASPICE Consulting",
    title: "Need something more powerful?",
    desc: "Custom pricing for organizations that need private deployment, advanced security, and end-to-end ASPICE certification.",
    option: "Option: ¥298K/yr ASPICE Consulting Package — on-site inspection + custom evidence pack",
    features: [
      "On-Premise deployment (K8s Helm)",
      "SAML / LDAP SSO + RBAC",
      "SLA guarantee (99.95% uptime)",
      "Dedicated CSM + on-site support",
      "SOC 2 / ISO 27001 compliance",
      "Custom HIL adapters (Vector/dSPACE etc.)",
      "ASPICE on-site assessment (CL1-CL3)",
      "Custom compliance evidence pack",
    ],
    cta: "Contact Sales",
  },
  faq: {
    title: "Frequently Asked Questions",
    items: [
      { q: "Can I try Pro before buying?", a: "Yes! Start with a free month of Pro — no credit card required. Upgrade via the dashboard anytime. Not satisfied? Just cancel within the first month at no cost." },
      { q: "What hardware adapters does Pro support?", a: "OpenOCD (STM32), JLink (ARM Cortex-M), esptool (ESP32), Vector CANoe/dSPACE for automotive. More on the way." },
      { q: "What's the difference between Team and Pro?", a: "Team is ¥199/mo for 3-10 person teams with the full pipeline and basic compliance. Pro is ¥999/mo for unlimited members, HIL, multi-tenant, plugin marketplace, advanced evidence packs, and 48h support." },
      { q: "Can I cancel anytime?", a: "Yes. No lock-in, no cancellation fees. Your data stays accessible on the Free tier after cancellation." },
      { q: "Do you offer educational/open-source discounts?", a: "Yes! Contact us at edu@yuleosh.com for academic pricing and open-source project sponsorships." },
    ],
  },
  cta: {
    title: "Start building in 5 minutes",
    desc: "No NDA. No Sales Call. No License Negotiation.",
    freeTrial: "Get Started Free",
    viewGitHub: "View on GitHub",
  },
  footer: {
    v: "v0.1.0 · MIT License",
    freeTrial: "Free Trial",
    home: "Home",
    login: "Login",
    tagline: "Built for embedded developers · Open source and community driven.",
  },
  switchLang: "中文",
};

/* ===== Component ===== */
export default function PricingPage() {
  const [locale, toggleLocale] = useLocale();
  const [mobileOpen, setMobileOpen] = useState(false);
  const t = locale === "zh-CN" ? zh : en;

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
            <div className="hidden md:flex items-center gap-6">

              <Link href="/" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">{t.nav.home}</Link>
              <Link href="/pricing" className="text-sm text-[#e2e8f0] font-medium transition-colors">{t.nav.pricing}</Link>

              <button
                onClick={toggleLocale}
                className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors px-2 py-1 rounded border border-[#1e293b] hover:border-[#1e293b]/80"
              >
                <Globe className="w-3 h-3" />
                {t.switchLang}
              </button>

              <Link href="/register"
                className="text-sm inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg font-semibold min-h-[42px] bg-gradient-to-r from-[#10b981] to-[#059669] text-white shadow-lg shadow-[#10b981]/20 hover:from-[#10b981]/90 hover:to-[#059669]/90 transition-all"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {t.nav.freeTrial}
              </Link>
              <Link href="/login" className="text-sm text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">{t.nav.login}</Link>
            </div>
            <div className="md:hidden flex items-center gap-2">
              <button
                onClick={toggleLocale}
                className="text-xs text-[#64748b] p-1 rounded"
              >
                <Globe className="w-4 h-4" />
              </button>
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
              <Link href="/" onClick={() => setMobileOpen(false)} className="block text-sm text-[#94a3b8] hover:text-white transition-colors">{t.nav.home}</Link>
              <Link href="/pricing" onClick={() => setMobileOpen(false)} className="block text-sm text-white font-medium transition-colors">{t.nav.pricing}</Link>
              <Link href="/login" onClick={() => setMobileOpen(false)} className="block text-sm text-[#94a3b8] hover:text-white transition-colors">{t.nav.login}</Link>
              <Link href="/register" onClick={() => setMobileOpen(false)}
                className="block text-sm px-4 py-2 rounded-lg font-semibold bg-gradient-to-r from-[#10b981] to-[#059669] text-white text-center"
              >
                {t.nav.freeTrial}
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
            {t.hero.badge}
          </Badge>
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight leading-[1.1] mb-6">
            {locale === "zh-CN" ? (
              <span className="text-[#e2e8f0]">{t.hero.title}</span>
            ) : (
              <>
                <span className="gradient-text">{t.hero.title}</span><br />
                <span className="text-[#e2e8f0]">{t.hero.sub}</span>
              </>
            )}
          </h1>
          {/* English uses hero.sub inside the h1; only show sub paragraph for non-English */}
          {locale !== "en" && <p className="text-lg text-[#94a3b8] max-w-2xl mx-auto mb-4">{t.hero.sub}</p>}
          <p className="text-sm text-[#64748b] max-w-xl mx-auto">
            {t.hero.desc}
            <code className="text-[#10b981] bg-[#10b981]/10 px-1.5 py-0.5 rounded text-xs mx-1">{t.hero.code}</code>
            {t.hero.codeAfter}
          </p>
        </div>
      </section>

      {/* Pricing Cards - 4 tiers */}
      <section className="py-16 bg-[#0d111f]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-3 gap-4 lg:gap-6 max-w-5xl mx-auto place-items-center">
            {t.plans.map((plan, idx) => {
              const isPro = plan.name === "Pro";
              const planKey = plan.name.toLowerCase();
              return (
                <Card
                  key={plan.name}
                  className={`relative flex flex-col bg-[#111827] border ${
                    isPro
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
                    {plan.annual && (
                      <p className="text-xs text-[#64748b] mt-1">{plan.annual}</p>
                    )}
                    <CardDescription className="mt-3 text-sm text-[#94a3b8] leading-relaxed">
                      {plan.description}
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="flex-1 pt-6">
                    <ul className="space-y-2.5">
                      {plan.features.map((feature, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-[#cbd5e1]">
                          <Check className="w-4 h-4 mt-0.5 shrink-0 text-[#10b981]" />
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>

                  <CardFooter className="border-t border-[#1e293b] bg-transparent pt-4 pb-6">
                    <Link
                      href={plan.name === "Free" ? "/register" : `/register?plan=${planKey}`}
                      className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all ${
                        isPro
                          ? "bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20"
                          : "border border-[#1e293b] text-[#94a3b8] hover:border-[#1677ff]/40 hover:text-white"
                      }`}
                    >
                      {plan.cta}
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </CardFooter>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* Enterprise */}
      <section className="py-20 bg-[#0a0e17] border-t border-[#1e293b]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="gradient-border rounded-2xl">
            <div className="bg-[#111827] rounded-2xl p-8 sm:p-12 text-center">
              <Badge variant="outline" className="mb-4 border-[#f59e0b]/30 text-[#f59e0b] bg-[#f59e0b]/5">
                {t.enterprise.badge}
              </Badge>
              <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">
                {locale === "zh-CN" ? (
                  t.enterprise.title
                ) : (
                  <>
                    {t.enterprise.title.split("?")[0]}<span className="gradient-text">?</span>
                  </>
                )}
              </h2>
              <p className="text-[#94a3b8] max-w-2xl mx-auto mb-4 leading-relaxed">
                {t.enterprise.desc}
              </p>
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#f59e0b]/10 border border-[#f59e0b]/20 text-[#f59e0b] text-sm font-semibold mb-8">
                <span className="w-2 h-2 rounded-full bg-[#f59e0b] animate-pulse"></span>
                {t.enterprise.option}
              </div>
              <div className="grid sm:grid-cols-2 gap-4 max-w-2xl mx-auto mb-10 text-left">
                {t.enterprise.features.map((feature, i) => (
                  <div key={i} className="flex items-start gap-2.5 text-sm text-[#cbd5e1]">
                    <Check className="w-4 h-4 mt-0.5 shrink-0 text-[#f59e0b]" />
                    <span>{feature}</span>
                  </div>
                ))}
              </div>
              <a href="mailto:sales@yuleosh.com"
                className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#f59e0b] to-[#f97316] text-white hover:from-[#f59e0b]/90 hover:to-[#f97316]/90 shadow-lg shadow-[#f59e0b]/20 transition-all"
              >
                {t.enterprise.cta}
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
            {t.faq.title}
          </h2>
          <div className="space-y-5">
            {t.faq.items.map((faq, i) => (
              <details key={i}
                className="group rounded-xl border border-[#1e293b] bg-[#111827] p-5 cursor-pointer transition-all hover:border-[#1e293b]/80"
              >
                <summary className="text-sm font-semibold text-[#e2e8f0] list-none flex items-center justify-between">
                  {faq.q}
                  <span className="text-[#64748b] transition-transform group-open:rotate-180">▾</span>
                </summary>
                <p className="mt-3 text-sm text-[#94a3b8] leading-relaxed pr-8">{faq.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-[#0a0e17] border-t border-[#1e293b]">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl sm:text-4xl font-black text-[#e2e8f0] mb-4">
            {t.cta.title}
          </h2>
          <p className="text-[#94a3b8] mb-8">{t.cta.desc}</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/register"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-[#10b981] to-[#059669] text-white font-semibold text-sm shadow-lg shadow-[#10b981]/20 hover:from-[#10b981]/90 hover:to-[#059669]/90 transition-all"
            >
              <Sparkles className="w-4 h-4" />
              {t.cta.freeTrial}
              <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="https://github.com/frisky1985/yuleOSH" target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl border border-[#1e293b] text-[#94a3b8] hover:border-white/20 hover:text-white text-sm font-medium transition-all"
            >
              <GithubIcon className="w-4 h-4" />
              {t.cta.viewGitHub}
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
              <span className="text-xs text-[#64748b]">{t.footer.v}</span>
            </div>
            <div className="flex items-center gap-6">
              <Link href="/register" className="text-xs text-[#10b981] hover:text-[#10b981]/80 transition-colors font-medium">{t.footer.freeTrial}</Link>
              <Link href="/" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">{t.footer.home}</Link>
              <Link href="/login" className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">{t.footer.login}</Link>
              <a href="https://github.com/frisky1985/yuleOSH" target="_blank" rel="noreferrer"
                className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors"
              >
                GitHub
              </a>
            </div>
          </div>
          <div className="mt-6 text-center text-xs text-[#393e4a]">
            {t.footer.tagline}
          </div>
        </div>
      </footer>
    </div>
  );
}

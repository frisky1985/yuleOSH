"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Check, X, AlertTriangle, Sparkles, Loader2, CreditCard,
  ExternalLink, Calendar, BarChart3, ChevronRight, Zap,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { api, getToken } from "@/lib/api";

interface SubscriptionStatus {
  tier: string;
  tier_name: string;
  org_name: string;
  org_slug: string;
  subscription: {
    stripe_enabled: boolean;
    has_subscription: boolean;
    status: string;
    current_period_end: string;
    stripe_subscription_id: string;
  };
  trial: {
    in_trial: boolean;
    days_left: number;
    trial_end: string;
  };
  usage: Record<string, { used: number; limit: number }>;
  plans: Array<{ name: string; tier: string; price_monthly: number }>;
}

export default function SubscriptionPage() {
  const router = useRouter();
  const [data, setData] = useState<SubscriptionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [upgrading, setUpgrading] = useState(false);
  const [cancelMsg, setCancelMsg] = useState("");

  useEffect(() => {
    loadStatus();
  }, []);

  async function loadStatus() {
    try {
      const resp = await fetch("/api/v1/subscription/status", {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const json = await resp.json();
      if (json.error) {
        setError(json.error);
        return;
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || "Failed to load subscription status");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpgrade(tier: string) {
    setUpgrading(true);
    try {
      const resp = await fetch("/api/v1/subscription/upgrade", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ tier }),
      });
      const json = await resp.json();
      if (json.url) {
        window.location.href = json.url;
      } else {
        setError(json.error || "Failed to create checkout session");
      }
    } catch (err: any) {
      setError(err.message || "Upgrade failed");
    } finally {
      setUpgrading(false);
    }
  }

  async function handleCancel() {
    setCancelMsg("正在取消...");
    try {
      const resp = await fetch("/api/v1/subscription/cancel", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
      });
      const json = await resp.json();
      if (json.status === "cancel_at_period_end") {
        setCancelMsg("已提交取消，当前周期结束后将降级为 Free 方案");
        loadStatus();
      } else {
        setCancelMsg(json.error || "取消失败");
      }
    } catch (err: any) {
      setCancelMsg(err.message || "请求失败");
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-[#10b981]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0] flex items-center justify-center p-4">
        <Card className="border-[#1e293b] bg-[#111827] max-w-md w-full">
          <CardHeader>
            <CardTitle className="text-lg text-[#e2e8f0]">无法加载订阅信息</CardTitle>
            <CardDescription className="text-[#94a3b8]">{error}</CardDescription>
          </CardHeader>
          <CardFooter>
            <Button onClick={loadStatus} variant="outline" className="border-[#1e293b] text-[#94a3b8]">
              重试
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  if (!data) return null;

  const isPro = data.tier === "pro" || data.tier === "enterprise";
  const isTrialing = data.trial?.in_trial;
  const daysLeft = data.trial?.days_left || 0;
  const isCancelAtPeriodEnd = data.subscription?.status === "cancel_at_period_end";

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <Link href="/dashboard" className="inline-flex items-center gap-1 text-xs text-[#64748b] hover:text-[#94a3b8] mb-2 transition-colors">
              <ArrowLeft className="w-3 h-3" /> 返回 Dashboard
            </Link>
            <h1 className="text-2xl font-bold">订阅管理</h1>
            <p className="text-sm text-[#94a3b8]">{data.org_name}</p>
          </div>
          <Badge className={
            isPro
              ? "bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30"
              : "bg-[#64748b]/10 text-[#64748b] border-[#64748b]/30"
          }>
            {data.tier_name}
          </Badge>
        </div>

        {/* Trial Banner */}
        {isTrialing && (
          <Card className="mb-6 border-[#10b981]/30 bg-gradient-to-r from-[#10b981]/5 to-[#059669]/5">
            <CardContent className="flex items-center gap-4 p-5">
              <Sparkles className="w-6 h-6 text-[#10b981] shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-[#e2e8f0]">
                  Pro 免费试用中 · 剩余 {daysLeft} 天
                </p>
                <p className="text-xs text-[#94a3b8]">
                  试用到期后需升级为付费方案。随时可取消。
                </p>
              </div>
              <Button
                onClick={() => handleUpgrade("pro")}
                disabled={upgrading}
                className="bg-gradient-to-r from-[#10b981] to-[#059669] text-white gap-1"
                size="sm"
              >
                {upgrading ? <Loader2 className="w-3 h-3 animate-spin" /> : <CreditCard className="w-3 h-3" />}
                升级 Pro
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Upgrade warning banner */}
        {!isPro && (
          <Card className="mb-6 border-[#f59e0b]/30 bg-gradient-to-r from-[#f59e0b]/5 to-[#d97706]/5">
            <CardContent className="flex items-center gap-4 p-5">
              <AlertTriangle className="w-6 h-6 text-[#f59e0b] shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-[#e2e8f0]">
                  当前使用 Free 方案 — 1 个项目限制
                </p>
                <p className="text-xs text-[#94a3b8]">
                  升级到 Pro 获取无限项目、完整 CI/CD 流水线等功能。
                </p>
              </div>
              <Button
                onClick={() => handleUpgrade("pro")}
                disabled={upgrading}
                className="bg-gradient-to-r from-[#10b981] to-[#059669] text-white gap-1"
                size="sm"
              >
                {upgrading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                升级
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Plan Overview */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader>
              <CardTitle className="text-base text-[#e2e8f0] flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-[#10b981]" />
                当前方案
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#94a3b8]">方案</span>
                <span className="text-sm font-semibold">{data.tier_name}</span>
              </div>
              <Separator className="bg-[#1e293b]" />
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#94a3b8]">状态</span>
                <Badge className={
                  isPro && !isCancelAtPeriodEnd
                    ? "bg-[#10b981]/10 text-[#10b981]"
                    : isCancelAtPeriodEnd
                    ? "bg-[#f59e0b]/10 text-[#f59e0b]"
                    : "bg-[#64748b]/10 text-[#64748b]"
                }>
                  {isCancelAtPeriodEnd ? "将于周期结束取消" : isPro ? "活跃" : "免费"}
                </Badge>
              </div>
              {data.subscription?.current_period_end && (
                <>
                  <Separator className="bg-[#1e293b]" />
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-[#94a3b8]">当前周期</span>
                    <span className="text-sm flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-[#64748b]" />
                      {new Date(data.subscription.current_period_end).toLocaleDateString("zh-CN")}
                    </span>
                  </div>
                </>
              )}
            </CardContent>
            {isPro && !isCancelAtPeriodEnd && (
              <CardFooter>
                <Button
                  onClick={handleCancel}
                  variant="outline"
                  className="w-full border-[#1e293b] text-[#94a3b8] hover:border-[#ff4d4f]/40 hover:text-[#ff4d4f] gap-1"
                  size="sm"
                >
                  <X className="w-3 h-3" />
                  取消订阅
                </Button>
              </CardFooter>
            )}
          </Card>

          {/* Usage Summary */}
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader>
              <CardTitle className="text-base text-[#e2e8f0] flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-[#1677ff]" />
                使用量
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(data.usage || {}).map(([key, val]: [string, any]) => {
                const pct = val.limit > 0 ? Math.round((val.used / val.limit) * 100) : 0;
                return (
                  <div key={key}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-[#94a3b8]">{key}</span>
                      <span className={val.used >= val.limit ? "text-[#ff4d4f]" : "text-[#e2e8f0]"}>
                        {val.used}/{val.limit}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          pct >= 90 ? "bg-[#ff4d4f]" : pct >= 70 ? "bg-[#f59e0b]" : "bg-[#10b981]"
                        }`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>

        {/* Upgrade Options */}
        <Card className="border-[#1e293b] bg-[#111827] mb-6">
          <CardHeader>
            <CardTitle className="text-base text-[#e2e8f0]">升级选项</CardTitle>
            <CardDescription className="text-[#94a3b8]">选择适合你的方案</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="rounded-xl border border-[#1e293b] p-5 hover:border-[#10b981]/40 transition-all">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-[#e2e8f0]">Pro</h3>
                  <span className="text-lg font-black text-[#e2e8f0]">¥599<small className="text-xs text-[#64748b]">/月</small></span>
                </div>
                <p className="text-xs text-[#94a3b8] mb-4">无限项目 · 完整流水线 · ASPICE 合规包</p>
                <Button
                  onClick={() => handleUpgrade("pro")}
                  disabled={upgrading || isPro}
                  className="w-full bg-gradient-to-r from-[#10b981] to-[#059669] text-white gap-1"
                  size="sm"
                >
                  {isPro ? (upgrading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />) : <CreditCard className="w-3 h-3" />}
                  {isPro ? "当前方案" : "升级到 Pro"}
                </Button>
              </div>

              <div className="rounded-xl border border-[#f59e0b]/40 bg-gradient-to-br from-[#f59e0b]/5 to-transparent p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-[#e2e8f0]">Enterprise</h3>
                  <span className="text-lg font-black text-[#e2e8f0]">¥98,000<small className="text-xs text-[#64748b]">/年</small></span>
                </div>
                <p className="text-xs text-[#94a3b8] mb-4">私有部署 · SSO · 专属支持 · SLA</p>
                <a
                  href="mailto:sales@yuleosh.com"
                  className="block w-full text-center py-2 rounded-lg border border-[#f59e0b]/30 text-[#f59e0b] hover:bg-[#f59e0b]/10 text-sm font-medium transition-all"
                >
                  联系我们
                </a>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Cancel message */}
        {cancelMsg && (
          <Card className="border-[#f59e0b]/30 bg-[#f59e0b]/5">
            <CardContent className="p-4 text-sm text-[#e2e8f0]">{cancelMsg}</CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

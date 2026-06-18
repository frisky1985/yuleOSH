"use client";

import { useState, FormEvent, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Mail, ArrowRight, Lock, Loader2, Eye, EyeOff, User, Building2, Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { api, setToken } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [success, setSuccess] = useState(false);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");

  const plan = searchParams?.get("plan") || "pro";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      // Validation
      if (!email || !password || !name) {
        setError("请填写所有必填字段");
        setLoading(false);
        return;
      }
      if (password.length < 8) {
        setError("密码至少需要8个字符");
        setLoading(false);
        return;
      }

      // Step 1: Signin to check if user needs org
      const signinResult = await api.auth.signin(email, password);

      if (signinResult.error && !signinResult.needs_org) {
        setError(signinResult.error === "Invalid email or password"
          ? "该邮箱已被注册，请直接登录"
          : signinResult.error);
        setLoading(false);
        return;
      }

      // Step 2: Create org + project (auto-provision Trial)
      const slug = (orgName || name + "-org")
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "");
      const projSlug = "my-first-project";

      const orgResult = await api.auth.createOrg({
        org_name: orgName || `${name}的组织`,
        org_slug: slug || `${name.toLowerCase().replace(/[^a-z0-9]/g, "")}-org`,
        project_name: "My First Project",
        project_slug: projSlug,
        email,
        password,
      });

      if (orgResult.error) {
        setError(orgResult.error);
        setLoading(false);
        return;
      }

      if (orgResult.token) {
        setToken(orgResult.token);
        setSuccess(true);

        // Step 3: Redirect to onboarding or dashboard
        setTimeout(() => {
          router.push("/dashboard");
        }, 1500);
        return;
      }

      setError("注册失败，请重试");
    } catch (err: any) {
      setError(err.message || "请求失败，请检查网络连接");
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <div className="relative min-h-screen bg-[#0a0e17] text-[#e2e8f0] flex items-center justify-center p-4">
        <div className="absolute top-1/3 right-1/3 w-96 h-96 bg-[#10b981]/5 rounded-full blur-[120px]"></div>
        <Card className="border-[#10b981]/30 bg-[#111827] max-w-md w-full text-center p-8">
          <div className="text-5xl mb-4">🎉</div>
          <CardTitle className="text-xl text-[#e2e8f0] mb-2">
            注册成功！
          </CardTitle>
          <CardDescription className="text-[#94a3b8] mb-6">
            你的账号已创建，正在跳转到 Dashboard...<br />
            期间已为你自动创建了示例项目和 14 天 Pro 试用。
          </CardDescription>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-[#10b981]">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
              <span>账号创建成功</span>
            </div>
            <div className="flex items-center gap-2 text-sm text-[#10b981]">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
              <span>已创建示例项目「My First Project」</span>
            </div>
            <div className="flex items-center gap-2 text-sm text-[#10b981]">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/></svg>
              <span>已激活 14 天 Pro 免费试用</span>
            </div>
          </div>
          <Loader2 className="w-5 h-5 animate-spin mx-auto mt-6 text-[#10b981]" />
        </Card>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen bg-[#0a0e17] text-[#e2e8f0] flex items-center justify-center p-4">
      {/* Background orbs */}
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-[#10b981]/5 rounded-full blur-[120px]"></div>
      <div className="absolute bottom-1/3 left-1/4 w-80 h-80 bg-[#1677ff]/5 rounded-full blur-[120px]"></div>

      <div className="relative w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="text-3xl font-black tracking-tight">
            <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
          </Link>
          <p className="text-sm text-[#94a3b8] mt-2">嵌入式AI开发全流程平台</p>
        </div>

        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#10b981]/30 bg-[#10b981]/5 text-[#10b981] text-xs font-medium mb-3">
              <Sparkles className="w-3 h-3" />
              14 天免费试用 · 无需信用卡
            </div>
            <CardTitle className="text-xl text-[#e2e8f0]">
              创建你的 yuleOSH 账号
            </CardTitle>
            <CardDescription className="text-[#94a3b8]">
              填写信息，即可免费使用全部 Pro 功能 14 天
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Error banner */}
              {error && (
                <div className="rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-4 py-2.5 text-sm text-[#ff4d4f]">
                  {error}
                </div>
              )}

              {/* Name */}
              <div className="space-y-1">
                <Label htmlFor="name" className="text-sm text-[#94a3b8]">
                  姓名 <span className="text-[#ff4d4f]">*</span>
                </Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
                  <Input
                    id="name"
                    type="text"
                    placeholder="你的姓名"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="pl-9 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#10b981]"
                    autoFocus
                  />
                </div>
              </div>

              {/* Email */}
              <div className="space-y-1">
                <Label htmlFor="email" className="text-sm text-[#94a3b8]">
                  邮箱 <span className="text-[#ff4d4f]">*</span>
                </Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-9 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#10b981]"
                  />
                </div>
              </div>

              {/* Password */}
              <div className="space-y-1">
                <Label htmlFor="password" className="text-sm text-[#94a3b8]">
                  密码 <span className="text-[#ff4d4f]">*</span>
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="至少8个字符"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-9 pr-10 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#10b981]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#64748b] hover:text-[#94a3b8] transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Organization name */}
              <div className="space-y-1">
                <Label htmlFor="orgName" className="text-sm text-[#94a3b8]">
                  组织名称 <span className="text-[#64748b] font-normal">(可选)</span>
                </Label>
                <div className="relative">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
                  <Input
                    id="orgName"
                    type="text"
                    placeholder="我的组织 (不填则使用姓名)"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    className="pl-9 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#10b981]"
                  />
                </div>
              </div>

              <p className="text-xs text-[#64748b] leading-relaxed">
                注册即表示您同意我们的{" "}
                <a href="#" className="text-[#1677ff] hover:underline">服务条款</a>
                {" "}和{" "}
                <a href="#" className="text-[#1677ff] hover:underline">隐私政策</a>
              </p>

              <Button
                type="submit"
                disabled={loading}
                className="w-full h-12 bg-gradient-to-r from-[#10b981] to-[#059669] text-white hover:from-[#10b981]/90 hover:to-[#059669]/90 shadow-lg shadow-[#10b981]/20 gap-2 disabled:opacity-60 text-base font-semibold"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                {loading ? "创建账号中..." : "免费开始试用"}
                {!loading && <ArrowRight className="w-3.5 h-3.5" />}
              </Button>
            </form>
          </CardContent>
          <CardFooter className="flex-col gap-3">
            <p className="text-xs text-[#64748b]">
              已有账号？
              <Link href="/login" className="text-[#1677ff] hover:underline ml-1">
                立即登录
              </Link>
            </p>
            <Link
              href="/dashboard"
              className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors flex items-center gap-1"
            >
              <Lock className="w-3 h-3" />
              无需登录，直接体验 Dashboard
            </Link>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}

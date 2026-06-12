"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Mail, ArrowRight, Lock, Loader2, Eye, EyeOff, User, Building2 } from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { api, setToken } from "@/lib/api";

type AuthMode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [orgName, setOrgName] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (mode === "login") {
        // --- LOGIN FLOW ---
        if (!email || !password) {
          setError("请填写邮箱和密码");
          setLoading(false);
          return;
        }
        const result = await api.auth.signin(email, password);

        if (result.error) {
          setError(result.error);
          setLoading(false);
          return;
        }

        if (result.needs_org) {
          // First-time user – auto-create org + project
          const slug = (orgName || "my-org")
            .toLowerCase()
            .replace(/[^a-z0-9-]/g, "-")
            .replace(/-+/g, "-")
            .replace(/^-|-$/g, "");
          const projSlug = "my-first-project";

          const orgResult = await api.auth.createOrg({
            org_name: orgName || "我的组织",
            org_slug: slug || "my-org",
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
            router.push("/dashboard");
            return;
          }
          setError("注册失败，请重试");
          setLoading(false);
          return;
        }

        // Normal login
        if (result.token) {
          setToken(result.token);
          router.push("/dashboard");
        } else {
          setError("登录失败，请重试");
        }
      } else {
        // --- REGISTER FLOW ---
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

        // First try signin
        const signinResult = await api.auth.signin(email, password);

        if (signinResult.error && !signinResult.needs_org) {
          setError(signinResult.error);
          setLoading(false);
          return;
        }

        if (signinResult.needs_org) {
          // Create org automatically
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
            router.push("/dashboard");
            return;
          }
        }

        // User already exists — try normal login
        const result = await api.auth.signin(email, password);
        if (result.error) {
          setError(result.error);
          setLoading(false);
          return;
        }
        if (result.token) {
          setToken(result.token);
          router.push("/dashboard");
          return;
        }
        setError("注册失败，请重试");
      }
    } catch (err: any) {
      setError(err.message || "请求失败，请检查网络连接");
    } finally {
      setLoading(false);
    }
  }

  function toggleMode() {
    setMode(mode === "login" ? "register" : "login");
    setError("");
  }

  return (
    <div className="relative min-h-screen bg-[#0a0e17] text-[#e2e8f0] flex items-center justify-center p-4">
      {/* Background orbs */}
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-[#722ed1]/5 rounded-full blur-[120px]"></div>
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
            <CardTitle className="text-xl text-[#e2e8f0]">
              {mode === "login" ? "登录" : "注册"}
            </CardTitle>
            <CardDescription className="text-[#94a3b8]">
              {mode === "login"
                ? "使用邮箱或 GitHub 账号登录"
                : "创建你的账号并开始使用"}
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

              {/* GitHub OAuth */}
              <Button
                type="button"
                variant="outline"
                className="w-full h-11 border-[#1e293b] text-[#e2e8f0] hover:bg-[#1e293b] hover:text-white gap-2"
              >
                <GithubIcon className="w-4 h-4" />
                GitHub OAuth 登录
              </Button>

              <div className="relative">
                <Separator className="bg-[#1e293b]" />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#111827] px-3 text-xs text-[#64748b]">
                  或使用邮箱
                </span>
              </div>

              {/* Name (register only) */}
              {mode === "register" && (
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
                      className="pl-9 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
                    />
                  </div>
                </div>
              )}

              {/* Email */}
              <div className="space-y-1">
                <Label htmlFor="email" className="text-sm text-[#94a3b8]">
                  邮箱 <span className="text-[#ff4d4f]">*</span>
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
                />
              </div>

              {/* Password */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-sm text-[#94a3b8]">
                    密码 <span className="text-[#ff4d4f]">*</span>
                  </Label>
                  {mode === "login" && (
                    <button
                      type="button"
                      className="text-xs text-[#1677ff] hover:text-[#1677ff]/80 transition-colors"
                    >
                      忘记密码？
                    </button>
                  )}
                </div>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder={mode === "register" ? "至少8个字符" : "输入密码"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pr-10 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
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

              {/* Organization name (register only) */}
              {mode === "register" && (
                <div className="space-y-1">
                  <Label htmlFor="orgName" className="text-sm text-[#94a3b8]">
                    组织名称
                  </Label>
                  <div className="relative">
                    <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
                    <Input
                      id="orgName"
                      type="text"
                      placeholder="我的组织 (可选)"
                      value={orgName}
                      onChange={(e) => setOrgName(e.target.value)}
                      className="pl-9 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
                    />
                  </div>
                </div>
              )}

              {mode === "register" && (
                <p className="text-xs text-[#64748b] leading-relaxed">
                  注册即表示您同意我们的{" "}
                  <a href="#" className="text-[#1677ff] hover:underline">服务条款</a>
                  {" "}和{" "}
                  <a href="#" className="text-[#1677ff] hover:underline">隐私政策</a>
                </p>
              )}

              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 gap-2 disabled:opacity-60"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Mail className="w-4 h-4" />
                )}
                {loading
                  ? "处理中..."
                  : mode === "login"
                  ? "登录"
                  : "注册"}
                {!loading && <ArrowRight className="w-3.5 h-3.5" />}
              </Button>
            </form>
          </CardContent>
          <CardFooter className="flex-col gap-3">
            <p className="text-xs text-[#64748b]">
              {mode === "login" ? (
                <>
                  还没有账号？
                  <button
                    type="button"
                    onClick={toggleMode}
                    className="text-[#1677ff] hover:underline ml-1 bg-transparent border-none cursor-pointer"
                  >
                    立即注册
                  </button>
                </>
              ) : (
                <>
                  已有账号？
                  <button
                    type="button"
                    onClick={toggleMode}
                    className="text-[#1677ff] hover:underline ml-1 bg-transparent border-none cursor-pointer"
                  >
                    立即登录
                  </button>
                </>
              )}
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

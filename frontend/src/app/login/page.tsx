"use client";

import Link from "next/link";
import { Mail, ArrowRight, Lock } from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function LoginPage() {
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
            <CardTitle className="text-xl text-[#e2e8f0]">登录</CardTitle>
            <CardDescription className="text-[#94a3b8]">
              使用邮箱或 GitHub 账号登录
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* GitHub OAuth */}
            <Button
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

            {/* Email form */}
            <div className="space-y-3">
              <div className="space-y-1">
                <Label htmlFor="email" className="text-sm text-[#94a3b8]">邮箱</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
                />
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-sm text-[#94a3b8]">密码</Label>
                  <a href="#" className="text-xs text-[#1677ff] hover:text-[#1677ff]/80 transition-colors">
                    忘记密码？
                  </a>
                </div>
                <Input
                  id="password"
                  type="password"
                  placeholder="输入密码"
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
                />
              </div>
            </div>

            <Button
              className="w-full h-11 bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 gap-2"
            >
              <Mail className="w-4 h-4" />
              登录
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          </CardContent>
          <CardFooter className="flex-col gap-3">
            <p className="text-xs text-[#64748b]">
              还没有账号？
              <a href="#" className="text-[#1677ff] hover:underline ml-1">立即注册</a>
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

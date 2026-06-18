"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight, ArrowLeft, Check, Sparkles, FileText, Play, Eye,
  Loader2, Rocket, ChevronRight, Github,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { getToken, setToken } from "@/lib/api";

type StepStatus = "pending" | "active" | "done";

const STEPS = [
  { num: 1, title: "创建项目", icon: "📁", desc: "给你的项目起个名字" },
  { num: 2, title: "编写 Spec", icon: "📝", desc: "定义需求文档" },
  { num: 3, title: "运行 Pipeline", icon: "🚀", desc: "启动 AI 自动开发流水线" },
  { num: 4, title: "查看成果", icon: "🎊", desc: "查看追溯矩阵与合规包" },
];

const TEMPLATE_SPEC = `## 需求: Hello World（示例项目）

### RS-001: LED 控制
- 系统 SHALL 通过 GPIO 控制 LED
- 系统 SHALL 支持 LED 开关切换
- 系统 SHALL 以 1Hz 频率闪烁 LED

#### 场景: LED 切换
GIVEN GPIO 已配置为输出
WHEN 发送切换命令
THEN LED 状态翻转

#### 场景: LED 闪烁
GIVEN GPIO 已配置为输出
WHEN 激活闪烁模式
THEN LED 以 1Hz 频率闪烁`;

const TEMPLATE_SPEC2 = `## 需求: 温控系统（示例项目）

### RS-001: 温度采集
- 系统 SHALL 每秒采集一次温度传感器数据
- 系统 SHALL 精度达到 ±0.5°C

#### 场景: 温度读取
GIVEN 传感器已初始化
WHEN 发起温度读取请求
THEN 返回有效的温度值`;

export default function OnboardingPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(1);
  const [projectName, setProjectName] = useState("My First Project");
  const [specContent, setSpecContent] = useState(TEMPLATE_SPEC);
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);

  async function createProject() {
    setLoading(true);
    try {
      const token = getToken();
      const slug = projectName.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-");
      const resp = await fetch("/api/v1/project", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: projectName,
          slug: slug,
          description: "通过 Onboarding 向导创建",
        }),
      });
      const json = await resp.json();
      if (json.error) {
        console.error("Project create error:", json.error);
      }
      setCurrentStep(2);
    } finally {
      setLoading(false);
    }
  }

  async function saveSpec() {
    setLoading(true);
    try {
      const token = getToken();
      const resp = await fetch("/api/v1/spec", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          project: projectName,
          content: specContent,
        }),
      });
      const json = await resp.json();
      if (json.error) {
        console.error("Spec save error:", json.error);
      }
      setCurrentStep(3);
    } finally {
      setLoading(false);
    }
  }

  async function runPipeline() {
    setLoading(true);
    setPipelineStatus("running");
    try {
      const token = getToken();
      const resp = await fetch("/api/v1/pipeline", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: projectName, action: "run" }),
      });
      const json = await resp.json();
      if (json.ok || json.status === "started") {
        setPipelineStatus("completed");
        setTimeout(() => setCurrentStep(4), 1500);
      } else {
        setPipelineStatus("failed");
      }
    } catch (err) {
      console.error("Pipeline error:", err);
      setPipelineStatus("failed");
    } finally {
      setLoading(false);
    }
  }

  function useTemplate(template: string) {
    setSpecContent(template);
  }

  function finishAndGo() {
    setCompleted(true);
    // Mark wizard as completed
    fetch("/api/v1/wizard/complete", { method: "POST" }).catch(() => {});
    setTimeout(() => {
      router.push("/dashboard");
    }, 1500);
  }

  function skip() {
    markComplete();
    router.push("/dashboard");
  }

  async function markComplete() {
    try {
      await fetch("/api/v1/wizard/complete", { method: "POST" });
    } catch {}
  }

  const stepStatus = (num: number): StepStatus => {
    if (num < currentStep) return "done";
    if (num === currentStep) return "active";
    return "pending";
  };

  const progressPct = ((currentStep - 1) / STEPS.length) * 100;

  if (completed) {
    return (
      <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0] flex items-center justify-center p-4">
        <Card className="border-[#10b981]/30 bg-[#111827] max-w-md w-full text-center p-8">
          <div className="text-5xl mb-4">🎉</div>
          <CardTitle className="text-xl text-[#e2e8f0] mb-2">恭喜完成入门向导！</CardTitle>
          <CardDescription className="text-[#94a3b8] mb-6">
            你已创建项目、编写 Spec 并运行 Pipeline。现在可以自由使用 yuleOSH 的全部功能了。
          </CardDescription>
          <div className="flex justify-center gap-2">
            <Loader2 className="w-5 h-5 animate-spin text-[#10b981]" />
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <div className="max-w-3xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-10">
          <Badge className="mb-3 bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30">
            <Sparkles className="w-3 h-3 mr-1" />
            Onboarding 向导
          </Badge>
          <h1 className="text-3xl font-black mb-2">
            <span className="gradient-text">开始你的第一个项目</span>
          </h1>
          <p className="text-sm text-[#94a3b8]">
            三步创建嵌入式 AI 开发项目，体验全流程自动化
          </p>
          <button onClick={skip} className="mt-2 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
            跳过向导 →
          </button>
        </div>

        {/* Progress Bar */}
        <div className="mb-10">
          <Progress value={progressPct} className="h-1.5 bg-[#1e293b]" indicatorClassName="bg-gradient-to-r from-[#10b981] to-[#1677ff]" />
          <div className="flex justify-between mt-2">
            {STEPS.map((s) => (
              <span key={s.num} className={`text-[10px] uppercase tracking-wider ${
                stepStatus(s.num) === "done" ? "text-[#10b981]" :
                stepStatus(s.num) === "active" ? "text-[#1677ff]" : "text-[#64748b]"
              }`}>
                {s.icon} {s.title}
              </span>
            ))}
          </div>
        </div>

        {/* Step 1: Create Project */}
        {currentStep === 1 && (
          <Card className="border-[#10b981]/50 bg-[#111827]">
            <CardHeader>
              <div className="flex items-center gap-3 mb-2">
                <span className="w-8 h-8 rounded-full bg-gradient-to-br from-[#10b981] to-[#059669] flex items-center justify-center text-white text-xs font-black">1</span>
                <div>
                  <CardTitle className="text-lg text-[#e2e8f0]">创建项目</CardTitle>
                  <CardDescription className="text-[#94a3b8]">给你的嵌入式开发项目起个名字</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="project-name" className="text-sm text-[#94a3b8]">项目名称</Label>
                <Input
                  id="project-name"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="My First Project"
                  className="mt-1 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] focus-visible:ring-[#10b981]"
                />
              </div>
              <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-4">
                <p className="text-xs text-[#64748b] mb-2">💡 预置模板</p>
                <div className="flex flex-wrap gap-2">
                  {["ESP32 基础", "STM32 HAL", "FreeRTOS", "Zephyr"].map((t) => (
                    <span key={t} className="px-2.5 py-1 rounded-lg text-xs bg-[#1677ff]/10 text-[#1677ff] border border-[#1677ff]/20">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </CardContent>
            <div className="px-6 pb-6">
              <Button
                onClick={createProject}
                disabled={loading || !projectName.trim()}
                className="w-full bg-gradient-to-r from-[#10b981] to-[#059669] text-white gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
                {loading ? "创建中..." : "创建项目"}
                {!loading && <ArrowRight className="w-3.5 h-3.5" />}
              </Button>
            </div>
          </Card>
        )}

        {/* Step 2: Write Spec */}
        {currentStep === 2 && (
          <Card className="border-[#1677ff]/50 bg-[#111827]">
            <CardHeader>
              <div className="flex items-center gap-3 mb-2">
                <span className="w-8 h-8 rounded-full bg-gradient-to-br from-[#1677ff] to-[#2563eb] flex items-center justify-center text-white text-xs font-black">2</span>
                <div>
                  <CardTitle className="text-lg text-[#e2e8f0]">编写 Spec</CardTitle>
                  <CardDescription className="text-[#94a3b8]">定义需求文档，AI 将据此生成代码</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Button
                  onClick={() => useTemplate(TEMPLATE_SPEC)}
                  variant="outline"
                  size="sm"
                  className="border-[#1e293b] text-[#94a3b8] text-xs"
                >
                  LED 示例
                </Button>
                <Button
                  onClick={() => useTemplate(TEMPLATE_SPEC2)}
                  variant="outline"
                  size="sm"
                  className="border-[#1e293b] text-[#94a3b8] text-xs"
                >
                  温控示例
                </Button>
              </div>
              <textarea
                value={specContent}
                onChange={(e) => setSpecContent(e.target.value)}
                rows={14}
                className="w-full bg-[#0a0e17] border border-[#1e293b] rounded-xl px-4 py-3 text-[#e2e8f0] font-mono text-sm focus:border-[#1677ff] outline-none resize-y"
              />
            </CardContent>
            <div className="px-6 pb-6">
              <Button
                onClick={saveSpec}
                disabled={loading || !specContent.trim()}
                className="w-full bg-gradient-to-r from-[#1677ff] to-[#2563eb] text-white gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                {loading ? "保存中..." : "保存 Spec"}
                {!loading && <ArrowRight className="w-3.5 h-3.5" />}
              </Button>
            </div>
          </Card>
        )}

        {/* Step 3: Run Pipeline */}
        {currentStep === 3 && (
          <Card className="border-[#f59e0b]/50 bg-[#111827]">
            <CardHeader>
              <div className="flex items-center gap-3 mb-2">
                <span className="w-8 h-8 rounded-full bg-gradient-to-br from-[#f59e0b] to-[#d97706] flex items-center justify-center text-white text-xs font-black">3</span>
                <div>
                  <CardTitle className="text-lg text-[#e2e8f0]">运行 Pipeline</CardTitle>
                  <CardDescription className="text-[#94a3b8]">启动 AI 开发流水线，全自动执行</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-4">
                <p className="text-sm text-[#94a3b8] mb-3">Pipeline 将自动完成：</p>
                <ul className="space-y-2 text-sm text-[#94a3b8]">
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-[#10b981]" /> 需求分析
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-[#10b981]" /> 架构设计 (SDD)
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-[#10b981]" /> 代码生成 (DDD → TDD)
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-[#10b981]" /> 自动测试
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-[#10b981]" /> 代码审查 + 审计报告
                  </li>
                </ul>
              </div>

              {pipelineStatus === "running" && (
                <div className="text-center py-4">
                  <Loader2 className="w-6 h-6 animate-spin text-[#f59e0b] mx-auto mb-2" />
                  <p className="text-sm text-[#e2e8f0]">Pipeline 执行中...</p>
                  <p className="text-xs text-[#64748b]">AI Agent 正在自动开发</p>
                </div>
              )}

              {pipelineStatus === "failed" && (
                <div className="rounded-xl border border-[#ff4d4f]/30 bg-[#ff4d4f]/5 p-4 text-center">
                  <p className="text-sm text-[#ff4d4f]">Pipeline 执行失败</p>
                  <p className="text-xs text-[#64748b] mt-1">可跳过此步骤，稍后在 Dashboard 中重试</p>
                </div>
              )}

              {pipelineStatus === "completed" && (
                <div className="text-center py-4">
                  <div className="text-3xl mb-2">✅</div>
                  <p className="text-sm text-[#10b981] font-semibold">Pipeline 执行完成！</p>
                </div>
              )}
            </CardContent>
            <div className="px-6 pb-6">
              <Button
                onClick={runPipeline}
                disabled={loading || pipelineStatus === "running"}
                className="w-full bg-gradient-to-r from-[#f59e0b] to-[#d97706] text-black font-bold gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : pipelineStatus === "completed" ? <Check className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                {pipelineStatus === "running" ? "执行中..." :
                 pipelineStatus === "completed" ? "已完成" :
                 "启动 AI 流水线"}
              </Button>
              <Button
                onClick={() => setCurrentStep(4)}
                variant="ghost"
                className="w-full mt-2 text-xs text-[#64748b] hover:text-[#94a3b8]"
              >
                跳过，稍后运行
              </Button>
            </div>
          </Card>
        )}

        {/* Step 4: View Results */}
        {currentStep === 4 && (
          <Card className="border-[#10b981]/50 bg-[#111827] text-center">
            <CardHeader>
              <div className="text-5xl mb-3">🎊</div>
              <CardTitle className="text-xl text-[#e2e8f0]">全部就绪！</CardTitle>
              <CardDescription className="text-[#94a3b8]">
                你已成功完成 Onboarding。接下来可以：
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-4 text-center hover:border-[#10b981]/30 transition-all cursor-pointer" onClick={() => router.push("/dashboard")}>
                  <Eye className="w-5 h-5 text-[#10b981] mx-auto mb-1" />
                  <p className="text-xs font-medium">查看 Dashboard</p>
                  <p className="text-[10px] text-[#64748b]">项目概览</p>
                </div>
                <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-4 text-center hover:border-[#1677ff]/30 transition-all cursor-pointer" onClick={() => router.push("/subscription")}>
                  <Sparkles className="w-5 h-5 text-[#1677ff] mx-auto mb-1" />
                  <p className="text-xs font-medium">订阅管理</p>
                  <p className="text-[10px] text-[#64748b]">Trial 状态</p>
                </div>
                <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-4 text-center hover:border-[#f59e0b]/30 transition-all cursor-pointer" onClick={() => router.push("/pricing")}>
                  <Rocket className="w-5 h-5 text-[#f59e0b] mx-auto mb-1" />
                  <p className="text-xs font-medium">升级 Pro</p>
                  <p className="text-[10px] text-[#64748b]">解锁更多功能</p>
                </div>
                <div className="rounded-xl border border-[#1e293b] bg-[#0a0e17] p-4 text-center hover:border-[#722ed1]/30 transition-all cursor-pointer" onClick={() => router.push("/demo")}>
                  <Play className="w-5 h-5 text-[#722ed1] mx-auto mb-1" />
                  <p className="text-xs font-medium">体验 Demo</p>
                  <p className="text-[10px] text-[#64748b]">在线演示</p>
                </div>
              </div>
            </CardContent>
            <div className="px-6 pb-6">
              <Button
                onClick={finishAndGo}
                className="w-full bg-gradient-to-r from-[#10b981] to-[#059669] text-white gap-2"
              >
                进入 Dashboard
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </Card>
        )}

        {/* Skip / navigation */}
        <div className="text-center mt-8">
          {currentStep > 1 && currentStep < 4 && (
            <Link href="/dashboard" className="text-xs text-[#64748b] hover:text-[#94a3b8]">
              跳过向导，进入 Dashboard →
            </Link>
          )}
          <br />
          <Link href="/dashboard" className="text-xs text-[#64748b] hover:text-[#94a3b8] mt-2 inline-block">
            已有项目？直接使用
          </Link>
        </div>
      </div>
    </div>
  );
}

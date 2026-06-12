"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Plus,
  Search,
  GitBranch,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  MoreHorizontal,
  FileText,
  LogOut,
  User as UserIcon,
  Settings,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { api, getToken, clearToken, type UserInfo, type ProjectItem, type ProjectDetail } from "@/lib/api";

type ProjectDisplay = {
  id: string;
  name: string;
  description: string;
  status: string;
  stage: string;
  stageColor: string;
  progress: number;
  lastRun: string;
  agents: number;
  github: string;
};

const statusConfig: Record<string, { label: string; icon: React.ReactNode; className: string }> = {
  active: { label: "运行中", icon: <Loader2 className="w-3 h-3 animate-spin" />, className: "bg-[#722ed1]/10 text-[#722ed1] border-[#722ed1]/20" },
  idle: { label: "就绪", icon: <Clock className="w-3 h-3" />, className: "bg-[#1677ff]/10 text-[#1677ff] border-[#1677ff]/20" },
  completed: { label: "已完成", icon: <CheckCircle2 className="w-3 h-3" />, className: "bg-[#10b981]/10 text-[#10b981] border-[#10b981]/20" },
  failed: { label: "失败", icon: <AlertCircle className="w-3 h-3" />, className: "bg-[#ff4d4f]/10 text-[#ff4d4f] border-[#ff4d4f]/20" },
  draft: { label: "草稿", icon: <FileText className="w-3 h-3" />, className: "bg-[#64748b]/10 text-[#64748b] border-[#64748b]/20" },
};

function getInitials(name: string): string {
  return name
    .split(/[\s@]+/)
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function displayProject(p: ProjectItem | ProjectDetail): ProjectDisplay {
  const name = "name" in p ? p.name : "";
  const desc = "description" in p ? (p.description || "") : "";
  return {
    id: String(p.id),
    name,
    description: desc,
    status: "idle",
    stage: "待启动",
    stageColor: "#64748b",
    progress: 0,
    lastRun: "-",
    agents: 0,
    github: "",
  };
}

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectDisplay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [session, setSession] = useState<UserInfo | null>(null);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      // Try to get session info for the logged-in user
      const token = getToken();
      if (token) {
        try {
          const s = await api.auth.session();
          setSession(s);
        } catch {
          // Token might be expired or invalid — that's fine
        }
      }

      // Load projects — try tenant projects first, fall back to API v1
      let projectList: ProjectDisplay[] = [];

      if (token) {
        try {
          const tenantProjects = await api.projects.list();
          projectList = (tenantProjects.projects || []).map(displayProject);
        } catch {
          // Fallback: try API v1
        }
      }

      // If no tenant projects, try API v1
      if (projectList.length === 0) {
        try {
          const v1Projects = await api.v1.projects.list();
          projectList = (v1Projects.projects || [])
            .filter((p: any) => p.name)
            .map(displayProject);
        } catch {
          // No projects at all — show empty state
        }
      }

      setProjects(projectList);
    } catch (err: any) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateProject() {
    if (!newProjectName.trim()) return;
    setCreating(true);
    setError("");

    try {
      const slug = newProjectName
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "");

      // Try tenant project create
      if (getToken()) {
        try {
          await api.projects.create(newProjectName.trim(), slug || "project-" + Date.now());
        } catch {
          // Fallback: API v1
          await api.v1.projects.create(newProjectName.trim());
        }
      } else {
        // No auth — try API v1
        await api.v1.projects.create(newProjectName.trim());
      }

      setNewProjectName("");
      setShowCreate(false);
      await loadData();
    } catch (err: any) {
      setError(err.message || "创建失败");
    } finally {
      setCreating(false);
    }
  }

  async function handleLogout() {
    try {
      await api.auth.logout();
    } catch {
      // Ignore errors during logout
    }
    clearToken();
    router.push("/login");
  }

  const filteredProjects = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase())
  );

  const activeCount = projects.filter((p) => p.status === "active").length;
  const completedCount = projects.filter((p) => p.status === "completed").length;
  const failedCount = projects.filter((p) => p.status === "failed").length;

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      {/* Top Nav */}
      <nav className="sticky top-0 z-50 border-b border-[#1e293b]/60 nav-blur" style={{ background: "rgba(10,14,23,.85)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <Link href="/" className="text-lg font-black tracking-tight">
              <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
            </Link>
            <div className="flex items-center gap-3">
              {getToken() ? (
                <DropdownMenu>
                  <DropdownMenuTrigger className="flex items-center gap-2 rounded-lg border border-[#1e293b] hover:border-[#722ed1]/40 px-2 py-1 transition-all cursor-pointer">
                    <Avatar className="w-7 h-7 border border-[#1e293b]">
                      <AvatarFallback className="bg-[#722ed1]/20 text-[#722ed1] text-[10px]">
                        {session ? getInitials(session.email) : "YU"}
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-xs text-[#94a3b8] hidden sm:inline max-w-[120px] truncate">
                      {session?.email || "用户"}
                    </span>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    className="w-56 border-[#1e293b] bg-[#111827] text-[#e2e8f0]"
                  >
                    <DropdownMenuLabel className="text-xs text-[#94a3b8]">
                      {session?.org_name || "账号"}
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator className="bg-[#1e293b]" />
                    <DropdownMenuItem className="text-sm text-[#94a3b8] hover:text-white hover:bg-[#1e293b] cursor-pointer gap-2">
                      <UserIcon className="w-3.5 h-3.5" />
                      个人信息
                    </DropdownMenuItem>
                    <DropdownMenuItem className="text-sm text-[#94a3b8] hover:text-white hover:bg-[#1e293b] cursor-pointer gap-2">
                      <Settings className="w-3.5 h-3.5" />
                      项目设置
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="bg-[#1e293b]" />
                    <DropdownMenuItem
                      onClick={handleLogout}
                      className="text-sm text-[#ff4d4f] hover:text-[#ff4d4f] hover:bg-[#ff4d4f]/10 cursor-pointer gap-2"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      退出登录
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Link
                  href="/login"
                  className="text-sm px-3 py-1.5 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40 transition-all"
                >
                  登录
                </Link>
              )}
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-black text-[#e2e8f0]">我的项目</h1>
            <p className="text-sm text-[#94a3b8] mt-1">管理你的嵌入式开发项目与 AI Agent 流水线</p>
          </div>
          <Button
            onClick={() => setShowCreate(true)}
            className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 gap-2"
          >
            <Plus className="w-4 h-4" />
            新建项目
          </Button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-4 py-3 text-sm text-[#ff4d4f] flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError("")} className="ml-2 hover:text-white">&times;</button>
          </div>
        )}

        {/* Create project dialog */}
        {showCreate && (
          <Card className="border-[#1e293b] bg-[#111827] mb-6">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-[#e2e8f0]">新建项目</CardTitle>
            </CardHeader>
            <CardContent className="pb-4">
              <div className="flex items-center gap-3">
                <Input
                  placeholder="项目名称"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
                  className="flex-1 border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
                />
                <Button
                  onClick={handleCreateProject}
                  disabled={creating || !newProjectName.trim()}
                  className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white h-10 gap-1.5 disabled:opacity-60"
                >
                  {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                  创建
                </Button>
                <Button
                  variant="outline"
                  onClick={() => { setShowCreate(false); setNewProjectName(""); }}
                  className="border-[#1e293b] text-[#94a3b8] h-10"
                >
                  取消
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Search & Filter */}
        <div className="flex items-center gap-3 mb-6">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
            <Input
              placeholder="搜索项目..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 border-[#1e293b] bg-[#111827] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
            />
          </div>
          <select className="h-10 px-3 rounded-lg border border-[#1e293b] bg-[#111827] text-sm text-[#94a3b8] focus:outline-none focus:ring-1 focus:ring-[#722ed1]">
            <option>全部状态</option>
            <option>运行中</option>
            <option>就绪</option>
            <option>已完成</option>
            <option>失败</option>
          </select>
        </div>

        {/* Loading state */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 text-[#722ed1] animate-spin" />
            <span className="ml-3 text-sm text-[#94a3b8]">加载项目列表...</span>
          </div>
        ) : filteredProjects.length === 0 ? (
          /* Empty state */
          <div className="text-center py-20">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[#722ed1]/10 mb-4">
              <FileText className="w-7 h-7 text-[#722ed1]" />
            </div>
            <h3 className="text-lg font-semibold text-[#e2e8f0] mb-2">还没有项目</h3>
            <p className="text-sm text-[#94a3b8] mb-6 max-w-xs mx-auto">
              创建一个新项目，开始使用 AI Agent 流水线
            </p>
            <Button
              onClick={() => setShowCreate(true)}
              className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white gap-2"
            >
              <Plus className="w-4 h-4" />
              创建第一个项目
            </Button>
          </div>
        ) : (
          /* Project Grid */
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredProjects.map((project) => {
              const status = statusConfig[project.status] || statusConfig.draft;
              return (
                <Link key={project.id} href={`/dashboard/projects/${project.name}`} className="group block">
                  <Card className="h-full border-[#1e293b] bg-[#111827] hover:border-[#722ed1]/30 transition-all cursor-pointer">
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <CardTitle className="text-base font-bold text-[#e2e8f0] truncate group-hover:text-[#722ed1] transition-colors">
                            {project.name}
                          </CardTitle>
                          <CardDescription className="text-xs text-[#94a3b8] mt-1 line-clamp-1">
                            {project.description || "暂无描述"}
                          </CardDescription>
                        </div>
                        <button className="h-8 w-8 p-0 text-[#64748b] hover:text-white hover:bg-[#1e293b] rounded-lg transition-colors">
                          <MoreHorizontal className="w-4 h-4 mx-auto" />
                        </button>
                      </div>
                    </CardHeader>
                    <CardContent>
                      {/* Status Badge */}
                      <div className="flex items-center gap-2 mb-3">
                        <Badge variant="outline" className={`text-xs px-2 py-0.5 gap-1 ${status.className}`}>
                          {status.icon}
                          {status.label}
                        </Badge>
                        <Badge
                          variant="outline"
                          className="text-xs px-2 py-0.5"
                          style={{
                            background: `${project.stageColor}10`,
                            color: project.stageColor,
                            borderColor: `${project.stageColor}20`,
                          }}
                        >
                          {project.stage}
                        </Badge>
                      </div>

                      {/* Progress Bar */}
                      <div className="mb-3">
                        <div className="flex items-center justify-between text-xs mb-1">
                          <span className="text-[#64748b]">进度</span>
                          <span className="text-[#94a3b8] font-medium">{project.progress}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${project.progress}%`,
                              background: `linear-gradient(90deg, ${project.stageColor}, ${project.progress >= 100 ? "#10b981" : project.stageColor})`,
                            }}
                          />
                        </div>
                      </div>

                      {/* Meta */}
                      <div className="flex items-center gap-4 text-xs text-[#64748b]">
                        <span className="flex items-center gap-1">
                          <GitBranch className="w-3 h-3" /> {project.agents} Agents
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" /> {project.lastRun}
                        </span>
                      </div>
                    </CardContent>
                    <CardFooter className="pt-0">
                      <div className="flex items-center justify-between w-full">
                        {project.github && (
                          <a
                            href={`https://github.com/${project.github}`}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="flex items-center gap-1 text-xs text-[#64748b] hover:text-[#1677ff] transition-colors"
                          >
                            <GithubIcon className="w-3 h-3" />
                            {project.github}
                          </a>
                        )}
                        <span className="flex items-center gap-1 text-xs text-[#722ed1] opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
                          详情 <ArrowRight className="w-3 h-3" />
                        </span>
                      </div>
                    </CardFooter>
                  </Card>
                </Link>
              );
            })}
          </div>
        )}

        {/* Quick Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-10">
          {[
            { label: "项目总数", value: String(projects.length), color: "#722ed1" },
            { label: "运行中", value: String(activeCount), color: "#722ed1" },
            { label: "已完成", value: String(completedCount), color: "#10b981" },
            { label: "失败", value: String(failedCount), color: "#ff4d4f" },
          ].map((s, i) => (
            <div key={i} className="rounded-xl border border-[#1e293b] bg-[#111827] p-4 text-center">
              <div className="text-2xl font-black" style={{ color: s.color }}>{s.value}</div>
              <div className="text-xs text-[#64748b] mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

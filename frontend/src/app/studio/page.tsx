"use client";

/**
 * yuleOSH Studio — OpenSpec 需求工作台 (/studio)
 *
 * Trae 式工作台：先选工程（工作区），再在工程内编辑规格。
 *   - 一个工程 = OSH_HOME/projects/<pid>/，规格文件放在它的 docs/ 下
 *   - 文件树只展示当前工程 docs/ 里的规格
 *
 * 数据全部来自真实后端：
 *   GET  /api/v1/spec/projects        — 工程（工作区）列表
 *   GET  /api/v1/spec/list?project=   — 工程 docs/ 下的规格文件
 *   GET  /api/v1/spec/read            — 读取单个规格文件
 *   POST /api/v1/spec/gen             — 自然语言 → OpenSpec 文档（mock 可选）
 *   POST /api/v1/spec/save            — 先校验后落盘
 *   POST /api/v1/spec/validate        — 校验已保存文件
 *   POST /api/v1/project              — 新建工程
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  Sparkles,
  RefreshCw,
  FileText,
  SendHorizonal,
  Play,
  ClipboardCopy,
  Save,
  ShieldCheck,
  Loader2,
  CircleAlert,
  Eye,
  PencilLine,
  LayoutDashboard,
  FolderOpen,
  FolderPlus,
  ChevronDown,
  Plus,
  Check,
  Clock,
  X,
} from "lucide-react";
import { apiFetch } from "@/lib/api-fetch";

/* ─── Types ─── */

interface ProjectHealth {
  errors: number;
  warnings: number;
  /** 连需求都没有的规格文件数（新建工程的占位 docs/spec.md） */
  stubs?: number;
  /** 实际参与体检的文件数 */
  checked?: number;
}

interface Project {
  id: string;
  name: string;
  dir: string;
  spec_count: number;
  has_docs: boolean;
  mtime: number;
  health?: ProjectHealth;
}

interface SpecFile {
  path: string;
  name: string;
  size: number;
  mtime: number;
}

interface DocStats {
  requirements: number;
  scenarios: number;
  shall: number;
  should: number;
  may: number;
}

interface GenCardData {
  model: string;
  mock: boolean;
  repairs: number;
  errorCount: number;
  stats: DocStats;
}

interface ChatMsg {
  id: number;
  role: "user" | "ai";
  text: string;
  card?: GenCardData;
  tone?: "normal" | "error" | "success";
}

interface GenResponse {
  markdown: string;
  spec_path: string | null;
  stats: {
    requirements: number;
    scenarios: number;
    total_shall: number;
    total_should: number;
    total_may: number;
  };
  issues: { severity: string; message: string }[];
  error_count: number;
  repairs: number;
  mock: boolean;
  model: string;
}

interface SaveResponse {
  spec_path: string;
  stats: { requirements: number; scenarios: number; total_shall: number };
  issues: { severity: string; message: string }[];
  error_count: number;
}

/* ─── 工作区记忆（Trae 的 last-opened workspace） ─── */

const PROJECT_KEY = "yuleosh.studio.project";
const RECENT_KEY = "yuleosh.studio.recent";
const DEFAULT_SPEC_PATH = "docs/spec.md";

function readRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const list = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(list) ? list.filter((x) => typeof x === "string").slice(0, 5) : [];
  } catch {
    return [];
  }
}

function pushRecent(id: string): string[] {
  const next = [id, ...readRecent().filter((x) => x !== id)].slice(0, 5);
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    window.localStorage.setItem(PROJECT_KEY, id);
  } catch {
    /* localStorage 不可用时降级为仅内存 */
  }
  return next;
}

/* ─── 工程级会话状态（Trae 的 per-workspace editor state） ─── */

const STATE_PREFIX = "yuleosh.studio.state.";

interface WorkspaceState {
  activePath: string | null;
  editMode: boolean;
  mockMode: boolean;
  chatTail: Pick<ChatMsg, "role" | "text" | "tone" | "card">[];
}

function readWorkspaceState(pid: string): WorkspaceState | null {
  try {
    const raw = window.localStorage.getItem(STATE_PREFIX + pid);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WorkspaceState>;
    return {
      activePath: typeof parsed.activePath === "string" ? parsed.activePath : null,
      editMode: parsed.editMode === true,
      mockMode: parsed.mockMode !== false,
      chatTail: Array.isArray(parsed.chatTail) ? parsed.chatTail.slice(-6) : [],
    };
  } catch {
    return null;
  }
}

function writeWorkspaceState(pid: string, state: WorkspaceState) {
  try {
    window.localStorage.setItem(STATE_PREFIX + pid, JSON.stringify(state));
  } catch {
    /* 容量/隐私模式下静默降级 */
  }
}

/* ─── 工程模板（新建工程时写入 docs/spec.md，必须能过校验） ─── */

interface ProjectTemplate {
  id: string;
  name: string;
  hint: string;
  markdown: string;
}

const TEMPLATES: ProjectTemplate[] = [
  {
    id: "blank",
    name: "空白骨架",
    hint: "一条可编辑的起始需求 + 场景",
    markdown: `# {{name}} — 需求规格

### REQ-001: {{name}} 的核心能力

- The system SHALL provide the core capability described in this requirement.
- The system SHOULD log every invocation for traceability.

#### Reason

为架构设计提供可验证的最小起点。

#### Scenario: 基础能力可用

- GIVEN the system is deployed and configured
- WHEN the core capability is invoked
- THEN it completes within the defined acceptance criteria
`,
  },
  {
    id: "brake-light",
    name: "刹车灯控制",
    hint: "点亮/熄灭时序 + 开路故障检测",
    markdown: `# 刹车灯控制规格

### REQ-001: 刹车灯点亮与熄灭

- The system SHALL turn on the brake light within 100ms after the brake pedal is pressed.
- The system SHALL turn off the brake light within 200ms after the brake pedal is released.

#### Reason

向后方车辆传递制动意图，满足法规与安全要求。

#### Scenario: 正常制动

- GIVEN the vehicle is powered and the brake light is off
- WHEN the driver presses the brake pedal
- THEN the brake light turns on within 100ms

#### Scenario: 松开踏板

- GIVEN the vehicle is powered and the brake light is on
- WHEN the driver releases the brake pedal
- THEN the brake light turns off within 200ms

### REQ-002: 制动灯开路检测

- The system SHALL detect an open-circuit brake lamp within 500ms and record a DTC.

#### Reason

故障可诊断，便于售后定位与法规追溯。

#### Scenario: 灯泡开路

- GIVEN the brake light circuit is open
- WHEN the driver presses the brake pedal
- THEN the system records a DTC within 500ms
`,
  },
  {
    id: "can-monitor",
    name: "CAN 通信监控",
    hint: "心跳帧监控 + 跛行模式",
    markdown: `# CAN 通信监控规格

### REQ-001: 心跳帧监控

- The system SHALL monitor the CAN heartbeat frame every 100ms.
- The system SHALL enter limp-home mode when no heartbeat is received for 500ms.

#### Reason

总线失联时保证整车仍可安全行驶。

#### Scenario: 心跳丢失

- GIVEN the CAN bus is active and heartbeats arrive normally
- WHEN no heartbeat frame is received for 500ms
- THEN the system enters limp-home mode within 50ms
- AND the system records DTC U0100

#### Scenario: 心跳恢复

- GIVEN the system is in limp-home mode
- WHEN heartbeat frames are received again for 2s
- THEN the system leaves limp-home mode
`,
  },
  {
    id: "motor-overtemp",
    name: "电机过温保护",
    hint: "过温限功率 + 回落恢复",
    markdown: `# 电机过温保护规格

### REQ-001: 绕组过温限功率

- The system SHALL derate motor power when the winding temperature exceeds 150 degrees Celsius.
- The system SHALL restore full power when the winding temperature drops below 120 degrees Celsius.

#### Reason

防止绕组绝缘老化与永磁体退磁。

#### Scenario: 温度超限

- GIVEN the motor is running at rated power
- WHEN the winding temperature exceeds 150 degrees Celsius
- THEN the system derates output power within 200ms

#### Scenario: 温度回落

- GIVEN the motor output is derated
- WHEN the winding temperature drops below 120 degrees Celsius
- THEN the system restores full power
`,
  },
];

/* ─── 展示辅助 ─── */

function relTime(mtime: number): string {
  const diff = Date.now() / 1000 - mtime;
  if (!Number.isFinite(diff)) return "—";
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`;
  return new Date(mtime * 1000).toLocaleDateString("zh-CN");
}

/* ─── 文档统计（打开文件 / 手动编辑后的即时统计） ─── */

function computeStats(md: string): DocStats {
  const count = (re: RegExp) => (md.match(re) || []).length;
  return {
    requirements: count(/^#{2,4}\s+(?:Requirement\b|[A-Za-z]+-\d[\w.]*)/gim),
    scenarios: count(/^#{2,5}\s+Scenario:/gim),
    shall: count(/^\s*-\s*The\s+system\s+SHALL\b/gim),
    should: count(/^\s*-\s*The\s+system\s+SHOULD\b/gim),
    may: count(/^\s*-\s*The\s+system\s+MAY\b/gim),
  };
}

/* ─── Markdown 行高亮 ─── */

const TOKEN_RE =
  /(\bSHALL\b|\bSHOULD\b|\bMAY\b|\bGIVEN\b|\bWHEN\b|\bTHEN\b|\bAND\b|\b[A-Z]{2,}(?:-[A-Z0-9]+)*-\d+\b)/g;

const TOKEN_CLASS: Record<string, string> = {
  SHALL: "text-[#f87171] font-semibold",
  SHOULD: "text-[#fbbf24] font-semibold",
  MAY: "text-[#60a5fa] font-semibold",
  GIVEN: "text-[#c084fc] font-semibold",
  WHEN: "text-[#c084fc] font-semibold",
  THEN: "text-[#c084fc] font-semibold",
  AND: "text-[#c084fc] font-semibold",
};

function inlineTokens(line: string): ReactNode {
  const parts = line.split(TOKEN_RE);
  return parts.map((p, i) => {
    if (!p) return null;
    const kw = TOKEN_CLASS[p];
    if (kw) {
      return (
        <span key={i} className={kw}>
          {p}
        </span>
      );
    }
    if (/^[A-Z]{2,}(?:-[A-Z0-9]+)*-\d+$/.test(p)) {
      return (
        <span key={i} className="text-[#5eead4]">
          {p}
        </span>
      );
    }
    return <span key={i}>{p}</span>;
  });
}

function lineClass(line: string): string {
  if (/^#\s/.test(line)) return "text-[#a78bfa] font-bold";
  if (/^##\s/.test(line)) return "text-[#a78bfa] font-semibold";
  if (/^###\s/.test(line)) return "text-[#c4b5fd] font-semibold";
  if (/^####\s+Scenario:/i.test(line)) return "text-[#60a5fa] font-semibold";
  if (/^####\s+Reason/i.test(line)) return "text-[#94a3b8] italic";
  if (/^#{4,5}\s/.test(line)) return "text-[#93c5fd]";
  if (/^\s*Status:/i.test(line)) return "text-[#64748b] italic";
  if (/^\s*-\s*(GIVEN|WHEN|THEN|AND)\b/i.test(line)) return "text-[#cbd5e1]";
  return "text-[#c9d1e0]";
}

/* ─── 示例提示词 ─── */

const EXAMPLE_PROMPTS = [
  "写一个刹车灯控制需求：踩下刹车踏板后 100ms 内点亮刹车灯，松开后 200ms 内熄灭",
  "CAN 通信故障检测：连续 500ms 未收到心跳帧则进入跛行模式并记录 DTC",
  "电机过温保护：绕组温度超过 150°C 时限功率输出，降到 120°C 后恢复",
];

const GREETING_TEXT =
  "先在上方选择一个工程，然后用一句话描述需求。我会把它转换成符合 OpenSpec 规范的文档（SHALL 语句 + GIVEN/WHEN/THEN 场景），保存到该工程的 docs/ 目录后即可交给 Pipeline 执行。";

/* ─── Component ─── */

export default function StudioPage() {
  // 工程（工作区）
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [newName, setNewName] = useState("");
  const [templateId, setTemplateId] = useState(TEMPLATES[0].id);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  // 文件树
  const [files, setFiles] = useState<SpecFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  // 编辑器
  const [doc, setDoc] = useState("");
  const [activePath, setActivePath] = useState<string | null>(null);
  const [savedAbs, setSavedAbs] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [editMode, setEditMode] = useState(false);
  // 聊天
  const [messages, setMessages] = useState<ChatMsg[]>([
    { id: 0, role: "ai", text: GREETING_TEXT },
  ]);
  const [input, setInput] = useState("");
  const [mockMode, setMockMode] = useState(true);
  const [generating, setGenerating] = useState(false);
  // 状态
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<"save" | "validate" | "run" | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const msgId = useRef(1);
  const swRef = useRef<HTMLDivElement>(null);
  // 工程切换时用来「存上一个 / 恢复下一个」的快照
  const prevProjectRef = useRef<string | null>(null);
  const stateSnap = useRef<WorkspaceState>({
    activePath: null,
    editMode: false,
    mockMode: true,
    chatTail: [],
  });

  const stats = useMemo(() => computeStats(doc), [doc]);
  const activeProject = useMemo(
    () => projects.find((p) => p.id === projectId) ?? null,
    [projects, projectId],
  );

  const showToast = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast((t) => (t === text ? null : t)), 3000);
  }, []);

  const pushMsg = useCallback((m: Omit<ChatMsg, "id">) => {
    setMessages((prev) => [...prev, { ...m, id: msgId.current++ }]);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, generating]);

  // 点击外部关闭工程下拉
  useEffect(() => {
    if (!switcherOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (swRef.current && !swRef.current.contains(e.target as Node)) setSwitcherOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [switcherOpen]);

  /* ── 工程列表 ── */
  const loadProjects = useCallback(async (): Promise<Project[]> => {
    setProjectsLoading(true);
    try {
      const data = await apiFetch<{ projects: Project[] }>("/api/v1/spec/projects");
      const list = data.projects || [];
      setProjects(list);
      // 只恢复上次打开的工程；没有记忆就停在欢迎页（工程卡片），
      // 不擅自替用户挑一个工程。
      setProjectId((cur) => {
        if (cur && list.some((p) => p.id === cur)) return cur;
        const saved = window.localStorage.getItem(PROJECT_KEY);
        if (saved && list.some((p) => p.id === saved)) return saved;
        return null;
      });
      return list;
    } catch {
      setProjects([]);
      return [];
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  /* ── 切换工程后加载该工程 docs/ 下的规格 ── */
  const loadFiles = useCallback(async (pid: string | null): Promise<SpecFile[]> => {
    if (!pid) {
      setFiles([]);
      setFilesLoading(false);
      return [];
    }
    setFilesLoading(true);
    try {
      const data = await apiFetch<{ files: SpecFile[] }>(
        `/api/v1/spec/list?project=${encodeURIComponent(pid)}`,
      );
      const list = data.files || [];
      setFiles(list);
      return list;
    } catch {
      setFiles([]);
      return [];
    } finally {
      setFilesLoading(false);
    }
  }, []);

  // 初始加载：工程列表 + 健康检查
  useEffect(() => {
    loadProjects();
    setRecentIds(readRecent());
    apiFetch("/api/v1/health")
      .then(() => setHealthy(true))
      .catch(() => setHealthy(false));
  }, [loadProjects]);

  // 每次渲染同步最新会话状态，供工程切换时落盘
  useEffect(() => {
    stateSnap.current = {
      activePath,
      editMode,
      mockMode,
      chatTail: messages.slice(1).slice(-6).map(({ role, text, tone, card }) => ({
        role,
        text,
        tone,
        card,
      })),
    };
  });

  // 工程变化：先存上一个工程的会话状态，再恢复本工程的
  useEffect(() => {
    if (!projectId) {
      setFiles([]);
      return;
    }
    setRecentIds(pushRecent(projectId));

    const prev = prevProjectRef.current;
    if (prev && prev !== projectId) writeWorkspaceState(prev, stateSnap.current);
    prevProjectRef.current = projectId;

    const saved = readWorkspaceState(projectId);
    setDoc("");
    setActivePath(null);
    setSavedAbs(null);
    setDirty(false);
    setEditMode(false);
    setMockMode(saved?.mockMode ?? true);
    setMessages([
      { id: 0, role: "ai", text: GREETING_TEXT },
      ...(saved?.chatTail ?? []).map((m) => ({ ...m, id: msgId.current++ })),
    ]);

    let cancelled = false;
    loadFiles(projectId).then((list) => {
      if (cancelled) return;
      const path = saved?.activePath;
      if (path && list.some((f) => f.path === path)) {
        // openFile 会把 editMode 复位到预览，恢复记忆时要再切回编辑
        openFile(path).then(() => {
          if (!cancelled && saved?.editMode) setEditMode(true);
        });
      }
    });
    return () => {
      cancelled = true;
    };
    // openFile 依赖 projectId，这里跟随 projectId 一起变即可
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, loadFiles]);

  /* ── 新建工程（可选模板，模板内容直接写入 docs/spec.md） ── */
  const createProject = useCallback(async () => {
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const created = await apiFetch<{ id?: number | string; name?: string }>(
        "/api/v1/project",
        { method: "POST", body: JSON.stringify({ name }) },
      );
      const pid = created?.id != null ? String(created.id) : "";
      const template = TEMPLATES.find((t) => t.id === templateId) ?? TEMPLATES[0];

      // 新工程默认会落一个占位 spec.md；模板内容覆盖它，保证健康徽标是绿的
      if (pid && template.markdown) {
        const markdown = template.markdown.replaceAll(
          "{{name}}",
          created?.name || name,
        );
        try {
          await apiFetch("/api/v1/spec/save", {
            method: "POST",
            body: JSON.stringify({
              project: pid,
              path: DEFAULT_SPEC_PATH,
              markdown,
              force: true,
            }),
          });
        } catch (e) {
          pushMsg({
            role: "ai",
            text: `工程已创建，但模板写入失败：${(e as Error).message}`,
            tone: "error",
          });
        }
      }

      const list = await loadProjects();
      const hit = (pid ? list.find((p) => p.id === pid) : undefined)
        ?? list.find((p) => p.name === (created?.name || name));
      if (hit) setProjectId(hit.id);
      setNewName("");
      setTemplateId(TEMPLATES[0].id);
      setCreateOpen(false);
      setSwitcherOpen(false);
      showToast(`已创建工程「${created?.name || name}」`);
    } catch (e) {
      pushMsg({ role: "ai", text: `创建工程失败：${(e as Error).message}`, tone: "error" });
    } finally {
      setCreating(false);
    }
  }, [newName, creating, templateId, loadProjects, showToast, pushMsg]);

  /* ── 打开文件 ── */
  const openFile = useCallback(async (path: string) => {
    if (!projectId) return;
    try {
      const data = await apiFetch<{ content: string }>(
        `/api/v1/spec/read?project=${encodeURIComponent(projectId)}&path=${encodeURIComponent(path)}`,
      );
      setDoc(data.content);
      setActivePath(path);
      setSavedAbs(null);
      setDirty(false);
      setEditMode(false);
    } catch (e) {
      pushMsg({ role: "ai", text: `读取 ${path} 失败：${(e as Error).message}`, tone: "error" });
    }
  }, [projectId, pushMsg]);

  /* ── 生成 ── */
  const send = useCallback(async (rawPrompt?: string) => {
    const prompt = (rawPrompt ?? input).trim();
    if (!prompt || generating || !projectId) return;
    setInput("");
    pushMsg({ role: "user", text: prompt });
    setGenerating(true);
    try {
      const data = await apiFetch<GenResponse>("/api/v1/spec/gen", {
        method: "POST",
        body: JSON.stringify({ prompt, mock: mockMode, project: projectId }),
      });
      setDoc(data.markdown);
      setActivePath(null);
      setSavedAbs(null);
      setDirty(false);
      setEditMode(false);
      const s = data.stats;
      pushMsg({
        role: "ai",
        text:
          data.error_count > 0
            ? `已生成草稿，但校验发现 ${data.error_count} 个错误，请在编辑器中修正后保存。`
            : `已生成 OpenSpec 文档：${s.requirements} 条需求、${s.scenarios} 个场景（${s.total_shall} SHALL / ${s.total_should} SHOULD / ${s.total_may} MAY）。点击「保存到项目」写入本工程 docs/ 后即可运行 Pipeline。`,
        tone: data.error_count > 0 ? "error" : "success",
        card: {
          model: data.model,
          mock: data.mock,
          repairs: data.repairs,
          errorCount: data.error_count,
          stats: {
            requirements: s.requirements,
            scenarios: s.scenarios,
            shall: s.total_shall,
            should: s.total_should,
            may: s.total_may,
          },
        },
      });
    } catch (e) {
      pushMsg({
        role: "ai",
        text: `生成失败：${(e as Error).message}${mockMode ? "" : "（可打开 Mock 开关离线试玩）"}`,
        tone: "error",
      });
    } finally {
      setGenerating(false);
    }
  }, [input, generating, mockMode, projectId, pushMsg]);

  /* ── 保存（工程内 docs/，先校验后落盘；409 → 确认覆盖） ── */
  const save = useCallback(async (): Promise<{ rel: string; abs: string } | null> => {
    if (!projectId || !activeProject) {
      showToast("请先选择一个工程");
      return null;
    }
    if (!doc.trim()) {
      showToast("编辑器为空，请先生成或打开一个规格");
      return null;
    }
    const target = activePath || DEFAULT_SPEC_PATH;
    setBusy("save");
    try {
      const attempt = async (force: boolean) =>
        fetch("/api/v1/spec/save", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project: projectId, path: target, markdown: doc, force }),
        });
      let res = await attempt(false);
      if (res.status === 409) {
        if (!window.confirm(`${target} 已存在，覆盖？`)) return null;
        res = await attempt(true);
      }
      const body = await res.json();
      if (!res.ok || body.ok === false) {
        const issues = body.details?.issues as { severity: string; message: string }[] | undefined;
        const errs = (issues || []).filter((i) => i.severity === "ERROR").slice(0, 5);
        pushMsg({
          role: "ai",
          text:
            `保存失败：${body.error || res.status}` +
            (errs.length ? `\n${errs.map((i) => `• ${i.message}`).join("\n")}` : ""),
          tone: "error",
        });
        return null;
      }
      const data = body.data as SaveResponse;
      setActivePath(target);
      setSavedAbs(data.spec_path);
      setDirty(false);
      await loadFiles(projectId);
      await loadProjects();
      showToast(`已保存 ${activeProject.dir}/${target}`);
      pushMsg({
        role: "ai",
        text: `已保存到 \`${activeProject.dir}/${target}\`，校验通过。下一步：运行 Pipeline。`,
        tone: "success",
      });
      return { rel: target, abs: data.spec_path };
    } catch (e) {
      pushMsg({ role: "ai", text: `保存失败：${(e as Error).message}`, tone: "error" });
      return null;
    } finally {
      setBusy(null);
    }
  }, [doc, activePath, projectId, activeProject, loadFiles, loadProjects, pushMsg, showToast]);

  /* ── 校验：未保存先保存；validate 以 OSH_HOME 为根，需传绝对路径 ── */
  const validate = useCallback(async () => {
    if (!projectId) return;
    let abs = savedAbs;
    if (!abs || dirty) {
      const saved = await save();
      if (!saved) return;
      abs = saved.abs;
    }
    if (!abs) return;
    setBusy("validate");
    try {
      const data = await apiFetch<{
        issues: { severity: string; message: string }[];
        error_count: number;
        issue_count: number;
      }>("/api/v1/spec/validate", {
        method: "POST",
        body: JSON.stringify({ path: abs }),
      });
      if (data.error_count === 0) {
        pushMsg({
          role: "ai",
          text: `校验通过：${activePath || DEFAULT_SPEC_PATH}${data.issue_count ? `（${data.issue_count} 条 WARN 建议）` : ""}`,
          tone: "success",
        });
        showToast("校验通过");
      } else {
        const errs = data.issues.filter((i) => i.severity === "ERROR").slice(0, 5);
        pushMsg({
          role: "ai",
          text: `校验发现 ${data.error_count} 个错误：\n${errs.map((i) => `• ${i.message}`).join("\n")}`,
          tone: "error",
        });
      }
    } catch (e) {
      pushMsg({ role: "ai", text: `校验失败：${(e as Error).message}`, tone: "error" });
    } finally {
      setBusy(null);
    }
  }, [projectId, savedAbs, dirty, save, activePath, pushMsg, showToast]);

  /* ── 运行 Pipeline ── */
  const runPipeline = useCallback(async () => {
    if (!projectId) {
      showToast("请先选择一个工程");
      return;
    }
    let path = activePath;
    if (!path || dirty) {
      const saved = await save();
      if (!saved) return;
      path = saved.rel;
    }
    setBusy("run");
    try {
      const data = await apiFetch<{ job_id?: string; id?: string }>(
        "/api/v1/pipeline/trigger",
        { method: "POST", body: JSON.stringify({ type: "full", project: projectId }) },
      );
      const jobId = data.job_id || data.id || "";
      pushMsg({
        role: "ai",
        text: `Pipeline 已触发${jobId ? `（任务 ${jobId}）` : ""}，进度见 Dashboard 流水线页。`,
        tone: "success",
      });
    } catch (e) {
      pushMsg({
        role: "ai",
        text: `Pipeline 触发失败：${(e as Error).message}\n也可在终端执行：yuleosh pipeline run ${activeProject?.dir}/${path}`,
        tone: "error",
      });
    } finally {
      setBusy(null);
    }
  }, [projectId, activePath, dirty, save, pushMsg, activeProject, showToast]);

  /* ── 复制 CLI ── */
  const cliHint = `yuleosh pipeline run ${activeProject?.dir || "projects/<id>"}/${activePath || DEFAULT_SPEC_PATH}`;

  const copyCLI = useCallback(() => {
    navigator.clipboard?.writeText(cliHint).then(
      () => showToast("已复制 CLI 命令"),
      () => showToast(cliHint),
    );
  }, [cliHint, showToast]);

  const recentProjects = useMemo(
    () => recentIds.map((id) => projects.find((p) => p.id === id)).filter((p): p is Project => !!p),
    [recentIds, projects],
  );

  /* ═══ Render ═══ */

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#0a0e17] text-[13px] leading-relaxed text-[#e2e8f0]">
      {/* ── 顶栏：工程切换器 ── */}
      <header className="flex h-11 flex-none items-center gap-2.5 border-b border-[#1e293b] bg-[#0b0f1a] px-4">
        <div className="flex items-center gap-2 font-semibold">
          <span className="grid h-5 w-5 place-items-center rounded-md bg-gradient-to-br from-[#722ed1] to-[#1677ff] text-[10px] font-bold text-white">
            yO
          </span>
          yuleOSH Studio
        </div>
        <span className="text-[#334155]">|</span>

        {/* 工程（工作区）切换 */}
        <div className="relative" ref={swRef}>
          <button
            onClick={() => setSwitcherOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded-md border border-[#1e293b] bg-[#111827] px-2.5 py-1 text-[12px] text-[#cbd5e1] transition-colors hover:border-[#722ed1]/50 hover:text-white"
            title="切换工程（工作区）"
          >
            <FolderOpen className="h-3.5 w-3.5 text-[#a78bfa]" />
            <span className="max-w-[180px] truncate">
              {activeProject ? activeProject.name : projectsLoading ? "加载工程…" : "选择工程"}
            </span>
            <ChevronDown className="h-3 w-3 text-[#64748b]" />
          </button>

          {switcherOpen && (
            <div className="absolute left-0 top-full z-30 mt-1 w-[22rem] rounded-lg border border-[#1e293b] bg-[#0f1420] p-2 shadow-2xl shadow-black/60">
              {recentProjects.length > 0 && (
                <>
                  <p className="px-2 pb-1 pt-1 text-[10.5px] uppercase tracking-wider text-[#475569]">
                    最近打开
                  </p>
                  {recentProjects.map((p) => (
                    <ProjectRow
                      key={`recent-${p.id}`}
                      project={p}
                      active={p.id === projectId}
                      onClick={() => {
                        setProjectId(p.id);
                        setSwitcherOpen(false);
                      }}
                    />
                  ))}
                  <div className="my-1.5 h-px bg-[#1e293b]" />
                </>
              )}

              <p className="px-2 pb-1 text-[10.5px] uppercase tracking-wider text-[#475569]">
                全部工程（{projects.length}）
              </p>
              <div className="max-h-64 overflow-y-auto">
                {projects.length === 0 && !projectsLoading && (
                  <p className="px-2 py-3 text-[11.5px] leading-relaxed text-[#64748b]">
                    还没有工程。点击下方「新建工程」，规格会保存在它的
                    <span className="text-[#94a3b8]"> docs/ </span>目录。
                  </p>
                )}
                {projects.map((p) => (
                  <ProjectRow
                    key={p.id}
                    project={p}
                    active={p.id === projectId}
                    onClick={() => {
                      setProjectId(p.id);
                      setSwitcherOpen(false);
                    }}
                  />
                ))}
              </div>

              {/* 新建工程 */}
              <div className="mt-2 border-t border-[#1e293b] pt-2">
                <button
                  onClick={() => {
                    setSwitcherOpen(false);
                    setCreateOpen(true);
                  }}
                  className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-[12px] text-[#c4b5fd] transition-colors hover:bg-[#722ed1]/15"
                >
                  <FolderPlus className="h-3.5 w-3.5" />
                  新建工程（可选模板）
                </button>
              </div>
            </div>
          )}
        </div>

        <span className="truncate text-xs text-[#475569]">
          {activePath || (doc.trim() ? "未保存的草稿" : "")}
          {dirty && <span className="ml-1 text-[#fbbf24]">●</span>}
        </span>

        <div className="ml-auto flex items-center gap-3">
          <span
            className="flex items-center gap-1.5 rounded-full border border-[#1e293b] px-2.5 py-1 text-[11px] text-[#94a3b8]"
            title="后端服务状态"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                healthy === null ? "bg-[#64748b]" : healthy ? "bg-[#10b981]" : "bg-[#ff4d4f]"
              }`}
            />
            {healthy === null ? "检测中" : healthy ? "服务正常" : "服务异常"}
          </span>
          <Link
            href="/dashboard"
            className="flex items-center gap-1 rounded-md border border-[#1e293b] px-2.5 py-1 text-[11px] text-[#94a3b8] transition-colors hover:border-[#722ed1]/40 hover:text-white"
          >
            <LayoutDashboard className="h-3 w-3" />
            Dashboard
          </Link>
        </div>
      </header>

      {projectId ? (
      /* ── 三栏工作区 ── */
      <div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)_380px]">
        {/* 左：工程信息 + 规格文件树 */}
        <aside className="flex min-h-0 flex-col border-r border-[#1e293b] bg-[#0b0f1a]">
          <div className="flex items-center justify-between px-3.5 pb-1.5 pt-3 text-[11px] uppercase tracking-wider text-[#64748b]">
            规格文件
            <button
              onClick={() => {
                loadFiles(projectId);
                loadProjects();
              }}
              title="刷新"
              className="rounded p-1 text-[#64748b] transition-colors hover:bg-[#1e293b] hover:text-white"
            >
              <RefreshCw className={`h-3 w-3 ${filesLoading ? "animate-spin" : ""}`} />
            </button>
          </div>

          {activeProject && (
            <div className="mx-2 mb-2 rounded-md border border-[#1e293b] bg-[#111827] px-2.5 py-2 text-[10.5px] text-[#64748b]">
              <div className="truncate text-[#94a3b8]" title={activeProject.dir}>
                {activeProject.dir}/
              </div>
              <div className="mt-0.5 flex items-center gap-1.5">
                <FileText className="h-3 w-3" />
                {activeProject.spec_count} 个规格文件
              </div>
              <div className="mt-1">
                <HealthBadge project={activeProject} />
              </div>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {files.length === 0 && !filesLoading && (
              <p className="px-2 py-4 text-[11px] leading-relaxed text-[#475569]">
                该工程 docs/ 下还没有规格文件。
                <br />
                在右侧描述需求，生成后点击「保存到项目」。
              </p>
            )}
            {files.map((f) => (
              <button
                key={f.path}
                onClick={() => openFile(f.path)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] transition-colors ${
                  activePath === f.path
                    ? "bg-[#722ed1]/15 text-white"
                    : "text-[#94a3b8] hover:bg-[#111827] hover:text-[#e2e8f0]"
                }`}
                title={`${activeProject?.dir || ""}/${f.path}`}
              >
                <FileText className="h-3.5 w-3.5 flex-none text-[#64748b]" />
                <span className="min-w-0 flex-1 truncate">{f.path}</span>
              </button>
            ))}
          </div>

          <div className="flex-none border-t border-[#1e293b] px-3.5 py-2 text-[10.5px] text-[#475569]">
            {projectId ? `docs/ · ${files.length} 个文件` : "未打开工程"}
          </div>
        </aside>

        {/* 中：编辑器 */}
        <section className="flex min-w-0 flex-col bg-[#0a0e17]">
          {/* 编辑器工具栏 */}
          <div className="flex h-10 flex-none items-center gap-2 border-b border-[#1e293b] bg-[#0b0f1a] px-3">
            <div className="flex rounded-md border border-[#1e293b] bg-[#111827] p-0.5">
              <button
                onClick={() => setEditMode(false)}
                className={`flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition-colors ${
                  !editMode ? "bg-[#722ed1]/20 text-[#c4b5fd]" : "text-[#64748b] hover:text-white"
                }`}
              >
                <Eye className="h-3 w-3" /> 预览
              </button>
              <button
                onClick={() => setEditMode(true)}
                disabled={!projectId}
                className={`flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                  editMode ? "bg-[#722ed1]/15 text-[#c4b5fd]" : "text-[#64748b] hover:text-white"
                }`}
              >
                <PencilLine className="h-3 w-3" /> 编辑
              </button>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={validate}
                disabled={busy !== null || !doc.trim() || !projectId}
                className="flex items-center gap-1.5 rounded-md border border-[#1e293b] px-2.5 py-1 text-[11.5px] text-[#94a3b8] transition-colors hover:border-[#334155] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy === "validate" ? <Loader2 className="h-3 w-3 animate-spin" /> : <ShieldCheck className="h-3 w-3" />}
                校验
              </button>
              <button
                onClick={save}
                disabled={busy !== null || !doc.trim() || !projectId}
                className="flex items-center gap-1.5 rounded-md border border-[#1e293b] px-2.5 py-1 text-[11.5px] text-[#94a3b8] transition-colors hover:border-[#334155] hover:text-white disabled:opacity-40"
              >
                {busy === "save" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                保存到项目
              </button>
            </div>
          </div>

          {/* 文档区 */}
          <div className="relative min-h-0 flex-1 overflow-hidden">
            {/* 浮动统计卡 */}
            {doc.trim() && !editMode && (
              <div className="absolute right-4 top-3 z-10 flex items-center gap-3 rounded-lg border border-[#1e293b] bg-[#111827]/95 px-3.5 py-2 shadow-lg shadow-black/40 backdrop-blur">
                <Stat label="需求" value={stats.requirements} />
                <Divider />
                <Stat label="场景" value={stats.scenarios} />
                <Divider />
                <Stat label="SHALL" value={stats.shall} valueClass="text-[#f87171]" />
                <Divider />
                <Stat label="SHOULD" value={stats.should} valueClass="text-[#fbbf24]" />
                <Divider />
                <Stat label="MAY" value={stats.may} valueClass="text-[#60a5fa]" />
              </div>
            )}

            {!doc.trim() ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-[#475569]">
                <Sparkles className="h-8 w-8 text-[#722ed1]/50" />
                <p className="text-sm">
                  在右侧描述需求，或从左侧打开 <span className="text-[#94a3b8]">{activeProject?.name}</span> 的现有规格
                </p>
                <p className="font-mono text-[11px] text-[#334155]">
                  也支持 CLI：yuleosh spec gen &quot;需求描述&quot;
                </p>
              </div>
            ) : editMode ? (
              <textarea
                value={doc}
                onChange={(e) => {
                  setDoc(e.target.value);
                  setDirty(true);
                }}
                spellCheck={false}
                className="h-full w-full resize-none bg-transparent p-4 font-mono text-[12.5px] leading-[1.75] text-[#c9d1e0] outline-none"
              />
            ) : (
              <div className="h-full overflow-y-auto">
                <div className="grid grid-cols-[3rem_1fr] py-3 font-mono text-[12.5px] leading-[1.75]">
                  <div className="select-none pr-3 text-right text-[#334155]">
                    {doc.split("\n").map((_, i) => (
                      <div key={i}>{i + 1}</div>
                    ))}
                  </div>
                  <div className="whitespace-pre-wrap break-words pr-8">
                    {doc.split("\n").map((line, i) => (
                      <div key={i} className={lineClass(line)}>
                        {line ? inlineTokens(line) : " "}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 底部操作栏 */}
          <div className="flex flex-none items-center gap-2.5 border-t border-[#1e293b] bg-[#0b0f1a] px-3.5 py-2">
            <button
              onClick={runPipeline}
              disabled={busy !== null || !doc.trim() || !projectId}
              className="flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-[#722ed1] to-[#5b21b6] px-3.5 py-1.5 text-[12px] font-semibold text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy === "run" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              运行 Pipeline
            </button>
            <button
              onClick={copyCLI}
              disabled={!projectId}
              className="flex items-center gap-1.5 rounded-lg border border-[#1e293b] px-3 py-1.5 text-[12px] text-[#94a3b8] transition-colors hover:border-[#334155] hover:text-white disabled:opacity-40"
            >
              <ClipboardCopy className="h-3.5 w-3.5" />
              复制 CLI
            </button>
            <div className="flex-1" />
            <code className="max-w-[60%] truncate rounded-md border border-[#1e293b] bg-[#111827] px-2.5 py-1 font-mono text-[11px] text-[#64748b]" title={cliHint}>
              {cliHint}
            </code>
          </div>
        </section>

        {/* 右：需求助手 */}
        <aside className="flex min-h-0 flex-col border-l border-[#1e293b] bg-[#0b0f1a]">
          <div className="flex h-12 flex-none items-center gap-2 border-b border-[#1e293b] px-3.5">
            <Sparkles className="h-4 w-4 text-[#a78bfa]" />
            <span className="text-[13px] font-semibold">需求助手</span>
            <div className="ml-auto flex items-center gap-2">
              <span className="text-[10.5px] text-[#64748b]">{mockMode ? "离线 Mock" : "真实模型"}</span>
              <button
                onClick={() => setMockMode((v) => !v)}
                title={mockMode ? "切换到真实 LLM（需配置 API Key）" : "切换到离线 Mock"}
                className={`relative w-8 rounded-full transition-colors ${mockMode ? "bg-[#722ed1]" : "bg-[#1e293b]"}`}
                style={{ height: 18 }}
              >
                <span
                  className={`absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-all ${
                    mockMode ? "left-4" : "left-0.5"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* 消息流 */}
          <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto p-3.5">
            {messages.map((m) => (
              <div key={m.id} className="flex gap-2.5">
                <span
                  className={`grid flex-none place-items-center rounded-lg text-[11px] font-bold ${
                    m.role === "ai"
                      ? "bg-gradient-to-br from-[#722ed1] to-[#1677ff] text-white"
                      : "bg-[#1e293b] text-[#94a3b8]"
                  }`}
                  style={{ width: 26, height: 26 }}
                >
                  {m.role === "ai" ? "yO" : "我"}
                </span>
                <div
                  className={`min-w-0 flex-1 rounded-lg border px-3 py-2 text-[12.5px] ${
                    m.role === "user"
                      ? "border-[#1e3a5f] bg-[#0f1b2d] text-[#e2e8f0]"
                      : m.tone === "error"
                        ? "border-[#ff4d4f]/30 bg-[#ff4d4f]/5 text-[#fca5a5]"
                        : m.tone === "success"
                          ? "border-[#10b981]/30 bg-[#10b981]/5 text-[#d1fae5]"
                          : "border-[#1e293b] bg-[#111827] text-[#cbd5e1]"
                  }`}
                  style={{ whiteSpace: "pre-wrap" }}
                >
                  {m.text}
                  {m.card && (
                    <div className="mt-2 rounded-md border border-[#1e293b] bg-[#0a0e17] px-2.5 py-2 text-[11px] text-[#94a3b8]">
                      <div className="flex items-center justify-between">
                        <span>{m.card.mock ? "Mock 引擎" : m.card.model}</span>
                        {m.card.errorCount === 0 ? (
                          <span className="text-[#10b981]">✓ 校验通过</span>
                        ) : (
                          <span className="flex items-center gap-1 text-[#ff4d4f]">
                            <CircleAlert className="h-3 w-3" /> {m.card.errorCount} 错误
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-[#64748b]">
                        {m.card.stats.requirements} 需求 · {m.card.stats.scenarios} 场景 ·{" "}
                        {m.card.stats.shall} SHALL
                        {m.card.repairs > 0 && ` · ${m.card.repairs} 次自动修复`}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {generating && (
              <div className="flex gap-2.5">
                <span
                  className="grid flex-none place-items-center rounded-lg bg-gradient-to-br from-[#722ed1] to-[#1677ff] text-[11px] font-bold text-white"
                  style={{ width: 26, height: 26 }}
                >
                  yO
                </span>
                <div className="flex items-center gap-1.5 rounded-lg border border-[#1e293b] bg-[#111827] px-3 py-2.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#a78bfa]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#a78bfa]" style={{ animationDelay: "0.15s" }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#a78bfa]" style={{ animationDelay: "0.3s" }} />
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* 输入区 */}
          <div className="flex-none border-t border-[#1e293b] p-3">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {EXAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => send(p)}
                  disabled={generating || !projectId}
                  className="max-w-full truncate rounded-full border border-[#722ed1]/25 bg-[#722ed1]/10 px-2.5 py-1 text-[11px] text-[#c4b5fd] transition-colors hover:border-[#722ed1]/50 disabled:opacity-40"
                  title={p}
                >
                  {p.slice(0, 14)}…
                </button>
              ))}
            </div>
            <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-2.5 transition-colors focus-within:border-[#722ed1]/60">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder={
                  projectId
                    ? `描述「${activeProject?.name ?? ""}」的需求，Enter 发送 / Shift+Enter 换行`
                    : "请先选择一个工程"
                }
                disabled={!projectId}
                rows={3}
                className="w-full resize-none bg-transparent text-[12.5px] text-[#e2e8f0] outline-none placeholder:text-[#475569] disabled:cursor-not-allowed"
              />
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[10.5px] text-[#475569]">
                  {mockMode ? "Mock 引擎 · 离线可用" : "LLM · 需配置 API Key"}
                </span>
                <button
                  onClick={() => send()}
                  disabled={generating || !input.trim() || !projectId}
                  className="grid h-7 w-7 place-items-center rounded-lg bg-[#722ed1] text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:bg-[#1e293b] disabled:text-[#475569]"
                >
                  {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <SendHorizonal className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          </div>
        </aside>
      </div>
      ) : (
        /* ── 欢迎页：工程卡片（Trae 的 Welcome / Recent Workspaces） ── */
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-8 py-10">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-[22px] font-semibold text-white">选择一个工程开始</h1>
                <p className="mt-1.5 text-[12.5px] leading-relaxed text-[#64748b]">
                  一个工程就是一个工作区（
                  <code className="font-mono text-[#94a3b8]">OSH_HOME/projects/&lt;id&gt;/</code>
                  ），规格文件放在它的{" "}
                  <code className="font-mono text-[#94a3b8]">docs/</code> 下 —— 与 Pipeline
                  用的是同一份。
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCreateOpen(true)}
                  className="flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-[#722ed1] to-[#5b21b6] px-3.5 py-1.5 text-[12px] font-semibold text-white transition-all hover:brightness-110"
                >
                  <FolderPlus className="h-3.5 w-3.5" />
                  新建工程
                </button>
                <button
                  onClick={() => loadProjects()}
                  className="flex items-center gap-1.5 rounded-lg border border-[#1e293b] px-3 py-1.5 text-[12px] text-[#94a3b8] transition-colors hover:border-[#334155] hover:text-white"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${projectsLoading ? "animate-spin" : ""}`} />
                  刷新
                </button>
              </div>
            </div>

            {projectsLoading ? (
              <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-[108px] animate-pulse rounded-xl border border-[#1e293b] bg-[#111827]/60"
                  />
                ))}
              </div>
            ) : projects.length === 0 ? (
              <button
                onClick={() => setCreateOpen(true)}
                className="mt-8 flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-[#1e293b] py-14 text-[#475569] transition-colors hover:border-[#722ed1]/50 hover:text-[#c4b5fd]"
              >
                <FolderPlus className="h-7 w-7" />
                <span className="text-[13px]">还没有工程，创建第一个工程</span>
                <span className="text-[11px]">可从模板开始：刹车灯 / CAN 通信 / 电机过温</span>
              </button>
            ) : (
              <>
                {recentProjects.length > 0 && (
                  <section className="mt-7">
                    <SectionTitle>最近打开</SectionTitle>
                    <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {recentProjects.map((p) => (
                        <ProjectCard key={`recent-${p.id}`} project={p} onOpen={setProjectId} />
                      ))}
                    </div>
                  </section>
                )}
                <section className="mt-7">
                  <SectionTitle>全部工程（{projects.length}）</SectionTitle>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {projects.map((p) => (
                      <ProjectCard key={p.id} project={p} onOpen={setProjectId} />
                    ))}
                  </div>
                </section>
              </>
            )}

            <p className="mt-9 text-[11px] text-[#334155]">
              卡片上的徽标来自后端对每个工程 docs/ 规格的实时校验；红色表示保存前会被拦下的 ERROR。
            </p>
          </div>
        </div>
      )}

      {/* ── 新建工程弹层（名称 + 模板） ── */}
      {createOpen && (
        <div
          className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-6"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setCreateOpen(false);
          }}
        >
          <div className="w-full max-w-lg rounded-xl border border-[#1e293b] bg-[#0f1420] p-5 shadow-2xl shadow-black/70">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[14px] font-semibold text-white">
                <FolderPlus className="h-4 w-4 text-[#a78bfa]" />
                新建工程
              </div>
              <button
                onClick={() => setCreateOpen(false)}
                className="rounded p-1 text-[#64748b] transition-colors hover:bg-[#1e293b] hover:text-white"
                title="关闭"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            <label className="mt-4 block text-[11px] uppercase tracking-wider text-[#64748b]">
              工程名称
            </label>
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) createProject();
                if (e.key === "Escape") setCreateOpen(false);
              }}
              placeholder="例如：刹车灯控制"
              className="mt-1.5 w-full rounded-md border border-[#1e293b] bg-[#0a0e17] px-2.5 py-2 text-[12.5px] text-[#e2e8f0] outline-none placeholder:text-[#475569] focus:border-[#722ed1]/60"
            />

            <label className="mt-4 block text-[11px] uppercase tracking-wider text-[#64748b]">
              起始模板
            </label>
            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
              {TEMPLATES.map((t) => {
                const active = t.id === templateId;
                return (
                  <button
                    key={t.id}
                    onClick={() => setTemplateId(t.id)}
                    className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                      active
                        ? "border-[#722ed1]/70 bg-[#722ed1]/15"
                        : "border-[#1e293b] bg-[#111827] hover:border-[#334155]"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className={`text-[12px] font-semibold ${active ? "text-white" : "text-[#cbd5e1]"}`}>
                        {t.name}
                      </span>
                      {active && <Check className="h-3 w-3 text-[#a78bfa]" />}
                    </div>
                    <div className="mt-0.5 text-[10.5px] leading-relaxed text-[#64748b]">{t.hint}</div>
                  </button>
                );
              })}
            </div>

            <div className="mt-5 flex items-center justify-between gap-3">
              <span className="text-[10.5px] text-[#475569]">
                模板会写入新工程的 <code className="font-mono">docs/spec.md</code> 并通过校验
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCreateOpen(false)}
                  className="rounded-md border border-[#1e293b] px-3 py-1.5 text-[12px] text-[#94a3b8] transition-colors hover:text-white"
                >
                  取消
                </button>
                <button
                  onClick={createProject}
                  disabled={creating || !newName.trim()}
                  className="flex items-center gap-1.5 rounded-md bg-[#722ed1] px-3.5 py-1.5 text-[12px] font-semibold text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:bg-[#1e293b] disabled:text-[#475569]"
                >
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  创建
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 状态栏 ── */}
      <footer
        className="flex flex-none items-center gap-4 border-t border-[#1e293b] bg-[#0b0f1a] px-3.5 text-[11px] text-[#64748b]"
        style={{ height: 26 }}
      >
        <span className={stats.requirements > 0 ? "text-[#10b981]" : ""}>
          {stats.requirements > 0 ? `✓ ${stats.requirements} 需求 / ${stats.scenarios} 场景` : "无规格内容"}
        </span>
        <span className="truncate">
          {activeProject ? `工程：${activeProject.dir}` : "未打开工程"}
          {activePath ? ` · ${activePath}${dirty ? "（未保存）" : ""}` : ""}
        </span>
        <span className="ml-auto truncate">{toast ?? "OpenSpec → SDD → DDD → TDD → 持续交付"}</span>
      </footer>
    </main>
  );
}

/* ─── 工程列表行 ─── */

function ProjectRow({
  project,
  active,
  onClick,
}: {
  project: Project;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] transition-colors ${
        active ? "bg-[#722ed1]/15 text-white" : "text-[#cbd5e1] hover:bg-[#1e293b]"
      }`}
      title={project.dir}
    >
      <FolderOpen className={`h-3.5 w-3.5 flex-none ${active ? "text-[#a78bfa]" : "text-[#64748b]"}`} />
      <span className="min-w-0 flex-1 truncate">{project.name}</span>
      <span className="flex-none text-[10px] text-[#475569]">{project.spec_count}</span>
      {active && <Check className="h-3 w-3 flex-none text-[#a78bfa]" />}
    </button>
  );
}

/* ─── 工程卡片（欢迎页） ─── */

function ProjectCard({ project, onOpen }: { project: Project; onOpen: (id: string) => void }) {
  return (
    <button
      onClick={() => onOpen(project.id)}
      className="group flex flex-col rounded-xl border border-[#1e293b] bg-[#111827] p-4 text-left transition-all hover:border-[#722ed1]/60 hover:bg-[#141b2b]"
    >
      <div className="flex items-center gap-2">
        <FolderOpen className="h-4 w-4 flex-none text-[#a78bfa]" />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-white" title={project.name}>
          {project.name}
        </span>
      </div>
      <div className="mt-1 truncate font-mono text-[10.5px] text-[#475569]" title={project.dir}>
        {project.dir}/
      </div>
      <div className="mt-auto flex items-center gap-3 pt-4 text-[11px] text-[#64748b]">
        <span className="flex items-center gap-1">
          <FileText className="h-3 w-3" />
          {project.spec_count}
        </span>
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {relTime(project.mtime)}
        </span>
        <span className="ml-auto">
          <HealthBadge project={project} />
        </span>
      </div>
    </button>
  );
}

/* ─── 工程健康徽标 ─── */

function HealthBadge({ project }: { project: Project }) {
  if (project.spec_count === 0) {
    return (
      <span className="rounded-full border border-[#334155] px-2 py-0.5 text-[10px] text-[#64748b]">
        无规格
      </span>
    );
  }
  const health = project.health;
  if (!health) return null;
  // 全是占位文件（只有新建工程自带的 YAML 模板）→ 中性提示，不吓人
  if (
    health.errors > 0 &&
    health.checked !== undefined &&
    health.checked > 0 &&
    health.stubs === health.checked
  ) {
    return (
      <span className="rounded-full border border-[#334155] px-2 py-0.5 text-[10px] text-[#94a3b8]">
        占位规格
      </span>
    );
  }
  if (health.errors > 0) {
    return (
      <span className="flex items-center gap-1 rounded-full border border-[#ff4d4f]/30 bg-[#ff4d4f]/10 px-2 py-0.5 text-[10px] text-[#fca5a5]">
        <CircleAlert className="h-2.5 w-2.5" />
        {health.errors} 错误
      </span>
    );
  }
  if (health.warnings > 0) {
    return (
      <span className="rounded-full border border-[#fbbf24]/30 bg-[#fbbf24]/10 px-2 py-0.5 text-[10px] text-[#fbbf24]">
        {health.warnings} 建议
      </span>
    );
  }
  return (
    <span className="rounded-full border border-[#10b981]/30 bg-[#10b981]/10 px-2 py-0.5 text-[10px] text-[#6ee7b7]">
      ✓ 健康
    </span>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="text-[11px] uppercase tracking-wider text-[#64748b]">{children}</h2>
  );
}

/* ─── 统计卡小组件 ─── */

function Stat({ label, value, valueClass }: { label: string; value: number; valueClass?: string }) {
  return (
    <div className="flex flex-col items-center">
      <span className={`text-[13px] font-bold ${valueClass ?? "text-[#e2e8f0]"}`}>{value}</span>
      <span className="text-[10px] text-[#64748b]">{label}</span>
    </div>
  );
}

function Divider() {
  return <span className="h-6 w-px bg-[#1e293b]" />;
}

"use client";

/** RealtimeStore: 仪表盘全局实时状态 (Context + reducer 版, 零新依赖).
 *
 * 为什么 Context+reducer 而不是 zustand/redux: 项目除了 lib/sse.ts 之外
 * 没有全局 store；引入新依赖要权衡。本次只 store「仪表盘需要的 5 类聚
 * 合态」: 活跃运行 / 当前 stage / 项目数字徽标 / 新证据数 / 项目 stats
 * 加载状态, 数据量小, Context 完全够。后续若要扩展再加 zustand。
 *
 * 聚合规则:
 *   - activeRuns: 按 runId 维护; pipeline.run_done 时清掉对应 run, 给
 *     每个 active run 维护 currentStageTitle (后端 pipeline.stage_end /
 *     stage_start 推过来)。
 *   - projectStats: 按 projectDir 维护数字徽标 (缺需求数 / 待执行用例
 *     / 证据数), 由各 topic 事件触发增量更新。
 *   - newEvidenceCount: 每次 evidence.file_ready (未来 topic) +1, 用
 *     脉冲动画展示给用户看。
 *   - producedFiles: 按 runId+filePath dedupe, 产出物面板可即时合并到
 *     现有列表。
 *   - projectStatsCache: 全局唯一的 stats fetcher 状态(loading /
 *     loaded / error), Provider 内置副作用(详见 useEffect), 任何组件
 *     读 statsByProject 都拿到同一份缓存(避免多个 fetcher 重复拉取)。
 *
 * 用法:
 *   <RealtimeProvider>...</RealtimeProvider>     -- 仅 dashboard layout 根挂一次
 *   const { activeRuns } = useRealtimeStore();    -- 任何子组件
 */
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import { useRealtimeFeed, type RealtimeFrame } from "./use-realtime-feed";
import { api } from "./api";

export interface ActiveRun {
  run_id: string;
  project_dir: string;
  current_stage_index?: number;
  current_stage_key?: string;
  current_stage_title?: string;
  agent?: string;
  status: "running" | "completed" | "failed" | "cached";
  /** stage_start 事件时间戳(ms) —— 用于阶段耗时倒计时 */
  stage_started_at?: number;
  /** 最近一次 file_produced 的相对路径 —— 详情卡展示当前 step 的产物 */
  current_file_path?: string;
  /** 累计 LLM token (input + output) —— Stage-6 (2026-09-05) */
  total_tokens?: number;
  /** 累计 LLM 调用次数 —— 同上 */
  llm_calls?: number;
  /** 累计 LLM 成本 (USD) —— 同上 */
  llm_cost_usd?: number;
  updated_at: number;
}

export interface ProjectStat {
  project_dir: string;
  /** 缺需求数（红/橙徽标） */
  missing_requirements: number;
  /** 待执行用例数（蓝徽标） */
  pending_tests: number;
  /** 证据总数（含历史） */
  evidence_count: number;
  /** 是否有活跃运行 */
  has_active_run: boolean;
  /** stats 是否正在加载 (loading / loaded / error) */
  load_state?: "loading" | "loaded" | "error";
}

/** 后端「按项目聚合（最新优先）」的会话索引条目。
 *
 * 来源：GET /api/v1/pipeline/status 的 ``projects`` 字段（递归发现 +
 * 同项目多会话取 updated_at 最新一份）。无论会话来自后台(CLI)跑还是 UI
 * 触发跑，只要共享 OSH_HOME 都会被同一份索引聚合 → 前端据此把「最新结果」
 * 关联到对应项目。 */
export interface ProjectIndexEntry {
  project_dir: string;
  project_name: string;
  spec_path?: string | null;
  latest_run_id?: string;
  latest_status?: string | null;
  latest_name?: string | null;
  latest_updated_at?: string | null;
  /** 该项目是否有正在跑的会话（后台运行中） */
  active: boolean;
  runs_count: number;
  statuses: string[];
  /** 最新一份会话的完整 session dict */
  latest: Record<string, any>;
}

interface State {
  activeRuns: Record<string, ActiveRun>;
  statsByProject: Record<string, ProjectStat>;
  /** 按项目聚合的会话索引（最新优先）。后台跑 / UI 触发跑都汇入此处。 */
  projectsByDir: Record<string, ProjectIndexEntry>;
  newEvidenceCount: number;
  producedFilesByRun: Record<string, Set<string>>;
  connected: boolean;
  /** 最近一次轮询时间戳(ms) —— 前端「实时同步中」指示条用，让用户感知页面在自动刷新 */
  last_poll_at: number;
}

type Action =
  | {
      type: "pipeline_stage_start";
      payload: { run_id: string; project_dir: string; step_index: number;
                  step_key: string; step_title: string; agent: string };
    }
  | {
      type: "pipeline_stage_end";
      payload: { run_id: string; project_dir: string; step_index: number;
                  step_key: string; step_title: string; status: string;
                  duration_ms?: number };
    }
  | {
      type: "pipeline_file_produced";
      payload: { run_id: string; project_dir: string; file_path: string;
                  category: string; size_bytes: number };
    }
  | {
      type: "pipeline_run_done";
      payload: { run_id: string; project_dir: string; status: string;
                  summary?: Record<string, unknown> };
    }
  | {
      type: "pipeline_checkpoint";
      payload: { run_id: string; project_dir: string; status: string;
                  progress_pct?: number };
    }
  | {
      // 1s 轮询快照: 把后端 GET /api/v1/pipeline/status 扫到的「正在运行」会话
      // 回填 activeRuns。CLI 启动的 run 不 emit SSE、API 编排器又不 emit step
      // 标题, 轮询是「当前在跑哪一步」最可靠的统一来源。与 SSE 增量字段
      // (total_tokens / llm_calls / current_file_path) 通过合并保留, 互不覆盖。
      type: "pipeline_poll_snapshot";
      payload: { runs: ActiveRun[]; last_poll_at: number };
    }
  | {
      // Stage-6 (2026-09-05): 单次 LLM 调用 token 增量。
      // 与 file_produced 类似 —— 按 run_id 累加 total_tokens / llm_calls / llm_cost_usd。
      type: "pipeline_llm_call";
      payload: { run_id: string; project_dir: string;
                  prompt_tokens: number; completion_tokens: number;
                  cost_usd: number; model: string; provider: string };
    }
  | {
      // Stage-4 (2026-09-05): initialise the per-project stats baseline
      // (missing_requirements / pending_tests / evidence_count). Provider
      // 内置 fetcher 拉完接口后 dispatch 一次; 多个 component 共享同一份。
      type: "set_project_stats";
      payload: { project_dir: string; missing_requirements: number;
                  pending_tests: number; evidence_count: number;
                  has_active_run?: boolean };
    }
  | {
      // Stage-5 (2026-09-05): 标记某 project_dir 的 stats 进入 loading/loaded/
      // error。Provider useEffect 监听 activeRuns → 触发 ensure + loading → fetch
      // → loaded / error。任何 component 看到 load_state 可显示骨架/spinner。
      type: "set_project_stats_state";
      payload: { project_dir: string; load_state: ProjectStat["load_state"] };
    }
  | { type: "set_connected"; connected: boolean }
  | {
      // 1s 轮询：把后端「按项目聚合（最新优先）」的会话索引回填
      // projectsByDir。这是「后台跑 / UI 触发跑 两条路径的数据最终按最新
      // 结果关联到对应项目」的统一入口（不依赖 SSE stats_by_project 事件，
      // CLI 后台跑不会发该事件也能被聚合）。每次轮询都更新 last_poll_at，
      // 供 LiveSyncBar 展示「页面在自动刷新」。
      type: "pipeline_projects_snapshot";
      payload: { projects: ProjectIndexEntry[]; last_poll_at: number };
    };

const emptyStats = (project_dir: string): ProjectStat => ({
  project_dir,
  missing_requirements: 0,
  pending_tests: 0,
  evidence_count: 0,
  has_active_run: false,
  load_state: "loading",
});

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "pipeline_stage_start": {
      const p = action.payload;
      const run: ActiveRun = {
        run_id: p.run_id,
        project_dir: p.project_dir,
        current_stage_index: p.step_index,
        current_stage_key: p.step_key,
        current_stage_title: p.step_title,
        agent: p.agent,
        status: "running",
        // 记录阶段开始时间 —— 详情卡用于阶段耗时倒计时
        stage_started_at: Date.now(),
        updated_at: Date.now(),
      };
      const stats = {
        ...(state.statsByProject[p.project_dir] || emptyStats(p.project_dir)),
        has_active_run: true,
      };
      return {
        ...state,
        activeRuns: { ...state.activeRuns, [p.run_id]: run },
        statsByProject: { ...state.statsByProject, [p.project_dir]: stats },
      };
    }
    case "pipeline_stage_end": {
      const p = action.payload;
      const existing = state.activeRuns[p.run_id];
      if (!existing) {
        // 收到 end 但没收到 start —— 仍然记录, 但 mark 完成态
        return state;
      }
      const updated: ActiveRun = {
        ...existing,
        current_stage_index: p.step_index,
        current_stage_key: p.step_key,
        current_stage_title: p.step_title,
        status: p.status as ActiveRun["status"],
        updated_at: Date.now(),
      };
      return {
        ...state,
        activeRuns: { ...state.activeRuns, [p.run_id]: updated },
      };
    }
    case "pipeline_file_produced": {
      const p = action.payload;
      const set = new Set(state.producedFilesByRun[p.run_id] || []);
      set.add(p.file_path);
      const producedFilesByRun = { ...state.producedFilesByRun, [p.run_id]: set };
      const projStats = state.statsByProject[p.project_dir] || emptyStats(p.project_dir);
      const existingRun = state.activeRuns[p.run_id];
      const updatedRuns = existingRun
        ? {
            ...state.activeRuns,
            [p.run_id]: {
              ...existingRun,
              // 记录最近一次产物路径 —— 详情卡用于「当前 step 产物链接」
              current_file_path: p.file_path,
              updated_at: Date.now(),
            },
          }
        : state.activeRuns;
      return {
        ...state,
        producedFilesByRun,
        activeRuns: updatedRuns,
        statsByProject: {
          ...state.statsByProject,
          [p.project_dir]: {
            ...projStats,
            evidence_count: projStats.evidence_count + 1,
          },
        },
        newEvidenceCount: state.newEvidenceCount + 1,
      };
    }
    case "pipeline_run_done": {
      const p = action.payload;
      const { [p.run_id]: _drop, ...rest } = state.activeRuns;
      void _drop;
      const projStats = state.statsByProject[p.project_dir] || emptyStats(p.project_dir);
      return {
        ...state,
        activeRuns: rest,
        statsByProject: {
          ...state.statsByProject,
          [p.project_dir]: { ...projStats, has_active_run: false },
        },
      };
    }
    case "pipeline_checkpoint": {
      // 增量状态: 把进度百分比同步到 activeRuns (避免后端重复 publish 整棵树)
      const p = action.payload;
      const existing = state.activeRuns[p.run_id];
      if (!existing) return state;
      return {
        ...state,
        activeRuns: {
          ...state.activeRuns,
          [p.run_id]: {
            ...existing,
            status: p.status as ActiveRun["status"],
            updated_at: Date.now(),
          },
        },
      };
    }
    case "pipeline_llm_call": {
      // Stage-6 (2026-09-05): 累计 LLM 调用次数 + token + 成本, 供详情卡
      // 实时显示。run 不在 activeRuns 里时 (罕见的 LLM call 在 run_done
      // 之后) 也累加到 statsByProject (不, 应该是丢——避免污染)。所以仍
      // 要先确认 active run 存在, 否则忽略。
      const p = action.payload;
      const existing = state.activeRuns[p.run_id];
      if (!existing) return state;
      const inc = p.prompt_tokens + p.completion_tokens;
      return {
        ...state,
        activeRuns: {
          ...state.activeRuns,
          [p.run_id]: {
            ...existing,
            total_tokens: (existing.total_tokens ?? 0) + inc,
            llm_calls: (existing.llm_calls ?? 0) + 1,
            llm_cost_usd: (existing.llm_cost_usd ?? 0) + p.cost_usd,
            updated_at: Date.now(),
          },
        },
      };
    }
    case "set_project_stats": {
      // Stage-4 (2026-09-05): 用后端 stats 接口返回的基线值覆盖既有
      // stats 条目。如果该 project_dir 已有 stats 条目, 保留
      // has_active_run 状态(因为 store 可能已经收到 pipeline.stage_start
      // 标记为 true); 仅 missing_requirements / pending_tests /
      // evidence_count 从基线重新填充, evidence_count 已经把本地
      // 增量算进基线里(见 caller 的 fetch-and-merge 逻辑)。
      const p = action.payload;
      const existing = state.statsByProject[p.project_dir];
      const merged: ProjectStat = {
        project_dir: p.project_dir,
        missing_requirements: p.missing_requirements,
        pending_tests: p.pending_tests,
        // 若之前已有增量 evidence_count, 用 max(baseline, 之前的值)
        // —— file_produced 增量不会因 set_project_stats 被"覆盖回去",
        // 但当 baseline 比本地累计大(后端扫到更多历史文件)时仍采纳。
        evidence_count: existing
          ? Math.max(p.evidence_count, existing.evidence_count)
          : p.evidence_count,
        // has_active_run 优先沿用已有值, 否则按 payload 决定。
        has_active_run: existing?.has_active_run ?? (p.has_active_run ?? false),
        load_state: "loaded",
      };
      return {
        ...state,
        statsByProject: {
          ...state.statsByProject,
          [p.project_dir]: merged,
        },
      };
    }
    case "set_project_stats_state": {
      // Stage-5 (2026-09-05): 仅更新 load_state, 数字字段不动
      const p = action.payload;
      const existing = state.statsByProject[p.project_dir] || emptyStats(p.project_dir);
      return {
        ...state,
        statsByProject: {
          ...state.statsByProject,
          [p.project_dir]: { ...existing, load_state: p.load_state },
        },
      };
    }
    case "set_connected":
      return { ...state, connected: action.connected };
    case "pipeline_projects_snapshot": {
      // 按项目目录建索引；last_poll_at 每次轮询都刷新（供 LiveSyncBar）。
      const { projects, last_poll_at } = action.payload;
      const next: Record<string, ProjectIndexEntry> = {};
      for (const p of projects) next[p.project_dir] = p;
      return { ...state, projectsByDir: next, last_poll_at };
    }
    case "pipeline_poll_snapshot": {
      // 1s 轮询快照: 合并「正在运行」会话到 activeRuns。先展开 existing 以
      // 保留 SSE 累加到该 run 的字段(total_tokens / llm_calls / llm_cost_usd /
      // current_file_path), 再展开 polling 提供的字段(current_step/status);
      // stage_started_at 优先沿用 SSE 的时间戳, 否则用轮询首次发现时间(耗时倒计时)。
      const { runs, last_poll_at } = action.payload;
      const next = { ...state.activeRuns };
      for (const r of runs) {
        const existing = next[r.run_id];
        next[r.run_id] = {
          ...existing,
          ...r,
          stage_started_at: existing?.stage_started_at ?? r.stage_started_at,
          updated_at: Date.now(),
        };
      }
      return { ...state, activeRuns: next, last_poll_at };
    }
    default:
      return state;
  }
}

const initialState: State = {
  activeRuns: {},
  statsByProject: {},
  projectsByDir: {},
  newEvidenceCount: 0,
  producedFilesByRun: {},
  connected: false,
  last_poll_at: 0,
};

// ── Context + Provider ─────────────────────────────────────────────────────

const RealtimeCtx = createContext<State | null>(null);
const RealtimeDispatchCtx = createContext<React.Dispatch<Action> | null>(null);

export interface RealtimeProviderProps {
  /** 要订阅的 topic 白名单；不传则订阅全部 (默认 `["pipeline"]`) */
  topics?: string[];
  children: ReactNode;
}

export function RealtimeProvider({
  topics = ["pipeline"],
  children,
}: RealtimeProviderProps) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── 1s 轮询「正在运行」的 pipeline (2026-09-13) ─────────────────────────
  // SSE 只覆盖 API 编排器且不明确发 step 标题; CLI 启动的 run 完全不 emit
  // 事件。这里每 1s 拉一次 GET /api/v1/pipeline/status(后端扫 session.json),
  // 把 running 会话回填 activeRuns, 让「阶段看板 / 活跃项目卡 / 实时同步条」
  // 真正活起来。SSE 的 llm_call/file_produced 等增量字段在 reducer 合并时保留。
  const stepDefsRef = useRef<any>(null);
  const prevPollIdsRef = useRef<Set<string>>(new Set());
  const firstSeenRef = useRef<Map<string, number>>(new Map());

  // ── 全局 stats fetcher (Stage-5) ──────────────────────────────────────
  // 共享缓存: loadedRef (已成功加载) + inFlightRef (在飞请求) 双重去重,
  // 任何 component 触发新 project_dir 时只会发起一次 HTTP 请求。所有
  // 数字徽标(ActiveProjectsCard + sidebar)都从 statsByProject 读同一份。
  const loadedRef = useRef<Set<string>>(new Set());
  const inFlightRef = useRef<Set<string>>(new Set());

  // 接 SSE 后每隔 N 秒 ping 一次心跳；用 onError 标记 connected 状态。
  const onEvent = useCallback((frame: RealtimeFrame) => {
    const t = frame.topic;
    const p = frame.payload as Record<string, any>;
    if (t === "pipeline") {
      const kind = p.kind as string;
      if (kind === "stage_start") {
        dispatchRef.current({
          type: "pipeline_stage_start",
          payload: {
            run_id: p.run_id || "",
            project_dir: p.project_dir || "",
            step_index: p.step_index ?? -1,
            step_key: p.step_key || "",
            step_title: p.step_title || "",
            agent: p.agent || "",
          },
        });
      } else if (kind === "stage_end") {
        dispatchRef.current({
          type: "pipeline_stage_end",
          payload: {
            run_id: p.run_id || "",
            project_dir: p.project_dir || "",
            step_index: p.step_index ?? -1,
            step_key: p.step_key || "",
            step_title: p.step_title || "",
            status: p.status || "completed",
            duration_ms: p.duration_ms,
          },
        });
      } else if (kind === "file_produced") {
        dispatchRef.current({
          type: "pipeline_file_produced",
          payload: {
            run_id: p.run_id || "",
            project_dir: p.project_dir || "",
            file_path: p.file_path || "",
            category: p.category || "",
            size_bytes: p.size_bytes ?? 0,
          },
        });
      } else if (kind === "run_done") {
        dispatchRef.current({
          type: "pipeline_run_done",
          payload: {
            run_id: p.run_id || "",
            project_dir: p.project_dir || "",
            status: p.status || "completed",
            summary: p.summary,
          },
        });
      } else if (kind === "checkpoint") {
        dispatchRef.current({
          type: "pipeline_checkpoint",
          payload: {
            run_id: p.run_id || "",
            project_dir: p.project_dir || "",
            status: p.status || "running",
            progress_pct: p.progress_pct,
          },
        });
      } else if (kind === "llm_call") {
        dispatchRef.current({
          type: "pipeline_llm_call",
          payload: {
            run_id: p.run_id || "",
            project_dir: p.project_dir || "",
            prompt_tokens: p.prompt_tokens ?? 0,
            completion_tokens: p.completion_tokens ?? 0,
            cost_usd: p.cost_usd ?? 0,
            model: p.model || "",
            provider: p.provider || "",
          },
        });
      }
    }
    // 其它 topic (evidence / gap / coverage / misra) 后续按需扩展
  }, []);

  useRealtimeFeed({
    topics,
    onEvent,
    onError: () => {
      dispatchRef.current({ type: "set_connected", connected: false });
    },
  });

  // ── 1s 轮询: 把「正在运行」的 pipeline 会话回填 activeRuns ────────────
  // 立即跑一次, 之后每 1s 一次; inFlight 防重叠(单次请求 >1s 时跳过下一拍)。
  // 会话从 running 变为终态(或目录消失)时, 从 prevPollIds 摘掉并 dispatch
  // run_done 清掉, 让「后台运行中」指示条与阶段看板正确归零。
  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const tick = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      try {
        const status = (await api.v1.pipeline.status()) as any;
        if (cancelled) return;
        const sessions: any[] = (status && status.sessions) || [];
        if (!stepDefsRef.current) {
          try {
            stepDefsRef.current = await api.v1.pipeline.steps();
          } catch {
            /* 步骤定义拉不到也不阻塞轮询 */
          }
        }
        const defs: any[] = (stepDefsRef.current && stepDefsRef.current.steps) || [];
        // 注意: session.json 的 current_step 是 0-based(对应 self.steps[idx]),
        // 而 /pipeline/steps 接口返回的 index 是 1-based(start=1)。统一成 0-based
        // 建索引, 这样 defMap.get(current_step) 直接命中正确步骤的标题/agent。
        const defMap = new Map<number, any>();
        for (const d of defs) defMap.set(Number(d.index) - 1, d);
        const now = Date.now();
        const incoming: ActiveRun[] = [];
        const incomingIds = new Set<string>();
        for (const s of sessions) {
          const st = (s.status || "").toLowerCase();
          if (st === "completed" || st === "failed" || st === "cached" || st === "error") {
            continue;
          }
          const stepIdx = typeof s.current_step === "number" ? s.current_step : -1;
          const def = defMap.get(stepIdx) || {};
          const runId = s.run_id || s.name || "";
          if (!runId) continue;
          if (!firstSeenRef.current.has(runId)) firstSeenRef.current.set(runId, now);
          // 由 spec_path(…/docs/spec.md) 反推 project_dir(其父目录的父目录)
          let projectDir = "";
          const sp = s.spec_path || "";
          if (sp) {
            const parts = sp.split("/").filter(Boolean);
            if (parts.length >= 2) {
              parts.pop();
              parts.pop();
              projectDir = "/" + parts.join("/");
            }
          }
          incoming.push({
            run_id: runId,
            project_dir: projectDir,
            current_stage_index: stepIdx,
            current_stage_key: def.key || "",
            current_stage_title:
              def.name || (typeof s.current_step_title === "string" ? s.current_step_title : ""),
            agent: def.agent || "",
            status: "running",
            stage_started_at: firstSeenRef.current.get(runId),
            updated_at: now,
          });
          incomingIds.add(runId);
        }
        // 上一拍在跑、这一拍不在了 → 清掉(终态或目录消失)
        for (const id of prevPollIdsRef.current) {
          if (!incomingIds.has(id)) {
            dispatchRef.current({
              type: "pipeline_run_done",
              payload: { run_id: id, project_dir: "", status: "completed" },
            });
            firstSeenRef.current.delete(id);
          }
        }
        prevPollIdsRef.current = incomingIds;
        // 按项目聚合（最新优先）索引：后台跑 / UI 触发跑都汇入此处。
        // 即使没有正在跑的会话也照常回填（含已完成会话的最新结果关联）。
        const projList: ProjectIndexEntry[] = (status && status.projects) || [];
        dispatchRef.current({
          type: "pipeline_projects_snapshot",
          payload: { projects: projList, last_poll_at: now },
        });
        dispatchRef.current({
          type: "pipeline_poll_snapshot",
          payload: { runs: incoming, last_poll_at: now },
        });
      } catch {
        // 后端/网络抖动: 保留上一拍状态, 下一拍重试, 不抛错不打断 UI
      } finally {
        inFlight = false;
      }
    };

    tick();
    const iv = setInterval(tick, 1000);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── stats fetcher 主循环 ──────────────────────────────────────────────
  // 监听 activeRuns, 对每个出现过的 project_dir:
  //   1. basename → project name
  //   2. dispatch loading (skeleton/灰态)
  //   3. fetch GET /api/v1/projects-stats/stats
  //   4. dispatch loaded (数字填入) 或 error
  // 双重去重: loadedRef (成功后再拉不算数, 直到 run_done) + inFlightRef (并
  // 发请求只发一次)。
  useEffect(() => {
    const runs = Object.values(state.activeRuns);
    for (const run of runs) {
      const dir = run.project_dir;
      if (!dir) continue;
      const parts = dir.split(/[/\\]/).filter(Boolean);
      const name = parts[parts.length - 1];
      if (!name) continue;
      // 路径完全相同的 project_dir 已加载过 → 跳过
      const cacheKey = dir;
      if (loadedRef.current.has(cacheKey)) continue;
      if (inFlightRef.current.has(cacheKey)) continue;
      inFlightRef.current.add(cacheKey);
      dispatchRef.current({
        type: "set_project_stats_state",
        payload: { project_dir: dir, load_state: "loading" },
      });
      void (async () => {
        try {
          const stats = await api.v1.projectsStats.get(name);
          loadedRef.current.add(cacheKey);
          dispatchRef.current({
            type: "set_project_stats",
            payload: {
              project_dir: dir,
              missing_requirements: stats.missing_requirements,
              pending_tests: stats.pending_tests,
              evidence_count: stats.evidence_count,
            },
          });
        } catch (_e) {
          dispatchRef.current({
            type: "set_project_stats_state",
            payload: { project_dir: dir, load_state: "error" },
          });
          // 失败也标记 loaded, 避免每个渲染周期都重试 (用户手动刷新页面才再尝试)
          loadedRef.current.add(cacheKey);
        } finally {
          inFlightRef.current.delete(cacheKey);
        }
      })();
    }
  }, [state.activeRuns]);

  // 心跳: connected 初始 true (SSE 已建); 长时间无帧把它置 false
  useEffect(() => {
    if (state.connected) {
      heartbeatRef.current = setInterval(() => {
        // 连上但 idle 过久 (>=45s 无事件) 视为降级.
        // 这里不做精细时间检测，留扩展位。
      }, 45_000);
    }
    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    };
  }, [state.connected]);

  // 初次订阅: 立即认为 connected (EventSource 进 useEffect 即开)
  useEffect(() => {
    dispatchRef.current({ type: "set_connected", connected: true });
  }, []);

  return createElement(
    RealtimeCtx.Provider,
    { value: state },
    createElement(
      RealtimeDispatchCtx.Provider,
      { value: dispatch },
      children,
    ),
  );
}

/** 订阅 store（只读）。 */
export function useRealtimeStore(): State {
  const ctx = useContext(RealtimeCtx);
  if (!ctx) {
    // 没有 Provider 时 fallback 到默认 state（避免组件树多 Provider 重复挂）
    return initialState;
  }
  return ctx;
}

/** 订阅 store + dispatch（仅 Provider 子树内可写）。 */
export function useRealtimeDispatch() {
  const state = useContext(RealtimeCtx);
  const dispatch = useContext(RealtimeDispatchCtx);
  return useMemo(
    () => ({ state: state || initialState, dispatch }),
    [state, dispatch],
  );
}
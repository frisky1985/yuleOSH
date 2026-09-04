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

interface State {
  activeRuns: Record<string, ActiveRun>;
  statsByProject: Record<string, ProjectStat>;
  newEvidenceCount: number;
  producedFilesByRun: Record<string, Set<string>>;
  connected: boolean;
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
  | { type: "set_connected"; connected: boolean };

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
    default:
      return state;
  }
}

const initialState: State = {
  activeRuns: {},
  statsByProject: {},
  newEvidenceCount: 0,
  producedFilesByRun: {},
  connected: false,
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
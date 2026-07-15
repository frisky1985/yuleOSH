/**
 * yuleOSH Unified API Client
 *
 * Centralizes all backend API calls. Handles auth token management,
 * request/response formatting, and 401 auto-redirect.
 */

export const TOKEN_KEY = "yuleosh_token";

// ⚠️  SECURITY NOTE (S-P2-03): Token is stored in localStorage (not httpOnly),
//    meaning any XSS vulnerability can exfiltrate it.
//
//    For production hardening, consider one of:
//    - Use httpOnly session cookies instead of bearer tokens
//    - Implement a BFF (Backend-for-Frontend) proxy that stores the token
//      server-side and issues a short-lived httpOnly cookie to the browser
//    - At minimum, keep token lifetime short and rotate on each page load

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UserInfo {
  user_id: number;
  org_id: number;
  email: string;
  role: string;
  org_name: string;
  org_slug: string;
  projects: ProjectItem[];
}

export interface ProjectItem {
  id: number;
  name: string;
  slug: string;
  description?: string;
  created_at: string;
}

export interface ProjectDetail {
  id: number;
  name: string;
  description: string;
  spec_path: string | null;
  created_at: string;
  updated_at: string;
  pipeline_run_count?: number;
  last_active_at?: string | null;
}

export interface PipelineSession {
  name?: string;
  spec_path?: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  steps?: string[];
  artifacts?: Record<string, unknown>;
  errors?: string[];
}

export interface SigninResult {
  token?: string;
  redirect?: string;
  needs_org?: boolean;
  user_id?: number;
  org_id?: number;
  role?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem(TOKEN_KEY);
  }
  return null;
}

function setToken(token: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(TOKEN_KEY, token);
  }
}

function clearToken() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
  }
}

function redirectToLogin() {
  if (typeof window !== "undefined") {
    clearToken();
    window.location.href = "/login";
  }
}

// ---------------------------------------------------------------------------
// Base request
// ---------------------------------------------------------------------------

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(path, {
    ...options,
    headers,
  });

  // 401 → auto-redirect to login
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("Unauthorized — redirecting to login");
  }

  // Parse response body
  let body: any;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    body = await res.json();
  } else {
    const text = await res.text();
    throw new Error(`Non-JSON response (${res.status}): ${text.slice(0, 200)}`);
  }

  // Check API v1 ok/error envelope
  if (body && body.ok === false) {
    throw new Error(body.error || `API error (${res.status})`);
  }

  return body as T;
}

// ---------------------------------------------------------------------------
// Multi-tenant auth endpoints (under /api/auth/ and /api/org/)
// ---------------------------------------------------------------------------

async function signin(email: string, password: string): Promise<SigninResult> {
  const result = await request<SigninResult>("/api/auth/signin", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return result;
}

async function createOrg(body: {
  org_name: string;
  org_slug: string;
  project_name: string;
  project_slug: string;
  email: string;
  password: string;
}): Promise<{ token?: string; error?: string }> {
  return request("/api/org/create", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function getSession(): Promise<UserInfo> {
  const data = await request<UserInfo>("/api/auth/session", { method: "GET" });
  return data;
}

async function getProjects(): Promise<{ projects: ProjectItem[] }> {
  return request<{ projects: ProjectItem[] }>("/api/project/list", {
    method: "GET",
  });
}

async function createProject(
  name: string,
  slug: string
): Promise<ProjectItem> {
  return request<ProjectItem>("/api/project/create", {
    method: "POST",
    body: JSON.stringify({ name, slug }),
  });
}

async function logout(): Promise<void> {
  await request("/api/auth/logout", { method: "POST" });
  clearToken();
}

// ---------------------------------------------------------------------------
// API v1 endpoints (under /api/v1/)
// ---------------------------------------------------------------------------

async function getV1Health(): Promise<any> {
  const data = await request<any>("/api/v1/health", { method: "GET" });
  // API v1 wraps in {ok, data}
  if (data && data.ok === true) {
    return data.data;
  }
  return data;
}

async function getV1Project(name: string): Promise<ProjectDetail> {
  const data = await request<any>(`/api/v1/project/${encodeURIComponent(name)}`, {
    method: "GET",
  });
  if (data && data.ok === true) {
    return data.data;
  }
  return data;
}

async function getV1Projects(): Promise<{ projects: ProjectDetail[]; count: number }> {
  const data = await request<any>("/api/v1/project", { method: "GET" });
  if (data && data.ok === true) {
    return data.data;
  }
  return data;
}

async function createV1Project(name: string, description?: string): Promise<ProjectDetail> {
  const data = await request<any>("/api/v1/project", {
    method: "POST",
    body: JSON.stringify({ name, description: description || "" }),
  });
  if (data && data.ok === true) {
    return data.data;
  }
  return data;
}

async function getPipelineStatus(): Promise<{ sessions: PipelineSession[]; count: number }> {
  const data = await request<any>("/api/v1/pipeline/status", { method: "GET" });
  if (data && data.ok === true) {
    return data.data;
  }
  return data;
}

async function getV1Stats(): Promise<any> {
  const data = await request<any>("/api/v1/project/stats", { method: "GET" });
  if (data && data.ok === true) {
    return data.data;
  }
  return data;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const api = {
  auth: {
    signin,
    createOrg,
    session: getSession,
    logout,
  },
  projects: {
    list: getProjects,
    create: createProject,
  },
  v1: {
    health: getV1Health,
    projects: {
      list: getV1Projects,
      get: getV1Project,
      create: createV1Project,
    },
    pipeline: {
      status: getPipelineStatus,
    },
    stats: getV1Stats,
  },
};

// ───────────────────────────────────────────────────────────────────────────
// Dashboard API endpoints (under /api/v1/dashboard/)
// ───────────────────────────────────────────────────────────────────────────

interface DashboardProject {
  id: string;
  name: string;
  slug: string;
  description: string;
  last_updated: string;
  swe_completed_count: number;
  swe_total: number;
}

interface DashboardProjectsResponse {
  projects: DashboardProject[];
  count: number;
  note: string | null;
}

interface SWEStatus {
  name: string;
  short: string;
  status: "completed" | "partial" | "not_started";
  label: string;
  color: string;
  details_url: string;
  description: string;
  last_updated: string;
}

interface SWEStatusResponse {
  swe: Record<string, SWEStatus>;
  overall_pct: number;
  completed_count: number;
  total_count: number;
  note: string | null;
}

interface GapItem {
  id: string;
  swe_area: string;
  description: string;
  severity: "critical" | "major" | "minor";
  status: string;
  suggestion: string;
}

interface GapSummary {
  total: number;
  critical: number;
  major: number;
  minor: number;
}

interface GapAnalysisResponse {
  items: GapItem[];
  summary: GapSummary;
  page: number;
  limit: number;
  has_more: boolean;
  total_items: number;
  note: string | null;
}

interface EvidenceTask {
  task_id: string;
  project_id: string;
  status: string;
  progress_pct: number;
  started_at: string;
  download_url: string | null;
  valid: boolean;
  error: string | null;
  note?: string;
}

interface CoverageModule {
  name: string;
  line_pct: number;
  branch_pct: number;
}

interface CoverageTrendPoint {
  date: string;
  line_pct: number;
}

interface CoverageResponse {
  line_pct: number;
  branch_pct: number;
  function_pct: number;
  trend: CoverageTrendPoint[];
  modules: CoverageModule[];
  note: string | null;
  display_mode?: string;
}

async function getDashboardProjects(): Promise<DashboardProjectsResponse> {
  const data = await request<any>("/api/v1/dashboard/projects", { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

async function getSWEStatus(projectId?: string): Promise<SWEStatusResponse> {
  const path = projectId
    ? `/api/v1/dashboard/swe-status?project_id=${encodeURIComponent(projectId)}`
    : "/api/v1/dashboard/swe-status";
  const data = await request<any>(path, { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

async function getGapAnalysis(params?: {
  projectId?: string;
  page?: number;
  limit?: number;
  severity?: string;
}): Promise<GapAnalysisResponse> {
  const sp = new URLSearchParams();
  if (params?.projectId) sp.set("project_id", params.projectId);
  if (params?.page) sp.set("page", String(params.page));
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.severity) sp.set("severity", params.severity);
  const qs = sp.toString();
  const path = qs ? `/api/v1/dashboard/gap-analysis?${qs}` : "/api/v1/dashboard/gap-analysis";
  const data = await request<any>(path, { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

async function generateEvidence(projectId?: string): Promise<{ task_id: string; status: string }> {
  const data = await request<any>("/api/v1/dashboard/evidence/generate", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId || "default" }),
  });
  if (data && data.ok === true) return data.data;
  return data;
}

async function getEvidenceStatus(taskId: string): Promise<EvidenceTask> {
  const data = await request<any>(
    `/api/v1/dashboard/evidence/status?task_id=${encodeURIComponent(taskId)}`,
    { method: "GET" }
  );
  if (data && data.ok === true) return data.data;
  return data;
}

async function getCoverage(projectId?: string): Promise<CoverageResponse> {
  const path = projectId
    ? `/api/v1/dashboard/coverage?project_id=${encodeURIComponent(projectId)}`
    : "/api/v1/dashboard/coverage";
  const data = await request<any>(path, { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

// ───────────────────────────────────────────────────────────────────────────
// KB (Knowledge Base) API endpoints (under /api/v1/kb/)
// ───────────────────────────────────────────────────────────────────────────

interface KbArticle {
  id: number;
  title: string;
  content: string;
  source: string;
  source_ref: string;
  tags: string;
  created_at: string | null;
  updated_at: string | null;
}

interface KbArticlesResponse {
  items: KbArticle[];
  total: number;
  limit: number;
  offset: number;
}

interface FmeaEntry {
  id: number;
  item: string;
  failure_mode: string;
  effect: string;
  cause: string;
  severity: number;
  occurence: number;
  detection: number;
  rpn: number;
  recommendation: string;
  created_at: string | null;
}

interface FmeaResponse {
  items: FmeaEntry[];
  total: number;
  limit: number;
  offset: number;
}

async function getKBArticles(params?: {
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<KbArticlesResponse> {
  const sp = new URLSearchParams();
  if (params?.search) sp.set("search", params.search);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/api/v1/kb/articles?${qs}` : "/api/v1/kb/articles";
  const data = await request<any>(path, { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

async function getKBArticle(id: number): Promise<KbArticle> {
  const data = await request<any>(`/api/v1/kb/articles/${id}`, { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

async function getFMEAEntries(params?: {
  sort_by?: string;
  sort_desc?: boolean;
  limit?: number;
  offset?: number;
}): Promise<FmeaResponse> {
  const sp = new URLSearchParams();
  if (params?.sort_by) sp.set("sort_by", params.sort_by);
  if (params?.sort_desc !== undefined) sp.set("sort_desc", String(params.sort_desc));
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/api/v1/kb/fmea?${qs}` : "/api/v1/kb/fmea";
  const data = await request<any>(path, { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

// ───────────────────────────────────────────────────────────────────────────
// MISRA Dashboard endpoint (under /api/v1/dashboard/misra-trend)
// ───────────────────────────────────────────────────────────────────────────

interface MisraTrendPoint {
  week: string;
  violations: number;
  required: number;
  advisory: number;
}

interface MisraDistribution {
  required: number;
  advisory: number;
}

interface MisraViolationItem {
  rule_id: string;
  category: string;
  file: string;
  line: number;
  message: string;
  severity: string;
}

interface MisraTrendResponse {
  weekly_trend: MisraTrendPoint[];
  distribution: MisraDistribution;
  recent_violations: MisraViolationItem[];
  note: string | null;
}

async function getMISRATrend(projectId?: string): Promise<MisraTrendResponse> {
  const path = projectId
    ? `/api/v1/dashboard/misra-trend?project_id=${encodeURIComponent(projectId)}`
    : "/api/v1/dashboard/misra-trend";
  const data = await request<any>(path, { method: "GET" });
  if (data && data.ok === true) return data.data;
  return data;
}

export {
  getToken,
  setToken,
  clearToken,
  redirectToLogin,
  // Dashboard
  getDashboardProjects,
  getSWEStatus,
  getGapAnalysis,
  generateEvidence,
  getEvidenceStatus,
  getCoverage,
  // KB
  getKBArticles,
  getKBArticle,
  getFMEAEntries,
  // MISRA
  getMISRATrend,
};
export type {
  DashboardProject,
  DashboardProjectsResponse,
  SWEStatus,
  SWEStatusResponse,
  GapItem,
  GapSummary,
  GapAnalysisResponse,
  EvidenceTask,
  CoverageResponse,
  CoverageModule,
  CoverageTrendPoint,
  // KB
  KbArticle,
  KbArticlesResponse,
  FmeaEntry,
  FmeaResponse,
  // MISRA
  MisraTrendPoint,
  MisraDistribution,
  MisraViolationItem,
  MisraTrendResponse,
};

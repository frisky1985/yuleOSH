/**
 * yuleOSH Unified API Client
 *
 * Centralizes all backend API calls. Handles auth token management,
 * request/response formatting, and 401 auto-redirect.
 */

export const TOKEN_KEY = "yuleosh_token";

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

export { getToken, setToken, clearToken, redirectToLogin };

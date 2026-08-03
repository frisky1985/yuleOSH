/**
 * Unit tests for src/lib/api.ts
 * Mocks global fetch to test all API client functions.
 *
 * T1 (v3.9.0): the client is cookie-mode — no localStorage JWT, no manual
 * Authorization header; 401 triggers one silent refresh + replay.
 */

import {
  api,
  getToken,
  setToken,
  clearToken,
  type SigninResult,
  type UserInfo,
} from "@/lib/api";

const TEST_TOKEN = "test-jwt-token";

beforeEach(() => {
  jest.restoreAllMocks();
  clearToken();
});

function jsonResponse(status: number, body: unknown, headers?: Record<string, string>) {
  return {
    status,
    headers: { get: (n: string) => (headers ? headers[n] : "application/json") ?? "application/json" },
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  };
}

// ---------------------------------------------------------------------------
// Token helpers (memory-only)
// ---------------------------------------------------------------------------

describe("token helpers (memory-only, T1)", () => {
  it("returns null when no token is stored", () => {
    expect(getToken()).toBeNull();
  });

  it("stores and retrieves token in memory (no localStorage)", () => {
    setToken(TEST_TOKEN);
    expect(getToken()).toBe(TEST_TOKEN);
    // Must NOT touch localStorage at all (SHALL-T1.11)
    expect(localStorage.getItem("yuleosh_token")).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it("clears token", () => {
    setToken(TEST_TOKEN);
    clearToken();
    expect(getToken()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

describe("api.auth.signin", () => {
  it("sends POST to /api/auth/signin without Authorization header", async () => {
    const mockResult: SigninResult = { token: TEST_TOKEN };
    global.fetch = jest.fn().mockResolvedValue(jsonResponse(200, mockResult));

    const result = await api.auth.signin("alice@test.com", "secret123");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/auth/signin",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "alice@test.com", password: "secret123" }),
        credentials: "same-origin",
      })
    );
    const headers = (global.fetch as jest.Mock).mock.calls[0][1].headers;
    expect(headers["Authorization"]).toBeUndefined();
    expect(result.token).toBe(TEST_TOKEN);
  });

  it("never sends an Authorization header on data requests", async () => {
    global.fetch = jest.fn().mockResolvedValue(jsonResponse(200, {}));

    await api.auth.session();
    await api.v1.health();

    for (const call of (global.fetch as jest.Mock).mock.calls) {
      expect(call[1].headers["Authorization"]).toBeUndefined();
    }
  });

  it("throws on 401 for signin WITHOUT attempting refresh", async () => {
    // signin is in NO_REFRESH_PATHS — a failed login is not a renewal case
    const fetchMock = jest
      .fn()
      .mockResolvedValue(jsonResponse(401, { error: "Invalid email or password" }));
    global.fetch = fetchMock;

    await expect(api.auth.signin("bad@test.com", "wrong")).rejects.toThrow(
      "Unauthorized"
    );
    // only the signin call — no refresh call
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/signin");
  });

  it("throws on API error envelope (ok: false)", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      jsonResponse(400, { ok: false, error: "Invalid credentials" })
    );

    await expect(api.auth.signin("bad@test.com", "wrong")).rejects.toThrow(
      "Invalid credentials"
    );
  });

  it("throws on non-JSON response", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      status: 500,
      headers: { get: () => "text/plain" },
      text: () => Promise.resolve("Internal Server Error"),
    });

    await expect(api.auth.signin("x@y.com", "pwd")).rejects.toThrow(
      "Non-JSON response"
    );
  });
});

describe("401 → silent refresh → replay (T1.5)", () => {
  it("replays the original request once after a successful refresh", async () => {
    let calls = 0;
    global.fetch = jest.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === "/api/auth/refresh") {
        return Promise.resolve(jsonResponse(200, { ok: true }));
      }
      calls += 1;
      if (calls === 1) {
        return Promise.resolve(jsonResponse(401, {}));
      }
      return Promise.resolve(jsonResponse(200, { user_id: 1, email: "a@t.com" }));
    });

    const result = await api.auth.session();

    expect(result).toEqual({ user_id: 1, email: "a@t.com" });
    expect(calls).toBe(2); // original + replay
    const refreshCalls = (global.fetch as jest.Mock).mock.calls.filter(
      (c) => c[0] === "/api/auth/refresh"
    );
    expect(refreshCalls).toHaveLength(1);
    // the original request was replayed once (session called twice total)
    const sessionCalls = (global.fetch as jest.Mock).mock.calls.filter(
      (c) => c[0] === "/api/auth/session"
    );
    expect(sessionCalls).toHaveLength(2);
    expect(sessionCalls[1][1]).toMatchObject({ credentials: "same-origin" });
  });

  it("single-flights concurrent 401s into one refresh", async () => {
    let refreshCount = 0;
    global.fetch = jest.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === "/api/auth/refresh") {
        refreshCount += 1;
        return new Promise((resolve) =>
          setTimeout(() => resolve(jsonResponse(200, { ok: true })), 10)
        );
      }
      return Promise.resolve(jsonResponse(401, {}));
    });

    // both requests 401 → share one refresh → replay still 401 → reject
    const [r1, r2] = await Promise.allSettled([api.v1.health(), api.v1.health()]);
    expect(refreshCount).toBe(1);
    expect(r1.status).toBe("rejected");
    expect(r2.status).toBe("rejected");
  });

  it("redirects to login when refresh fails", async () => {
    // jsdom logs "Not implemented: navigation" when redirectToLogin sets
    // window.location.href — harmless (matches pre-T1 behavior); we assert
    // the rejection and that the refresh endpoint was attempted.
    global.fetch = jest.fn().mockImplementation((url: string) => {
      if (url === "/api/auth/refresh") {
        return Promise.resolve(jsonResponse(401, { error: "expired" }));
      }
      return Promise.resolve(jsonResponse(401, {}));
    });

    await expect(api.auth.session()).rejects.toThrow("Unauthorized");
    const refreshCalls = (global.fetch as jest.Mock).mock.calls.filter(
      (c) => c[0] === "/api/auth/refresh"
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it("does not replay when refresh succeeds but replay still 401", async () => {
    global.fetch = jest.fn().mockImplementation((url: string) => {
      if (url === "/api/auth/refresh") {
        return Promise.resolve(jsonResponse(200, { ok: true }));
      }
      return Promise.resolve(jsonResponse(401, {}));
    });

    await expect(api.auth.session()).rejects.toThrow("Unauthorized");
    // exactly one refresh attempt
    const refreshCalls = (global.fetch as jest.Mock).mock.calls.filter(
      (c) => c[0] === "/api/auth/refresh"
    );
    expect(refreshCalls).toHaveLength(1);
  });
});

describe("api.auth.createOrg", () => {
  it("creates an org without Authorization header (cookie mode)", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      jsonResponse(200, { token: TEST_TOKEN })
    );

    const result = await api.auth.createOrg({
      org_name: "TestOrg",
      org_slug: "test-org",
      project_name: "Proj",
      project_slug: "proj",
      email: "a@b.com",
      password: "pw",
    });

    expect(result.token).toBe(TEST_TOKEN);
    const headers = (global.fetch as jest.Mock).mock.calls[0][1].headers;
    expect(headers["Authorization"]).toBeUndefined();
  });
});

describe("api.v1.health", () => {
  it("unwraps {ok, data} envelope for v1 health", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      jsonResponse(200, { ok: true, data: { status: "ok" } })
    );

    const result = await api.v1.health();
    expect(result).toEqual({ status: "ok" });
  });
});

describe("api.auth.logout", () => {
  it("posts to logout (cookies cleared server-side)", async () => {
    global.fetch = jest.fn().mockResolvedValue(jsonResponse(200, {}));

    await api.auth.logout();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/auth/logout",
      expect.objectContaining({ method: "POST", credentials: "same-origin" })
    );
  });
});

// Re-export type check (compilation only)
export type { SigninResult, UserInfo };

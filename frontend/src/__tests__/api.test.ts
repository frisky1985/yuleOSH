/**
 * Unit tests for src/lib/api.ts
 * Mocks global fetch to test all API client functions.
 */

import {
  api,
  getToken,
  setToken,
  clearToken,
  TOKEN_KEY,
  type SigninResult,
  type UserInfo,
} from "@/lib/api";

const TEST_TOKEN = "test-jwt-token";
const API_BASE = ""; // paths are relative like /api/auth/signin

beforeEach(() => {
  localStorage.clear();
  jest.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Token helpers
// ---------------------------------------------------------------------------

describe("token helpers", () => {
  it("returns null when no token is stored", () => {
    expect(getToken()).toBeNull();
  });

  it("stores and retrieves token", () => {
    setToken(TEST_TOKEN);
    expect(localStorage.getItem(TOKEN_KEY)).toBe(TEST_TOKEN);
    expect(getToken()).toBe(TEST_TOKEN);
  });

  it("clears token", () => {
    setToken(TEST_TOKEN);
    clearToken();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

describe("api.auth.signin", () => {
  it("sends POST to /api/auth/signin and returns token", async () => {
    const mockResult: SigninResult = { token: TEST_TOKEN };
    global.fetch = jest.fn().mockResolvedValue({
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(mockResult),
    });

    const result = await api.auth.signin("alice@test.com", "secret123");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/auth/signin",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "alice@test.com", password: "secret123" }),
      })
    );
    expect(result.token).toBe(TEST_TOKEN);
  });

  it("includes Bearer token in requests when token is present", async () => {
    setToken(TEST_TOKEN);
    global.fetch = jest.fn().mockResolvedValue({
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({}),
    });

    await api.auth.session();

    const call = (global.fetch as jest.Mock).mock.calls[0];
    const headers = call[1].headers;
    expect(headers["Authorization"]).toBe(`Bearer ${TEST_TOKEN}`);
  });

  it("throws on 401 response and clears token", async () => {
    setToken(TEST_TOKEN);

    global.fetch = jest.fn().mockResolvedValue({
      status: 401,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({}),
    });

    await expect(api.auth.session()).rejects.toThrow("Unauthorized");
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("throws on API error envelope (ok: false)", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      status: 400,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({ ok: false, error: "Invalid credentials" }),
    });

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

describe("api.auth.createOrg", () => {
  it("creates an org and returns token", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({ token: TEST_TOKEN }),
    });

    const result = await api.auth.createOrg({
      org_name: "TestOrg",
      org_slug: "test-org",
      project_name: "Proj",
      project_slug: "proj",
      email: "a@b.com",
      password: "pw",
    });

    expect(result.token).toBe(TEST_TOKEN);
  });
});

describe("api.v1.health", () => {
  it("unwraps {ok, data} envelope for v1 health", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({ ok: true, data: { status: "ok" } }),
    });

    const result = await api.v1.health();
    expect(result).toEqual({ status: "ok" });
  });
});

describe("api.auth.logout", () => {
  it("posts to logout and clears token", async () => {
    setToken(TEST_TOKEN);
    global.fetch = jest.fn().mockResolvedValue({
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({}),
    });

    await api.auth.logout();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

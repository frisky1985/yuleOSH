/**
 * Component tests for src/app/login/page.tsx
 * Tests login form rendering, validation, and submit flow.
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { api, setToken } from "@/lib/api";

// Mock the API module
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: {
    auth: {
      signin: jest.fn(),
      createOrg: jest.fn(),
    },
  },
  setToken: jest.fn(),
  getToken: jest.fn(() => null),
}));

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
  }),
}));

// Mock lucide-react icons with simple SVG-like components
jest.mock("lucide-react", () => {
  const MockIcon = ({ className }: { className?: string }) =>
    React.createElement("svg", { "data-testid": "mock-icon", className });
  return {
    Mail: MockIcon,
    ArrowRight: MockIcon,
    Lock: MockIcon,
    Loader2: MockIcon,
    Eye: MockIcon,
    EyeOff: MockIcon,
    User: MockIcon,
    Building2: MockIcon,
  };
});

import LoginPage from "@/app/login/page";

// ---------------------------------------------------------------------------

const mockedSignin = api.auth.signin as jest.Mock;
const mockedCreateOrg = api.auth.createOrg as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
});

describe("LoginPage rendering", () => {
  it("renders login form by default with email and password fields", () => {
    render(React.createElement(LoginPage));

    // Verify the card title (not the button text)
    // The card title is the first element with text "登录"; we use getAllByText
    const titles = screen.getAllByText("登录");
    expect(titles.length).toBeGreaterThanOrEqual(1);

    // Verify the description is present
    expect(screen.getByText("使用邮箱或 GitHub 账号登录")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("输入密码")).toBeInTheDocument();
  });

  it("renders register form when toggle is clicked", async () => {
    render(React.createElement(LoginPage));

    const toggleBtn = screen.getByText("立即注册");
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      // Verify register mode title and fields
      expect(screen.getByText("创建你的账号并开始使用")).toBeInTheDocument();
      expect(screen.getByPlaceholderText("你的姓名")).toBeInTheDocument();
      expect(screen.getByPlaceholderText("至少8个字符")).toBeInTheDocument();
    });
  });
});

describe("LoginPage validation", () => {
  it("shows error when login form is submitted with empty fields", async () => {
    render(React.createElement(LoginPage));

    // Find the submit button (not the GitHub OAuth button)
    // "GitHub OAuth 登录" doesn't match /^登录$/
    const submitBtn = screen.getByRole("button", { name: /^登录$/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("请填写邮箱和密码")).toBeInTheDocument();
    });
  });

  it("shows error when register form has short password", async () => {
    render(React.createElement(LoginPage));

    // Switch to register mode
    fireEvent.click(screen.getByText("立即注册"));

    await waitFor(() => {
      expect(screen.getByText("创建你的账号并开始使用")).toBeInTheDocument();
    });

    // Fill fields with short password
    const nameInput = screen.getByPlaceholderText("你的姓名");
    const emailInput = screen.getByPlaceholderText("you@example.com");
    const passwordInput = screen.getByPlaceholderText("至少8个字符");

    fireEvent.change(nameInput, { target: { value: "Alice" } });
    fireEvent.change(emailInput, { target: { value: "alice@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "123" } });

    // Find the submit button in register mode
    const submitBtn = screen.getByRole("button", { name: /^注册$/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("密码至少需要8个字符")).toBeInTheDocument();
    });
  });
});

describe("LoginPage submit flow", () => {
  it("calls signin and redirects on successful login", async () => {
    const mockPush = jest.fn();
    jest.spyOn(require("next/navigation"), "useRouter").mockReturnValue({
      push: mockPush,
    });

    mockedSignin.mockResolvedValue({
      token: "test-token",
    });

    render(React.createElement(LoginPage));

    const emailInput = screen.getByPlaceholderText("you@example.com");
    const passwordInput = screen.getByPlaceholderText("输入密码");

    fireEvent.change(emailInput, { target: { value: "alice@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "secret123" } });

    const submitBtn = screen.getByRole("button", { name: /^登录$/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockedSignin).toHaveBeenCalledWith("alice@test.com", "secret123");
      expect(setToken).toHaveBeenCalledWith("test-token");
      expect(mockPush).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("displays API error message on failed login", async () => {
    mockedSignin.mockResolvedValue({
      error: "Invalid email or password",
    });

    render(React.createElement(LoginPage));

    const emailInput = screen.getByPlaceholderText("you@example.com");
    const passwordInput = screen.getByPlaceholderText("输入密码");

    fireEvent.change(emailInput, { target: { value: "bad@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "wrong" } });

    const submitBtn = screen.getByRole("button", { name: /^登录$/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("Invalid email or password")).toBeInTheDocument();
    });
  });

  it("shows loading spinner during form submission", async () => {
    // Never resolve
    mockedSignin.mockImplementation(() => new Promise(() => {}));

    render(React.createElement(LoginPage));

    const emailInput = screen.getByPlaceholderText("you@example.com");
    const passwordInput = screen.getByPlaceholderText("输入密码");

    fireEvent.change(emailInput, { target: { value: "a@b.com" } });
    fireEvent.change(passwordInput, { target: { value: "secret123" } });

    const submitBtn = screen.getByRole("button", { name: /^登录$/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("处理中...")).toBeInTheDocument();
    });
  });

  it("shows error when network request throws", async () => {
    mockedSignin.mockRejectedValue(new Error("网络连接失败"));

    render(React.createElement(LoginPage));

    const emailInput = screen.getByPlaceholderText("you@example.com");
    const passwordInput = screen.getByPlaceholderText("输入密码");

    fireEvent.change(emailInput, { target: { value: "a@b.com" } });
    fireEvent.change(passwordInput, { target: { value: "secret123" } });

    const submitBtn = screen.getByRole("button", { name: /^登录$/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("网络连接失败")).toBeInTheDocument();
    });
  });
});

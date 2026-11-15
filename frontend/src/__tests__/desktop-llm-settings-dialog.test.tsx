/**
 * DesktopLLMSettingsDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载配置并回填服务商 / 模型 / Base URL
 *  - 已保存 Key 只展示掩码，不回显明文
 *  - 保存时提交 provider / model / base_url / api_key，保存后回显生效配置（不关闭）
 *  - 留空 Key 时不提交 api_key（后端保持原值）
 *  - 「清除已保存的 Key」发送 clear_api_key
 *  - 保存失败时展示后端错误且不关闭弹窗
 *  - 「测试连接」成功展示延迟与模型、失败展示后端错误、未保存也可测试
 *  - 连接测试计数回显
 *  - Mock 服务商下禁用 API Key 输入
 */
import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { DesktopLLMSettingsDialog } from "@/components/account/desktop-llm-settings-dialog";

const API_URL = "/api/v1/desktop/settings/llm";

const DEFAULT_MODELS: Record<string, string> = {
  anthropic: "claude-4-sonnet",
  deepseek: "deepseek-v4",
  openai: "gpt-4o",
  mock: "deepseek-v4",
};

interface ConfigOverrides {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key_set?: boolean;
  api_key_masked?: string;
  api_key_source?: "settings" | "env" | "";
  effective?: Record<string, unknown>;
  stats?: Record<string, unknown>;
}

function config(over: ConfigOverrides = {}) {
  const provider = over.provider ?? "deepseek";
  const model = over.model ?? "";
  const baseUrl = over.base_url ?? "";
  return {
    ok: true,
    provider,
    model,
    base_url: baseUrl,
    default_model: DEFAULT_MODELS[provider] ?? "",
    default_models: DEFAULT_MODELS,
    providers: ["deepseek", "openai", "anthropic", "mock"],
    api_key_set: over.api_key_set ?? false,
    api_key_masked: over.api_key_masked ?? "",
    api_key_source: over.api_key_source ?? "",
    effective: over.effective ?? {
      provider,
      model: model || DEFAULT_MODELS[provider] || "",
      model_is_default: !model,
      base_url: baseUrl || "https://api.deepseek.com",
      base_url_is_default: !baseUrl,
      api_key_set: over.api_key_set ?? false,
      api_key_source: over.api_key_source ?? "",
    },
    stats: over.stats ?? {
      success: 0,
      failure: 0,
      last_tested_at: "",
      last_latency_ms: null,
      last_ok: false,
      last_error: "",
    },
  };
}

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: async () => body } as Response);
}

const fetchMock = jest.fn();

beforeAll(() => {
  // Base UI Dialog / floating-ui touch these browser APIs in jsdom.
  if (!("ResizeObserver" in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = jest.fn();
});

beforeEach(() => {
  fetchMock.mockReset();
  (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
});

describe("DesktopLLMSettingsDialog", () => {
  it("加载并回填已有配置，Key 只显示掩码", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse(
        config({
          provider: "openai",
          model: "qwen2.5-coder",
          base_url: "http://127.0.0.1:11434/v1",
          api_key_set: true,
          api_key_masked: "••••3456",
          api_key_source: "settings",
        }),
      ),
    );

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);

    expect(await screen.findByDisplayValue("qwen2.5-coder")).toBeInTheDocument();
    expect(screen.getByLabelText("服务商")).toHaveValue("openai");
    expect(screen.getByLabelText("Base URL")).toHaveValue("http://127.0.0.1:11434/v1");

    const keyInput = screen.getByLabelText("API Key") as HTMLInputElement;
    expect(keyInput.value).toBe("");
    expect(keyInput.placeholder).toContain("••••3456");
    expect(keyInput.placeholder).not.toContain("sk-");

    // 当前生效配置回显（模型 / Base URL 来自后端解析结果）。
    const effective = screen.getByTestId("llm-effective-config");
    expect(within(effective).getByText("qwen2.5-coder")).toBeInTheDocument();
    expect(within(effective).getByText("已配置（本机设置）")).toBeInTheDocument();
  });

  it("保存时提交完整配置，保存后回显生效配置且不关闭弹窗", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(config()))
      .mockReturnValueOnce(
        jsonResponse(
          config({
            provider: "openai",
            model: "gpt-4o-mini",
            api_key_set: true,
            api_key_source: "settings",
          }),
        ),
      );
    const onOpenChange = jest.fn();

    render(<DesktopLLMSettingsDialog open onOpenChange={onOpenChange} />);
    await screen.findByPlaceholderText("留空使用默认：deepseek-v4");

    fireEvent.change(screen.getByLabelText("服务商"), { target: { value: "openai" } });
    fireEvent.change(screen.getByLabelText("模型"), { target: { value: "gpt-4o-mini" } });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "sk-new-1234" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));

    expect(await screen.findByTestId("llm-save-notice")).toHaveTextContent("已保存并生效");
    expect(onOpenChange).not.toHaveBeenCalled();

    expect(fetchMock).toHaveBeenLastCalledWith(
      API_URL,
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          provider: "openai",
          model: "gpt-4o-mini",
          base_url: "https://api.openai.com/v1",
          api_key: "sk-new-1234",
        }),
      }),
    );

    const effective = screen.getByTestId("llm-effective-config");
    expect(within(effective).getByText("gpt-4o-mini")).toBeInTheDocument();
    // 保存后清空一次性 Key 输入，避免误重复提交。
    expect((screen.getByLabelText("API Key") as HTMLInputElement).value).toBe("");
  });

  it("Key 留空时不提交 api_key，避免覆盖已保存的 Key", async () => {
    fetchMock
      .mockReturnValueOnce(
        jsonResponse(
          config({ api_key_set: true, api_key_masked: "••••3456", api_key_source: "settings" }),
        ),
      )
      .mockReturnValueOnce(
        jsonResponse(
          config({ api_key_set: true, api_key_masked: "••••3456", api_key_source: "settings" }),
        ),
      );

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);
    await screen.findByPlaceholderText(/••••3456/);

    fireEvent.change(screen.getByLabelText("模型"), { target: { value: "deepseek-v4" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body).not.toHaveProperty("api_key");
    expect(body).not.toHaveProperty("clear_api_key");
  });

  it("清除已保存的 Key 时发送 clear_api_key", async () => {
    fetchMock
      .mockReturnValueOnce(
        jsonResponse(
          config({ api_key_set: true, api_key_masked: "••••3456", api_key_source: "settings" }),
        ),
      )
      .mockReturnValueOnce(jsonResponse(config()));

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "清除已保存的 Key" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.clear_api_key).toBe(true);
  });

  it("保存失败时展示后端错误且不关闭弹窗", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(config()))
      .mockReturnValueOnce(jsonResponse({ ok: false, error: "provider 必须是合法值" }, false));
    const onOpenChange = jest.fn();

    render(<DesktopLLMSettingsDialog open onOpenChange={onOpenChange} />);
    await screen.findByPlaceholderText("留空使用默认：deepseek-v4");

    fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));

    expect(await screen.findByText("provider 必须是合法值")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("测试连接成功时展示延迟与模型，并提交当前表单值", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(config()))
      .mockReturnValueOnce(
        jsonResponse({
          ok: true,
          provider: "openai",
          model: "qwen2.5-coder",
          latency_ms: 42,
          reply: "pong",
          stats: {
            success: 1,
            failure: 0,
            last_tested_at: "2026-11-15T18:20:00",
            last_latency_ms: 42,
            last_ok: true,
            last_error: "",
          },
        }),
      );

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);
    await screen.findByPlaceholderText("留空使用默认：deepseek-v4");

    fireEvent.change(screen.getByLabelText("服务商"), { target: { value: "openai" } });
    fireEvent.change(screen.getByLabelText("模型"), { target: { value: "qwen2.5-coder" } });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "http://127.0.0.1:11434/v1" },
    });
    fireEvent.click(screen.getByTestId("llm-test-button"));

    const result = await screen.findByTestId("llm-test-result");
    expect(result).toHaveTextContent("连接成功");
    expect(result).toHaveTextContent("42 ms");
    expect(result).toHaveTextContent("qwen2.5-coder");

    expect(fetchMock).toHaveBeenLastCalledWith(
      `${API_URL}/test`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          provider: "openai",
          model: "qwen2.5-coder",
          base_url: "http://127.0.0.1:11434/v1",
        }),
      }),
    );

    // 测试计数回显到生效配置面板。
    expect(screen.getByTestId("llm-test-stats")).toHaveTextContent("成功 1");
  });

  it("测试连接失败时展示后端错误信息", async () => {
    fetchMock
      .mockReturnValueOnce(
        jsonResponse(
          config({
            api_key_set: true,
            api_key_masked: "••••3456",
            api_key_source: "settings",
          }),
        ),
      )
      .mockReturnValueOnce(
        jsonResponse({ ok: false, error: "认证失败（401）：API Key 无效或已过期" }, false),
      );

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);
    await screen.findByPlaceholderText(/••••3456/);

    fireEvent.click(screen.getByTestId("llm-test-button"));

    const result = await screen.findByTestId("llm-test-result");
    expect(result).toHaveTextContent("认证失败（401）");
    expect(screen.queryByTestId("llm-save-notice")).not.toBeInTheDocument();
  });

  it("未配置 Key 时测试连接展示缺 Key 提示", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(config({ provider: "openai" })))
      .mockReturnValueOnce(
        jsonResponse({ ok: false, error: "请先填写 API Key，或先在服务商处获取 Key 后再测试" }, false),
      );

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);
    await screen.findByPlaceholderText("留空使用默认：gpt-4o");

    fireEvent.click(screen.getByTestId("llm-test-button"));

    const result = await screen.findByTestId("llm-test-result");
    expect(result).toHaveTextContent("请先填写 API Key");
  });

  it("Mock 服务商下禁用 API Key 输入", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(config({ provider: "mock" })));

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);

    expect(await screen.findByLabelText("API Key")).toBeDisabled();
  });
});

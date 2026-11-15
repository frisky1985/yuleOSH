/**
 * DesktopLLMSettingsDialog 单元测试。
 *
 * 覆盖点：
 *  - 打开时加载配置并回填服务商 / 模型 / Base URL
 *  - 已保存 Key 只展示掩码，不回显明文
 *  - 保存时提交 provider / model / base_url / api_key，成功后关闭
 *  - 留空 Key 时不提交 api_key（后端保持原值）
 *  - 「清除已保存的 Key」发送 clear_api_key
 *  - 保存失败时展示后端错误且不关闭弹窗
 *  - Mock 服务商下禁用 API Key 输入
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DesktopLLMSettingsDialog } from "@/components/account/desktop-llm-settings-dialog";

const API_URL = "/api/v1/desktop/settings/llm";

interface ConfigOverrides {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key_set?: boolean;
  api_key_masked?: string;
  api_key_source?: "settings" | "env" | "";
}

function config(over: ConfigOverrides = {}) {
  return {
    ok: true,
    provider: "deepseek",
    model: "",
    base_url: "",
    default_model: "deepseek-v4",
    default_models: {
      anthropic: "claude-4-sonnet",
      deepseek: "deepseek-v4",
      openai: "gpt-4o",
      mock: "deepseek-v4",
    },
    providers: ["deepseek", "openai", "anthropic", "mock"],
    api_key_set: false,
    api_key_masked: "",
    api_key_source: "",
    ...over,
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
  });

  it("保存时提交完整配置并在成功后关闭", async () => {
    fetchMock
      .mockReturnValueOnce(jsonResponse(config()))
      .mockReturnValueOnce(
        jsonResponse(config({ provider: "openai", model: "gpt-4o-mini", api_key_set: true })),
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

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));

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

  it("Mock 服务商下禁用 API Key 输入", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(config({ provider: "mock" })));

    render(<DesktopLLMSettingsDialog open onOpenChange={jest.fn()} />);

    expect(await screen.findByLabelText("API Key")).toBeDisabled();
  });
});

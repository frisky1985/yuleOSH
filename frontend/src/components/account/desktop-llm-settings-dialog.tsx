"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const API_URL = "/api/v1/desktop/settings/llm";

const PROVIDER_LABELS: Record<string, string> = {
  deepseek: "DeepSeek",
  openai: "OpenAI / 兼容端点",
  anthropic: "Anthropic",
  mock: "Mock（离线演示，无需 Key）",
};

interface LLMEffective {
  provider: string;
  model: string;
  model_is_default: boolean;
  base_url: string;
  base_url_is_default: boolean;
  api_key_set: boolean;
  api_key_source: "settings" | "env" | "";
}

interface LLMStats {
  success: number;
  failure: number;
  last_tested_at: string;
  last_latency_ms: number | null;
  last_ok: boolean;
  last_error: string;
}

interface LLMConfig {
  provider: string;
  model: string;
  base_url: string;
  default_model: string;
  default_models: Record<string, string>;
  providers: string[];
  api_key_set: boolean;
  api_key_masked: string;
  api_key_source: "settings" | "env" | "";
  effective?: LLMEffective;
  stats?: LLMStats;
}

interface TestResult {
  ok: boolean;
  message: string;
}

interface DesktopLLMSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function formatTime(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", { hour12: false });
}

/** 桌面端模型设置：配置本地流水线使用的 provider / model / API Key。
 * 配置写入桌面工作区并即时生效，无需登录云端账号。 */
export function DesktopLLMSettingsDialog({ open, onOpenChange }: DesktopLLMSettingsDialogProps) {
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const loading = open && !config && !error;

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      // 关闭时清空一次性输入，避免下次打开泄漏或误提交上次的 Key。
      setApiKey("");
      setError("");
      setNotice("");
      setTestResult(null);
      setConfig(null);
      setSaving(false);
      setTesting(false);
    }
    onOpenChange(next);
  };

  useEffect(() => {
    if (!open) return;
    let alive = true;
    fetch(API_URL, { credentials: "same-origin" })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || "读取模型设置失败");
        if (!alive) return;
        setConfig(data);
        setProvider(data.provider);
        setModel(data.model || "");
        setBaseUrl(data.base_url || "");
        setError("");
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  const edit = (apply: () => void) => {
    apply();
    setNotice("");
    setTestResult(null);
  };

  const buildPayload = (): Record<string, unknown> => {
    const payload: Record<string, unknown> = {
      provider,
      model: model.trim(),
      base_url: baseUrl.trim(),
    };
    if (apiKey.trim()) payload.api_key = apiKey.trim();
    return payload;
  };

  const submit = async (clearKey = false) => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = buildPayload();
      if (clearKey) payload.clear_api_key = true;
      else if (!payload.api_key) delete payload.api_key;

      const res = await fetch(API_URL, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "保存模型设置失败");
      // 保存后不关闭弹窗：回显当前生效配置，便于确认后再继续操作。
      setConfig(data);
      setProvider(data.provider);
      setModel(data.model || "");
      setBaseUrl(data.base_url || "");
      setApiKey("");
      setTestResult(null);
      setNotice("已保存并生效");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存模型设置失败");
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/test`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (data.stats) {
        setConfig((prev) => (prev ? { ...prev, stats: data.stats } : prev));
      }
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "连接测试失败");
      }
      setTestResult({
        ok: true,
        message: `连接成功 · ${data.latency_ms} ms · ${data.model}`,
      });
    } catch (e) {
      setTestResult({
        ok: false,
        message: e instanceof Error ? e.message : "连接测试失败",
      });
    } finally {
      setTesting(false);
    }
  };

  const defaultModel = config?.default_models?.[provider] || config?.default_model || "";
  const effective = config?.effective;
  const stats = config?.stats;
  const tested = stats ? stats.success + stats.failure : 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent size="md" data-testid="desktop-llm-settings-dialog">
        <DialogHeader>
          <DialogTitle>模型设置</DialogTitle>
          <DialogDescription>
            配置本机流水线使用的大模型。设置仅保存在当前桌面工作区，保存后立即生效。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="py-8 text-center text-sm text-[#64748b]">加载中…</div>
        ) : (
          <div className="flex flex-col gap-4 mt-1">
            {effective && (
              <section
                data-testid="llm-effective-config"
                className="rounded-lg border border-[#1e293b] bg-[#0b1020] px-3 py-2.5"
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-[#94a3b8]">当前生效配置</span>
                  {notice && (
                    <span data-testid="llm-save-notice" className="text-[11px] text-[#10b981]">
                      {notice}
                    </span>
                  )}
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
                  <div className="flex gap-1.5">
                    <dt className="shrink-0 text-[#64748b]">服务商</dt>
                    <dd className="truncate text-[#cbd5e1]">
                      {PROVIDER_LABELS[effective.provider] ?? effective.provider}
                    </dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt className="shrink-0 text-[#64748b]">模型</dt>
                    <dd className="truncate text-[#cbd5e1]">
                      {effective.model || "—"}
                      {effective.model_is_default && (
                        <span className="ml-1 text-[#64748b]">（默认）</span>
                      )}
                    </dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt className="shrink-0 text-[#64748b]">Base URL</dt>
                    <dd className="truncate text-[#cbd5e1]" title={effective.base_url}>
                      {effective.base_url || "—"}
                      {effective.base_url && effective.base_url_is_default && (
                        <span className="ml-1 text-[#64748b]">（默认）</span>
                      )}
                    </dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt className="shrink-0 text-[#64748b]">API Key</dt>
                    <dd className="truncate text-[#cbd5e1]">
                      {effective.provider === "mock"
                        ? "无需配置"
                        : effective.api_key_set
                          ? effective.api_key_source === "env"
                            ? "已配置（环境变量）"
                            : "已配置（本机设置）"
                          : "未配置"}
                    </dd>
                  </div>
                </dl>
                {stats && tested > 0 && (
                  <div data-testid="llm-test-stats" className="mt-2 text-[11px] text-[#64748b]">
                    连接测试 {tested} 次 · 成功 {stats.success} · 失败 {stats.failure}
                    {stats.last_latency_ms != null && (
                      <> · 最近 {stats.last_latency_ms} ms</>
                    )}
                    {stats.last_tested_at && <> · {formatTime(stats.last_tested_at)}</>}
                  </div>
                )}
              </section>
            )}

            <div className="flex flex-col gap-2">
              <Label htmlFor="llm-provider" className="text-xs text-[#94a3b8]">
                服务商
              </Label>
              <select
                id="llm-provider"
                data-slot="select"
                className="h-8 w-full rounded-lg border border-input bg-input/30 px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                value={provider}
                onChange={(e) => edit(() => setProvider(e.target.value))}
              >
                {(config?.providers ?? ["deepseek", "openai", "anthropic", "mock"]).map((p) => (
                  <option key={p} value={p}>
                    {PROVIDER_LABELS[p] ?? p}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="llm-model" className="text-xs text-[#94a3b8]">
                模型
              </Label>
              <Input
                id="llm-model"
                value={model}
                onChange={(e) => edit(() => setModel(e.target.value))}
                placeholder={defaultModel ? `留空使用默认：${defaultModel}` : "例如 deepseek-v4"}
                autoComplete="off"
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="llm-api-key" className="text-xs text-[#94a3b8]">
                API Key
              </Label>
              <Input
                id="llm-api-key"
                type="password"
                value={apiKey}
                onChange={(e) => edit(() => setApiKey(e.target.value))}
                placeholder={
                  config?.api_key_set
                    ? config.api_key_source === "env"
                      ? "已通过环境变量配置，留空保持不变"
                      : `已保存（${config.api_key_masked}），留空保持不变`
                    : provider === "mock"
                      ? "Mock 模式无需 API Key"
                      : "请输入 API Key"
                }
                autoComplete="off"
                disabled={provider === "mock"}
              />
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-[#64748b]">
                  {config?.api_key_set
                    ? config.api_key_source === "env"
                      ? "当前 Key 来自系统环境变量"
                      : "Key 已保存在本机设置文件中"
                    : "Key 仅保存在本机，不会上传"}
                </span>
                {config?.api_key_set && config.api_key_source === "settings" && (
                  <button
                    type="button"
                    onClick={() => void submit(true)}
                    className="text-[11px] text-[#f59e0b] hover:underline"
                  >
                    清除已保存的 Key
                  </button>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="llm-base-url" className="text-xs text-[#94a3b8]">
                Base URL
              </Label>
              <Input
                id="llm-base-url"
                value={baseUrl}
                onChange={(e) => edit(() => setBaseUrl(e.target.value))}
                placeholder={
                  provider === "openai"
                    ? "自建端点示例：http://127.0.0.1:11434/v1"
                    : "留空使用服务商默认地址"
                }
                autoComplete="off"
              />
              <span className="text-[11px] text-[#64748b]">
                OpenAI 兼容端点（如本机 Ollama、vLLM）请选择「OpenAI」并填写此地址。
              </span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void testConnection()}
                disabled={loading || saving || testing}
                data-testid="llm-test-button"
              >
                {testing ? "测试中…" : "测试连接"}
              </Button>
              <span className="text-[11px] text-[#64748b]">使用当前填写的内容测试，无需先保存</span>
            </div>

            {testResult && (
              <div
                data-testid="llm-test-result"
                className={`rounded-lg border px-3 py-2 text-[11px] leading-relaxed ${
                  testResult.ok
                    ? "border-[#065f46] bg-[#052e2b] text-[#34d399]"
                    : "border-[#7f1d1d] bg-[#2a1215] text-[#f87171]"
                }`}
              >
                {testResult.message}
              </div>
            )}

            {error && <div className="text-xs text-[#ef4444]">{error}</div>}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => handleOpenChange(false)}>
            {notice ? "关闭" : "取消"}
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={() => void submit(false)}
            disabled={loading || saving || testing}
          >
            {saving ? "保存中…" : "保存并应用"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

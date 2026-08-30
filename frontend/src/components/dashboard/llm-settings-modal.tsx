"use client";

import { useState, useEffect } from "react";
import { X, Cpu, Loader2 } from "lucide-react";

const PROVIDER_MODELS: Record<string, string[]> = {
  deepseek: ["deepseek-chat", "deepseek-v3", "deepseek-coder"],
  anthropic: ["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
};

const PROVIDER_LABEL: Record<string, string> = {
  deepseek: "DeepSeek",
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI (GPT)",
};

export default function LLMSettingsModal({
  open,
  current,
  onClose,
  onSaved,
}: {
  open: boolean;
  current?: { provider?: string | null; model?: string | null };
  onClose: () => void;
  onSaved: (cfg: { provider?: string | null; model?: string | null }) => void;
}) {
  const [provider, setProvider] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      const p = current?.provider || "";
      const m = current?.model || "";
      setProvider(p);
      setModel(m);
      setErr(null);
    }
  }, [open, current?.provider, current?.model]);

  if (!open) return null;

  const onProviderChange = (p: string) => {
    setProvider(p);
    // Reset model to the provider's first default when switching
    const defaults = PROVIDER_MODELS[p] || [];
    if (!defaults.includes(model)) setModel(defaults[0] || "");
  };

  const handleSave = async () => {
    setSaving(true);
    setErr(null);
    try {
      const { api } = await import("@/lib/api");
      const cfg = await api.v1.org.updateLLMConfig({
        provider: provider || null,
        model: model || null,
      });
      if (cfg && cfg.ok === false) {
        throw new Error(cfg.error || "保存失败");
      }
      const data = cfg?.data ?? cfg ?? { provider, model };
      onSaved({ provider: data.provider ?? provider, model: data.model ?? model });
      onClose();
    } catch (e: any) {
      setErr(e?.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-[#1e293b] bg-[#0f172a] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#1e293b] px-5 py-3.5">
          <div className="flex items-center gap-2 text-[#e2e8f0] font-semibold">
            <Cpu className="w-4 h-4 text-[#1677ff]" />
            模型设置
          </div>
          <button
            onClick={onClose}
            className="text-[#64748b] hover:text-[#e2e8f0] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <p className="text-xs text-[#64748b]">
            为当前租户（组织）选择默认大模型。保存后，本组织内的 LLM/对话调用将优先使用该模型。
          </p>

          <div>
            <label className="block text-xs text-[#94a3b8] mb-1.5">服务商</label>
            <select
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
              className="w-full rounded-md border border-[#1e293b] bg-[#0b1220] px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#1677ff]"
            >
              <option value="">系统默认</option>
              {Object.keys(PROVIDER_MODELS).map((p) => (
                <option key={p} value={p}>
                  {PROVIDER_LABEL[p] || p}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-[#94a3b8] mb-1.5">模型</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={!provider}
              className="w-full rounded-md border border-[#1e293b] bg-[#0b1220] px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#1677ff] disabled:opacity-50"
            >
              <option value="">{provider ? "请选择模型" : "请先选择服务商"}</option>
              {(PROVIDER_MODELS[provider] || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          {err ? (
            <div className="text-xs text-[#ff4d4f]">{err}</div>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-[#1e293b] px-5 py-3.5">
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-sm text-[#94a3b8] hover:bg-[#1e293b] transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-md bg-[#1677ff] px-4 py-1.5 text-sm font-medium text-white hover:bg-[#1677ff]/90 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

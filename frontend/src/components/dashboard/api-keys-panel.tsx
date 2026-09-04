"use client";

/**
 * 加密 API Key 管理面板（SEC-PK）。
 *
 * 行为约束（与后端 /api/v1/secrets 对齐）：
 *  - 列表只显示脱敏元数据（provider / key_name / 时间戳），永不显示明文；
 *  - 新增时明文只在提交瞬间存在于输入框内存，POST 后立即被后端加密，本地不留存；
 *  - 删除即销密（DELETE /api/v1/secrets/{id}）。
 *
 * 该面板为纯 UI，可在 Dialog 内嵌（决策者视图）或直接作为页面内容（工程师视图）。
 */
import { useEffect, useState } from "react";
import { Trash2, Plus, KeyRound, Loader2, ShieldCheck } from "lucide-react";

import { api, type SecretMeta } from "@/lib/api";

const PROVIDERS: { value: string; label: string; defaultKey: string }[] = [
  { value: "deepseek", label: "DeepSeek", defaultKey: "DEEPSEEK_API_KEY" },
  { value: "openai", label: "OpenAI", defaultKey: "OPENAI_API_KEY" },
  { value: "anthropic", label: "Anthropic (Claude)", defaultKey: "ANTHROPIC_API_KEY" },
  { value: "embed", label: "Embed (YULEOSH_EMBED)", defaultKey: "YULEOSH_EMBED_API_KEY" },
];

function providerLabel(p: string) {
  return PROVIDERS.find((x) => x.value === p)?.label ?? p;
}

function ts(v: string | null) {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return v;
  }
}

export default function ApiKeysPanel() {
  const [secrets, setSecrets] = useState<SecretMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [provider, setProvider] = useState("deepseek");
  const [keyName, setKeyName] = useState("DEEPSEEK_API_KEY");
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await api.v1.secrets.list();
      setSecrets(res.secrets || []);
    } catch (e: any) {
      setErr(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onProviderChange = (p: string) => {
    setProvider(p);
    const def = PROVIDERS.find((x) => x.value === p)?.defaultKey;
    if (def) setKeyName(def);
  };

  const onCreate = async () => {
    setSaving(true);
    setSaveErr(null);
    try {
      if (!value.trim()) throw new Error("请填写密钥值");
      if (!keyName.trim()) throw new Error("请填写 key_name");
      await api.v1.secrets.create({ provider, key_name: keyName.trim(), value: value.trim() });
      setValue("");
      setSaveErr(null);
      await load();
    } catch (e: any) {
      setSaveErr(e?.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (id: number) => {
    setBusyId(id);
    try {
      await api.v1.secrets.remove(id);
      setSecrets((s) => s.filter((x) => x.id !== id));
    } catch (e: any) {
      setErr(e?.message || "删除失败");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-lg border border-[#1e293b] bg-[#0b1220] p-4">
        <ShieldCheck className="mt-0.5 w-5 h-5 text-[#10b981] shrink-0" />
        <div className="text-xs text-[#94a3b8] leading-relaxed">
          密钥在后端以 <span className="text-[#e2e8f0]">Fernet（AES-128-CBC + HMAC-SHA256）</span>{" "}
          加密后落库（<span className="text-[#e2e8f0]">provider_secrets</span> 表）。明文仅在提交瞬间存在于内存，
          列表与接口均<span className="text-[#e2e8f0]">绝不回传明文</span>。环境变量中的同名校验优先于保险库。
        </div>
      </div>

      {/* 列表 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-[#e2e8f0]">已存储密钥</h3>
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-[#64748b]" />
          ) : (
            <span className="text-xs text-[#64748b]">{secrets.length} 项</span>
          )}
        </div>

        {err ? <div className="text-xs text-[#ff4d4f] mb-2">{err}</div> : null}

        {!loading && secrets.length === 0 ? (
          <div className="rounded-lg border border-dashed border-[#1e293b] px-4 py-6 text-center text-xs text-[#64748b]">
            暂无加密存储的密钥。可在下方新增。
          </div>
        ) : (
          <ul className="space-y-2">
            {secrets.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between rounded-lg border border-[#1e293b] bg-[#0b1220] px-3 py-2.5"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <KeyRound className="w-3.5 h-3.5 text-[#722ed1] shrink-0" />
                    <span className="text-sm text-[#e2e8f0]">{s.key_name}</span>
                    <span className="rounded-full border border-[#1e293b] px-1.5 py-0.5 text-[10px] text-[#94a3b8]">
                      {providerLabel(s.provider)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-[#64748b]">
                    创建 {ts(s.created_at)} · 上次使用 {ts(s.last_used_at)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onDelete(s.id)}
                  disabled={busyId === s.id}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[#94a3b8] hover:bg-[#ff4d4f]/10 hover:text-[#ff4d4f] transition-colors disabled:opacity-50"
                >
                  {busyId === s.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 新增 */}
      <div className="rounded-lg border border-[#1e293b] bg-[#0b1220] p-4 space-y-3">
        <h3 className="text-sm font-medium text-[#e2e8f0]">新增密钥</h3>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs text-[#94a3b8] mb-1.5">服务商</label>
            <select
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
              className="w-full rounded-md border border-[#1e293b] bg-[#0a0e17] px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#1677ff]"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#94a3b8] mb-1.5">key_name</label>
            <input
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="DEEPSEEK_API_KEY"
              className="w-full rounded-md border border-[#1e293b] bg-[#0a0e17] px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#1677ff]"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-[#94a3b8] mb-1.5">密钥值（明文仅在提交瞬间存在，不回显）</label>
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="sk-..."
            autoComplete="new-password"
            className="w-full rounded-md border border-[#1e293b] bg-[#0a0e17] px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#1677ff]"
          />
        </div>

        {saveErr ? <div className="text-xs text-[#ff4d4f]">{saveErr}</div> : null}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={onCreate}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-md bg-[#1677ff] px-4 py-1.5 text-sm font-medium text-white hover:bg-[#1677ff]/90 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            加密保存
          </button>
        </div>
      </div>
    </div>
  );
}

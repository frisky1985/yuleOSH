"use client";

import ApiKeysPanel from "@/components/dashboard/api-keys-panel";

export default function ApiKeysPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-5">
        <h1 className="text-lg font-semibold text-[#e2e8f0]">API 密钥</h1>
        <p className="mt-1 text-xs text-[#64748b]">
          加密存储 LLM provider 密钥（DeepSeek / OpenAI / Anthropic / Embed）。密钥加密后落库，明文不回显。
        </p>
      </div>
      <ApiKeysPanel />
    </div>
  );
}

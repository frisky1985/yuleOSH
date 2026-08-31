"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Archive,
  Download,
  FileText,
  FolderOpen,
  Loader2,
  RefreshCw,
} from "lucide-react";
// 导航（顶栏/左栏）由 dashboard/layout 统一渲染，页面只提供内容
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface EvidenceFile {
  name: string;
  size: number;
  mtime: number;
  type: string;
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = res.headers.get("content-type") || "";
  let body: unknown = null;
  if (contentType.includes("application/json")) {
    body = await res.json();
  } else {
    const text = await res.text();
    throw new Error(`Non-JSON response (${res.status}): ${text.slice(0, 200)}`);
  }
  const record = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  if (record.ok === false) {
    throw new Error(typeof record.error === "string" ? record.error : `API error (${res.status})`);
  }
  const payload = record.data !== undefined ? record.data : body;
  return payload as T;
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function fmtTime(t: number): string {
  try {
    return new Date(t * 1000).toLocaleString("zh-CN");
  } catch {
    return "—";
  }
}

export default function EvidencePage() {
  const [files, setFiles] = useState<EvidenceFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ files: EvidenceFile[]; count: number }>(
        "/api/v1/evidence/files",
      );
      setFiles(data.files || []);
    } catch (e: any) {
      setError(e?.message || "加载证据文件失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      await apiFetch("/api/v1/evidence/generate", {
        method: "POST",
        body: JSON.stringify({}),
      });
      await load();
    } catch (e: any) {
      setError(e?.message || "生成证据包失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadPack = () => {
    const a = document.createElement("a");
    a.href = "/api/v1/evidence/pack";
    a.download = "evidence-pack.zip";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-[#e2e8f0]">证据包</h1>
            <p className="mt-1 text-sm text-[#94a3b8]">
              合规证据与报告打包（<code className="text-[#64748b]">.osh/evidence</code>）
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => void load()}
              disabled={loading}
              className="border-[#1e293b] text-[#e2e8f0] hover:bg-[#1e293b]"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              刷新
            </Button>
            <Button
              onClick={() => void handleGenerate()}
              disabled={generating}
              className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90"
            >
              {generating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Archive className="h-4 w-4" />
              )}
              生成证据包
            </Button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-[#ff4d4f]/20 bg-[#ff4d4f]/10 px-4 py-2.5 text-sm text-[#ff4d4f]">
            {error}
          </div>
        )}

        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader>
            <CardTitle className="text-[#e2e8f0]">已生成证据文件（{files.length}）</CardTitle>
            <CardDescription className="text-[#64748b]">
              由「生成证据包」产出，涵盖需求追溯、评审记录、测试报告与 ASPICE 合规清单
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center gap-2 py-8 text-sm text-[#64748b]">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
              </div>
            ) : files.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-[#64748b]">
                <FolderOpen className="h-8 w-8 text-[#334155]" />
                暂无证据文件，点击「生成证据包」开始产出合规证据
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#1e293b] text-left text-[#64748b]">
                      <th className="px-3 py-2 font-medium">文件</th>
                      <th className="px-3 py-2 font-medium">类型</th>
                      <th className="px-3 py-2 font-medium">大小</th>
                      <th className="px-3 py-2 font-medium">修改时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {files.map((f) => (
                      <tr
                        key={f.name}
                        className="border-b border-[#1e293b]/60 last:border-0"
                      >
                        <td className="px-3 py-2.5 text-[#e2e8f0]">
                          <span className="inline-flex items-center gap-2">
                            <FileText className="h-4 w-4 text-[#722ed1]" />
                            {f.name}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <Badge className="border-[#1e293b] bg-[#0a0e17] text-[#94a3b8]">
                            {f.type || "—"}
                          </Badge>
                        </td>
                        <td className="px-3 py-2.5 text-[#94a3b8]">{fmtSize(f.size)}</td>
                        <td className="px-3 py-2.5 text-[#94a3b8]">{fmtTime(f.mtime)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="mt-4 flex items-center gap-3">
          <Button
            onClick={handleDownloadPack}
            disabled={files.length === 0}
            variant="outline"
            className="border-[#1e293b] text-[#e2e8f0] hover:bg-[#1e293b] disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            下载完整合规包（ZIP）
          </Button>
          <span className="text-xs text-[#64748b]">
            合规包以 ZIP 形式打包全部证据文件，可直接提交客户 / 认证机构审计
          </span>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { FolderPlus, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

interface CreateProjectModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (project: { id?: string; name: string; slug?: string }) => void;
}

export function CreateProjectModal({ open, onClose, onCreated }: CreateProjectModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  async function handleCreate() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("请输入项目名称");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const proj = (await api.v1.projects.create(trimmed, description.trim())) as any;
      if (proj && proj.error) {
        setError(proj.error);
        return;
      }
      onCreated({ id: proj?.id, name: trimmed, slug: proj?.slug });
      setName("");
      setDescription("");
      onClose();
    } catch (e: any) {
      setError(e?.message || "创建项目失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-[#1e293b] bg-[#111827] p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-[#e2e8f0] flex items-center gap-2">
            <FolderPlus className="w-4 h-4 text-[#722ed1]" />
            新建项目
          </h3>
          <button
            onClick={onClose}
            className="text-[#64748b] hover:text-[#94a3b8] transition-colors"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <label className="block text-xs text-[#94a3b8] mb-1.5">项目名称</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !loading) void handleCreate();
          }}
          placeholder="例如：UART 驱动演示项目"
          className="w-full rounded-lg border border-[#1e293b] bg-[#0a0e17] px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#722ed1] transition-colors"
          autoFocus
        />

        <label className="block text-xs text-[#94a3b8] mb-1.5 mt-3">描述（可选）</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="项目说明"
          rows={3}
          className="w-full rounded-lg border border-[#1e293b] bg-[#0a0e17] px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#722ed1] transition-colors resize-none"
        />

        {error && <p className="text-xs text-[#ef4444] mt-2">{error}</p>}

        <div className="flex justify-end gap-2 mt-4">
          <Button
            variant="outline"
            onClick={onClose}
            className="border-[#1e293b] text-[#94a3b8] text-xs"
          >
            取消
          </Button>
          <Button
            onClick={handleCreate}
            disabled={loading || !name.trim()}
            className="bg-[#722ed1] text-white text-xs gap-1.5 disabled:opacity-50 hover:bg-[#722ed1]/90"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <FolderPlus className="w-3.5 h-3.5" />
            )}
            {loading ? "创建中..." : "创建项目"}
          </Button>
        </div>
      </div>
    </div>
  );
}

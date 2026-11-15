"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Loader2, MoreHorizontal, Pencil, Trash2, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-fetch";

export interface ProjectRef {
  id: string;
  name: string;
  description?: string;
}

interface ProjectActionsMenuProps {
  project: ProjectRef | null;
  syncing: boolean;
  onSync: () => void;
  onUpdated: (project: ProjectRef) => void;
  onDeleted: (id: string) => void;
}

export function ProjectActionsMenu({
  project,
  syncing,
  onSync,
  onUpdated,
  onDeleted,
}: ProjectActionsMenuProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const openRename = () => {
    if (!project) return;
    setName(project.name);
    setDescription(project.description ?? "");
    setError(null);
    setMenuOpen(false);
    setRenameOpen(true);
  };

  const handleRename = async () => {
    if (!project || !name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<{ project: ProjectRef }>(
        `/api/v1/desktop/projects/${project.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ name: name.trim(), description: description.trim() }),
        },
      );
      onUpdated(res.project);
      setRenameOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!project || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/desktop/projects/${project.id}`, { method: "DELETE" });
      onDeleted(project.id);
      setDeleteOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="relative" ref={menuRef}>
        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          disabled={!project}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          title="工程操作"
          data-testid="project-actions-trigger"
          className="h-8 w-8 flex items-center justify-center rounded-md border border-[#1e293b] text-[#94a3b8] hover:text-white disabled:opacity-40"
        >
          <MoreHorizontal className="w-4 h-4" />
        </button>
        {menuOpen && (
          <div
            role="menu"
            data-testid="project-actions-menu"
            className="absolute right-0 top-9 z-50 w-40 rounded-lg border border-[#1e293b] bg-[#111827] shadow-xl py-1"
          >
            <MenuItem icon={<Pencil className="w-3.5 h-3.5" />} onClick={openRename} testId="project-action-rename">
              重命名 / 编辑
            </MenuItem>
            <MenuItem
              icon={syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UploadCloud className="w-3.5 h-3.5" />}
              onClick={() => {
                setMenuOpen(false);
                onSync();
              }}
              disabled={syncing}
              testId="project-action-sync"
            >
              立即同步到云端
            </MenuItem>
            <div className="my-1 h-px bg-[#1e293b]" />
            <MenuItem
              icon={<Trash2 className="w-3.5 h-3.5" />}
              onClick={() => {
                setError(null);
                setMenuOpen(false);
                setDeleteOpen(true);
              }}
              danger
              testId="project-action-delete"
            >
              删除工程
            </MenuItem>
          </div>
        )}
      </div>

      {renameOpen && project && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
          onClick={() => !busy && setRenameOpen(false)}
        >
          <div
            className="w-[420px] rounded-xl border border-[#1e293b] bg-[#0d111f] p-5 space-y-3"
            onClick={(e) => e.stopPropagation()}
            data-testid="project-rename-dialog"
          >
            <div className="text-sm font-medium text-[#e2e8f0]">重命名工程</div>
            <div className="space-y-2">
              <Input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRename()}
                className="bg-[#111827] border-[#1e293b] text-[#e2e8f0]"
                data-testid="project-rename-name"
              />
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="描述（可选）"
                className="bg-[#111827] border-[#1e293b] text-[#e2e8f0]"
                data-testid="project-rename-description"
              />
            </div>
            {error && <div className="text-xs text-[#f87171]">{error}</div>}
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setRenameOpen(false)}
                disabled={busy}
                className="border-[#1e293b] text-[#94a3b8]"
              >
                取消
              </Button>
              <Button
                size="sm"
                onClick={handleRename}
                disabled={!name.trim() || busy}
                className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white"
                data-testid="project-rename-confirm"
              >
                {busy && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
                保存
              </Button>
            </div>
          </div>
        </div>
      )}

      {deleteOpen && project && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
          onClick={() => !busy && setDeleteOpen(false)}
        >
          <div
            className="w-[420px] rounded-xl border border-[#1e293b] bg-[#0d111f] p-5 space-y-3"
            onClick={(e) => e.stopPropagation()}
            data-testid="project-delete-dialog"
          >
            <div className="text-sm font-medium text-[#e2e8f0] flex items-center gap-2">
              <Trash2 className="w-4 h-4 text-[#ef4444]" /> 删除工程
            </div>
            <p className="text-xs text-[#94a3b8] leading-relaxed">
              将永久删除「{project.name}」及其全部产出物（需求、设计、代码、测试、证据）。
              此操作不可撤销，已同步到云端的副本不会被删除。
            </p>
            {error && <div className="text-xs text-[#f87171]">{error}</div>}
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteOpen(false)}
                disabled={busy}
                className="border-[#1e293b] text-[#94a3b8]"
              >
                取消
              </Button>
              <Button
                size="sm"
                onClick={handleDelete}
                disabled={busy}
                className="bg-[#ef4444] hover:bg-[#dc2626] text-white"
                data-testid="project-delete-confirm"
              >
                {busy && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
                确认删除
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function MenuItem({
  icon,
  children,
  onClick,
  disabled,
  danger,
  testId,
}: {
  icon: ReactNode;
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  testId?: string;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
      className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left disabled:opacity-40 ${
        danger ? "text-[#f87171] hover:bg-[#ef4444]/10" : "text-[#cbd5e1] hover:bg-[#1e293b]"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

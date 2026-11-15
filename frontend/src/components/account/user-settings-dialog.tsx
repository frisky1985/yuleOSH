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
import { Label } from "@/components/ui/label";
import { Moon, Sun } from "lucide-react";

interface UserSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userId?: number | string;
  /** 桌面端：打开模型配置弹窗（不传则不展示该入口）。 */
  onOpenLLM?: () => void;
  llmLabel?: string;
}

interface PersistedSettings {
  theme: "system" | "dark" | "light";
  notifyOnEvidence: boolean;
  notifyOnPipelineFinish: boolean;
  language: "zh-CN" | "en-US";
}

const DEFAULT_SETTINGS: PersistedSettings = {
  theme: "system",
  notifyOnEvidence: true,
  notifyOnPipelineFinish: true,
  language: "zh-CN",
};

function settingsKey(userId?: number | string) {
  return `yuleosh:settings:${userId ?? "anonymous"}`;
}

function loadSettings(userId?: number | string): PersistedSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(settingsKey(userId));
    if (!raw) return DEFAULT_SETTINGS;
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function saveSettings(userId: number | string | undefined, settings: PersistedSettings) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(settingsKey(userId), JSON.stringify(settings));
  } catch {
    // 忽略（隐私模式 / 配额满）
  }
}

/** 决策者顶栏 → 用户设置：本地偏好设置（语言/通知/主题）。
 * 占位实现：后端无 /api/v1/me/settings 端点，仅持久化在 localStorage。 */
export function UserSettingsDialog({ open, onOpenChange, userId, onOpenLLM, llmLabel }: UserSettingsDialogProps) {
  const [settings, setSettings] = useState<PersistedSettings>(DEFAULT_SETTINGS);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (open) {
      setSettings(loadSettings(userId));
      setHydrated(true);
    }
  }, [open, userId]);

  const update = <K extends keyof PersistedSettings>(key: K, value: PersistedSettings[K]) => {
    setSettings((s) => ({ ...s, [key]: value }));
  };

  const onSave = () => {
    saveSettings(userId, settings);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" data-testid="user-settings-dialog">
        <DialogHeader>
          <DialogTitle>用户设置</DialogTitle>
          <DialogDescription>
            当前用户偏好。界面偏好保存在本浏览器 localStorage；桌面端的模型配置保存在本机工作区。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5 mt-1">
          {onOpenLLM && (
            <div className="flex flex-col gap-2">
              <Label className="text-xs text-[#94a3b8]">大模型</Label>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-[#1e293b] bg-[#0f172a] px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-sm text-[#e2e8f0]">
                    {llmLabel || "本地模型服务"}
                  </div>
                  <div className="text-[11px] text-[#64748b]">配置服务商、模型与 API Key</div>
                </div>
                <Button variant="outline" size="sm" onClick={onOpenLLM}>
                  配置
                </Button>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <Label htmlFor="settings-language" className="text-xs text-[#94a3b8]">
              语言
            </Label>
            <select
              id="settings-language"
              data-slot="select"
              className="h-8 w-full rounded-lg border border-input bg-input/30 px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              value={settings.language}
              onChange={(e) => update("language", e.target.value as PersistedSettings["language"])}
              disabled={!hydrated}
            >
              <option value="zh-CN">简体中文</option>
              <option value="en-US">English (US)</option>
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-xs text-[#94a3b8]">主题</Label>
            <div className="grid grid-cols-3 gap-2">
              {(["system", "dark", "light"] as const).map((t) => (
                <Button
                  key={t}
                  variant={settings.theme === t ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => update("theme", t)}
                  disabled={!hydrated}
                  className="justify-center"
                >
                  {t === "dark" ? <Moon className="w-3.5 h-3.5" /> : t === "light" ? <Sun className="w-3.5 h-3.5" /> : null}
                  {t === "system" ? "跟随系统" : t === "dark" ? "深色" : "浅色"}
                </Button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-xs text-[#94a3b8]">通知</Label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input
                type="checkbox"
                className="accent-[#722ed1]"
                checked={settings.notifyOnEvidence}
                onChange={(e) => update("notifyOnEvidence", e.target.checked)}
                disabled={!hydrated}
              />
              <span>证据包就绪时通知我</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input
                type="checkbox"
                className="accent-[#722ed1]"
                checked={settings.notifyOnPipelineFinish}
                onChange={(e) => update("notifyOnPipelineFinish", e.target.checked)}
                disabled={!hydrated}
              />
              <span>流水线完成 / 失败时通知我</span>
            </label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button variant="default" size="sm" onClick={onSave} disabled={!hydrated}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

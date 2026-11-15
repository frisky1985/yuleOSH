"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  FolderPlus,
  Loader2,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { apiFetch } from "@/lib/api-fetch";

export interface ProjectTemplateMeta {
  id: string;
  name: string;
  tag: string;
  description: string;
  doc_templates: string[];
  has_requirements_seed: boolean;
}

export interface ProjectLite {
  id: string;
  name: string;
  description: string;
}

export interface TemplateApplyResult {
  template: string;
  created_docs: string[];
  requirements_saved: boolean;
}

interface ProjectWizardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (project: ProjectLite, template: TemplateApplyResult | null) => void;
}

const TEMPLATE_ICONS: Record<string, string> = {
  blank: "📁",
  "aspice-lite": "🧩",
  automotive: "🚗",
  "web-app": "🌐",
};

export function ProjectWizardDialog({ open, onOpenChange, onCreated }: ProjectWizardDialogProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [templateId, setTemplateId] = useState("blank");
  const [templates, setTemplates] = useState<ProjectTemplateMeta[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = useCallback(() => {
    if (submitting) return;
    onOpenChange(false);
  }, [onOpenChange, submitting]);

  // Reset the wizard each time it is reopened.
  useEffect(() => {
    if (!open) return;
    setStep(1);
    setName("");
    setDescription("");
    setTemplateId("blank");
    setError(null);
  }, [open]);

  useEffect(() => {
    if (!open || templates.length) return;
    let alive = true;
    setLoadingTemplates(true);
    apiFetch<{ templates: ProjectTemplateMeta[] }>("/api/v1/desktop/project-templates")
      .then((d) => {
        if (!alive) return;
        const list = d.templates || [];
        setTemplates(list);
        if (list.length && !list.some((t) => t.id === "blank")) {
          setTemplateId(list[0].id);
        }
      })
      .catch((e: Error) => {
        if (alive) setError(`模板加载失败: ${e.message}`);
      })
      .finally(() => {
        if (alive) setLoadingTemplates(false);
      });
    return () => {
      alive = false;
    };
  }, [open, templates.length]);

  const selected = templates.find((t) => t.id === templateId) ?? null;

  const handleCreate = async () => {
    const trimmed = name.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<{
        project: ProjectLite;
        template?: TemplateApplyResult | null;
      }>("/api/v1/desktop/projects", {
        method: "POST",
        body: JSON.stringify({
          name: trimmed,
          description: description.trim(),
          template: templateId,
        }),
      });
      onCreated(res.project, res.template ?? null);
      onOpenChange(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={close}
      data-testid="project-wizard"
    >
      <Card
        className="w-[560px] bg-[#0d111f] border-[#1e293b]"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader>
          <CardTitle className="text-[#e2e8f0] flex items-center gap-2">
            <FolderPlus className="w-5 h-5 text-[#1677ff]" /> 新建工程
            <span className="ml-auto text-xs font-normal text-[#64748b]">
              第 {step} / 2 步
            </span>
          </CardTitle>
          <CardDescription className="text-[#64748b]">
            {step === 1
              ? "填写工程基本信息，产出物将保存在独立文件夹中。"
              : "选择一个模板，创建时自动生成对应的文档骨架与需求模板。"}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {step === 1 ? (
            <div className="space-y-3">
              <label className="block text-xs text-[#94a3b8]">
                工程名称
                <Input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && name.trim()) setStep(2);
                  }}
                  placeholder="如：智能车灯控制器"
                  className="mt-1 bg-[#111827] border-[#1e293b] text-[#e2e8f0]"
                  data-testid="wizard-name"
                />
              </label>
              <label className="block text-xs text-[#94a3b8]">
                描述（可选）
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="一句话说明工程目标"
                  className="mt-1 bg-[#111827] border-[#1e293b] text-[#e2e8f0]"
                  data-testid="wizard-description"
                />
              </label>
            </div>
          ) : (
            <div className="space-y-2">
              {loadingTemplates && (
                <div className="flex items-center gap-2 text-xs text-[#64748b]">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> 正在加载模板…
                </div>
              )}
              <div className="grid grid-cols-2 gap-2" data-testid="wizard-templates">
                {templates.map((t) => {
                  const active = t.id === templateId;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setTemplateId(t.id)}
                      data-testid={`wizard-template-${t.id}`}
                      className={`text-left rounded-lg border p-3 transition-colors ${
                        active
                          ? "border-[#1677ff] bg-[#1677ff]/10"
                          : "border-[#1e293b] bg-[#111827] hover:border-[#334155]"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-base leading-none">
                          {TEMPLATE_ICONS[t.id] ?? "📄"}
                        </span>
                        <span className="text-sm text-[#e2e8f0]">{t.name}</span>
                        {active && <Check className="w-3.5 h-3.5 text-[#1677ff] ml-auto" />}
                      </div>
                      <div className="mt-1 text-[11px] text-[#64748b] leading-relaxed">
                        {t.description}
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1e293b] text-[#94a3b8]">
                          {t.tag}
                        </span>
                        {t.doc_templates.length > 0 && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1e293b] text-[#94a3b8]">
                            {t.doc_templates.length} 份文档
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
              {selected && (
                <div
                  className="rounded-md border border-[#1e293b] bg-[#0b1020] px-3 py-2 text-[11px] text-[#94a3b8] space-y-1"
                  data-testid="wizard-summary"
                >
                  <div className="flex items-center gap-1 text-[#10b981]">
                    <Sparkles className="w-3 h-3" /> 创建后将生成：
                  </div>
                  <div>
                    文档：
                    {selected.doc_templates.length
                      ? selected.doc_templates.join("、")
                      : "无（空白工程）"}
                  </div>
                  <div>需求模板：{selected.has_requirements_seed ? "是" : "否"}</div>
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="text-xs text-[#f87171]" data-testid="wizard-error">
              {error}
            </div>
          )}

          <div className="flex justify-between gap-2 pt-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => (step === 1 ? close() : setStep(1))}
              className="border-[#1e293b] text-[#94a3b8]"
            >
              {step === 1 ? "取消" : (
                <>
                  <ChevronLeft className="w-4 h-4 mr-1" /> 上一步
                </>
              )}
            </Button>
            {step === 1 ? (
              <Button
                size="sm"
                onClick={() => setStep(2)}
                disabled={!name.trim()}
                className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white"
                data-testid="wizard-next"
              >
                下一步 <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={handleCreate}
                disabled={!name.trim() || submitting}
                className="bg-gradient-to-r from-[#10b981] to-[#059669] text-white"
                data-testid="wizard-create"
              >
                {submitting ? (
                  <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                ) : (
                  <Check className="w-4 h-4 mr-1" />
                )}
                创建工程
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

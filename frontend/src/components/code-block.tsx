"use client";

import { detectLang, highlight, type Lang } from "@/lib/syntax-highlight";

interface CodeBlockProps {
  content: string;
  path?: string | null;
  placeholder?: string;
}

export function CodeBlock({ content, path, placeholder }: CodeBlockProps) {
  const lang: Lang = path ? detectLang(path) : "plain";
  const isCode = lang !== "markdown" && lang !== "plain";

  return (
    <div className="flex flex-col h-full">
      {path && (
        <div className="flex items-center gap-2 px-4 py-1.5 border-b border-[#1e293b] bg-[#0d111f] shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-[#64748b] bg-[#1e293b] px-1.5 py-0.5 rounded">
            {lang}
          </span>
          <span className="text-[11px] text-[#475569] font-mono truncate">{path}</span>
        </div>
      )}
      <pre className={`flex-1 overflow-auto px-4 py-3 text-sm text-[#cbd5e1] font-mono leading-relaxed whitespace-pre-wrap ${isCode ? "font-mono" : ""}`}>
        {content ? highlight(content, lang) : (placeholder || "暂无内容")}
      </pre>
    </div>
  );
}

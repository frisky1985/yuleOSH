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
  const placeholderText = placeholder || "暂无内容";
  const lineCount = content ? content.split("\n").length : 0;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {path && (
        <div className="flex items-center gap-2 px-4 py-1.5 border-b border-[#1e293b] bg-[#0d111f] shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-[#64748b] bg-[#1e293b] px-1.5 py-0.5 rounded">
            {lang}
          </span>
          <span className="text-[11px] text-[#475569] font-mono truncate">{path}</span>
          {isCode && lineCount > 0 && (
            <span className="ml-auto shrink-0 text-[10px] text-[#475569]">{lineCount} 行</span>
          )}
        </div>
      )}
      {isCode ? (
        // 代码：行号 + 不自动换行（横向滚动），保持代码原始排版
        <div className="flex-1 min-h-0 overflow-auto">
          <div className="flex min-w-full w-max">
            <div className="shrink-0 sticky left-0 z-10 bg-[#0a0e17] border-r border-[#1e293b] py-3 pl-3 pr-2 text-right font-mono text-sm leading-relaxed text-[#3f4b63] select-none">
              {Array.from({ length: lineCount }, (_, i) => (
                <div key={i}>{i + 1}</div>
              ))}
            </div>
            <pre className="px-4 py-3 text-sm font-mono leading-relaxed whitespace-pre text-[#cbd5e1]">
              {content ? highlight(content, lang) : placeholderText}
            </pre>
          </div>
        </div>
      ) : (
        <pre className="flex-1 min-h-0 overflow-auto px-4 py-3 text-sm text-[#cbd5e1] font-mono leading-relaxed whitespace-pre-wrap">
          {content ? highlight(content, lang) : placeholderText}
        </pre>
      )}
    </div>
  );
}

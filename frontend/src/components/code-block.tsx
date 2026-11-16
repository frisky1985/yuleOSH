"use client";

import type { ReactNode } from "react";
import { detectLang, highlight, type Lang } from "@/lib/syntax-highlight";

interface CodeBlockProps {
  content: string;
  path?: string | null;
  placeholder?: string;
  /** 顶部提示条（如大文件截断、二进制文件）。 */
  notice?: string | null;
  /** 需要高亮的行范围（1 基，含首尾），用于评审行 / 搜索命中行。 */
  lineRange?: { start: number; end: number } | null;
  /** 点击行号时回调，用于快速选择评审起始行。 */
  onLineClick?: (line: number) => void;
  /** 文件头右侧的操作按钮。 */
  actions?: ReactNode;
}

export function CodeBlock({
  content,
  path,
  placeholder,
  notice,
  lineRange,
  onLineClick,
  actions,
}: CodeBlockProps) {
  const lang: Lang = path ? detectLang(path) : "plain";
  const isCode = lang !== "markdown" && lang !== "plain";
  const placeholderText = placeholder || "暂无内容";
  const lineCount = content ? content.split("\n").length : 0;
  const inRange = (line: number) =>
    Boolean(lineRange && line >= lineRange.start && line <= lineRange.end);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {path && (
        <div className="flex items-center gap-2 px-4 py-1.5 border-b border-[#1e293b] bg-[#0d111f] shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-[#64748b] bg-[#1e293b] px-1.5 py-0.5 rounded">
            {lang}
          </span>
          <span className="text-[11px] text-[#475569] font-mono truncate">{path}</span>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {isCode && lineCount > 0 && (
              <span className="text-[10px] text-[#475569]">{lineCount} 行</span>
            )}
            {actions}
          </div>
        </div>
      )}
      {notice && (
        <div
          data-testid="file-notice"
          className="flex items-center gap-1.5 border-b border-[#f59e0b]/30 bg-[#f59e0b]/10 px-4 py-1 text-[11px] text-[#fbbf24] shrink-0"
        >
          {notice}
        </div>
      )}
      {isCode ? (
        // 代码：行号 + 不自动换行（横向滚动），保持代码原始排版
        <div className="flex-1 min-h-0 overflow-auto">
          <div className="flex min-w-full w-max">
            <div className="shrink-0 sticky left-0 z-10 bg-[#0a0e17] border-r border-[#1e293b] py-3 pl-3 pr-2 text-right font-mono text-sm leading-relaxed text-[#3f4b63] select-none">
              {Array.from({ length: lineCount }, (_, i) => {
                const line = i + 1;
                const active = inRange(line);
                return (
                  <div
                    key={i}
                    data-testid={`code-line-${line}`}
                    data-active={active ? "true" : undefined}
                    onClick={onLineClick ? () => onLineClick(line) : undefined}
                    title={onLineClick ? `以第 ${line} 行作为评审起始行` : undefined}
                    className={`${onLineClick ? "cursor-pointer hover:text-[#93c5fd]" : ""} ${
                      active ? "bg-[#1677ff]/30 text-[#93c5fd]" : ""
                    }`}
                  >
                    {line}
                  </div>
                );
              })}
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

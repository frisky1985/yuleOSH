"use client";

/** Zero-dependency syntax highlighter — single regex multi-group + group→class map. */

export type Lang = "c" | "python" | "json" | "markdown" | "plain";

export function detectLang(path?: string | null): Lang {
  if (!path) return "plain";
  const p = path.toLowerCase();
  if (p.endsWith(".c") || p.endsWith(".h") || p.includes("/c/")) return "c";
  if (p.endsWith(".py")) return "python";
  if (p.endsWith(".json")) return "json";
  if (p.endsWith(".md") || p.endsWith(".markdown")) return "markdown";
  return "plain";
}

const RULES: Record<Lang, Array<{ pattern: string; cls: string }>> = {
  c: [
    { pattern: "(//[^\\n]*)|(/\\*[\\s\\S]*?\\*/)", cls: "text-[#64748b] italic" },
    { pattern: "\"[^\"\\\\]*(?:\\\\.[^\"\\\\]*)*\"", cls: "text-[#34d399]" },
    { pattern: "'[^'\\\\]*(?:\\\\.[^'\\\\]*)*'", cls: "text-[#34d399]" },
    { pattern: "\\b(0[xX][0-9a-fA-F]+|\\d+\\.\\d*[fFlLuLuU]?|\\d+[fFlLuLuU]?)\\b", cls: "text-[#fbbf24]" },
    { pattern: "\\b(auto|break|case|char|const|continue|default|do|double|else|enum|extern|float|for|goto|if|inline|int|long|register|return|short|signed|sizeof|static|struct|switch|typedef|union|unsigned|void|volatile|while|_Bool|_Complex|_Imaginary)\\b", cls: "text-[#93c5fd]" },
    { pattern: "#\\s*(define|include|ifdef|ifndef|endif|if|else|elif|pragma|undef|error|warning|line)\\b[^\\n]*", cls: "text-[#c084fc]" },
  ],
  python: [
    { pattern: "#[^\\n]*", cls: "text-[#64748b] italic" },
    { pattern: "\"\"\"[\\s\\S]*?\"\"\"|'''[\\s\\S]*?'''", cls: "text-[#34d399]" },
    { pattern: "\"[^\"\\\\]*(?:\\\\.[^\"\\\\]*)*\"|'[^'\\\\]*(?:\\\\.[^'\\\\]*)*'", cls: "text-[#34d399]" },
    { pattern: "\\b(\\d+\\.\\d*[eE]?[+-]?\\d*|\\d+[jJ]?|0[xX][0-9a-fA-F]+|0[oO][0-7]+)\\b", cls: "text-[#fbbf24]" },
    { pattern: "\\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\\b", cls: "text-[#93c5fd]" },
    { pattern: "^\\s*(class|def)\\s+\\w+", cls: "text-[#e2e8f0] font-semibold" },
    { pattern: "@\\w+", cls: "text-[#c084fc]" },
  ],
  json: [
    { pattern: "\"(?:[^\"\\\\]|\\\\.)*\"(\\s*:)?", cls: "text-[#34d399]" },
    { pattern: "\\b(true|false|null)\\b", cls: "text-[#93c5fd]" },
    { pattern: "-?\\b(0|[1-9]\\d*)(\\.\\d+)?([eE][+-]?\\d+)?\\b", cls: "text-[#fbbf24]" },
  ],
  markdown: [
    { pattern: "^#{1,6}\\s+.*$", cls: "text-[#e2e8f0] font-semibold" },
    { pattern: "```[\\s\\S]*?```", cls: "text-[#93c5fd]" },
    { pattern: "\\*\\*[^*]+\\*\\*", cls: "font-bold" },
    { pattern: "`[^`]+`", cls: "text-[#34d399]" },
    { pattern: "^\\s*[-*+]\\s", cls: "text-[#93c5fd]" },
  ],
  plain: [],
};

import React from "react";

export function highlight(code: string, lang: Lang): React.ReactNode[] {
  if (!code) return [];
  const rules = RULES[lang];
  if (!rules || rules.length === 0) return [code];

  const combined = new RegExp(rules.map((r) => `(${r.pattern})`).join("|"), "gm");
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;

  while ((m = combined.exec(code)) !== null) {
    // Push literal gap
    if (m.index > lastIndex) parts.push(code.slice(lastIndex, m.index));
    // Find which group matched (skip group 0 which is the whole match)
    let hitIdx = -1;
    for (let i = 1; i <= m.length; i++) {
      if (m[i] !== undefined) { hitIdx = i - 1; break; }
    }
    if (hitIdx >= 0) {
      parts.push(React.createElement("span", { key: parts.length, className: rules[hitIdx].cls }, m[0]));
    } else {
      parts.push(m[0]);
    }
    lastIndex = m.index + m[0].length;
    // Guard against empty match → infinite loop
    if (m[0].length === 0) combined.lastIndex += 1;
  }
  if (lastIndex < code.length) parts.push(code.slice(lastIndex));

  return parts.length === 0 ? [code] : parts;
}

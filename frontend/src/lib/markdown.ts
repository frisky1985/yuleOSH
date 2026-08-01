/**
 * Simple Markdown renderer for KB article content (XSS-safe).
 *
 * SECURITY (S-P2-03 / XSS audit X-01): article content is user/LLM-authored
 * and may contain raw HTML. Every render path MUST escape HTML before any
 * markdown transform is applied, so injected `<script>` / `<img onerror>`
 * payloads are rendered as inert text instead of executing.
 *
 * Order matters: escapeHtml() runs FIRST, then the markdown regexes wrap the
 * already-escaped text in generated tags (the $1/$2 captures are escaped,
 * the wrapper tags/classes are hard-coded constants).
 */

export function escapeHtml(input: string): string {
  return String(input)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function simpleMarkdown(content: string): string {
  // Escape raw HTML FIRST — this is the XSS boundary (X-01).
  let html = escapeHtml(content)
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-[#1e293b] rounded-lg p-3 my-2 overflow-x-auto text-xs text-[#e2e8f0] font-mono"><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-[#1e293b] px-1.5 py-0.5 rounded text-xs text-[#10b981] font-mono">$1</code>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-bold text-[#e2e8f0] mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold text-[#e2e8f0] mt-5 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold text-[#e2e8f0] mt-5 mb-3">$1</h1>')
    // Bold/italic
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-bold text-[#e2e8f0]">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em class="italic text-[#94a3b8]">$1</em>')
    // Lists
    .replace(/^- (.+)$/gm, '<li class="text-xs text-[#94a3b8] ml-4 list-disc">$1</li>')
    // Paragraphs (double newlines)
    .replace(/\n\n/g, '</p><p class="text-xs text-[#94a3b8] leading-relaxed mb-1">')
    // Single newlines within paragraphs
    .replace(/\n/g, "<br/>");

  return '<p class="text-xs text-[#94a3b8] leading-relaxed mb-1">' + html + "</p>";
}

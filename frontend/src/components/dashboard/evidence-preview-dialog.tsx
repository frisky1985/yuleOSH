"use client";

import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
import {
  AlertCircle,
  Download,
  FileText,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// 超大文件保护：超过此字节数只展示前 120KB，防止 Dialog 卡壳。
const MAX_PREVIEW_BYTES = 2 * 1024 * 1024; // 2 MB
const TRUNCATE_HEAD = 120 * 1024;         // 展示前 120KB

interface EvidencePreviewDialogProps {
  open: boolean;
  file: { name: string; type: string } | null;
  onOpenChange: (open: boolean) => void;
}

// marked 全局配置：GFM + 表格 + 代码块行号标记（可选）
marked.setOptions({
  gfm: true,
  breaks: false,
});

function isMarkdown(name: string) {
  return /\.(md|markdown|mdown|mkd)$/i.test(name);
}
function isHtmlFile(name: string) {
  return /\.(html|htm)$/i.test(name);
}

/** 深色主题 Markdown 样式 —— Tailwind @layer，dialog content 内生效。 */
const MARKDOWN_STYLE = `
.ev-md { color: #e2e8f0; line-height: 1.7; font-size: 0.875rem; }
.ev-md h1,.ev-md h2,.ev-md h3,.ev-md h4 { color: #f8fafc; font-weight: 600; margin: 1.2em 0 0.5em; }
.ev-md h1 { font-size: 1.375rem; border-bottom: 1px solid #1e293b; padding-bottom: 0.3em; }
.ev-md h2 { font-size: 1.125rem; border-bottom: 1px solid #1e293b; padding-bottom: 0.25em; }
.ev-md h3 { font-size: 1rem; }
.ev-md p { margin: 0.6em 0; }
.ev-md a { color: #60a5fa; text-decoration: underline; }
.ev-md ul,.ev-md ol { padding-left: 1.6em; margin: 0.4em 0; }
.ev-md li { margin: 0.15em 0; }
.ev-md table { border-collapse: collapse; width: 100%; margin: 0.8em 0; font-size: 0.8rem; }
.ev-md th,.ev-md td { border: 1px solid #1e293b; padding: 0.35em 0.6em; text-align: left; }
.ev-md th { background: #1e293b; color: #cbd5e1; font-weight: 600; }
.ev-md tr:nth-child(even) td { background: rgba(30,41,59,0.35); }
.ev-md code { background: #1e293b; padding: 0.1em 0.35em; border-radius: 3px; font-size: 0.82em; }
.ev-md pre { background: #0a0e17; border: 1px solid #1e293b; border-radius: 6px; padding: 0.8em 1em; overflow-x: auto; margin: 0.6em 0; }
.ev-md pre code { background: transparent; padding: 0; font-size: 0.8rem; }
.ev-md blockquote { border-left: 3px solid #722ed1; padding-left: 0.9em; color: #94a3b8; margin: 0.8em 0; }
.ev-md hr { border: 0; border-top: 1px solid #1e293b; margin: 1.2em 0; }
.ev-md img { max-width: 100%; }
`;

export function EvidencePreviewDialog({
  open,
  file,
  onOpenChange,
}: EvidencePreviewDialogProps) {
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [truncated, setTruncated] = useState(false);

  // open 时 fetch 内容；file 不变也不重拉（避免每次打开都请求）
  useEffect(() => {
    if (!open || !file) return;
    if (content && !error) return;

    let cancelled = false;
    setLoading(true);
    setError("");
    setTruncated(false);

    const url = `/api/v1/evidence/file?name=${encodeURIComponent(file.name)}`;
    // 直接用原生 fetch —— 这个端点返回流式二进制（handler 路径），
    // 不走 apiFetch 的 JSON 信封解包。
    fetch(url, { credentials: "same-origin" })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        // 大文件截断：读前 MAX_PREVIEW_BYTES，避免 res.text() 把 20MB 读进内存
        const reader = res.body?.getReader();
        if (!reader) {
          const text = await res.text();
          if (cancelled) return;
          setContent(text);
          return;
        }
        const chunks: Uint8Array[] = [];
        let total = 0;
        let exceeded = false;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          total += value.length;
          if (total > MAX_PREVIEW_BYTES) {
            exceeded = true;
            break;
          }
        }
        if (cancelled) return;
        const full = new Uint8Array(total);
        let offset = 0;
        for (const c of chunks) {
          full.set(c, offset);
          offset += c.length;
        }
        const text = new TextDecoder("utf-8", { fatal: false }).decode(
          exceeded ? full.slice(0, TRUNCATE_HEAD) : full,
        );
        setContent(text);
        setTruncated(exceeded);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, file?.name]);

  // Dialog 关闭时清空内容，下一次打开会触发重拉
  useEffect(() => {
    if (!open) {
      setContent("");
      setError("");
      setTruncated(false);
    }
  }, [open]);

  const isMd: boolean = useMemo(() => (file ? isMarkdown(file.name) : false), [file]);
  const isHtml: boolean = useMemo(() => (file ? isHtmlFile(file.name) : false), [file]);
  const isText: boolean = useMemo(() => !isMd && !isHtml, [isMd, isHtml]);

  const htmlFromMd = useMemo(() => {
    if (!isMd) return "";
    try {
      return marked.parse(content) as string;
    } catch {
      return `<pre style="white-space:pre-wrap">${content}</pre>`;
    }
  }, [isMd, content]);

  const iframeSrcDoc = useMemo(() => {
    if (!isHtml) return "";
    // 内嵌默认样式让裸 HTML 看起来协调一些（不影响文档内已定义的样式）
    return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>
      body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#e2e8f0;background:#0a0e17;margin:1.2rem;line-height:1.6}
      a{color:#60a5fa}table{border-collapse:collapse}th,td{border:1px solid #1e293b;padding:.35em .6em}
      h1,h2,h3,h4{color:#f8fafc}hr{border:0;border-top:1px solid #1e293b}
      img{max-width:100%}pre,code{background:#1e293b}
    </style></head><body>${content}</body></html>`;
  }, [isHtml, content]);

  if (!file) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        size="lg"
        className="max-h-[88vh] flex flex-col overflow-hidden"
      >
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2 text-[#e2e8f0]">
            <FileText className="h-4 w-4 text-[#722ed1]" />
            预览 · {file.name}
            <span className="ml-auto text-xs font-normal text-[#64748b]">
              {file.type || ""}
            </span>
          </DialogTitle>
        </DialogHeader>

        {/* 操作条 */}
        <div className="flex-shrink-0 flex items-center justify-between gap-2 -mt-1">
          <div className="text-xs text-[#64748b]">
            {isMd && "Markdown 渲染视图"}
            {isHtml && "HTML 内嵌视图（sandbox）"}
            {isText && "纯文本预览"}
          </div>
          <button
            type="button"
            onClick={() => {
              const a = document.createElement("a");
              a.href = `/api/v1/evidence/file?name=${encodeURIComponent(file.name)}`;
              a.download = file.name;
              document.body.appendChild(a);
              a.click();
              a.remove();
            }}
            className="inline-flex items-center gap-1.5 rounded-md border border-[#1e293b] px-2.5 py-1 text-xs text-[#e2e8f0] hover:bg-[#1e293b] transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            下载原文件
          </button>
        </div>

        {/* 内容区 */}
        <div className="flex-1 min-h-0 overflow-auto rounded-lg border border-[#1e293b] bg-[#0a0e17]">
          {loading && (
            <div className="h-full flex flex-col items-center justify-center gap-3 py-16 text-[#64748b]">
              <Loader2 className="h-6 w-6 animate-spin text-[#722ed1]" />
              <span className="text-sm">正在加载 {file.name} …</span>
            </div>
          )}

          {!loading && error && (
            <div className="h-full flex flex-col items-center justify-center gap-3 py-16 text-center">
              <AlertCircle className="h-7 w-7 text-[#ff4d4f]" />
              <div className="text-sm text-[#e2e8f0]">加载失败</div>
              <div className="text-xs text-[#64748b] break-all max-w-[80%]">
                {error}
              </div>
            </div>
          )}

          {!loading && !error && truncated && (
            <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-[#faad14]/30 bg-[#faad14]/10 px-3 py-2 text-xs text-[#faad14]">
              <AlertTriangle className="h-3.5 w-3.5" />
              文件较大，仅展示前 120KB —— 请下载完整文件查看全部内容。
            </div>
          )}

          {!loading && !error && isMd && (
            <>
              {/* 注入 Markdown 主题样式 —— DialogContent 作用域内生效 */}
              <style>{MARKDOWN_STYLE}</style>
              <div
                className="ev-md px-5 py-4"
                // marked 产出安全 HTML（无 script 注入）；渲染证据报告
                // 时标题/表格/代码块是唯一入口，XSS 风险由后端证据链内容可信性兜底。
                dangerouslySetInnerHTML={{ __html: htmlFromMd }}
              />
            </>
          )}

          {!loading && !error && isHtml && (
            <iframe
              // sandbox 防止被预览的 .html 报告执行脚本、访问父窗口、或发起
              // 外链导航；allow-same-origin 保留相对资源加载（如内联样式）。
              sandbox="allow-same-origin"
              srcDoc={iframeSrcDoc}
              title={file.name}
              className="block w-full h-full min-h-[400px] bg-[#0a0e17] border-0"
            />
          )}

          {!loading && !error && isText && (
            <pre className="px-5 py-4 text-xs leading-relaxed text-[#e2e8f0] whitespace-pre-wrap break-words font-mono">
              {content || "(文件为空)"}
            </pre>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

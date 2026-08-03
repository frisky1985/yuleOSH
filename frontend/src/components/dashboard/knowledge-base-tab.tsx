"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BookOpen, ChevronRight, Search, X, ExternalLink, Loader2,
  FileText, AlertCircle, Hash,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  getKBArticles, getFMEAEntries,
  type KbArticle, type FmeaEntry,
} from "@/lib/api";
import { simpleMarkdown } from "@/lib/markdown";


function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try { return new Date(dateStr).toLocaleString("zh-CN"); }
  catch { return dateStr; }
}

export function KnowledgeBaseTab() {
  const [articles, setArticles] = useState<KbArticle[]>([]);
  const [articlesLoading, setArticlesLoading] = useState(true);
  const [articlesError, setArticlesError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedArticle, setExpandedArticle] = useState<number | null>(null);
  const [kbOffset, setKbOffset] = useState(0);
  const [kbTotal, setKbTotal] = useState(0);
  const [kbSearching, setKbSearching] = useState(false);
  const pageSize = 10;

  // FMEA
  const [fmeaEntries, setFmeaEntries] = useState<FmeaEntry[]>([]);
  const [fmeaLoading, setFmeaLoading] = useState(true);

  // Load KB articles
  const loadArticles = useCallback(async (search?: string, offset?: number) => {
    setArticlesLoading(true);
    setArticlesError("");
    try {
      const res = await getKBArticles({
        search: search || undefined,
        limit: pageSize,
        offset: offset ?? kbOffset,
      });
      setArticles(res.items);
      setKbTotal(res.total);
    } catch (err: any) {
      setArticlesError(err.message || "加载知识库失败");
    } finally {
      setArticlesLoading(false);
    }
  }, [kbOffset]);

  // Load FMEA entries
  const loadFmea = useCallback(async () => {
    setFmeaLoading(true);
    try {
      const res = await getFMEAEntries({ limit: 10, sort_by: "rpn", sort_desc: true });
      setFmeaEntries(res.items);
    } catch {
      // Silently fail
    } finally {
      setFmeaLoading(false);
    }
  }, []);

  useEffect(() => {
    loadArticles();
    loadFmea();
  }, []);

  // Search handler
  const handleSearch = () => {
    setKbOffset(0);
    setKbSearching(true);
    loadArticles(searchQuery || undefined, 0).then(() => setKbSearching(false));
  };

  const handleClearSearch = () => {
    setSearchQuery("");
    setKbOffset(0);
    setKbSearching(true);
    loadArticles(undefined, 0).then(() => setKbSearching(false));
  };

  const handlePrevPage = () => {
    const newOffset = Math.max(0, kbOffset - pageSize);
    setKbOffset(newOffset);
    setKbSearching(true);
    loadArticles(searchQuery || undefined, newOffset).then(() => setKbSearching(false));
  };

  const handleNextPage = () => {
    const newOffset = kbOffset + pageSize;
    setKbOffset(newOffset);
    setKbSearching(true);
    loadArticles(searchQuery || undefined, newOffset).then(() => setKbSearching(false));
  };

  const totalPages = Math.ceil(kbTotal / pageSize);
  const currentPage = Math.floor(kbOffset / pageSize) + 1;

  function rpnColor(rpn: number): string {
    if (rpn >= 100) return "#ff4d4f";
    if (rpn >= 50) return "#faad14";
    return "#10b981";
  }

  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-[#722ed1]" />
            知识库
          </h1>
          <p className="text-xs text-[#64748b] mt-0.5">
            {kbTotal > 0 ? `共 ${kbTotal} 篇文章` : "浏览知识库文章和 FMEA 条目"}
          </p>
        </div>
      </div>

      {/* Search bar */}
      <div className="mb-5">
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#64748b]" />
            <Input
              placeholder="搜索知识库文章..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
              className="pl-9 h-9 text-xs border-[#1e293b] bg-[#111827] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
            />
            {searchQuery && (
              <button
                onClick={handleClearSearch}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#64748b] hover:text-white"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
          <Button
            onClick={handleSearch}
            disabled={kbSearching || !searchQuery.trim()}
            className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white h-9 text-xs gap-1.5 disabled:opacity-50"
          >
            {kbSearching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            搜索
          </Button>
        </div>
      </div>

      {/* Article list + FMEA grid */}
      <div className="grid lg:grid-cols-3 gap-5 mb-6">
        {/* Article list (spans 2 cols) */}
        <Card className="lg:col-span-2 border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#722ed1]" />
              文章列表
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {articlesLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
                <span className="ml-2 text-xs text-[#94a3b8]">加载文章...</span>
              </div>
            ) : articlesError ? (
              <div className="px-4 py-8 text-center">
                <AlertCircle className="w-6 h-6 text-[#ff4d4f] mx-auto mb-2" />
                <p className="text-xs text-[#ff4d4f]">{articlesError}</p>
              </div>
            ) : articles.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <BookOpen className="w-6 h-6 text-[#64748b] mx-auto mb-2" />
                <p className="text-xs text-[#64748b]">
                  {searchQuery ? "没有找到匹配的文章" : "暂无知识库文章"}
                </p>
              </div>
            ) : (
              <div>
                {articles.map((article) => {
                  const isExpanded = expandedArticle === article.id;
                  const tags = article.tags ? article.tags.split(/[,\s]+/).filter(Boolean) : [];
                  return (
                    <div key={article.id} className="border-b border-[#1e293b] last:border-b-0">
                      <button
                        onClick={() => setExpandedArticle(isExpanded ? null : article.id)}
                        className="w-full text-left px-4 py-3 hover:bg-[#1e293b]/50 transition-colors flex items-start gap-3"
                      >
                        <div className="mt-0.5 shrink-0">
                          <ChevronRight
                            className={`w-3.5 h-3.5 text-[#64748b] transition-transform ${
                              isExpanded ? "rotate-90" : ""
                            }`}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium text-[#e2e8f0] truncate">
                              {article.title}
                            </span>
                            {article.source && (
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 h-5 shrink-0 border-[#722ed1]/20 text-[#722ed1]"
                              >
                                {article.source}
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-wrap">
                            {tags.slice(0, 4).map((tag, i) => (
                              <span
                                key={i}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-[#722ed1]/10 text-[#722ed1]/80"
                              >
                                {tag}
                              </span>
                            ))}
                            <span className="text-[10px] text-[#64748b]">
                              {article.created_at ? formatDate(article.created_at) : "-"}
                            </span>
                          </div>
                        </div>
                      </button>
                      {isExpanded && (
                        <div className="px-4 pb-4 pl-12 border-t border-[#1e293b]/50 pt-3">
                          <div
                            className="prose prose-invert max-w-none text-xs leading-relaxed"
                            dangerouslySetInnerHTML={{ __html: simpleMarkdown(article.content || "*无内容*") }}
                          />
                          <div className="mt-3 flex items-center gap-3 text-[10px] text-[#64748b]">
                            {article.source && <span>来源: {article.source}</span>}
                            {article.source_ref && <span>参考: {article.source_ref}</span>}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Pagination */}
            {!articlesLoading && kbTotal > pageSize && (
              <div className="border-t border-[#1e293b] px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-[#64748b]">
                  第 {currentPage}/{totalPages} 页，共 {kbTotal} 篇
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    onClick={handlePrevPage}
                    disabled={kbOffset === 0}
                    variant="outline"
                    className="border-[#1e293b] text-[#94a3b8] h-8 text-xs disabled:opacity-40"
                  >
                    上一页
                  </Button>
                  <Button
                    onClick={handleNextPage}
                    disabled={kbOffset + pageSize >= kbTotal}
                    variant="outline"
                    className="border-[#1e293b] text-[#94a3b8] h-8 text-xs disabled:opacity-40"
                  >
                    下一页
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* FMEA Panel */}
        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <Hash className="w-4 h-4 text-[#faad14]" />
              FMEA 高 RPN 条目
            </CardTitle>
            <CardDescription className="text-[10px] text-[#64748b]">
              按 RPN 降序排列
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {fmeaLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 text-[#722ed1] animate-spin" />
              </div>
            ) : fmeaEntries.length === 0 ? (
              <div className="px-4 py-6 text-center">
                <p className="text-xs text-[#64748b]">暂无 FMEA 条目</p>
              </div>
            ) : (
              <div className="space-y-0">
                {fmeaEntries.map((entry) => (
                  <div
                    key={entry.id}
                    className="px-4 py-2.5 border-b border-[#1e293b] last:border-b-0 hover:bg-[#1e293b]/30 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-[#e2e8f0] truncate max-w-[160px]">
                        {entry.item}
                      </span>
                      <span
                        className="text-xs font-mono font-bold"
                        style={{ color: rpnColor(entry.rpn) }}
                      >
                        RPN {entry.rpn}
                      </span>
                    </div>
                    <p className="text-[10px] text-[#64748b] line-clamp-1 mb-1">
                      {entry.failure_mode}
                    </p>
                    <div className="flex items-center gap-2 text-[10px] text-[#64748b]">
                      <span>S:{entry.severity}</span>
                      <span>O:{entry.occurence}</span>
                      <span>D:{entry.detection}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

// ─── MISRA Trends Tab Component ─────────────────────────────────────────────



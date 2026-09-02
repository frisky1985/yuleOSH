"use client";

// 新建 /dashboard/knowledge-base 子页面：把 dashboard 落地页上的
// "知识库" tab 拎成独立路由，便于决策者顶栏在「管理」组下从任何子页
// 直达。 内容委托给既有 KnowledgeBaseTab（不再维护两份）。
//
// 注意：KnowledgeBaseTab 本身不带页面外壳（无 bg / 无居中容器），
// 因此这里套一层与其他子页（requirements / traceability 等）完全一致的
// 外壳，消除此前"知识库页宽度比其他页更宽"的视觉不一致。
import { KnowledgeBaseTab } from "@/components/dashboard/knowledge-base-tab";

export default function KnowledgeBasePage() {
  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <KnowledgeBaseTab />
      </div>
    </div>
  );
}

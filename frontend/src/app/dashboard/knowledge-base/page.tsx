"use client";

// 新建 /dashboard/knowledge-base 子页面：把 dashboard 落地页上的
// "知识库" tab 拎成独立路由，便于决策者顶栏在「管理」组下从任何子页
// 直达。 内容委托给既有 KnowledgeBaseTab（不再维护两份）。
import { KnowledgeBaseTab } from "@/components/dashboard/knowledge-base-tab";

export default function KnowledgeBasePage() {
  return <KnowledgeBaseTab />;
}

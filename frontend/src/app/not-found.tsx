import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-[#0a0e17] flex items-center justify-center p-4">
      <div className="text-center max-w-md">
        <div className="text-6xl font-black mb-4">
          <span className="text-[#722ed1]">4</span><span className="text-[#1677ff]">0</span><span className="text-[#722ed1]">4</span>
        </div>
        <h1 className="text-xl font-bold text-[#e2e8f0] mb-2">项目未找到</h1>
        <p className="text-sm text-[#94a3b8] mb-8">
          你访问的项目不存在或已被删除
        </p>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-semibold text-sm bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 transition-all"
        >
          返回 Dashboard
        </Link>
      </div>
    </div>
  );
}

"use client";

// Mini coverage progress bar (A6: extracted from dashboard/page.tsx)
export function MiniCoverageBar({ label, pct, color }: { label: string; pct: number; color?: string }) {
  const barColor = color || (pct >= 80 ? "#10b981" : pct >= 50 ? "#faad14" : "#ff4d4f");
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-[#94a3b8] w-16 truncate shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-[#1e293b] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(pct, 100)}%`, background: barColor }}
        />
      </div>
      <span className="text-xs font-mono font-medium w-11 text-right" style={{ color: barColor }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  );
}

// ─── SWE Status Card ─────────────────────────────────────────────────────────


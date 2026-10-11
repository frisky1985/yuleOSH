"use client";

import { useMemo } from "react";
import type { ASPICEStatusResponse } from "@/lib/api";

// ─── V-Model process definitions ────────────────────────────────────────
// ASPICE V-model pairs: left branch ↔ right branch (verification pairs)

interface VNode {
  id: string;
  label: string;
  short: string;
  side: "left" | "right" | "top";
  level: number;
  description: string;
}

const V_NODES: VNode[] = [
  { id: "SYS.1", label: "SYS.1", short: "需求获取", side: "top", level: 0, description: "System Requirements Elicitation" },
  { id: "SYS.2", label: "SYS.2", short: "系统需求", side: "left", level: 1, description: "System Requirements Analysis" },
  { id: "SYS.3", label: "SYS.3", short: "系统架构", side: "left", level: 2, description: "System Architectural Design" },
  { id: "SWE.1", label: "SWE.1", short: "软件需求", side: "left", level: 3, description: "Software Requirements Analysis" },
  { id: "SWE.2", label: "SWE.2", short: "软件架构", side: "left", level: 4, description: "Software Architectural Design" },
  { id: "SWE.3", label: "SWE.3", short: "详细设计", side: "left", level: 5, description: "Software Detailed Design" },
  { id: "SWE.4", label: "SWE.4", short: "单元测试", side: "right", level: 5, description: "Software Unit Verification" },
  { id: "SWE.5", label: "SWE.5", short: "集成测试", side: "right", level: 4, description: "Software Integration & Verification" },
  { id: "SWE.6", label: "SWE.6", short: "软件合格", side: "right", level: 3, description: "Software Qualification" },
  { id: "SYS.4", label: "SYS.4", short: "系统集成", side: "right", level: 2, description: "System Integration & Verification" },
  { id: "SYS.5", label: "SYS.5", short: "系统合格", side: "right", level: 1, description: "System Qualification" },
];

// Verification pairs: left ↔ right traceability
const TRACE_PAIRS: [string, string][] = [
  ["SYS.2", "SYS.5"],
  ["SYS.3", "SYS.4"],
  ["SWE.1", "SWE.6"],
  ["SWE.2", "SWE.5"],
  ["SWE.3", "SWE.4"],
];

// Gate definitions: between which levels
interface GateDef {
  id: string;
  label: string;
  y: number;
}

const GATES: GateDef[] = [
  { id: "G0", label: "G0", y: 80 },
  { id: "G1", label: "G1", y: 160 },
  { id: "G3", label: "G3", y: 240 },
  { id: "G5", label: "G5", y: 320 },
  { id: "G7", label: "G7", y: 400 },
  { id: "G10", label: "G10", y: 480 },
];

// ─── Layout constants ───────────────────────────────────────────────────
const SVG_W = 880;
const SVG_H = 560;
const LEFT_X = 160;
const RIGHT_X = 720;
const TOP_X = 440;
const LEVEL_Y = [55, 145, 235, 325, 415, 505];
const NODE_R = 28;

// ─── Status → color mapping ─────────────────────────────────────────────
function nodeColor(status?: string): string {
  switch (status) {
    case "good":
      return "#10b981";
    case "warning":
      return "#f59e0b";
    case "critical":
      return "#ef4444";
    default:
      return "#475569";
  }
}

function nodeBg(status?: string): string {
  switch (status) {
    case "good":
      return "#10b98118";
    case "warning":
      return "#f59e0b18";
    case "critical":
      return "#ef444418";
    default:
      return "#1e293b";
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────
function nodeX(side: "left" | "right" | "top"): number {
  if (side === "left") return LEFT_X;
  if (side === "right") return RIGHT_X;
  return TOP_X;
}

function nodePos(node: VNode): { x: number; y: number } {
  return { x: nodeX(node.side), y: LEVEL_Y[node.level] };
}

// ─── Component ───────────────────────────────────────────────────────────
export function VModelDiagram({
  data,
  selectedNode,
  onSelectNode,
}: {
  data?: ASPICEStatusResponse;
  selectedNode?: string | null;
  onSelectNode?: (id: string | null) => void;
}) {
  const familyMap = useMemo(() => {
    if (!data?.families) return {} as Record<string, { status: string; coverage: number }>;
    const map: Record<string, { status: string; coverage: number }> = {};
    for (const [family, info] of Object.entries(data.families)) {
      for (const [dimKey, dimVal] of Object.entries(info.dimensions || {})) {
        const prefix = dimKey.split(".")[0] + "." + dimKey.split(".")[1]?.split(" ")[0];
        map[dimKey] = {
          status: info.status || "unknown",
          coverage: dimVal.coverage_pct ?? 0,
        };
      }
      // Also map by family prefix for aggregate coloring
      map[family] = { status: info.status || "unknown", coverage: info.avg_coverage ?? 0 };
    }
    return map;
  }, [data]);

  function getStatus(nodeId: string): string | undefined {
    // Try exact match first, then family prefix
    const direct = familyMap[nodeId];
    if (direct) return direct.status;
    const prefix = nodeId.split(".")[0];
    const fam = familyMap[prefix];
    return fam?.status;
  }

  return (
    <svg
      viewBox={`0 0 ${SVG_W} ${SVG_H}`}
      className="w-full h-auto"
      style={{ maxHeight: 560 }}
    >
      <defs>
        <marker id="arrow-right" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6" fill="#722ed1" opacity="0.6" />
        </marker>
        <marker id="arrow-left" markerWidth="8" markerHeight="6" refX="0" refY="3" orient="auto">
          <path d="M8,0 L0,3 L8,6" fill="#722ed1" opacity="0.6" />
        </marker>
      </defs>

      {/* V-shape guide lines */}
      <path
        d={`M${TOP_X},${LEVEL_Y[0]} L${LEFT_X},${LEVEL_Y[5]} L${RIGHT_X},${LEVEL_Y[5]}`}
        fill="none"
        stroke="#1e293b"
        strokeWidth="2"
        strokeDasharray="6,4"
      />
      <path
        d={`M${TOP_X},${LEVEL_Y[0]} L${RIGHT_X},${LEVEL_Y[5]}`}
        fill="none"
        stroke="#1e293b"
        strokeWidth="2"
        strokeDasharray="6,4"
      />

      {/* Traceability arrows (horizontal pairs) */}
      {TRACE_PAIRS.map(([leftId, rightId]) => {
        const leftNode = V_NODES.find((n) => n.id === leftId)!;
        const rightNode = V_NODES.find((n) => n.id === rightId)!;
        const lp = nodePos(leftNode);
        const rp = nodePos(rightNode);
        const y = lp.y;
        const isHighlighted = selectedNode === leftId || selectedNode === rightId;
        return (
          <g key={`trace-${leftId}-${rightId}`}>
            <line
              x1={lp.x + NODE_R + 4}
              y1={y}
              x2={rp.x - NODE_R - 4}
              y2={y}
              stroke={isHighlighted ? "#722ed1" : "#722ed140"}
              strokeWidth={isHighlighted ? 2 : 1}
              strokeDasharray={isHighlighted ? "none" : "4,3"}
              markerEnd="url(#arrow-right)"
              markerStart="url(#arrow-left)"
            />
            <text
              x={(lp.x + rp.x) / 2}
              y={y - 6}
              textAnchor="middle"
              className="text-[9px]"
              fill="#722ed1"
              opacity={isHighlighted ? 1 : 0.5}
            >
              追溯
            </text>
          </g>
        );
      })}

      {/* Gate indicators (left side) */}
      {GATES.map((gate) => (
        <g key={gate.id}>
          <rect
            x={28}
            y={gate.y - 10}
            width={36}
            height={20}
            rx={4}
            fill="#0f172a"
            stroke="#334155"
            strokeWidth={1}
          />
          <text
            x={46}
            y={gate.y + 4}
            textAnchor="middle"
            fill="#94a3b8"
            className="text-[10px] font-mono"
          >
            {gate.label}
          </text>
        </g>
      ))}

      {/* Process nodes */}
      {V_NODES.map((node) => {
        const pos = nodePos(node);
        const status = getStatus(node.id);
        const color = nodeColor(status);
        const bg = nodeBg(status);
        const isSelected = selectedNode === node.id;
        return (
          <g
            key={node.id}
            className="cursor-pointer"
            onClick={() => onSelectNode?.(isSelected ? null : node.id)}
          >
            {/* Selection ring */}
            {isSelected && (
              <circle
                cx={pos.x}
                cy={pos.y}
                r={NODE_R + 5}
                fill="none"
                stroke="#722ed1"
                strokeWidth={2}
                opacity={0.8}
              />
            )}
            {/* Node circle */}
            <circle
              cx={pos.x}
              cy={pos.y}
              r={NODE_R}
              fill={bg}
              stroke={color}
              strokeWidth={2}
            />
            {/* Node label */}
            <text
              x={pos.x}
              y={pos.y - 4}
              textAnchor="middle"
              fill={color}
              className="text-[11px] font-bold"
            >
              {node.label}
            </text>
            <text
              x={pos.x}
              y={pos.y + 10}
              textAnchor="middle"
              fill="#94a3b8"
              className="text-[8px]"
            >
              {node.short}
            </text>
            {/* Description tooltip on hover (side labels) */}
            {node.side === "left" && (
              <text
                x={pos.x - NODE_R - 8}
                y={pos.y + 4}
                textAnchor="end"
                fill="#64748b"
                className="text-[8px]"
              >
                {node.description}
              </text>
            )}
            {node.side === "right" && (
              <text
                x={pos.x + NODE_R + 8}
                y={pos.y + 4}
                textAnchor="start"
                fill="#64748b"
                className="text-[8px]"
              >
                {node.description}
              </text>
            )}
          </g>
        );
      })}

      {/* Branch labels */}
      <text x={LEFT_X} y={LEVEL_Y[5] + 30} textAnchor="middle" fill="#64748b" className="text-[10px]">
        开发阶段 →
      </text>
      <text x={RIGHT_X} y={LEVEL_Y[5] + 30} textAnchor="middle" fill="#64748b" className="text-[10px]">
        ← 验证阶段
      </text>
      <text x={TOP_X} y={LEVEL_Y[0] - 20} textAnchor="middle" fill="#94a3b8" className="text-[11px] font-bold">
        ASPICE V-Model
      </text>
    </svg>
  );
}

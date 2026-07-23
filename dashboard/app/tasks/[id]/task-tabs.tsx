"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import Markdown from "@/components/Markdown";
import type { CrossTaskRunRow, BaselineRow } from "@/lib/tasks";

type TabKey = "leaderboard" | "prompt";

// Unified row for the merged leaderboard.
export interface UnifiedRow {
  kind: "run" | "baseline";
  taskId: string;
  partition?: string;
  method: string;         // for baselines: method name; for runs: agent/model
  runId?: string;         // only for runs
  agent?: string | null;
  reasoningEffort?: string | null;
  primaryModel?: string | null;
  auprc?: number | null;
  auroc?: number | null;
  durationSeconds?: number | null;
  totalCostUsd?: number | null;
  note?: string;
}

type SortKey =
  | "kind" | "partition" | "method" | "auprc" | "auroc"
  | "durationSeconds" | "totalCostUsd";
type SortDir = "asc" | "desc";

function cmp(a: unknown, b: unknown, dir: SortDir): number {
  const aNull = a === null || a === undefined;
  const bNull = b === null || b === undefined;
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  if (typeof a === "number" && typeof b === "number") return dir === "asc" ? a - b : b - a;
  const as = String(a);
  const bs = String(b);
  return dir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
}

export default function TaskTabs({
  taskId,
  prompt,
  runs,
  baselines,
}: {
  taskId: string;
  prompt: string | undefined;
  runs: CrossTaskRunRow[];
  baselines: BaselineRow[];
}) {
  const [tab, setTab] = useState<TabKey>("leaderboard");
  const [sortKey, setSortKey] = useState<SortKey>("auprc");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [partitionFilter, setPartitionFilter] = useState<string>("all");
  const [kindFilter, setKindFilter] = useState<"all" | "run" | "baseline">("all");

  const unified: UnifiedRow[] = useMemo(() => {
    const rows: UnifiedRow[] = [];
    for (const r of runs) {
      rows.push({
        kind: "run",
        taskId: r.taskId,
        partition: r.partition,
        method: [r.agent, r.primaryModel, r.reasoningEffort].filter(Boolean).join(" · ") || (r.primaryModel ?? "agent"),
        runId: r.runId,
        agent: r.agent,
        reasoningEffort: r.reasoningEffort,
        primaryModel: r.primaryModel,
        auprc: r.auprc,
        auroc: r.auroc,
        durationSeconds: r.durationSeconds,
        totalCostUsd: r.totalCostUsd,
      });
    }
    for (const b of baselines) {
      rows.push({
        kind: "baseline",
        taskId: b.taskId,
        partition: b.partition,
        method: b.method,
        auprc: b.auprc,
        auroc: b.auroc,
        note: b.note,
      });
    }
    return rows;
  }, [runs, baselines]);

  const partitions = useMemo(() => {
    const s = new Set<string>();
    unified.forEach((r) => r.partition && s.add(r.partition));
    return Array.from(s).sort();
  }, [unified]);

  const filtered = useMemo(() => {
    let out = unified;
    if (partitionFilter !== "all") out = out.filter((r) => r.partition === partitionFilter);
    if (kindFilter !== "all") out = out.filter((r) => r.kind === kindFilter);
    return out;
  }, [unified, partitionFilter, kindFilter]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => cmp((a as unknown as Record<string, unknown>)[sortKey],
                            (b as unknown as Record<string, unknown>)[sortKey], sortDir));
    return copy;
  }, [filtered, sortKey, sortDir]);

  function toggle(k: SortKey) {
    if (sortKey === k) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(k);
      setSortDir(k === "auprc" || k === "auroc" || k === "durationSeconds" || k === "totalCostUsd" ? "desc" : "asc");
    }
  }

  const SortHead = ({ k, label, align = "left" }: { k: SortKey; label: string; align?: "left" | "right" }) => (
    <th
      className={`${align === "right" ? "text-right" : "text-left"} px-4 py-2 cursor-pointer select-none hover:text-stone-800`}
      onClick={() => toggle(k)}
    >
      {label}
      {sortKey === k && <span className="ml-1 text-stone-400">{sortDir === "asc" ? "▲" : "▼"}</span>}
    </th>
  );

  return (
    <div className="space-y-6">
      {/* Tab bar */}
      <div className="border-b border-stone-200 flex gap-6 text-sm">
        <button
          onClick={() => setTab("leaderboard")}
          className={`pb-3 -mb-px border-b-2 transition-colors font-medium ${
            tab === "leaderboard"
              ? "border-stone-900 text-stone-900"
              : "border-transparent text-stone-500 hover:text-stone-800"
          }`}
        >
          Leaderboard
          <span className="ml-2 text-xs text-stone-400 font-normal">
            {runs.length} run{runs.length === 1 ? "" : "s"} · {baselines.length} baseline{baselines.length === 1 ? "" : "s"}
          </span>
        </button>
        <button
          onClick={() => setTab("prompt")}
          className={`pb-3 -mb-px border-b-2 transition-colors font-medium ${
            tab === "prompt"
              ? "border-stone-900 text-stone-900"
              : "border-transparent text-stone-500 hover:text-stone-800"
          }`}
        >
          Prompt
        </button>
      </div>

      {tab === "leaderboard" && (
        <div className="space-y-4">
          {partitions.length > 1 && (
            <div className="flex gap-3 text-xs flex-wrap">
              <div className="flex items-center gap-2">
                <span className="uppercase tracking-wider text-stone-500 font-semibold">Partition</span>
                <select
                  value={partitionFilter}
                  onChange={(e) => setPartitionFilter(e.target.value)}
                  className="border border-stone-300 rounded px-2 py-1 text-xs bg-white"
                >
                  <option value="all">all</option>
                  {partitions.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <span className="uppercase tracking-wider text-stone-500 font-semibold">Kind</span>
                <select
                  value={kindFilter}
                  onChange={(e) => setKindFilter(e.target.value as "all" | "run" | "baseline")}
                  className="border border-stone-300 rounded px-2 py-1 text-xs bg-white"
                >
                  <option value="all">both</option>
                  <option value="run">agent runs</option>
                  <option value="baseline">SOTA baselines</option>
                </select>
              </div>
            </div>
          )}

          <div className="border border-stone-200 bg-white rounded overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase tracking-wider font-semibold text-stone-500 border-b border-stone-200">
                <tr>
                  <SortHead k="kind" label="Kind" />
                  <SortHead k="partition" label="Partition" />
                  <SortHead k="method" label="Method / Agent" />
                  <SortHead k="auprc" label="AUPRC" align="right" />
                  <SortHead k="auroc" label="AUROC" align="right" />
                  <SortHead k="durationSeconds" label="Duration" align="right" />
                  <SortHead k="totalCostUsd" label="Cost" align="right" />
                </tr>
              </thead>
              <tbody>
                {sorted.map((r, i) => {
                  const isRun = r.kind === "run";
                  const linkTarget = isRun && r.runId ? `/tasks/${r.taskId}/runs/${r.runId}/` : null;
                  const bgClass = isRun
                    ? "hover:bg-stone-50 cursor-pointer"
                    : "bg-amber-50/40 hover:bg-amber-50";
                  return (
                    <tr
                      key={`${r.kind}-${r.method}-${r.partition ?? "_"}-${i}`}
                      className={`border-b border-stone-100 last:border-b-0 ${bgClass}`}
                      onClick={() => linkTarget && (window.location.href = linkTarget)}
                    >
                      <td className="px-4 py-2">
                        {isRun ? (
                          <span className="inline-block px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-semibold bg-blue-50 text-blue-800">
                            agent
                          </span>
                        ) : (
                          <span className="inline-block px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-semibold bg-amber-100 text-amber-900">
                            SOTA
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs text-stone-700">
                        {r.partition ?? "—"}
                      </td>
                      <td className="px-4 py-2">
                        {isRun && linkTarget ? (
                          <Link
                            href={linkTarget}
                            className="text-blue-700 hover:underline font-mono text-xs"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {r.method}
                            {r.runId && <span className="text-stone-400 ml-2">· {r.runId}</span>}
                          </Link>
                        ) : (
                          <span className="font-mono text-xs text-stone-800">{r.method}</span>
                        )}
                      </td>
                      <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                        {r.auprc !== null && r.auprc !== undefined ? r.auprc.toFixed(4) : "—"}
                      </td>
                      <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                        {r.auroc !== null && r.auroc !== undefined ? r.auroc.toFixed(4) : "—"}
                      </td>
                      <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                        {r.durationSeconds ? `${(r.durationSeconds / 60).toFixed(1)}m` : "—"}
                      </td>
                      <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                        {r.totalCostUsd !== null && r.totalCostUsd !== undefined
                          ? `$${r.totalCostUsd.toFixed(2)}`
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
                {sorted.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-4 text-sm text-stone-500 text-center">
                      No entries.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="text-xs text-stone-500">
            Click any agent-run row to see the full trace, method, and grader output.
          </div>
        </div>
      )}

      {tab === "prompt" && (
        <div className="border border-stone-200 bg-white rounded p-6">
          {prompt ? (
            <Markdown>{prompt}</Markdown>
          ) : (
            <p className="text-sm text-stone-500 italic">No prompt.md for this task.</p>
          )}
        </div>
      )}
    </div>
  );
}

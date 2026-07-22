"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { CrossTaskRunRow } from "@/lib/tasks";

type SortKey =
  | "taskId"
  | "partition"
  | "agent"
  | "primaryModel"
  | "reasoningEffort"
  | "auprc"
  | "auroc"
  | "totalCostUsd"
  | "numTurns"
  | "durationSeconds"
  | "runId";
type SortDir = "asc" | "desc";

function cmp(a: unknown, b: unknown, dir: SortDir): number {
  const aNull = a === null || a === undefined;
  const bNull = b === null || b === undefined;
  if (aNull && bNull) return 0;
  if (aNull) return 1;   // nulls always sort last, regardless of direction
  if (bNull) return -1;
  if (typeof a === "number" && typeof b === "number") {
    return dir === "asc" ? a - b : b - a;
  }
  const as = String(a);
  const bs = String(b);
  return dir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
}

export default function LeaderboardTable({ rows }: { rows: CrossTaskRunRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("auprc");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => cmp((a as unknown as Record<string, unknown>)[sortKey],
                            (b as unknown as Record<string, unknown>)[sortKey],
                            sortDir));
    return copy;
  }, [rows, sortKey, sortDir]);

  function toggle(key: SortKey) {
    if (key === sortKey) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDir(key === "auprc" || key === "auroc" || key === "totalCostUsd" || key === "numTurns" || key === "durationSeconds" ? "desc" : "asc");
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

  const graded = rows.filter((r) => r.hasGrade).length;

  return (
    <section>
      <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-3">
        Results ({graded} graded run{graded === 1 ? "" : "s"}) — click any column header to sort
      </div>
      <div className="border border-stone-200 bg-white rounded overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wider font-semibold text-stone-500 border-b border-stone-200">
            <tr>
              <SortHead k="taskId" label="Task" />
              <SortHead k="partition" label="Partition" />
              <SortHead k="agent" label="Agent" />
              <SortHead k="primaryModel" label="Model" />
              <SortHead k="reasoningEffort" label="Reasoning" />
              <SortHead k="auprc" label="AUPRC" align="right" />
              <SortHead k="auroc" label="AUROC" align="right" />
              <SortHead k="totalCostUsd" label="Cost" align="right" />
              <SortHead k="numTurns" label="Turns" align="right" />
              <SortHead k="durationSeconds" label="Duration" align="right" />
              <SortHead k="runId" label="Run" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr
                key={`${r.taskId}-${r.runId}-${r.partition ?? "_"}-${i}`}
                className="border-b border-stone-100 last:border-b-0 hover:bg-stone-50"
              >
                <td className="px-4 py-2">
                  <Link href={`/tasks/${r.taskId}/`} className="text-stone-800 hover:underline">
                    <code className="font-mono text-xs">{r.taskId}</code>
                  </Link>
                </td>
                <td className="px-4 py-2 font-mono text-xs text-stone-700">
                  {r.partition ?? "—"}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-stone-800">
                  {r.agent ?? "—"}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-stone-800">
                  {r.primaryModel ?? "—"}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-stone-800">
                  {r.reasoningEffort ?? "—"}
                </td>
                <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                  {r.auprc !== null && r.auprc !== undefined ? r.auprc.toFixed(4) : "—"}
                </td>
                <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                  {r.auroc !== null && r.auroc !== undefined ? r.auroc.toFixed(4) : "—"}
                </td>
                <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                  {r.totalCostUsd !== null && r.totalCostUsd !== undefined
                    ? `$${r.totalCostUsd.toFixed(2)}`
                    : "—"}
                </td>
                <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                  {r.numTurns ?? "—"}
                </td>
                <td className="text-right px-4 py-2 font-mono tabular-nums text-stone-800">
                  {r.durationSeconds ? `${(r.durationSeconds / 60).toFixed(1)}m` : "—"}
                </td>
                <td className="px-4 py-2">
                  <Link
                    href={`/tasks/${r.taskId}/runs/${r.runId}/`}
                    className="text-blue-700 hover:underline font-mono text-xs"
                  >
                    {r.runId}
                  </Link>
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-4 text-sm text-stone-500 text-center">
                  No runs yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

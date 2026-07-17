import Link from "next/link";
import { loadAllRuns, loadAllTasks } from "@/lib/tasks";

export default function Home() {
  const tasks = loadAllTasks();
  const runs = loadAllRuns();
  return (
    <main className="max-w-5xl mx-auto px-6 py-10 space-y-10">
      <header>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
          BioModelBench
        </div>
        <h1 className="text-3xl font-semibold text-stone-900 leading-tight">
          An agentic benchmark for biological modeling
        </h1>
        <p className="text-base text-stone-700 mt-4 leading-relaxed max-w-3xl">
          Each task hands a coding agent a data setup and asks it to build a
          predictor from scratch — picking foundation models, online
          resources, and features on its own — then submits blind for
          grading. A deterministic grader compares the submission to hidden
          ground truth.
        </p>
      </header>

      <section>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-3">
          Results ({runs.filter((r) => r.hasGrade).length} graded run{runs.filter((r) => r.hasGrade).length === 1 ? "" : "s"})
        </div>
        <div className="border border-stone-200 bg-white rounded overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wider font-semibold text-stone-500 border-b border-stone-200">
              <tr>
                <th className="text-left px-4 py-2">Task</th>
                <th className="text-left px-4 py-2">Partition</th>
                <th className="text-left px-4 py-2">Model</th>
                <th className="text-right px-4 py-2">AUPRC</th>
                <th className="text-right px-4 py-2">AUROC</th>
                <th className="text-right px-4 py-2">Cost</th>
                <th className="text-right px-4 py-2">Turns</th>
                <th className="text-right px-4 py-2">Duration</th>
                <th className="text-left px-4 py-2">Run</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r, i) => (
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
                    {r.primaryModel ?? "—"}
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
              {runs.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-4 text-sm text-stone-500 text-center">
                    No runs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-3">
          Tasks
        </div>
        <div className="space-y-3">
          {tasks.map((t) => {
            const graded = t.runs.filter((r) => r.hasGrade);
            const best = graded.reduce<null | number>(
              (m, r) =>
                r.auprc !== null && r.auprc !== undefined
                  ? Math.max(m ?? -Infinity, r.auprc)
                  : m,
              null,
            );
            return (
              <Link
                key={t.id}
                href={`/tasks/${t.id}/`}
                className="block border border-stone-200 bg-white hover:border-stone-400 transition-colors rounded"
              >
                <div className="px-5 py-4">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h2 className="font-semibold text-stone-900">
                      {t.meta.title ?? t.id}
                    </h2>
                    {t.meta.modality && (
                      <span className="text-xs uppercase tracking-wider text-stone-500">
                        {t.meta.modality}
                      </span>
                    )}
                    {t.meta.compute_tier && (
                      <span className="text-xs uppercase tracking-wider text-stone-500">
                        {t.meta.compute_tier}
                      </span>
                    )}
                    {t.meta.headline_metric && (
                      <span className="text-xs uppercase tracking-wider text-stone-500">
                        headline: {t.meta.headline_metric}
                      </span>
                    )}
                  </div>
                  {t.meta.description && (
                    <p className="text-sm text-stone-600 mt-2 whitespace-pre-line">
                      {t.meta.description.trim().slice(0, 320)}
                      {t.meta.description.length > 320 ? "…" : ""}
                    </p>
                  )}
                  <div className="text-xs text-stone-500 mt-2 flex flex-wrap gap-4">
                    <span>id: <code className="font-mono">{t.id}</code></span>
                    <span>runs: {t.runs.length}</span>
                    {best !== null && <span>best AUPRC: {best.toFixed(4)}</span>}
                  </div>
                </div>
              </Link>
            );
          })}
          {tasks.length === 0 && (
            <p className="text-sm text-stone-500">No tasks found.</p>
          )}
        </div>
      </section>
    </main>
  );
}

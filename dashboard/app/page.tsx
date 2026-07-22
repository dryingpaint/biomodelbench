import Link from "next/link";
import { loadAllRuns, loadAllTasks } from "@/lib/tasks";
import LeaderboardTable from "./leaderboard-table";

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

      <LeaderboardTable rows={runs} />

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

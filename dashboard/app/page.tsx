import Link from "next/link";
import { loadAllTasks, type TaskSummary } from "@/lib/tasks";
import { loadChartRows, SotaChart } from "./sota-chart";

function TaskCard({ task }: { task: TaskSummary }) {
  const graded = task.runs.filter((r) => r.hasGrade);
  const bestAgentAuprc = graded.reduce<number | null>(
    (m, r) => r.auprc !== null && r.auprc !== undefined
      ? Math.max(m ?? -Infinity, r.auprc)
      : m,
    null,
  );
  return (
    <Link
      href={`/tasks/${task.id}/`}
      className="block border border-stone-200 bg-white hover:border-stone-400 hover:shadow-sm transition-all rounded"
    >
      <div className="px-5 py-4">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="font-semibold text-stone-900">{task.meta.title ?? task.id}</h2>
          {task.meta.modality && (
            <span className="text-xs uppercase tracking-wider text-stone-500">{task.meta.modality}</span>
          )}
          {task.meta.compute_tier && (
            <span className="text-xs uppercase tracking-wider text-stone-500">{task.meta.compute_tier}</span>
          )}
        </div>
        {task.meta.description && (
          <p className="text-sm text-stone-600 mt-2 whitespace-pre-line">
            {task.meta.description.trim().slice(0, 320)}
            {task.meta.description.length > 320 ? "…" : ""}
          </p>
        )}
        <div className="text-xs text-stone-500 mt-3 flex flex-wrap gap-4">
          <span>id: <code className="font-mono">{task.id}</code></span>
          <span>graded runs: {graded.length} / {task.runs.length}</span>
          {bestAgentAuprc !== null && (
            <span>best agent AUPRC: <span className="font-mono text-stone-800">{bestAgentAuprc.toFixed(4)}</span></span>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function Home() {
  const tasks = loadAllTasks();
  const chartRows = loadChartRows();

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
          predictor from scratch. A deterministic grader compares the
          submission to hidden ground truth and reports per-partition metrics
          alongside published SOTA baselines.
        </p>
      </header>

      <SotaChart rows={chartRows} />

      <section>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-3">
          Tasks
        </div>
        <div className="grid gap-3">
          {tasks.map((t) => <TaskCard key={t.id} task={t} />)}
          {tasks.length === 0 && (
            <p className="text-sm text-stone-500">No tasks found.</p>
          )}
        </div>
      </section>
    </main>
  );
}

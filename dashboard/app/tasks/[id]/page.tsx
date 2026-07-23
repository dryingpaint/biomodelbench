import Link from "next/link";
import { notFound } from "next/navigation";
import {
  listTaskIds,
  loadTaskSummary,
  loadRunSummary,
  loadTaskBaselines,
  type CrossTaskRunRow,
} from "@/lib/tasks";
import TaskTabs from "./task-tabs";

export const dynamicParams = false;

export async function generateStaticParams() {
  return listTaskIds().map((id) => ({ id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = loadTaskSummary(id);
  return { title: `${t?.meta.title ?? id} · BioModelBench` };
}

// Build task-scoped run rows with per-partition expansion for multi-partition graders.
function loadTaskRuns(taskId: string): CrossTaskRunRow[] {
  const task = loadTaskSummary(taskId);
  if (!task) return [];
  const NOT_PARTITION = new Set([
    "auprc", "auroc", "brier", "coverage", "positive_rate",
    "test_variants_total", "test_variants_scored", "n_total", "n_scored",
    "per_chrom", "per_fold", "baselines", "reference_baselines",
    "gap_vs_best_baseline", "gap_vs_best_supervised", "gap_vs_best_zero_shot",
    "generalization_gap",
  ]);
  const rows: CrossTaskRunRow[] = [];
  const fs = require("fs") as typeof import("fs");
  const path = require("path") as typeof import("path");
  const REPO_ROOT = path.resolve(process.cwd(), "..");
  for (const r of task.runs) {
    const gradePath = path.join(REPO_ROOT, "tasks", taskId, "runs", r.runId, "grade.json");
    let grade: Record<string, unknown> | undefined;
    try { grade = JSON.parse(fs.readFileSync(gradePath, "utf-8")) as Record<string, unknown>; } catch { /* no grade */ }
    if (!grade) {
      rows.push({
        ...r,
        taskId,
        taskTitle: task.meta.title ?? taskId,
        headlineMetric: task.meta.headline_metric,
      });
      continue;
    }
    // Detect nested per-partition sections
    const partitions: { name: string; metrics: Record<string, unknown> }[] = [];
    for (const [k, v] of Object.entries(grade)) {
      if (NOT_PARTITION.has(k)) continue;
      if (v && typeof v === "object" && !Array.isArray(v)) {
        const obj = v as Record<string, unknown>;
        if ("auprc" in obj || "auroc" in obj) partitions.push({ name: k, metrics: obj });
      }
    }
    if (partitions.length === 0) {
      rows.push({
        ...r,
        taskId,
        taskTitle: task.meta.title ?? taskId,
        headlineMetric: task.meta.headline_metric,
      });
    } else {
      for (const p of partitions) {
        rows.push({
          ...r,
          auprc: (p.metrics["auprc"] as number | undefined) ?? null,
          auroc: (p.metrics["auroc"] as number | undefined) ?? null,
          brier: (p.metrics["brier"] as number | undefined) ?? null,
          coverage: (p.metrics["coverage"] as number | undefined) ?? null,
          taskId,
          taskTitle: task.meta.title ?? taskId,
          headlineMetric: task.meta.headline_metric,
          partition: p.name,
        });
      }
    }
  }
  return rows;
}

export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const task = loadTaskSummary(id);
  if (!task) notFound();

  const runs = loadTaskRuns(id);
  const baselines = loadTaskBaselines(id);

  return (
    <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
      <header>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
          <Link href="/tasks/" className="hover:text-stone-900">Tasks</Link> /{" "}
          <code className="font-mono">{task.id}</code>
        </div>
        <h1 className="text-2xl font-semibold text-stone-900">{task.meta.title ?? task.id}</h1>
        {task.meta.description && (
          <p className="text-sm text-stone-600 mt-2 max-w-3xl whitespace-pre-line">
            {task.meta.description.trim()}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-stone-600">
          {task.meta.compute_tier && (
            <div>
              <span className="uppercase tracking-wider font-semibold text-stone-500 mr-1">Tier</span>
              <span className="font-mono text-stone-900">{task.meta.compute_tier}</span>
            </div>
          )}
          {task.meta.headline_metric && (
            <div>
              <span className="uppercase tracking-wider font-semibold text-stone-500 mr-1">Scoring</span>
              <span className="font-mono text-stone-900">{task.meta.headline_metric}</span>
            </div>
          )}
          {task.meta.wall_clock_hours !== undefined && (
            <div>
              <span className="uppercase tracking-wider font-semibold text-stone-500 mr-1">Wall clock</span>
              <span className="font-mono text-stone-900">~{task.meta.wall_clock_hours}h</span>
            </div>
          )}
        </div>
      </header>

      <TaskTabs
        taskId={id}
        prompt={task.prompt}
        runs={runs}
        baselines={baselines}
      />
    </main>
  );
}

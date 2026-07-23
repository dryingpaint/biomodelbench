import Link from "next/link";
import fs from "fs";
import path from "path";
import {
  loadAllTasks,
  loadTaskBaselines,
  type TaskSummary,
  type BaselineRow,
} from "@/lib/tasks";

// For each task, compute:
//   - best agent score per partition (max AUPRC across all its runs)
//   - best SOTA baseline per partition (max AUPRC in reference_baselines)
// Return a flat set of (task, partition, best_agent, best_sota, metric) rows
// for the SOTA-comparison chart.
interface ChartRow {
  taskId: string;
  taskTitle: string;
  partition: string;
  metric: "auprc" | "auroc";
  bestAgent: number | null;
  bestSota: number | null;
  sotaMethod?: string;
  agentModel?: string;
  agentRunId?: string;
}

function loadChartRows(): ChartRow[] {
  const tasks = loadAllTasks();
  const rows: ChartRow[] = [];
  const REPO_ROOT = path.resolve(process.cwd(), "..");
  const NOT_PARTITION = new Set([
    "auprc", "auroc", "brier", "coverage", "positive_rate",
    "test_variants_total", "test_variants_scored", "n_total", "n_scored",
    "per_chrom", "per_fold", "baselines", "reference_baselines",
    "gap_vs_best_baseline", "gap_vs_best_supervised", "gap_vs_best_zero_shot",
    "generalization_gap",
  ]);

  for (const task of tasks) {
    // Aggregate best agent score per partition
    const bestAgentByPartition = new Map<string, { auprc: number | null; auroc: number | null; model?: string; runId: string }>();
    // Also track "flat" (single-partition) tasks under partition="_all"
    for (const run of task.runs) {
      if (!run.hasGrade) continue;
      const gradePath = path.join(REPO_ROOT, "tasks", task.id, "runs", run.runId, "grade.json");
      let grade: Record<string, unknown> | undefined;
      try { grade = JSON.parse(fs.readFileSync(gradePath, "utf-8")) as Record<string, unknown>; } catch { continue; }
      const partitions: { name: string; auprc: number | null; auroc: number | null }[] = [];
      for (const [k, v] of Object.entries(grade)) {
        if (NOT_PARTITION.has(k)) continue;
        if (v && typeof v === "object" && !Array.isArray(v)) {
          const o = v as Record<string, unknown>;
          if ("auprc" in o || "auroc" in o) {
            partitions.push({
              name: k,
              auprc: (o["auprc"] as number | null | undefined) ?? null,
              auroc: (o["auroc"] as number | null | undefined) ?? null,
            });
          }
        }
      }
      if (partitions.length === 0) {
        // Flat grade
        partitions.push({
          name: "_all",
          auprc: (grade["auprc"] as number | null | undefined) ?? null,
          auroc: (grade["auroc"] as number | null | undefined) ?? null,
        });
      }
      for (const p of partitions) {
        const cur = bestAgentByPartition.get(p.name);
        const better = !cur ||
          (p.auprc !== null && (cur.auprc === null || p.auprc > cur.auprc));
        if (better) {
          bestAgentByPartition.set(p.name, {
            auprc: p.auprc,
            auroc: p.auroc,
            model: run.primaryModel ?? undefined,
            runId: run.runId,
          });
        }
      }
    }

    // Aggregate best SOTA per partition
    const baselines: BaselineRow[] = loadTaskBaselines(task.id);
    const bestSotaByPartition = new Map<string, { auprc: number | null; auroc: number | null; method: string }>();
    for (const b of baselines) {
      const cur = bestSotaByPartition.get(b.partition);
      const bAuprc = b.auprc ?? null;
      const better = !cur ||
        (bAuprc !== null && (cur.auprc === null || bAuprc > (cur.auprc ?? 0)));
      if (better) {
        bestSotaByPartition.set(b.partition, {
          auprc: bAuprc,
          auroc: b.auroc ?? null,
          method: b.method,
        });
      }
    }

    // Emit a chart row per partition that has either an agent score or SOTA
    const allPartitions = new Set<string>([
      ...bestAgentByPartition.keys(),
      ...bestSotaByPartition.keys(),
    ]);
    for (const p of allPartitions) {
      const agent = bestAgentByPartition.get(p);
      const sota = bestSotaByPartition.get(p);
      // Pick primary metric: prefer AUPRC unless neither side has it
      const useAuprc = (agent?.auprc !== undefined && agent?.auprc !== null) ||
                       (sota?.auprc !== undefined && sota?.auprc !== null);
      rows.push({
        taskId: task.id,
        taskTitle: task.meta.title ?? task.id,
        partition: p === "_all" ? "" : p,
        metric: useAuprc ? "auprc" : "auroc",
        bestAgent: useAuprc ? (agent?.auprc ?? null) : (agent?.auroc ?? null),
        bestSota: useAuprc ? (sota?.auprc ?? null) : (sota?.auroc ?? null),
        sotaMethod: sota?.method,
        agentModel: agent?.model,
        agentRunId: agent?.runId,
      });
    }
  }
  return rows;
}

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

function SotaChart({ rows }: { rows: ChartRow[] }) {
  if (rows.length === 0) return null;

  // Bar layout parameters
  const rowHeight = 30;
  const labelW = 320;
  const barW = 340;
  const rightPad = 60;
  const totalW = labelW + barW + rightPad;
  const totalH = rows.length * rowHeight + 30;

  // Normalize each row on its own [0, max(agent, sota)] scale? No — better on [0, 1]
  // for AUPRC/AUROC (both are naturally 0-1). Draw agent bar in blue, SOTA bar in amber.

  return (
    <section>
      <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-3">
        Best agent vs. published SOTA — per task partition
      </div>
      <div className="border border-stone-200 bg-white rounded p-5 overflow-x-auto">
        <svg width={totalW} height={totalH} className="text-stone-800">
          {/* axis */}
          <line x1={labelW} y1={20} x2={labelW + barW} y2={20} stroke="#d6d3d1" strokeWidth={1} />
          {[0, 0.25, 0.5, 0.75, 1.0].map((t) => (
            <g key={t}>
              <line x1={labelW + t * barW} y1={16} x2={labelW + t * barW} y2={totalH - 10} stroke="#e7e5e4" strokeWidth={1} />
              <text x={labelW + t * barW} y={12} textAnchor="middle" fontSize={9} fill="#78716c">{t.toFixed(2)}</text>
            </g>
          ))}
          {rows.map((r, i) => {
            const y = 30 + i * rowHeight;
            const agentW = r.bestAgent !== null ? Math.max(0, Math.min(1, r.bestAgent)) * barW : 0;
            const sotaW = r.bestSota !== null ? Math.max(0, Math.min(1, r.bestSota)) * barW : 0;
            const partLabel = r.partition ? ` (${r.partition})` : "";
            return (
              <g key={`${r.taskId}-${r.partition}-${i}`}>
                <text x={labelW - 8} y={y + 12} textAnchor="end" fontSize={11} fill="#292524">
                  {r.taskId}<tspan fill="#78716c">{partLabel}</tspan>
                </text>
                {/* SOTA bar (amber, behind) */}
                {r.bestSota !== null && (
                  <>
                    <rect x={labelW} y={y + 4} width={sotaW} height={8} fill="#fbbf24" opacity={0.7} />
                    <text x={labelW + sotaW + 4} y={y + 11} fontSize={10} fill="#78716c">
                      SOTA {r.bestSota.toFixed(3)}
                    </text>
                  </>
                )}
                {/* Agent bar (blue, in front) */}
                {r.bestAgent !== null && (
                  <>
                    <rect x={labelW} y={y + 14} width={agentW} height={8} fill="#3b82f6" />
                    <text x={labelW + agentW + 4} y={y + 21} fontSize={10} fill="#1e40af">
                      agent {r.bestAgent.toFixed(3)}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </svg>
        <div className="flex gap-6 mt-4 text-xs text-stone-600">
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 bg-blue-500 rounded-sm"></span>
            Best agent score (any model, any effort)
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 bg-amber-400 rounded-sm opacity-70"></span>
            Best published SOTA (from task's reference_baselines)
          </div>
          <div className="text-stone-500">All bars on [0, 1]; metric is AUPRC where available, else AUROC.</div>
        </div>
      </div>
    </section>
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

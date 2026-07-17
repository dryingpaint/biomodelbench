import fs from "fs";
import path from "path";
import yaml from "js-yaml";

const SAFE = /^[A-Za-z0-9._-]+$/;
export const REPO_ROOT = path.resolve(process.cwd(), "..");
const TASKS_DIR = path.join(REPO_ROOT, "tasks");

export interface TaskYaml {
  id: string;
  title?: string;
  modality?: string;
  compute_tier?: string;
  headline_metric?: string;
  description?: string;
  wall_clock_hours?: number;
  sources?: Record<string, string>;
  anti_leak?: { policy?: string };
}

export interface RunSummary {
  runId: string;
  hasGrade: boolean;
  hasMethod: boolean;
  auprc?: number | null;
  auroc?: number | null;
  brier?: number | null;
  coverage?: number | null;
  gapVsBestBaseline?: { name: string; baseline_auprc: number; delta_auprc: number };
  primaryModel?: string | null;
  totalCostUsd?: number | null;
  numTurns?: number | null;
  durationSeconds?: number | null;
}

export interface TaskSummary {
  id: string;
  meta: TaskYaml;
  readme?: string;
  prompt?: string;
  runs: RunSummary[];
}

export interface RunDetail extends RunSummary {
  grade?: Record<string, unknown>;
  method?: string;
  manifest?: Record<string, unknown>;
  runMeta?: Record<string, unknown>;
}

export interface CrossTaskRunRow extends RunSummary {
  taskId: string;
  taskTitle: string;
  headlineMetric?: string;
  partition?: string;  // for multi-partition graders (e.g. "traitgym", "clinvar")
}

/** Detect if a grade.json has nested per-partition metrics rather than a
 * flat top-level shape. Returns the partition names if so, else []. */
function detectPartitions(taskId: string, runId: string): string[] {
  const p = path.join(TASKS_DIR, taskId, "runs", runId, "grade.json");
  const grade = readJsonIfExists<Record<string, unknown>>(p);
  if (!grade) return [];
  // Skip these top-level keys that aren't partition names.
  const NOT_PARTITION = new Set([
    "auprc", "auroc", "brier", "coverage", "positive_rate",
    "test_variants_total", "test_variants_scored", "n_total", "n_scored",
    "per_chrom", "per_fold", "baselines", "reference_baselines",
    "gap_vs_best_baseline", "gap_vs_best_supervised", "gap_vs_best_zero_shot",
    "generalization_gap",
  ]);
  const partitions: string[] = [];
  for (const [k, v] of Object.entries(grade)) {
    if (NOT_PARTITION.has(k)) continue;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const obj = v as Record<string, unknown>;
      if ("auprc" in obj || "auroc" in obj) {
        partitions.push(k);
      }
    }
  }
  return partitions;
}

function loadRunPartitionSummary(
  taskId: string,
  runId: string,
  partition: string,
): RunSummary {
  const base = loadRunSummary(taskId, runId);
  const p = path.join(TASKS_DIR, taskId, "runs", runId, "grade.json");
  const grade = readJsonIfExists<Record<string, unknown>>(p);
  const slice = grade?.[partition] as Record<string, unknown> | undefined;
  if (!slice) return base;
  return {
    ...base,
    auprc: (slice["auprc"] as number | null | undefined) ?? null,
    auroc: (slice["auroc"] as number | null | undefined) ?? null,
    brier: (slice["brier"] as number | null | undefined) ?? null,
    coverage: (slice["coverage"] as number | null | undefined) ?? null,
  };
}

export function loadAllRuns(): CrossTaskRunRow[] {
  const rows: CrossTaskRunRow[] = [];
  for (const t of loadAllTasks()) {
    for (const r of t.runs) {
      const partitions = detectPartitions(t.id, r.runId);
      if (partitions.length === 0) {
        rows.push({
          ...r,
          taskId: t.id,
          taskTitle: t.meta.title ?? t.id,
          headlineMetric: t.meta.headline_metric,
        });
      } else {
        for (const p of partitions) {
          rows.push({
            ...loadRunPartitionSummary(t.id, r.runId, p),
            taskId: t.id,
            taskTitle: t.meta.title ?? t.id,
            headlineMetric: t.meta.headline_metric,
            partition: p,
          });
        }
      }
    }
  }
  return rows.sort((a, b) => (b.auprc ?? -Infinity) - (a.auprc ?? -Infinity));
}

function readTextIfExists(p: string): string | undefined {
  try {
    return fs.readFileSync(p, "utf-8");
  } catch {
    return undefined;
  }
}

function readJsonIfExists<T>(p: string): T | undefined {
  const t = readTextIfExists(p);
  if (t === undefined) return undefined;
  try {
    return JSON.parse(t) as T;
  } catch {
    return undefined;
  }
}

export function listTaskIds(): string[] {
  if (!fs.existsSync(TASKS_DIR)) return [];
  return fs
    .readdirSync(TASKS_DIR)
    .filter((n) => SAFE.test(n) && !n.startsWith("_"))
    .filter((n) => fs.statSync(path.join(TASKS_DIR, n)).isDirectory())
    .sort();
}

function loadYaml(p: string): TaskYaml | undefined {
  const t = readTextIfExists(p);
  if (t === undefined) return undefined;
  try {
    return yaml.load(t) as TaskYaml;
  } catch {
    return undefined;
  }
}

export function listRunIds(taskId: string): string[] {
  const runsDir = path.join(TASKS_DIR, taskId, "runs");
  if (!fs.existsSync(runsDir)) return [];
  return fs
    .readdirSync(runsDir)
    .filter((n) => SAFE.test(n))
    .filter((n) => fs.statSync(path.join(runsDir, n)).isDirectory())
    .sort();
}

export function loadRunSummary(taskId: string, runId: string): RunSummary {
  const dir = path.join(TASKS_DIR, taskId, "runs", runId);
  const grade = readJsonIfExists<Record<string, unknown>>(path.join(dir, "grade.json"));
  const meta = readJsonIfExists<Record<string, unknown>>(path.join(dir, "run_meta.json"));
  const hasMethod = fs.existsSync(path.join(dir, "method.md"));
  const gap = grade?.["gap_vs_best_baseline"] as
    | { name: string; baseline_auprc: number; delta_auprc: number }
    | undefined;
  const durationMs = meta?.["duration_ms"] as number | null | undefined;
  return {
    runId,
    hasGrade: grade !== undefined,
    hasMethod,
    auprc: (grade?.["auprc"] as number | null | undefined) ?? null,
    auroc: (grade?.["auroc"] as number | null | undefined) ?? null,
    brier: (grade?.["brier"] as number | null | undefined) ?? null,
    coverage: (grade?.["coverage"] as number | null | undefined) ?? null,
    gapVsBestBaseline: gap,
    primaryModel: (meta?.["primary_model"] as string | null | undefined) ?? null,
    totalCostUsd: (meta?.["total_cost_usd"] as number | null | undefined) ?? null,
    numTurns: (meta?.["num_turns"] as number | null | undefined) ?? null,
    durationSeconds: typeof durationMs === "number" ? durationMs / 1000 : null,
  };
}

export function loadRunDetail(taskId: string, runId: string): RunDetail {
  const summary = loadRunSummary(taskId, runId);
  const dir = path.join(TASKS_DIR, taskId, "runs", runId);
  return {
    ...summary,
    grade: readJsonIfExists<Record<string, unknown>>(path.join(dir, "grade.json")),
    method: readTextIfExists(path.join(dir, "method.md")),
    manifest: readJsonIfExists<Record<string, unknown>>(
      path.join(dir, "training_manifest.json"),
    ),
    runMeta: readJsonIfExists<Record<string, unknown>>(path.join(dir, "run_meta.json")),
  };
}

export function loadTaskSummary(taskId: string): TaskSummary | null {
  if (!SAFE.test(taskId)) return null;
  const dir = path.join(TASKS_DIR, taskId);
  const meta = loadYaml(path.join(dir, "task.yaml"));
  if (!meta) return null;
  return {
    id: taskId,
    meta,
    readme: readTextIfExists(path.join(dir, "README.md")),
    prompt: readTextIfExists(path.join(dir, "prompt.md")),
    runs: listRunIds(taskId).map((r) => loadRunSummary(taskId, r)),
  };
}

export function loadAllTasks(): TaskSummary[] {
  return listTaskIds()
    .map(loadTaskSummary)
    .filter((t): t is TaskSummary => t !== null);
}

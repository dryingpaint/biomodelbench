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
  const hasMethod = fs.existsSync(path.join(dir, "method.md"));
  const gap = grade?.["gap_vs_best_baseline"] as
    | { name: string; baseline_auprc: number; delta_auprc: number }
    | undefined;
  return {
    runId,
    hasGrade: grade !== undefined,
    hasMethod,
    auprc: (grade?.["auprc"] as number | null | undefined) ?? null,
    auroc: (grade?.["auroc"] as number | null | undefined) ?? null,
    brier: (grade?.["brier"] as number | null | undefined) ?? null,
    coverage: (grade?.["coverage"] as number | null | undefined) ?? null,
    gapVsBestBaseline: gap,
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

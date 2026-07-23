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
  agent?: string | null;          // "claude-code" | "codex" | "unknown"
  reasoningEffort?: string | null; // "none" | "low" | "medium" | "high" | null (claude has no equivalent)
  methodSummary?: string | null;   // first paragraph / summary line of method.md
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

/** A published-baseline row for the leaderboard. Same shape as a CrossTaskRunRow
 * so the two can be merged and sorted together. Naming: `isBaseline: true`
 * distinguishes it from agent runs. */
export interface BaselineRow {
  isBaseline: true;
  taskId: string;
  partition: string;
  method: string;   // e.g. "AlphaMissense", "CADD_v1.7_LR"
  auprc?: number | null;
  auroc?: number | null;
  note?: string;
}

/** Extract published-baseline rows from a task's reference_baselines
 * (typically found on every run's grade.json under `reference_baselines`).
 * They're task-level metadata — pull from any graded run. Returns [] if
 * no baselines are declared. */
export function loadTaskBaselines(taskId: string): BaselineRow[] {
  const runsDir = path.join(TASKS_DIR, taskId, "runs");
  if (!fs.existsSync(runsDir)) return [];
  // Find any graded run; baselines are identical across runs of the same task.
  let baselines: Record<string, unknown> | undefined;
  for (const runId of listRunIds(taskId)) {
    const grade = readJsonIfExists<Record<string, unknown>>(
      path.join(runsDir, runId, "grade.json"),
    );
    const b = grade?.["reference_baselines"];
    if (b && typeof b === "object" && !Array.isArray(b)) {
      baselines = b as Record<string, unknown>;
      break;
    }
  }
  if (!baselines) return [];
  const rows: BaselineRow[] = [];
  for (const [partition, section] of Object.entries(baselines)) {
    if (!section || typeof section !== "object" || Array.isArray(section)) continue;
    for (const [method, val] of Object.entries(section as Record<string, unknown>)) {
      if (method === "note") continue;
      // Two supported shapes:
      //   {method: {auprc: X, auroc: Y}}    ← v1
      //   {method: {AlphaMissense_AUROC: X}} ← v0 nested
      if (val && typeof val === "object" && !Array.isArray(val)) {
        const v = val as Record<string, unknown>;
        // Standard shape
        if ("auprc" in v || "auroc" in v) {
          rows.push({
            isBaseline: true,
            taskId,
            partition,
            method,
            auprc: (v["auprc"] as number | undefined) ?? null,
            auroc: (v["auroc"] as number | undefined) ?? null,
            note: (v["note"] as string | undefined),
          });
        } else {
          // Nested shape (method sub-scores like AlphaMissense_AUROC)
          for (const [subK, subV] of Object.entries(v)) {
            if (typeof subV === "number") {
              const isAuroc = subK.toLowerCase().includes("auroc");
              rows.push({
                isBaseline: true,
                taskId,
                partition,
                method: subK.replace(/_AUROC$|_AUPRC$/, ""),
                auprc: isAuroc ? null : subV,
                auroc: isAuroc ? subV : null,
              });
            }
          }
        }
      } else if (typeof val === "number") {
        // Flat scalar shape (evo-2 per-consequence table)
        rows.push({
          isBaseline: true,
          taskId,
          partition,
          method,
          auprc: null,
          auroc: val,
        });
      }
    }
  }
  return rows;
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

/** Peek at the first line of agent_log.jsonl to detect the agent framework
 * and (for codex) the reasoning effort setting. Falls back to run_id suffix
 * heuristics when the log is empty or missing. */
function detectAgentInfo(
  taskId: string,
  runId: string,
  primaryModel: string | null,
): { agent: string | null; reasoningEffort: string | null } {
  const logPath = path.join(TASKS_DIR, taskId, "runs", runId, "agent_log.jsonl");
  let agent: string | null = null;
  let reasoning: string | null = null;

  // 1. First-line inspection of agent_log.jsonl
  try {
    if (fs.existsSync(logPath)) {
      const fd = fs.openSync(logPath, "r");
      const buf = Buffer.alloc(2048);
      const n = fs.readSync(fd, buf, 0, buf.length, 0);
      fs.closeSync(fd);
      const firstLine = buf.slice(0, n).toString("utf-8").split("\n")[0];
      if (firstLine.trim().length) {
        const obj = JSON.parse(firstLine) as Record<string, unknown>;
        const t = obj["type"] as string | undefined;
        // Codex emits "thread.started" as its opening event
        if (t === "thread.started" || t?.startsWith("thread.")) {
          agent = "codex";
          // Codex's reasoning_effort is on the thread.started event itself
          const re = obj["reasoning_effort"] as string | undefined;
          if (re) reasoning = re;
        } else if (t === "system" && obj["subtype"] === "init") {
          // Claude-code's init event
          agent = "claude-code";
        }
      }
    }
  } catch { /* ignore */ }

  // 2. Fall back to run_id suffix inference
  if (!agent) {
    if (runId.includes("codex")) agent = "codex";
    else if (runId.includes("claude")) agent = "claude-code";
  }

  // 3. Fall back to primary_model prefix
  if (!agent && primaryModel) {
    if (primaryModel.startsWith("claude")) agent = "claude-code";
    else if (primaryModel.startsWith("gpt") || primaryModel.startsWith("o")) agent = "codex";
  }

  // 4. Reasoning effort inference from run_id suffix if we didn't get it from the log
  if (!reasoning && agent === "codex") {
    if (runId.endsWith("-low")) reasoning = "low";
    else if (runId.endsWith("-medium")) reasoning = "medium";
    else if (runId.endsWith("-high")) reasoning = "high";
    else reasoning = "default";
  }

  return { agent, reasoningEffort: reasoning };
}

/** Extract a short (~300 char) methodology summary from method.md:
 * skip the H1 heading + any "## Overview" or "## Goal" heading and grab
 * the first ~2 sentences of prose. Falls back to the first non-heading
 * paragraph. */
function extractMethodSummary(methodPath: string): string | null {
  let text: string;
  try { text = fs.readFileSync(methodPath, "utf-8"); } catch { return null; }
  const lines = text.split("\n");
  const paragraph: string[] = [];
  let inParagraph = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("#")) {
      if (inParagraph) break;
      continue;
    }
    if (line === "") {
      if (inParagraph) break;
      continue;
    }
    // Skip bullet lists / code fences at the start
    if (line.startsWith("```") || line.startsWith("- ") || line.startsWith("* ")) {
      if (inParagraph) break;
      continue;
    }
    paragraph.push(line);
    inParagraph = true;
    if (paragraph.join(" ").length > 280) break;
  }
  const summary = paragraph.join(" ").trim();
  if (!summary) return null;
  return summary.length > 320 ? summary.slice(0, 317) + "…" : summary;
}

export function loadRunSummary(taskId: string, runId: string): RunSummary {
  const dir = path.join(TASKS_DIR, taskId, "runs", runId);
  const grade = readJsonIfExists<Record<string, unknown>>(path.join(dir, "grade.json"));
  const meta = readJsonIfExists<Record<string, unknown>>(path.join(dir, "run_meta.json"));
  const methodPath = path.join(dir, "method.md");
  const hasMethod = fs.existsSync(methodPath);
  const methodSummary = hasMethod ? extractMethodSummary(methodPath) : null;
  const gap = grade?.["gap_vs_best_baseline"] as
    | { name: string; baseline_auprc: number; delta_auprc: number }
    | undefined;
  const durationMs = meta?.["duration_ms"] as number | null | undefined;
  const primaryModel = (meta?.["primary_model"] as string | null | undefined) ?? null;
  const { agent, reasoningEffort } = detectAgentInfo(taskId, runId, primaryModel);
  return {
    runId,
    hasGrade: grade !== undefined,
    hasMethod,
    auprc: (grade?.["auprc"] as number | null | undefined) ?? null,
    auroc: (grade?.["auroc"] as number | null | undefined) ?? null,
    brier: (grade?.["brier"] as number | null | undefined) ?? null,
    coverage: (grade?.["coverage"] as number | null | undefined) ?? null,
    gapVsBestBaseline: gap,
    primaryModel,
    totalCostUsd: (meta?.["total_cost_usd"] as number | null | undefined) ?? null,
    numTurns: (meta?.["num_turns"] as number | null | undefined) ?? null,
    durationSeconds: typeof durationMs === "number" ? durationMs / 1000 : null,
    agent,
    reasoningEffort,
    methodSummary,
  };
}

export interface TraceEvent {
  kind: "session_start" | "text" | "tool_call" | "tool_result" | "result" | "retry";
  session_id?: string;
  session_num?: number;   // 1-based sequential
  model?: string;
  summary: string;        // one-line summary
  detail?: string;        // optional expanded detail (bash cmd, tool inputs, etc)
  cost_usd?: number;
  num_turns?: number;
  exit_code?: number;
}

export interface TraceSummary {
  agent: "claude-code" | "codex" | "unknown";
  total_events: number;
  session_count: number;
  api_retry_count: number;
  tool_call_count: number;
  first_events: TraceEvent[]; // capped to 200 to keep pages light
}

/** Parse agent_log.jsonl into a bounded trace summary. Streams the file so
 * we don't load 10 MB+ into memory. Returns null if no log exists. */
export function loadTraceSummary(taskId: string, runId: string): TraceSummary | null {
  const logPath = path.join(TASKS_DIR, taskId, "runs", runId, "agent_log.jsonl");
  if (!fs.existsSync(logPath)) return null;
  const raw = fs.readFileSync(logPath, "utf-8");
  const lines = raw.split("\n").filter((l) => l.trim());

  let agent: TraceSummary["agent"] = "unknown";
  let sessionCount = 0;
  let apiRetryCount = 0;
  let toolCallCount = 0;
  const events: TraceEvent[] = [];
  const MAX = 200;

  // Detect agent from first event
  if (lines.length > 0) {
    try {
      const first = JSON.parse(lines[0]) as Record<string, unknown>;
      const t = first["type"] as string | undefined;
      if (t === "system" && first["subtype"] === "init") agent = "claude-code";
      else if (t === "thread.started" || t?.startsWith("thread.")) agent = "codex";
    } catch { /* ignore */ }
  }

  for (const line of lines) {
    let obj: Record<string, unknown>;
    try { obj = JSON.parse(line) as Record<string, unknown>; } catch { continue; }
    const t = obj["type"] as string | undefined;
    const s = obj["subtype"] as string | undefined;

    if (agent === "claude-code") {
      if (t === "system" && s === "init") {
        sessionCount++;
        if (events.length < MAX) {
          events.push({
            kind: "session_start",
            session_num: sessionCount,
            session_id: (obj["session_id"] as string | undefined) ?? undefined,
            model: (obj["model"] as string | undefined) ?? undefined,
            summary: `Session ${sessionCount} started (model=${obj["model"] ?? "?"})`,
          });
        }
      } else if (t === "system" && s === "api_retry") {
        apiRetryCount++;
      } else if (t === "assistant") {
        const msg = obj["message"] as Record<string, unknown> | undefined;
        const content = Array.isArray(msg?.["content"]) ? (msg!["content"] as Array<Record<string, unknown>>) : [];
        for (const block of content) {
          const bt = block["type"] as string | undefined;
          if (bt === "text" && events.length < MAX) {
            const text = (block["text"] as string | undefined) ?? "";
            events.push({ kind: "text", summary: text.slice(0, 200) + (text.length > 200 ? "…" : "") });
          } else if (bt === "tool_use") {
            toolCallCount++;
            if (events.length < MAX) {
              const name = (block["name"] as string | undefined) ?? "?";
              const input = block["input"];
              events.push({
                kind: "tool_call",
                summary: `${name}(${JSON.stringify(input).slice(0, 160)}${JSON.stringify(input).length > 160 ? "…" : ""})`,
              });
            }
          }
        }
      } else if (t === "user") {
        const msg = obj["message"] as Record<string, unknown> | undefined;
        const content = Array.isArray(msg?.["content"]) ? (msg!["content"] as Array<Record<string, unknown>>) : [];
        for (const block of content) {
          if (block["type"] === "tool_result" && events.length < MAX) {
            const c = block["content"];
            const text = typeof c === "string" ? c : Array.isArray(c) ? JSON.stringify(c).slice(0, 200) : "";
            events.push({ kind: "tool_result", summary: text.slice(0, 200) });
          }
        }
      } else if (t === "result") {
        if (events.length < MAX) {
          events.push({
            kind: "result",
            summary: `Session complete: turns=${obj["num_turns"] ?? "?"} cost=$${(obj["total_cost_usd"] as number | undefined)?.toFixed(4) ?? "?"}`,
            cost_usd: obj["total_cost_usd"] as number | undefined,
            num_turns: obj["num_turns"] as number | undefined,
          });
        }
      }
    } else if (agent === "codex") {
      if (t === "thread.started") {
        sessionCount++;
        if (events.length < MAX) {
          events.push({
            kind: "session_start",
            session_num: sessionCount,
            session_id: (obj["thread_id"] as string | undefined) ?? undefined,
            summary: `Thread started (id=${obj["thread_id"] ?? "?"})`,
          });
        }
      } else if (t === "item.completed") {
        const item = obj["item"] as Record<string, unknown> | undefined;
        const itype = item?.["type"] as string | undefined;
        if (itype === "agent_message" && events.length < MAX) {
          const text = (item?.["text"] as string | undefined) ?? "";
          events.push({ kind: "text", summary: text.slice(0, 200) + (text.length > 200 ? "…" : "") });
        } else if (itype === "command_execution") {
          toolCallCount++;
          if (events.length < MAX) {
            const cmd = (item?.["command"] as string | undefined) ?? "";
            const exit = item?.["exit_code"] as number | undefined;
            events.push({
              kind: "tool_call",
              summary: `bash: ${cmd.slice(0, 160)}${cmd.length > 160 ? "…" : ""}`,
              exit_code: exit,
              detail: (item?.["aggregated_output"] as string | undefined)?.slice(0, 500),
            });
          }
        } else if (itype === "web_search" && events.length < MAX) {
          toolCallCount++;
          const q = (item?.["query"] as string | undefined) ?? "";
          events.push({ kind: "tool_call", summary: `web_search: ${q.slice(0, 160)}` });
        }
      }
    }
  }

  return {
    agent,
    total_events: lines.length,
    session_count: sessionCount,
    api_retry_count: apiRetryCount,
    tool_call_count: toolCallCount,
    first_events: events,
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

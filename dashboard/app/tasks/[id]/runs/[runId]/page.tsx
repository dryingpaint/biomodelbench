import Link from "next/link";
import { notFound } from "next/navigation";
import { listTaskIds, listRunIds, loadRunDetail, loadTaskSummary, loadTraceSummary } from "@/lib/tasks";
import Markdown from "@/components/Markdown";

export const dynamicParams = false;

export async function generateStaticParams() {
  const params: { id: string; runId: string }[] = [];
  for (const id of listTaskIds()) {
    for (const runId of listRunIds(id)) {
      params.push({ id, runId });
    }
  }
  return params;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = await params;
  return { title: `${id}/${runId} · BioModelBench` };
}

interface MetricBlock {
  auprc?: number | null;
  auroc?: number | null;
  brier?: number | null;
  coverage?: number | null;
  positive_rate?: number | null;
}

interface RefBaseline {
  auprc?: number;
  auroc?: number;
  note?: string;
}

function isMetricBlock(v: unknown): v is MetricBlock {
  if (!v || typeof v !== "object" || Array.isArray(v)) return false;
  const o = v as Record<string, unknown>;
  return "auprc" in o || "auroc" in o;
}

// Detect nested per-partition graders (e.g., traitgym / clinvar). Returns
// the list of partition names with their metric slices, or [] if the grade
// is flat.
function collectPartitions(grade: Record<string, unknown> | undefined): {
  name: string;
  metrics: MetricBlock;
  refs?: Record<string, RefBaseline>;
}[] {
  if (!grade) return [];
  const NOT_PARTITION = new Set([
    "auprc", "auroc", "brier", "coverage", "positive_rate",
    "test_variants_total", "test_variants_scored", "n_total", "n_scored",
    "per_chrom", "per_fold", "baselines", "reference_baselines",
    "gap_vs_best_baseline", "gap_vs_best_supervised", "gap_vs_best_zero_shot",
    "generalization_gap",
  ]);
  const out: { name: string; metrics: MetricBlock; refs?: Record<string, RefBaseline> }[] = [];
  const refs = grade["reference_baselines"] as Record<string, unknown> | undefined;
  for (const [k, v] of Object.entries(grade)) {
    if (NOT_PARTITION.has(k)) continue;
    if (isMetricBlock(v)) {
      const partitionRef = refs && typeof refs[k] === "object" && !Array.isArray(refs[k])
        ? (refs[k] as Record<string, RefBaseline>)
        : undefined;
      out.push({ name: k, metrics: v, refs: partitionRef });
    }
  }
  return out;
}

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = await params;
  const task = loadTaskSummary(id);
  if (!task) notFound();
  const run = loadRunDetail(id, runId);

  const partitions = collectPartitions(run.grade);
  const isMulti = partitions.length > 0;
  const flatRefs = !isMulti
    ? (run.grade?.["reference_baselines"] as Record<string, RefBaseline> | undefined)
    : undefined;
  const perChrom = (run.grade?.["per_chrom"] as Array<Record<string, unknown>>) ?? [];

  return (
    <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
      <header>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
          <Link href="/tasks/" className="hover:text-stone-900">Tasks</Link> /{" "}
          <Link href={`/tasks/${task.id}/`} className="hover:text-stone-900">
            <code className="font-mono">{task.id}</code>
          </Link>{" "}
          / <code className="font-mono">{run.runId}</code>
        </div>
        <h1 className="text-2xl font-semibold text-stone-900">Run {run.runId}</h1>
      </header>

      {/* Meta cards (model / cost / turns / wall clock) — same for flat + multi */}
      <section className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
        {run.primaryModel && <Metric label="Model" value={run.primaryModel} hint="primary — by output tokens" />}
        {run.totalCostUsd !== null && run.totalCostUsd !== undefined && (
          <Metric label="Cost" value={`$${run.totalCostUsd.toFixed(2)}`} hint="total agent tokens" />
        )}
        {run.numTurns !== null && run.numTurns !== undefined && (
          <Metric label="Turns" value={String(run.numTurns)} hint="agent tool calls" />
        )}
        {run.durationSeconds !== null && run.durationSeconds !== undefined && (
          <Metric label="Wall clock" value={`${(run.durationSeconds / 60).toFixed(1)}m`} hint="agent runtime" />
        )}
      </section>

      {/* Metric cards + reference-baseline table PER PARTITION for multi-eval */}
      {isMulti &&
        partitions.map((p) => (
          <section key={p.name} className="space-y-4">
            <div className="text-xs uppercase tracking-wider font-semibold text-stone-500">
              Partition: <code className="font-mono text-stone-900">{p.name}</code>
              {p.metrics.positive_rate !== undefined && p.metrics.positive_rate !== null && (
                <span className="ml-2 text-stone-500">
                  · base rate {p.metrics.positive_rate.toFixed(2)}
                </span>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-4">
              <Metric label="AUPRC" value={fmt(p.metrics.auprc)} hint="headline" />
              <Metric label="AUROC" value={fmt(p.metrics.auroc)} hint="" />
              <Metric label="Brier" value={fmt(p.metrics.brier)} hint="lower is better" />
              <Metric label="Coverage" value={fmt(p.metrics.coverage)} hint="frac of rows scored" />
            </div>
            {p.refs && Object.keys(p.refs).length > 0 && (
              <RefTable
                agentAuprc={p.metrics.auprc}
                agentAuroc={p.metrics.auroc}
                refs={p.refs}
              />
            )}
          </section>
        ))}

      {/* Flat-grade metric cards + reference-baseline table */}
      {!isMulti && (
        <section className="grid gap-3 sm:grid-cols-4">
          <Metric label="AUPRC" value={fmt(run.auprc)} hint="headline" />
          <Metric label="AUROC" value={fmt(run.auroc)} hint="" />
          <Metric label="Brier" value={fmt(run.brier)} hint="lower is better" />
          <Metric label="Coverage" value={fmt(run.coverage)} hint="frac of rows scored" />
          {run.gapVsBestBaseline && (
            <Metric
              label={`Δ vs ${run.gapVsBestBaseline.name}`}
              value={`${run.gapVsBestBaseline.delta_auprc >= 0 ? "+" : ""}${run.gapVsBestBaseline.delta_auprc.toFixed(4)}`}
              hint={`baseline ${run.gapVsBestBaseline.baseline_auprc.toFixed(4)}`}
            />
          )}
        </section>
      )}

      {!isMulti && flatRefs && Object.keys(flatRefs).length > 0 && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Reference baselines
          </div>
          <RefTable agentAuprc={run.auprc} agentAuroc={run.auroc} refs={flatRefs} />
        </section>
      )}

      {perChrom.length > 0 && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Per-chromosome breakdown (leak sanity)
          </div>
          <div className="border border-stone-200 bg-white rounded overflow-hidden">
            <div className="grid grid-cols-[1fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-2 text-xs uppercase tracking-wider font-semibold text-stone-500 border-b border-stone-200">
              <div>chrom</div>
              <div className="text-right">n</div>
              <div className="text-right">positives</div>
              <div className="text-right">AUPRC</div>
              <div className="text-right">AUROC</div>
            </div>
            {perChrom.map((r) => (
              <div
                key={String(r.chrom)}
                className="grid grid-cols-[1fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-2 text-sm border-b border-stone-100 last:border-b-0"
              >
                <div className="font-mono text-stone-800">{String(r.chrom)}</div>
                <div className="text-right font-mono tabular-nums text-stone-800">{String(r.n)}</div>
                <div className="text-right font-mono tabular-nums text-stone-800">{String(r.positives)}</div>
                <div className="text-right font-mono tabular-nums text-stone-800">
                  {typeof r.auprc === "number" ? r.auprc.toFixed(4) : "—"}
                </div>
                <div className="text-right font-mono tabular-nums text-stone-800">
                  {typeof r.auroc === "number" ? r.auroc.toFixed(4) : "—"}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {run.method && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Agent&#39;s <code className="font-mono">method.md</code>
          </div>
          <div className="border border-stone-200 bg-white rounded p-5">
            <Markdown>{run.method}</Markdown>
          </div>
        </section>
      )}

      {run.manifest && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Training manifest (external resources touched)
          </div>
          <pre className="border border-stone-200 bg-white rounded p-5 text-xs text-stone-800 font-mono whitespace-pre-wrap overflow-x-auto">
            {JSON.stringify(run.manifest, null, 2)}
          </pre>
        </section>
      )}

      {(() => {
        const trace = loadTraceSummary(id, run.runId);
        if (!trace) return null;
        return (
          <section>
            <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
              Agent trace
            </div>
            <div className="border border-stone-200 bg-white rounded p-5 space-y-3">
              <div className="text-xs text-stone-600 grid grid-cols-2 md:grid-cols-5 gap-3">
                <div><div className="uppercase tracking-wider text-stone-400 text-[10px]">Agent</div><div className="font-mono">{trace.agent}</div></div>
                <div><div className="uppercase tracking-wider text-stone-400 text-[10px]">Sessions</div><div className="font-mono">{trace.session_count}</div></div>
                <div><div className="uppercase tracking-wider text-stone-400 text-[10px]">Tool calls</div><div className="font-mono">{trace.tool_call_count}</div></div>
                <div><div className="uppercase tracking-wider text-stone-400 text-[10px]">API retries</div><div className="font-mono">{trace.api_retry_count}</div></div>
                <div><div className="uppercase tracking-wider text-stone-400 text-[10px]">Log lines</div><div className="font-mono">{trace.total_events}</div></div>
              </div>
              <details className="text-xs">
                <summary className="cursor-pointer text-stone-700 hover:text-stone-900 font-medium py-1">
                  First {trace.first_events.length} events (click to expand)
                </summary>
                <div className="mt-3 space-y-1 font-mono text-[11px] leading-snug max-h-[600px] overflow-y-auto">
                  {trace.first_events.map((e, i) => {
                    const color =
                      e.kind === "session_start" ? "text-blue-700" :
                      e.kind === "text" ? "text-stone-800" :
                      e.kind === "tool_call" ? "text-emerald-700" :
                      e.kind === "tool_result" ? "text-stone-500" :
                      e.kind === "result" ? "text-purple-700" :
                      "text-orange-600";
                    return (
                      <div key={i} className={`py-1 border-b border-stone-100 last:border-b-0 ${color}`}>
                        <span className="text-stone-400 mr-2">[{e.kind}]</span>
                        {e.summary}
                        {e.exit_code !== undefined && e.exit_code !== 0 && (
                          <span className="text-red-600 ml-2">exit={e.exit_code}</span>
                        )}
                      </div>
                    );
                  })}
                  {trace.first_events.length >= 200 && (
                    <div className="text-stone-400 italic py-2">
                      … truncated at 200 events. Full log at{" "}
                      <code>tasks/{id}/runs/{run.runId}/agent_log.jsonl</code>
                    </div>
                  )}
                </div>
              </details>
            </div>
          </section>
        );
      })()}

      {task.prompt && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Prompt this run received
          </div>
          <div className="border border-stone-200 bg-white rounded p-5">
            <Markdown>{task.prompt}</Markdown>
          </div>
        </section>
      )}
    </main>
  );
}

function fmt(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return v.toFixed(4);
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="border border-stone-200 bg-white rounded px-4 py-3">
      <div className="text-xs uppercase tracking-wider font-semibold text-stone-500">{label}</div>
      <div className="text-lg font-semibold text-stone-900 mt-1 font-mono tabular-nums">
        {value}
      </div>
      <div className="text-xs text-stone-500 mt-0.5">{hint}</div>
    </div>
  );
}

function RefTable({
  agentAuprc,
  agentAuroc,
  refs,
}: {
  agentAuprc?: number | null;
  agentAuroc?: number | null;
  refs: Record<string, RefBaseline>;
}) {
  const rows = Object.entries(refs)
    .filter(([, r]) => typeof r === "object" && r !== null && ("auprc" in r || "auroc" in r))
    .filter(([, r]) => typeof (r as RefBaseline).auprc === "number")
    .sort(
      (a, b) =>
        ((b[1] as RefBaseline).auprc ?? 0) - ((a[1] as RefBaseline).auprc ?? 0),
    );
  return (
    <div className="border border-stone-200 bg-white rounded overflow-hidden">
      <div className="grid grid-cols-[2fr_1fr_1fr] gap-4 px-4 py-2 text-xs uppercase tracking-wider font-semibold text-stone-500 border-b border-stone-200">
        <div>Method</div>
        <div className="text-right">AUPRC</div>
        <div className="text-right">AUROC</div>
      </div>
      <div className="grid grid-cols-[2fr_1fr_1fr] gap-4 px-4 py-2 text-sm border-b border-stone-100 bg-amber-50 font-semibold">
        <div className="font-mono text-stone-900">Agent (this run)</div>
        <div className="text-right font-mono tabular-nums">{fmt(agentAuprc)}</div>
        <div className="text-right font-mono tabular-nums">{fmt(agentAuroc)}</div>
      </div>
      {rows.map(([name, r]) => {
        const rb = r as RefBaseline;
        return (
          <div
            key={name}
            className="grid grid-cols-[2fr_1fr_1fr] gap-4 px-4 py-2 text-sm border-b border-stone-100 last:border-b-0"
          >
            <div className="font-mono text-stone-800">{name}</div>
            <div className="text-right font-mono tabular-nums text-stone-800">
              {typeof rb.auprc === "number" ? rb.auprc.toFixed(4) : "—"}
            </div>
            <div className="text-right font-mono tabular-nums text-stone-800">
              {typeof rb.auroc === "number" ? rb.auroc.toFixed(4) : "—"}
            </div>
          </div>
        );
      })}
      {rows.length === 0 && (
        <div className="px-4 py-3 text-xs text-stone-500">
          No numeric reference baselines recorded for this partition.
        </div>
      )}
    </div>
  );
}

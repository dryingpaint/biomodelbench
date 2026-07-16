import Link from "next/link";
import { notFound } from "next/navigation";
import { listTaskIds, listRunIds, loadRunDetail, loadTaskSummary } from "@/lib/tasks";
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

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = await params;
  const task = loadTaskSummary(id);
  if (!task) notFound();
  const run = loadRunDetail(id, runId);

  const referenceBaselines =
    (run.grade?.["reference_baselines"] as Record<string, { auprc: number; auroc: number }>) ??
    undefined;
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

      <section className="grid gap-3 sm:grid-cols-3">
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

      {referenceBaselines && Object.keys(referenceBaselines).length > 0 && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Reference baselines
          </div>
          <div className="border border-stone-200 bg-white rounded overflow-hidden">
            <div className="grid grid-cols-[2fr_1fr_1fr] gap-4 px-4 py-2 text-xs uppercase tracking-wider font-semibold text-stone-500 border-b border-stone-200">
              <div>Method</div>
              <div className="text-right">AUPRC</div>
              <div className="text-right">AUROC</div>
            </div>
            <div className="grid grid-cols-[2fr_1fr_1fr] gap-4 px-4 py-2 text-sm border-b border-stone-100 bg-amber-50 font-semibold">
              <div className="font-mono text-stone-900">Agent (this run)</div>
              <div className="text-right font-mono tabular-nums">{fmt(run.auprc)}</div>
              <div className="text-right font-mono tabular-nums">{fmt(run.auroc)}</div>
            </div>
            {Object.entries(referenceBaselines)
              .sort((a, b) => b[1].auprc - a[1].auprc)
              .map(([name, r]) => (
                <div
                  key={name}
                  className="grid grid-cols-[2fr_1fr_1fr] gap-4 px-4 py-2 text-sm border-b border-stone-100 last:border-b-0"
                >
                  <div className="font-mono text-stone-800">{name}</div>
                  <div className="text-right font-mono tabular-nums text-stone-800">
                    {r.auprc.toFixed(4)}
                  </div>
                  <div className="text-right font-mono tabular-nums text-stone-800">
                    {r.auroc.toFixed(4)}
                  </div>
                </div>
              ))}
          </div>
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
                <div className="text-right font-mono tabular-nums text-stone-800">
                  {String(r.n)}
                </div>
                <div className="text-right font-mono tabular-nums text-stone-800">
                  {String(r.positives)}
                </div>
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

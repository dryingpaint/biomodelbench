import Link from "next/link";
import { notFound } from "next/navigation";
import { listTaskIds, loadTaskSummary } from "@/lib/tasks";
import Markdown from "@/components/Markdown";

export const dynamicParams = false;

export async function generateStaticParams() {
  return listTaskIds().map((id) => ({ id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = loadTaskSummary(id);
  return { title: `${t?.meta.title ?? id} · BioModelBench` };
}

export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const task = loadTaskSummary(id);
  if (!task) notFound();

  return (
    <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
      <header>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
          <Link href="/tasks/" className="hover:text-stone-900">Tasks</Link> /{" "}
          <code className="font-mono">{task.id}</code>
        </div>
        <h1 className="text-2xl font-semibold text-stone-900">{task.meta.title ?? task.id}</h1>
        {task.meta.description && (
          <p className="text-sm text-stone-700 mt-3 whitespace-pre-line max-w-3xl">
            {task.meta.description.trim()}
          </p>
        )}
      </header>

      <section>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
          Metadata
        </div>
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 text-sm">
          {task.meta.modality && <Field label="Modality" value={task.meta.modality} />}
          {task.meta.compute_tier && <Field label="Compute tier" value={task.meta.compute_tier} />}
          {task.meta.headline_metric && <Field label="Headline metric" value={task.meta.headline_metric} />}
          {task.meta.wall_clock_hours !== undefined && (
            <Field label="Wall clock" value={`~${task.meta.wall_clock_hours}h`} />
          )}
          {task.meta.sources?.train && <Field label="Train source" value={task.meta.sources.train} />}
          {task.meta.sources?.test && <Field label="Test source" value={task.meta.sources.test} />}
        </div>
        {task.meta.anti_leak?.policy && (
          <div className="mt-3 text-sm text-stone-700">
            <span className="text-xs uppercase tracking-wider font-semibold text-stone-500 mr-2">
              Anti-leak
            </span>
            <span className="whitespace-pre-line">{task.meta.anti_leak.policy}</span>
          </div>
        )}
      </section>

      <section>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
          Runs ({task.runs.length})
        </div>
        <div className="border border-stone-200 bg-white rounded overflow-hidden">
          <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-2 text-xs uppercase tracking-wider font-semibold text-stone-500 border-b border-stone-200">
            <div>Run ID</div>
            <div className="text-right">AUPRC</div>
            <div className="text-right">AUROC</div>
            <div className="text-right">Coverage</div>
            <div className="text-right">Δ best baseline</div>
          </div>
          {task.runs.length === 0 && (
            <div className="px-4 py-3 text-sm text-stone-500">No runs recorded yet.</div>
          )}
          {task.runs.map((r) => (
            <Link
              key={r.runId}
              href={`/tasks/${task.id}/runs/${r.runId}/`}
              className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-2 text-sm border-b border-stone-100 last:border-b-0 hover:bg-stone-50"
            >
              <div className="font-mono text-stone-900 truncate">{r.runId}</div>
              <div className="text-right font-mono tabular-nums text-stone-800">
                {r.auprc !== null && r.auprc !== undefined ? r.auprc.toFixed(4) : "—"}
              </div>
              <div className="text-right font-mono tabular-nums text-stone-800">
                {r.auroc !== null && r.auroc !== undefined ? r.auroc.toFixed(4) : "—"}
              </div>
              <div className="text-right font-mono tabular-nums text-stone-800">
                {r.coverage !== null && r.coverage !== undefined ? r.coverage.toFixed(2) : "—"}
              </div>
              <div className="text-right font-mono tabular-nums text-stone-800">
                {r.gapVsBestBaseline
                  ? `${r.gapVsBestBaseline.delta_auprc >= 0 ? "+" : ""}${r.gapVsBestBaseline.delta_auprc.toFixed(4)}`
                  : "—"}
              </div>
            </Link>
          ))}
        </div>
      </section>

      {task.prompt && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Prompt shipped to the agent (<code className="font-mono">prompt.md</code>)
          </div>
          <div className="border border-stone-200 bg-white rounded p-5">
            <Markdown>{task.prompt}</Markdown>
          </div>
        </section>
      )}

      {task.readme && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Task README
          </div>
          <div className="border border-stone-200 bg-white rounded p-5">
            <Markdown>{task.readme}</Markdown>
          </div>
        </section>
      )}
    </main>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-stone-200 bg-white rounded px-3 py-2">
      <div className="text-xs uppercase tracking-wider font-semibold text-stone-500">{label}</div>
      <div className="text-sm text-stone-900 mt-0.5 break-words">{value}</div>
    </div>
  );
}

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
    <main className="max-w-4xl mx-auto px-6 py-10 space-y-8">
      <header>
        <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
          <Link href="/tasks/" className="hover:text-stone-900">Tasks</Link> /{" "}
          <code className="font-mono">{task.id}</code>
        </div>
        <h1 className="text-2xl font-semibold text-stone-900">{task.meta.title ?? task.id}</h1>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-stone-600">
          {task.meta.compute_tier && (
            <div>
              <span className="uppercase tracking-wider font-semibold text-stone-500 mr-1">
                Tier
              </span>
              <span className="font-mono text-stone-900">{task.meta.compute_tier}</span>
            </div>
          )}
          {task.meta.headline_metric && (
            <div>
              <span className="uppercase tracking-wider font-semibold text-stone-500 mr-1">
                Scoring
              </span>
              <span className="font-mono text-stone-900">{task.meta.headline_metric}</span>
              <span className="text-stone-500">
                {" "}(deterministic — see <code className="font-mono">grade.py</code>)
              </span>
            </div>
          )}
          {task.meta.wall_clock_hours !== undefined && (
            <div>
              <span className="uppercase tracking-wider font-semibold text-stone-500 mr-1">
                Wall clock
              </span>
              <span className="font-mono text-stone-900">~{task.meta.wall_clock_hours}h</span>
            </div>
          )}
        </div>
      </header>

      {task.prompt && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Prompt (<code className="font-mono">prompt.md</code>, verbatim)
          </div>
          <div className="border border-stone-200 bg-white rounded p-6">
            <Markdown>{task.prompt}</Markdown>
          </div>
        </section>
      )}

      {task.runs.length > 0 && (
        <section>
          <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
            Runs
          </div>
          <ul className="text-sm space-y-1">
            {task.runs.map((r) => (
              <li key={r.runId}>
                <Link
                  href={`/tasks/${task.id}/runs/${r.runId}/`}
                  className="text-blue-700 hover:underline font-mono text-xs"
                >
                  {r.runId}
                </Link>
                {r.primaryModel && (
                  <span className="text-stone-500 ml-2 font-mono text-xs">
                    · {r.primaryModel}
                  </span>
                )}
                {r.auprc !== null && r.auprc !== undefined && (
                  <span className="text-stone-800 ml-2 font-mono tabular-nums text-xs">
                    · AUPRC {r.auprc.toFixed(4)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

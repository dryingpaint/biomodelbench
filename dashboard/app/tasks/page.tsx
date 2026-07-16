import Link from "next/link";
import { loadAllTasks } from "@/lib/tasks";

export default function TasksIndex() {
  const tasks = loadAllTasks();
  return (
    <main className="max-w-5xl mx-auto px-6 py-10">
      <div className="text-xs uppercase tracking-wider font-semibold text-stone-500 mb-2">
        Tasks
      </div>
      <h1 className="text-2xl font-semibold text-stone-900 mb-6">All tasks</h1>
      <div className="space-y-3">
        {tasks.map((t) => (
          <Link
            key={t.id}
            href={`/tasks/${t.id}/`}
            className="block border border-stone-200 bg-white hover:border-stone-400 rounded"
          >
            <div className="px-5 py-4">
              <div className="flex items-center gap-3 flex-wrap">
                <h2 className="font-semibold text-stone-900">{t.meta.title ?? t.id}</h2>
                <span className="text-xs uppercase tracking-wider text-stone-500">
                  {t.meta.modality} · {t.meta.compute_tier}
                </span>
              </div>
              <div className="text-xs text-stone-500 mt-1">
                <code className="font-mono">{t.id}</code> · {t.runs.length} run{t.runs.length === 1 ? "" : "s"}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}

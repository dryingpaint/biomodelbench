import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm text-stone-800 leading-relaxed space-y-3 max-w-none [&_h1]:text-2xl [&_h1]:font-semibold [&_h1]:mt-4 [&_h1]:mb-2 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:mt-6 [&_h2]:mb-2 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:mt-4 [&_h3]:mb-1 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:font-mono [&_code]:text-xs [&_code]:bg-stone-100 [&_code]:px-1 [&_code]:rounded [&_pre]:bg-stone-900 [&_pre]:text-stone-100 [&_pre]:p-3 [&_pre]:rounded [&_pre]:overflow-x-auto [&_pre_code]:bg-transparent [&_pre_code]:text-inherit [&_a]:text-blue-700 [&_a]:underline [&_table]:border-collapse [&_th]:border [&_th]:border-stone-300 [&_th]:px-2 [&_th]:py-1 [&_th]:bg-stone-100 [&_td]:border [&_td]:border-stone-200 [&_td]:px-2 [&_td]:py-1 [&_strong]:font-semibold">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

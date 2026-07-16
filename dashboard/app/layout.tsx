import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "BioModelBench",
  description: "Agentic benchmark for biological modeling.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <nav className="border-b border-stone-200 bg-white">
          <div className="max-w-5xl mx-auto px-6 py-3 flex items-baseline gap-6 text-sm">
            <Link href="/" className="font-semibold text-stone-900">
              BioModelBench
            </Link>
            <Link href="/tasks/" className="text-stone-600 hover:text-stone-900">
              Tasks
            </Link>
            <a
              href="https://github.com/dryingpaint/biomodelbench"
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto text-stone-600 hover:text-stone-900"
            >
              GitHub
            </a>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}

import type { NextConfig } from "next";

// GitHub Pages serves the repo at /<repo>/ on <user>.github.io. Set
// PAGES_BASE_PATH in the Actions workflow so the built HTML uses the right
// absolute-path prefix. Locally (`npm run dev`) the var is unset and the
// site serves from /.
const basePath = process.env.PAGES_BASE_PATH || undefined;

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  basePath,
  assetPrefix: basePath,
  // Expose basePath to client bundles as NEXT_PUBLIC_BASE_PATH so
  // event handlers (e.g. row-click navigation) can prepend it.
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath ?? "",
  },
};

export default nextConfig;

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
};

export default nextConfig;

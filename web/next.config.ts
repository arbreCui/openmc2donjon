import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Honour an env-supplied build-output dir so local verification can
  // write to ``.next-build/`` without trampling the dev server's
  // ``.next/`` cache. See `npm run build:verify` and web/README.md.
  // Falls back to Next's default when the env var is unset, so CI's
  // ``npm run build`` keeps writing to ``.next/`` as expected.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
};

export default nextConfig;

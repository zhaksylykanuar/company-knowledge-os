/** @type {import('next').NextConfig} */

// Same-origin proxy: the browser calls /api/* (and /health) on the WEB origin,
// and Next proxies to the backend server-side. This makes the session cookie
// first-party across Railway's separate api/web domains (SameSite=Lax, no
// SameSite=None needed). FOUNDEROS_API_PROXY_TARGET is a server-only env var so
// the backend origin is never shipped to the browser.
const apiProxyTarget =
  process.env.FOUNDEROS_API_PROXY_TARGET?.trim() ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` },
      { source: "/health", destination: `${apiProxyTarget}/health` }
    ];
  }
};

export default nextConfig;

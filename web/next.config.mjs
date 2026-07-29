/** @type {import('next').NextConfig} */

// Same-origin proxy: the browser calls /api/* (and /health) on the WEB origin,
// and Next proxies to the backend server-side. This makes the session cookie
// first-party while the local web and API processes use separate ports.
// FOUNDEROS_API_PROXY_TARGET is a server-only env var, so the backend origin is
// never shipped to the browser.
const apiProxyTarget =
  process.env.FOUNDEROS_API_PROXY_TARGET?.trim() ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  "http://127.0.0.1:8765";

const isProduction = process.env.NODE_ENV === "production";
export function buildBrowserSecurityHeaders(production) {
  const contentSecurityPolicy = [
    "default-src 'self'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "form-action 'self' https://github.com",
    "img-src 'self' data: https:",
    `script-src 'self' 'unsafe-inline'${production ? "" : " 'unsafe-eval'"}`,
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    `connect-src 'self'${production ? "" : " ws: wss:"}`
  ].join("; ");

  const headers = [
    { key: "Content-Security-Policy", value: contentSecurityPolicy },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    {
      key: "Permissions-Policy",
      value: "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" }
  ];
  if (production) {
    headers.push({
      key: "Strict-Transport-Security",
      value: "max-age=31536000; includeSubDomains"
    });
  }
  return headers;
}

const browserSecurityHeaders = buildBrowserSecurityHeaders(isProduction);

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [{ source: "/:path*", headers: browserSecurityHeaders }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` },
      { source: "/health/:path*", destination: `${apiProxyTarget}/health/:path*` }
    ];
  }
};

export default nextConfig;

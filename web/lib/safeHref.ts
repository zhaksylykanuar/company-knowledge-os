// Untrusted, server-provided URLs (GitHub source links, evidence refs,
// external result URLs) are rendered as anchor hrefs. Source text is treated
// as untrusted, so a value like `javascript:...` must never become an
// executable/clickable link. safeHref returns the URL only when it parses as
// a well-formed http(s) URL, and null otherwise so callers render a
// non-clickable fallback instead.

const SAFE_PROTOCOLS = new Set(["http:", "https:"]);

export function safeHref(url: string | null | undefined): string | null {
  if (typeof url !== "string") {
    return null;
  }

  const trimmed = url.trim();
  if (!trimmed) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }

  if (!SAFE_PROTOCOLS.has(parsed.protocol)) {
    return null;
  }

  return trimmed;
}

// Setup redirects carry one-time state and must only ever leave FounderOS for
// the canonical GitHub web origin. A generic http(s) check is not sufficient
// for this higher-trust navigation boundary.
export function safeGitHubLaunchHref(
  url: string | null | undefined
): string | null {
  const href = safeHref(url);
  if (href === null) {
    return null;
  }

  const parsed = new URL(href);
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "github.com" ||
    parsed.port !== "" ||
    parsed.username !== "" ||
    parsed.password !== ""
  ) {
    return null;
  }
  return href;
}

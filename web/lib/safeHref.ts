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

import type { ReactNode } from "react";

import { safeHref } from "../lib/safeHref";

type SourceLinkProps = {
  url: string | null | undefined;
  children: ReactNode;
  className?: string;
};

// Renders an anchor only when the (untrusted, server-provided) URL is a
// well-formed http(s) link. Unsafe or malformed values (javascript:, data:,
// vbscript:, empty, relative) render as non-clickable text so they can never
// become an executable href.
export function SourceLink({
  url,
  children,
  className = "source-link"
}: SourceLinkProps) {
  const href = safeHref(url);

  if (href === null) {
    return <span className={`${className} source-link--unavailable`}>{children}</span>;
  }

  return (
    <a className={className} href={href} rel="noreferrer" target="_blank">
      {children}
    </a>
  );
}

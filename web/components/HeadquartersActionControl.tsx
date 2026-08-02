import Link from "next/link";

import type { HeadquartersAction } from "../lib/headquarters";

/** Renders only the action and role boundary supplied by the server. */
export function HeadquartersActionControl({
  action
}: {
  action: HeadquartersAction;
}) {
  if (action.enabled && action.target) {
    return (
      <Link className="headquarters-primary-action" href={action.target}>
        <span>{action.label}</span><span aria-hidden="true">→</span>
      </Link>
    );
  }
  return (
    <button
      className="headquarters-primary-action"
      disabled
      title={action.disabled_reason ?? undefined}
      type="button"
    >
      <span>{action.label}</span><span aria-hidden="true">—</span>
    </button>
  );
}

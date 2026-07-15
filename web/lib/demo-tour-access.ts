export const DEMO_TOUR_PATH = "/demo" as const;

export function isDemoTourEnabled(
  nodeEnv: string | undefined,
  enabledFlag: string | undefined
): boolean {
  if (nodeEnv === "development") {
    return true;
  }

  return nodeEnv === "production" && enabledFlag === "true";
}

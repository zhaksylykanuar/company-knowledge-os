import { M } from "../lib/messages";

type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label = M.common.loading }: LoadingStateProps) {
  return <section className="state loading">{label}</section>;
}

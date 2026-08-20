import { WorkflowMetrics } from "@/lib/workflow";

type StatProps = {
  label: string;
  value: string;
};

function Stat({ label, value }: StatProps) {
  return (
    <div className="flex-1 px-4 py-3.5 first:pl-5 last:pr-5">
      <p className="text-2xl font-semibold tracking-tight text-foreground">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

type MetricsBarProps = {
  metrics: WorkflowMetrics;
};

export function MetricsBar({ metrics }: MetricsBarProps) {
  return (
    <div className="flex divide-x divide-border rounded-xl border border-border bg-card">
      <Stat label="Agents executed" value={String(metrics.agentsExecuted)} />
      <Stat label="Tools used" value={String(metrics.toolsUsed.length)} />
      <Stat label="Latency" value={`${(metrics.latencyMs / 1000).toFixed(2)}s`} />
      <Stat label="Completion status" value={metrics.completionStatus === "resolved" ? "Resolved" : "Escalated"} />
    </div>
  );
}

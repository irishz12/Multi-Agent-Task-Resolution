"use client";

import { WorkflowRun, useWorkflowStore } from "@/lib/store";
import { cn } from "@/lib/utils";

function relativeTime(timestamp: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}

function RunRow({ run, isActive, onSelect }: { run: WorkflowRun; isActive: boolean; onSelect: () => void }) {
  const isEscalated = run.result.status === "escalated";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full cursor-pointer rounded-lg border px-3 py-2.5 text-left transition-colors",
        isActive ? "border-primary/40 bg-accent" : "border-transparent hover:bg-secondary/60"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-muted-foreground">#{run.result.case_id}</span>
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", isEscalated ? "bg-warning" : "bg-success")} />
      </div>
      <p className="mt-1 truncate text-sm text-foreground">{run.customerMessage}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{relativeTime(run.submittedAt)}</p>
    </button>
  );
}

export function RecentCasesList() {
  const runs = useWorkflowStore((state) => state.runs);
  const activeId = useWorkflowStore((state) => state.activeId);
  const selectRun = useWorkflowStore((state) => state.selectRun);

  if (runs.length === 0) {
    return <p className="px-1 text-xs text-muted-foreground">Cases you resolve this session will appear here.</p>;
  }

  return (
    <div className="space-y-1">
      {runs.map((run) => (
        <RunRow key={run.id} run={run} isActive={run.id === activeId} onSelect={() => selectRun(run.id)} />
      ))}
    </div>
  );
}

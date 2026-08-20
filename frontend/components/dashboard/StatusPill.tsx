"use client";

import { useBackendStatus } from "@/hooks/use-backend-status";
import { cn } from "@/lib/utils";

export function StatusPill() {
  const { data: isOnline, isLoading } = useBackendStatus();

  const label = isLoading ? "Checking…" : isOnline ? "Backend connected" : "Backend unreachable";
  const dotClass = isLoading ? "bg-muted-foreground" : isOnline ? "bg-success" : "bg-destructive";

  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground">
      <span className="relative flex h-2 w-2">
        {isOnline && !isLoading && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", dotClass)} />
        )}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", dotClass)} />
      </span>
      {label}
    </div>
  );
}

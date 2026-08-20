import { CheckCircle2, TriangleAlert } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { ResolveCaseResponse } from "@/lib/api";

const RESOLUTION_LABELS: Record<string, string> = {
  REFUND: "Refund",
  REPLACEMENT: "Replacement",
  ESCALATE: "Escalated",
};

type ResolutionSummaryProps = {
  result: ResolveCaseResponse;
};

export function ResolutionSummary({ result }: ResolutionSummaryProps) {
  const isEscalated = result.status === "escalated";
  const label = result.resolution ? RESOLUTION_LABELS[result.resolution] ?? result.resolution : "Pending";

  return (
    <Card className="overflow-hidden">
      <div className={cn("flex items-center gap-3 border-b border-border px-5 py-4", isEscalated ? "bg-warning/5" : "bg-success/5")}>
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
            isEscalated ? "bg-warning/15 text-warning" : "bg-success/15 text-success"
          )}
        >
          {isEscalated ? <TriangleAlert className="h-5 w-5" aria-hidden="true" /> : <CheckCircle2 className="h-5 w-5" aria-hidden="true" />}
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {isEscalated ? "Escalated" : "Resolved"}
          </p>
          <p className="text-lg font-semibold tracking-tight text-foreground">{label}</p>
        </div>
      </div>
      <CardContent className="space-y-3 py-4">
        {result.resolution_reason && <p className="text-sm leading-relaxed text-muted-foreground">{result.resolution_reason}</p>}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Reference</span>
          {result.action_reference ? (
            <code className="rounded-md bg-secondary px-2 py-0.5 font-mono text-xs text-foreground">{result.action_reference}</code>
          ) : (
            <span className="text-muted-foreground">pending manual review</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

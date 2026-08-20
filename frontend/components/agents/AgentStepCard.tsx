import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { WorkflowStep } from "@/lib/workflow";

const STATUS_CONFIG = {
  success: { badgeVariant: "success" as const, label: "Success" },
  warning: { badgeVariant: "warning" as const, label: "Needs review" },
  skipped: { badgeVariant: "secondary" as const, label: "Skipped" },
};

type AgentStepCardProps = {
  step: WorkflowStep;
  index: number;
};

export function AgentStepCard({ step, index }: AgentStepCardProps) {
  const config = STATUS_CONFIG[step.status];

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card p-4 transition-shadow",
        step.status === "skipped" ? "opacity-60" : "hover:shadow-md"
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            Step {String(index + 1).padStart(2, "0")}
          </p>
          <p className="text-sm font-semibold text-foreground">{step.agent}</p>
        </div>
        <Badge variant={config.badgeVariant}>{config.label}</Badge>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.description}</p>
      {step.tools.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {step.tools.map((tool) => (
            <span
              key={tool}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-secondary/50 px-2 py-1 font-mono text-[11px] text-muted-foreground"
            >
              <span className="h-1 w-1 rounded-full bg-primary/60" />
              {tool}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

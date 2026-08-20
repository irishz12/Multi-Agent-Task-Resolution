"use client";

import { motion } from "framer-motion";
import { Bot, Check, TriangleAlert } from "lucide-react";

import { AgentStepCard } from "@/components/agents/AgentStepCard";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { WorkflowStep } from "@/lib/workflow";

type WorkflowPanelProps = {
  steps: WorkflowStep[] | null;
  isPending: boolean;
};

export function WorkflowPanel({ steps, isPending }: WorkflowPanelProps) {
  if (isPending) {
    return (
      <div className="space-y-3" aria-busy="true" aria-live="polite">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  if (!steps) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border py-16 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
          <Bot className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="max-w-xs space-y-1">
          <p className="text-sm font-semibold text-foreground">No case running</p>
          <p className="text-sm text-muted-foreground">Submit a case on the left to see the agent workflow run live.</p>
        </div>
      </div>
    );
  }

  return (
    <ol className="relative">
      {steps.map((step, index) => (
        <motion.li
          key={step.key}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: index * 0.06 }}
          className="relative flex gap-4 pb-4 last:pb-0"
        >
          {index < steps.length - 1 && (
            <span aria-hidden="true" className="absolute left-[15px] top-9 h-[calc(100%-14px)] w-px bg-border" />
          )}
          <div
            className={cn(
              "z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
              step.status === "success" && "border-success/30 bg-success/10 text-success",
              step.status === "warning" && "border-warning/30 bg-warning/10 text-warning",
              step.status === "skipped" && "border-border bg-muted text-muted-foreground"
            )}
          >
            {step.status === "success" && <Check className="h-4 w-4" aria-hidden="true" />}
            {step.status === "warning" && <TriangleAlert className="h-4 w-4" aria-hidden="true" />}
            {step.status === "skipped" && <span aria-hidden="true">{index + 1}</span>}
          </div>
          <div className="min-w-0 flex-1">
            <AgentStepCard step={step} index={index} />
          </div>
        </motion.li>
      ))}
    </ol>
  );
}

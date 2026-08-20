import { ResolveCaseResponse, WorkflowStepOut } from "@/lib/api";

export type WorkflowStep = WorkflowStepOut;

export type WorkflowMetrics = {
  agentsExecuted: number;
  toolsUsed: string[];
  latencyMs: number;
  completionStatus: string;
};

export function summarizeMetrics(result: ResolveCaseResponse, latencyMs: number): WorkflowMetrics {
  return {
    agentsExecuted: result.steps.filter((step) => step.status !== "skipped").length,
    toolsUsed: result.tools_used,
    latencyMs,
    completionStatus: result.status,
  };
}

"use client";

import { useMutation } from "@tanstack/react-query";

import { resolveCase } from "@/lib/api";
import { useWorkflowStore } from "@/lib/store";
import { summarizeMetrics } from "@/lib/workflow";

export function useResolveCase() {
  const addRun = useWorkflowStore((state) => state.addRun);

  return useMutation({
    mutationFn: async ({ customerId, message }: { customerId: number; message: string }) => {
      const start = performance.now();
      const result = await resolveCase(customerId, message);
      const latencyMs = performance.now() - start;
      return { result, latencyMs, message };
    },
    onSuccess: ({ result, latencyMs, message }) => {
      addRun({
        id: `${result.case_id}-${Date.now()}`,
        customerMessage: message,
        result,
        steps: result.steps,
        metrics: summarizeMetrics(result, latencyMs),
        submittedAt: Date.now(),
      });
    },
  });
}

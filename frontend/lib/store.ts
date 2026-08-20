import { create } from "zustand";

import { ResolveCaseResponse } from "@/lib/api";
import { WorkflowMetrics, WorkflowStep } from "@/lib/workflow";

export type WorkflowRun = {
  id: string;
  customerMessage: string;
  result: ResolveCaseResponse;
  steps: WorkflowStep[];
  metrics: WorkflowMetrics;
  submittedAt: number;
};

type WorkflowState = {
  runs: WorkflowRun[];
  activeId: string | null;
  addRun: (run: WorkflowRun) => void;
  selectRun: (id: string) => void;
};

export const useWorkflowStore = create<WorkflowState>((set) => ({
  runs: [],
  activeId: null,
  addRun: (run) => set((state) => ({ runs: [run, ...state.runs], activeId: run.id })),
  selectRun: (id) => set({ activeId: id }),
}));

export function useActiveRun(): WorkflowRun | null {
  return useWorkflowStore((state) => state.runs.find((run) => run.id === state.activeId) ?? null);
}

"use client";

import { WorkflowPanel } from "@/components/agents/WorkflowPanel";
import { CaseInputForm } from "@/components/dashboard/CaseInputForm";
import { ErrorState } from "@/components/dashboard/ErrorState";
import { MetricsBar } from "@/components/dashboard/MetricsBar";
import { RecentCasesList } from "@/components/dashboard/RecentCasesList";
import { ResolutionSummary } from "@/components/dashboard/ResolutionSummary";
import { StatusPill } from "@/components/dashboard/StatusPill";
import { ThemeToggle } from "@/components/dashboard/ThemeToggle";
import { Separator } from "@/components/ui/separator";
import { useResolveCase } from "@/hooks/use-resolve-case";
import { ApiError } from "@/lib/api";
import { CaseInput } from "@/lib/schema";
import { useActiveRun } from "@/lib/store";

function Logo() {
  return (
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary font-mono text-sm font-semibold text-primary-foreground">
      M
    </div>
  );
}

function SectionEyebrow({ children }: { children: React.ReactNode }) {
  return <p className="font-mono text-xs font-semibold uppercase tracking-widest text-muted-foreground">{children}</p>;
}

export default function Home() {
  const mutation = useResolveCase();
  const run = useActiveRun();

  function handleSubmit(values: CaseInput) {
    mutation.mutate({ customerId: values.customerId, message: values.message });
  }

  const errorMessage = mutation.isError
    ? mutation.error instanceof ApiError
      ? mutation.error.message
      : "Something went wrong. Please try again."
    : null;

  return (
    <div className="app-gradient min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-3 px-6 py-4">
          <div className="flex items-center gap-3">
            <Logo />
            <div>
              <h1 className="text-base font-semibold tracking-tight text-foreground">Multi-Agent Task Resolution</h1>
              <p className="text-sm text-muted-foreground">Agentic AI Customer Resolution Workflow</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusPill />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1400px] gap-6 px-6 py-8 lg:grid-cols-[340px_1fr]">
        <div className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <CaseInputForm onSubmit={handleSubmit} isPending={mutation.isPending} />

          <div>
            <SectionEyebrow>Recent Cases</SectionEyebrow>
            <div className="mt-3">
              <RecentCasesList />
            </div>
          </div>
        </div>

        <section className="min-w-0 space-y-8">
          <div>
            <SectionEyebrow>Live Resolution Workflow</SectionEyebrow>
            {run?.result.plan ? (
              <p className="mb-4 mt-2 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Plan:</span> {run.result.plan.goal}
              </p>
            ) : (
              <div className="mb-4 mt-2" />
            )}
            <WorkflowPanel steps={run?.steps ?? null} isPending={mutation.isPending} />
          </div>

          {errorMessage && <ErrorState message={errorMessage} />}

          {run && (
            <>
              <Separator />
              <div className="space-y-4">
                <SectionEyebrow>Resolution</SectionEyebrow>
                <ResolutionSummary result={run.result} />
                <MetricsBar metrics={run.metrics} />
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}

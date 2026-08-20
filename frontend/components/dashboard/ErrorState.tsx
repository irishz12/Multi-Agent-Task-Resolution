import { AlertCircle } from "lucide-react";

type ErrorStateProps = {
  message: string;
};

export function ErrorState({ message }: ErrorStateProps) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-destructive/20 bg-destructive/5 p-4">
      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold text-destructive">Case could not be resolved</p>
        <p className="text-sm text-destructive/90">{message}</p>
      </div>
    </div>
  );
}

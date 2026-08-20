"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Loader2, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CaseInput, CaseInputFields, caseInputSchema } from "@/lib/schema";

type CaseInputFormProps = {
  onSubmit: (values: CaseInput) => void;
  isPending: boolean;
};

const EXAMPLES = [
  { label: "Damaged order", message: "My headphones from order 2001 arrived damaged, please refund me." },
  { label: "Missing delivery", message: "My package from order 2003 never arrived, please refund me." },
  { label: "Wrong item", message: "I ordered a Bluetooth Speaker but received a USB-C Cable instead." },
];

export function CaseInputForm({ onSubmit, isPending }: CaseInputFormProps) {
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<CaseInputFields, unknown, CaseInput>({
    resolver: zodResolver(caseInputSchema),
    defaultValues: { customerId: 1001, message: "" },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customer Case Input</CardTitle>
        <CardDescription>Describe a damaged order, a missing delivery, or the wrong item arriving.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="customerId">Customer ID</Label>
            <Input id="customerId" type="number" disabled={isPending} {...register("customerId")} />
            {errors.customerId && <p className="text-xs text-destructive">{errors.customerId.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="message">Customer message</Label>
            <Textarea
              id="message"
              placeholder="e.g. My headphones from order 2001 arrived damaged, please refund me."
              disabled={isPending}
              rows={5}
              {...register("message")}
            />
            {errors.message && <p className="text-xs text-destructive">{errors.message.message}</p>}
          </div>

          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">Try an example</p>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map((example) => (
                <button
                  key={example.label}
                  type="button"
                  disabled={isPending}
                  onClick={() => setValue("message", example.message, { shouldValidate: true })}
                  className="cursor-pointer rounded-full border border-border bg-secondary/50 px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/30 hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {example.label}
                </button>
              ))}
            </div>
          </div>

          <Button type="submit" disabled={isPending} className="w-full">
            {isPending ? (
              <>
                <Loader2 className="animate-spin" aria-hidden="true" />
                Resolving case…
              </>
            ) : (
              <>
                <Send aria-hidden="true" />
                Resolve Case
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

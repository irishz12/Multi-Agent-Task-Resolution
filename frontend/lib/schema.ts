import { z } from "zod";

export const caseInputSchema = z.object({
  customerId: z.coerce.number().int().positive("Enter a valid customer ID"),
  message: z.string().trim().min(5, "Describe the issue in a few more words"),
});

export type CaseInputFields = z.input<typeof caseInputSchema>;
export type CaseInput = z.output<typeof caseInputSchema>;

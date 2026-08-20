export type InvestigationPlan = {
  goal: string;
  required_steps: string[];
  required_tools: string[];
};

export type ReflectionResult = {
  complete: boolean;
  missing_information: string[];
  should_continue: boolean;
};

export type WorkflowStepStatus = "success" | "warning" | "skipped";

export type WorkflowStepOut = {
  key: string;
  agent: string;
  status: WorkflowStepStatus;
  description: string;
  tools: string[];
};

export type ResolveCaseResponse = {
  case_id: number;
  issue_type: string | null;
  resolution: string | null;
  status: string;
  action_reference: string | null;
  message: string;
  plan: InvestigationPlan | null;
  reflection: ReflectionResult | null;
  steps: WorkflowStepOut[];
  tools_used: string[];
  resolution_reason: string | null;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

export async function resolveCase(customerId: number, message: string): Promise<ResolveCaseResponse> {
  let response: Response;

  try {
    response = await fetch(`${API_URL}/api/cases/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id: customerId, message }),
    });
  } catch {
    throw new ApiError("Unable to reach the AgentFlow Support backend. Is the server running?", 0);
  }

  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }

  return response.json();
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") {
      return data.detail;
    }
  } catch {
    // response body wasn't JSON, fall through to a generic message
  }

  return response.status === 404
    ? "Customer not found."
    : "The request could not be resolved. Please try again.";
}

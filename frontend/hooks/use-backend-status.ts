"use client";

import { useQuery } from "@tanstack/react-query";

import { checkHealth } from "@/lib/api";

export function useBackendStatus() {
  return useQuery({
    queryKey: ["backend-health"],
    queryFn: checkHealth,
    refetchInterval: 15_000,
    retry: false,
  });
}

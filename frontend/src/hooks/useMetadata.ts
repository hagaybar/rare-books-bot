import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchCoverage,
  fetchIssues,
  fetchClusters,
  submitCorrection,
  agentChat,
  fetchCorrectionHistory,
} from '../api/metadata';

export function useCoverage() {
  return useQuery({
    queryKey: ['coverage'],
    queryFn: fetchCoverage,
    staleTime: 60_000,
  });
}

export function useIssues(
  field: string,
  maxConfidence?: number,
  limit?: number,
  offset?: number
) {
  return useQuery({
    queryKey: ['issues', field, maxConfidence, limit, offset],
    queryFn: () => fetchIssues(field, maxConfidence, limit, offset),
    enabled: !!field,
  });
}

export function useClusters(field?: string) {
  return useQuery({
    queryKey: ['clusters', field],
    queryFn: () => fetchClusters(field),
  });
}

export function useSubmitCorrection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: {
      field: string;
      rawValue: string;
      canonicalValue: string;
      evidence?: string;
    }) =>
      submitCorrection(
        params.field,
        params.rawValue,
        params.canonicalValue,
        params.evidence
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['coverage'] });
      queryClient.invalidateQueries({ queryKey: ['issues'] });
      queryClient.invalidateQueries({ queryKey: ['clusters'] });
    },
  });
}

export function useAgentChat() {
  return useMutation({
    mutationFn: (params: { field: string; message?: string }) =>
      agentChat(params.field, params.message),
  });
}

export function useCorrectionHistory(
  field?: string,
  source?: string,
  limit?: number,
  offset?: number
) {
  return useQuery({
    queryKey: ['correctionHistory', field, source, limit, offset],
    queryFn: () => fetchCorrectionHistory(field, source, limit, offset),
    staleTime: 30_000,
  });
}

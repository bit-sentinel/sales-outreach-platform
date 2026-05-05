/**
 * React Query hooks for lead API calls.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, type PaginatedData } from '@/lib/api-client';

export interface Lead {
  id: string;
  company_id: string | null;
  contact_id: string | null;
  status: string;
  source: string | null;
  enrichment_status: string;
  enriched_at: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

interface LeadFilters {
  page?: number;
  page_size?: number;
  status?: string;
  source?: string;
  search?: string;
  tags?: string[];
}

export function useLeads(filters: LeadFilters = {}) {
  return useQuery({
    queryKey: ['leads', filters],
    queryFn: () =>
      api<PaginatedData<Lead>>({
        url: '/leads',
        params: filters,
      }),
  });
}

export function useLead(id: string) {
  return useQuery({
    queryKey: ['leads', id],
    queryFn: () => api<Lead>({ url: `/leads/${id}` }),
    enabled: !!id,
  });
}

export function useCreateLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Lead>) =>
      api<Lead>({ url: '/leads', method: 'POST', data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
  });
}

export function useUpdateLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Lead> }) =>
      api<Lead>({ url: `/leads/${id}`, method: 'PATCH', data }),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['leads', id] });
    },
  });
}

export function useEnrichLeads() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { lead_ids: string[]; enrichment_types: string[] }) =>
      api({ url: '/enrichment/enrich', method: 'POST', data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
  });
}

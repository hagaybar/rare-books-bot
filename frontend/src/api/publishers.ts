import type { PublisherAuthorityListResponse, PublisherAuthority } from '../types/publishers';

const BASE = '/metadata';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchPublishers(
  type?: string
): Promise<PublisherAuthorityListResponse> {
  const params = new URLSearchParams();
  if (type) params.set('type', type);
  const qs = params.toString();
  const res = await fetch(`${BASE}/publishers${qs ? `?${qs}` : ''}`, { credentials: 'include' });
  return handleResponse<PublisherAuthorityListResponse>(res);
}

export async function createPublisher(data: {
  canonical_name: string;
  type: string;
  confidence: number;
  location?: string;
  dates_active?: string;
  notes?: string;
}): Promise<PublisherAuthority> {
  const res = await fetch(`${BASE}/publishers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  return handleResponse<PublisherAuthority>(res);
}

export async function updatePublisher(
  id: number,
  data: {
    canonical_name?: string;
    type?: string;
    confidence?: number;
    location?: string;
    dates_active?: string;
    notes?: string;
  }
): Promise<PublisherAuthority> {
  const res = await fetch(`${BASE}/publishers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  return handleResponse<PublisherAuthority>(res);
}

export async function deletePublisher(id: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/publishers/${id}`, { method: 'DELETE', credentials: 'include' });
  return handleResponse<{ success: boolean; message: string }>(res);
}

export async function addVariant(
  publisherId: number,
  data: { variant_form: string; script: string; language?: string }
): Promise<PublisherAuthority> {
  const res = await fetch(`${BASE}/publishers/${publisherId}/variants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  return handleResponse<PublisherAuthority>(res);
}

export async function deleteVariant(
  publisherId: number,
  variantId: number
): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/publishers/${publisherId}/variants/${variantId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  return handleResponse<{ success: boolean; message: string }>(res);
}

import { api } from '@/lib/api';
import type { UploadOut, UploadPurpose } from '@/lib/types';

export interface UploadSessionOut {
  id: string;
  filename: string;
  content_type: string;
  total_size_bytes: number;
  expected_sha256?: string | null;
  client_platform: 'web' | 'desktop' | 'ios' | 'android';
  part_size_bytes: number;
  received_parts: number[];
  status: 'open' | 'completed' | 'cancelled' | 'failed' | 'expired';
  upload_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
}

export interface CreateUploadSessionInput {
  filename: string;
  contentType: string;
  totalSizeBytes: number;
  purpose: UploadPurpose;
  conversationId?: string;
  expectedSha256?: string;
  clientPlatform?: 'web' | 'ios' | 'android' | 'desktop';
  partSizeBytes?: number;
}

export interface UploadFileInput {
  file: File | Blob;
  filename: string;
  purpose: UploadPurpose;
  conversationId?: string;
  clientPlatform?: 'web' | 'ios' | 'android' | 'desktop';
  signal?: AbortSignal;
  onProgress?: (progress: number) => void;
}

export async function uploadFile(input: UploadFileInput): Promise<UploadOut> {
  const formData = new FormData();
  formData.append('file', input.file, input.filename);
  formData.append('purpose', input.purpose);
  if (input.conversationId) formData.append('conversation_id', input.conversationId);
  if (input.clientPlatform) formData.append('client_platform', input.clientPlatform);

  const { data } = await api.post<UploadOut>('/api/v1/uploads', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    signal: input.signal,
    onUploadProgress: (event) => {
      if (!input.onProgress || !event.total) return;
      input.onProgress(Math.round((event.loaded / event.total) * 100));
    },
  });
  return data;
}

export async function deleteUpload(uploadId: string): Promise<void> {
  await api.delete(`/api/v1/uploads/${uploadId}`);
}

export async function downloadUpload(uploadId: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/api/v1/uploads/${uploadId}/download`, {
    responseType: 'blob',
  });
  return data;
}

export async function createUploadSession(input: CreateUploadSessionInput): Promise<UploadSessionOut> {
  const { data } = await api.post<UploadSessionOut>('/api/v1/uploads/sessions', {
    filename: input.filename,
    content_type: input.contentType,
    total_size_bytes: input.totalSizeBytes,
    purpose: input.purpose,
    conversation_id: input.conversationId,
    expected_sha256: input.expectedSha256,
    client_platform: input.clientPlatform ?? 'web',
    part_size_bytes: input.partSizeBytes,
  });
  return data;
}

export async function getUploadSession(sessionId: string): Promise<UploadSessionOut> {
  const { data } = await api.get<UploadSessionOut>(`/api/v1/uploads/sessions/${sessionId}`);
  return data;
}

export async function putUploadSessionPart(
  sessionId: string,
  partNumber: number,
  data: Blob | ArrayBuffer,
): Promise<UploadSessionOut> {
  const { data: session } = await api.put<UploadSessionOut>(
    `/api/v1/uploads/sessions/${sessionId}/parts/${partNumber}`,
    data,
    { headers: { 'Content-Type': 'application/octet-stream' } },
  );
  return session;
}

export async function completeUploadSession(
  sessionId: string,
  sha256?: string,
): Promise<{ session: UploadSessionOut; upload: UploadOut }> {
  const { data } = await api.post<{ session: UploadSessionOut; upload: UploadOut }>(
    `/api/v1/uploads/sessions/${sessionId}/complete`,
    { sha256 },
  );
  return data;
}

export async function cancelUploadSession(sessionId: string): Promise<UploadSessionOut> {
  const { data } = await api.delete<UploadSessionOut>(`/api/v1/uploads/sessions/${sessionId}`);
  return data;
}

export function uploadDownloadUrl(uploadId: string, variant: 'original' | 'thumbnail' = 'original') {
  const query = variant === 'original' ? '' : `?variant=${variant}`;
  return `/api/v1/uploads/${uploadId}/download${query}`;
}

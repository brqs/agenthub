import { api } from '@/lib/api';
import type { UploadOut, UploadPurpose } from '@/lib/types';

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

export function uploadDownloadUrl(uploadId: string, variant: 'original' | 'thumbnail' = 'original') {
  const query = variant === 'original' ? '' : `?variant=${variant}`;
  return `/api/v1/uploads/${uploadId}/download${query}`;
}

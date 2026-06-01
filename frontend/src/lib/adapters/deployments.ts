import { api } from '@/lib/api';
import type {
  WorkspaceDeploymentListResponse,
  WorkspaceDeploymentResponse,
} from '@/lib/types';

function deploymentPath(conversationId: string, deploymentId?: string): string {
  const base = `/api/v1/workspaces/${conversationId}/deployments`;
  return deploymentId ? `${base}/${deploymentId}` : base;
}

export async function listDeployments(
  conversationId: string,
): Promise<WorkspaceDeploymentListResponse> {
  const { data } = await api.get<WorkspaceDeploymentListResponse>(deploymentPath(conversationId));
  return data;
}

export async function getDeployment(
  conversationId: string,
  deploymentId: string,
): Promise<WorkspaceDeploymentResponse> {
  const { data } = await api.get<WorkspaceDeploymentResponse>(
    deploymentPath(conversationId, deploymentId),
  );
  return data;
}

export async function stopDeployment(
  conversationId: string,
  deploymentId: string,
): Promise<WorkspaceDeploymentResponse> {
  const { data } = await api.delete<WorkspaceDeploymentResponse>(
    deploymentPath(conversationId, deploymentId),
  );
  return data;
}

export async function downloadSourceArchive(
  conversationId: string,
  deploymentId: string,
  downloadUrl?: string | null,
): Promise<Blob> {
  const url = downloadUrl ?? `${deploymentPath(conversationId, deploymentId)}/download`;
  const { data } = await api.get<Blob>(url, { responseType: 'blob' });
  return data;
}

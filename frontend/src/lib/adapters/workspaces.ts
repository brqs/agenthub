import { api } from '@/lib/api';

export interface WorkspaceFileNode {
  type: 'file';
  name: string;
  path: string;
  size: number;
  mime_type: string;
}

export interface WorkspaceDirectoryNode {
  type: 'directory';
  name: string;
  path: string;
  children: WorkspaceNode[];
}

export type WorkspaceNode = WorkspaceFileNode | WorkspaceDirectoryNode;

interface RawWorkspaceNode {
  type: 'directory' | 'file';
  name: string;
  path: string;
  children?: RawWorkspaceNode[];
  size?: number | null;
  mime_type?: string | null;
}

interface RawWorkspaceTreeResponse {
  root: string;
  tree: RawWorkspaceNode;
}

export interface WorkspaceTreeResponse {
  root: string;
  tree: WorkspaceNode;
}

export interface WorkspaceFile {
  path: string;
  name: string;
  mime_type: string;
  size: number;
  content: string | Blob;
}

function normalizeNode(node: RawWorkspaceNode): WorkspaceNode {
  if (node.type === 'file') {
    return {
      type: 'file',
      name: node.name,
      path: node.path,
      size: node.size ?? 0,
      mime_type: node.mime_type ?? 'application/octet-stream',
    };
  }

  return {
    type: 'directory',
    name: node.name,
    path: node.path,
    children: (node.children ?? []).map(normalizeNode),
  };
}

function filenameFromPath(path: string): string {
  return path.split('/').filter(Boolean).at(-1) ?? path;
}

function encodeWorkspacePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/');
}

function isTextMime(mimeType: string): boolean {
  return (
    mimeType.startsWith('text/') ||
    ['application/json', 'application/javascript'].includes(mimeType)
  );
}

export async function getWorkspaceTree(
  conversationId: string,
  maxDepth = 5,
): Promise<WorkspaceTreeResponse> {
  const { data } = await api.get<RawWorkspaceTreeResponse>(
    `/api/v1/workspaces/${conversationId}/tree`,
    { params: { max_depth: maxDepth } },
  );
  return {
    root: data.root,
    tree: normalizeNode(data.tree),
  };
}

export async function readWorkspaceFile(
  conversationId: string,
  path: string,
): Promise<WorkspaceFile> {
  const response = await api.get<Blob>(
    `/api/v1/workspaces/${conversationId}/files/${encodeWorkspacePath(path)}`,
    { responseType: 'blob' },
  );
  const blob = response.data;
  const headerContentType = response.headers['content-type'];
  const mimeType =
    blob.type ||
    (typeof headerContentType === 'string' ? headerContentType : undefined) ||
    'application/octet-stream';
  return {
    path,
    name: filenameFromPath(path),
    mime_type: mimeType,
    size: blob.size,
    content: isTextMime(mimeType) ? await blob.text() : blob,
  };
}

export async function writeWorkspaceFile(
  conversationId: string,
  path: string,
  content: string | Blob,
  mimeType = 'text/plain',
): Promise<void> {
  await api.put(`/api/v1/workspaces/${conversationId}/files/${encodeWorkspacePath(path)}`, content, {
    headers: { 'Content-Type': mimeType },
  });
}

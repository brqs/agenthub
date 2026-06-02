import { ChevronDown, ChevronLeft, ChevronRight, FileCode2, Folder } from 'lucide-react';
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

export type WorkspaceNode = WorkspaceFileNode | WorkspaceDirectoryNode;

export interface WorkspaceFileNode {
  type: 'file';
  name: string;
  path: string;
  size: number;
  mime_type: string;
}

export interface WorkspaceDirectoryNode {
  type: 'dir' | 'directory';
  name: string;
  path: string;
  children: WorkspaceNode[];
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KB`;
}

function TreeNode({
  node,
  selectedPath,
  onSelectFile,
  depth,
}: {
  node: WorkspaceNode;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  depth: number;
}) {
  const [open, setOpen] = useState(true);

  if (node.type === 'dir' || node.type === 'directory') {
    return (
      <div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-slate-400 transition hover:bg-slate-800/70 hover:text-slate-200"
          style={{ paddingLeft: `${8 + depth * 12}px` }}
        >
          {open ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
          <Folder className="h-3.5 w-3.5 shrink-0 text-brand-light" />
          <span className="truncate">{node.name}</span>
        </button>
        {open && (
          <div>
            {node.children.map((child) => (
              <TreeNode
                key={child.path}
                node={child}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (node.type !== 'file') return null;

  return (
    <button
      type="button"
      onClick={() => onSelectFile(node.path)}
      className={cn(
        'flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition',
        selectedPath === node.path
          ? 'bg-brand/15 text-brand-light'
          : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-200',
      )}
      style={{ paddingLeft: `${28 + depth * 12}px` }}
      title={`${node.path} · ${formatSize(node.size)}`}
    >
      <FileCode2 className="h-3.5 w-3.5 shrink-0" />
      <span className="min-w-0 flex-1 truncate">{node.name}</span>
      <span className="shrink-0 text-[11px] text-slate-600">{formatSize(node.size)}</span>
    </button>
  );
}

export function WorkspaceFileTree({
  nodes,
  selectedPath,
  onSelectFile,
}: {
  nodes: WorkspaceNode[];
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
}) {
  return (
    <>
      <div className="hidden space-y-0.5 md:block">
        {nodes.map((node) => (
          <TreeNode key={node.path} node={node} selectedPath={selectedPath} onSelectFile={onSelectFile} depth={0} />
        ))}
      </div>
      <MobileWorkspaceBrowser nodes={nodes} selectedPath={selectedPath} onSelectFile={onSelectFile} />
    </>
  );
}

function MobileWorkspaceBrowser({
  nodes,
  selectedPath,
  onSelectFile,
}: {
  nodes: WorkspaceNode[];
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
}) {
  const [directoryPath, setDirectoryPath] = useState<string | null>(null);
  const directory = directoryPath ? findDirectory(nodes, directoryPath) : null;
  const visibleNodes = directory?.children ?? nodes;

  useEffect(() => {
    if (directoryPath && !findDirectory(nodes, directoryPath)) setDirectoryPath(null);
  }, [directoryPath, nodes]);

  return (
    <div className="space-y-1 md:hidden" data-testid="mobile-workspace-browser">
      <div className="mb-2 flex min-w-0 items-center gap-2 px-1 text-xs text-slate-500">
        {directory && (
          <button
            type="button"
            onClick={() => setDirectoryPath(getParentDirectoryPath(nodes, directory.path))}
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-slate-400 hover:bg-slate-800 hover:text-white"
            aria-label="返回上级目录"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            返回
          </button>
        )}
        <span className="truncate" title={directory?.path ?? 'Workspace'}>
          {directory?.path ?? 'Workspace'}
        </span>
      </div>
      {visibleNodes.map((node) =>
        node.type === 'file' ? (
          <button
            key={node.path}
            type="button"
            onClick={() => onSelectFile(node.path)}
            className={cn(
              'flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-2.5 text-left text-xs transition',
              selectedPath === node.path
                ? 'bg-brand/15 text-brand-light'
                : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-200',
            )}
            title={`${node.path} · ${formatSize(node.size)}`}
          >
            <FileCode2 className="h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">{node.name}</span>
            <span className="shrink-0 text-[11px] text-slate-600">{formatSize(node.size)}</span>
          </button>
        ) : (
          <button
            key={node.path}
            type="button"
            onClick={() => setDirectoryPath(node.path)}
            className="flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-2.5 text-left text-xs text-slate-400 transition hover:bg-slate-800/70 hover:text-slate-200"
          >
            <Folder className="h-4 w-4 shrink-0 text-brand-light" />
            <span className="min-w-0 flex-1 truncate">{node.name}</span>
            <ChevronRight className="h-4 w-4 shrink-0 text-slate-600" />
          </button>
        ),
      )}
    </div>
  );
}

function findDirectory(nodes: WorkspaceNode[], path: string): WorkspaceDirectoryNode | null {
  for (const node of nodes) {
    if (node.type === 'file') continue;
    if (node.path === path) return node;
    const nested = findDirectory(node.children, path);
    if (nested) return nested;
  }
  return null;
}

function getParentDirectoryPath(nodes: WorkspaceNode[], path: string): string | null {
  for (const node of nodes) {
    if (node.type === 'file') continue;
    if (node.children.some((child) => child.path === path)) return node.path;
    const nested = getParentDirectoryPath(node.children, path);
    if (nested !== null) return nested;
  }
  return null;
}

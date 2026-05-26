import { ChevronDown, ChevronRight, FileCode2, Folder } from 'lucide-react';
import { useState } from 'react';
import type { WorkspaceNode } from '@/lib/mockWorkspace';
import { cn } from '@/lib/utils';

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

  if (node.type === 'dir') {
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
    <div className="space-y-0.5">
      {nodes.map((node) => (
        <TreeNode key={node.path} node={node} selectedPath={selectedPath} onSelectFile={onSelectFile} depth={0} />
      ))}
    </div>
  );
}

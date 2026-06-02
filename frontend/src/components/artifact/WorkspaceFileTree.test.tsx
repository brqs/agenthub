import { fireEvent, render, screen, within } from '@testing-library/react';
import { WorkspaceFileTree, type WorkspaceNode } from './WorkspaceFileTree';

const nodes: WorkspaceNode[] = [
  {
    type: 'directory',
    name: 'src',
    path: 'src',
    children: [
      {
        type: 'directory',
        name: 'components',
        path: 'src/components',
        children: [
          {
            type: 'file',
            name: 'App.tsx',
            path: 'src/components/App.tsx',
            size: 512,
            mime_type: 'text/plain',
          },
        ],
      },
    ],
  },
];

describe('WorkspaceFileTree', () => {
  it('navigates directories as a compact mobile list', () => {
    const onSelectFile = vi.fn();
    render(<WorkspaceFileTree nodes={nodes} selectedPath={null} onSelectFile={onSelectFile} />);
    const mobileBrowser = within(screen.getByTestId('mobile-workspace-browser'));

    fireEvent.click(mobileBrowser.getByRole('button', { name: 'src' }));
    expect(mobileBrowser.getByText('src')).toBeInTheDocument();

    fireEvent.click(mobileBrowser.getByRole('button', { name: 'components' }));
    fireEvent.click(mobileBrowser.getByRole('button', { name: 'App.tsx 512 B' }));
    expect(onSelectFile).toHaveBeenCalledWith('src/components/App.tsx');

    fireEvent.click(mobileBrowser.getByRole('button', { name: '返回上级目录' }));
    expect(mobileBrowser.getByRole('button', { name: 'components' })).toBeInTheDocument();
  });
});

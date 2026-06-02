import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeploymentStatusBlock } from './DeploymentStatusBlock';
import * as deploymentsAdapter from '@/lib/adapters/deployments';
import type { DeploymentStatusBlock as DeploymentStatusBlockType } from '@/lib/types';

vi.mock('@/lib/adapters/deployments', () => ({
  getDeployment: vi.fn(),
  stopDeployment: vi.fn(),
  downloadSourceArchive: vi.fn(),
}));

const block: DeploymentStatusBlockType = {
  type: 'deployment_status',
  deployment_id: 'deployment-1',
  kind: 'static_site',
  status: 'published',
  title: 'Static site deployment',
  url: 'https://example.com/deployed',
};

function renderBlock(value: DeploymentStatusBlockType = block) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DeploymentStatusBlock block={value} conversationId="conversation-1" />
    </QueryClientProvider>,
  );
}

describe('DeploymentStatusBlock', () => {
  beforeEach(() => {
    vi.mocked(deploymentsAdapter.getDeployment).mockImplementation(() => new Promise(() => undefined));
    vi.mocked(deploymentsAdapter.stopDeployment).mockResolvedValue({
      id: 'deployment-1',
      conversation_id: 'conversation-1',
      workspace_id: 'workspace-1',
      kind: 'static_site',
      status: 'stopped',
      logs: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('copies the public deployment URL', async () => {
    renderBlock();

    fireEvent.click(screen.getByRole('button', { name: '复制部署地址' }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('https://example.com/deployed');
    });
    expect(screen.getByRole('button', { name: '已复制部署地址' })).toBeInTheDocument();
  });

  it('stops a published deployment', async () => {
    renderBlock();

    fireEvent.click(screen.getByRole('button', { name: '停止发布' }));

    await waitFor(() => {
      expect(deploymentsAdapter.stopDeployment).toHaveBeenCalledWith(
        'conversation-1',
        'deployment-1',
      );
    });
  });

  it('renders queued deployments without stop actions', () => {
    renderBlock({
      ...block,
      status: 'queued',
      url: undefined,
    });

    expect(screen.getByText('Queued')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '停止发布' })).not.toBeInTheDocument();
  });

  it('warns that source archives are temporary', () => {
    renderBlock({
      ...block,
      kind: 'source_zip',
      title: 'Source archive',
      download_url: '/api/v1/workspaces/conversation-1/deployments/deployment-1/download',
    });

    expect(screen.getByText('源码包为临时产物，请及时下载并妥善保存。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '删除源码包' })).toBeInTheDocument();
  });
});

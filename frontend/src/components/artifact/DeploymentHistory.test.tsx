import { render, screen } from '@testing-library/react';
import { DeploymentHistory } from './DeploymentHistory';
import type { WorkspaceDeploymentListResponse, WorkspaceDeploymentResponse } from '@/lib/types';

const hookMocks = vi.hoisted(() => ({
  useDeployments: vi.fn(),
  useRetryDeployment: vi.fn(),
  useStopDeployment: vi.fn(),
}));

vi.mock('@/hooks/useDeployments', () => hookMocks);

vi.mock('@/lib/nativeShell', () => ({
  handleExternalLink: vi.fn(),
}));

function deployment(overrides: Partial<WorkspaceDeploymentResponse> = {}): WorkspaceDeploymentResponse {
  return {
    id: '00000000-0000-4000-8000-000000000201',
    conversation_id: '00000000-0000-4000-8000-000000000101',
    workspace_id: '00000000-0000-4000-8000-000000000301',
    kind: 'source_zip',
    status: 'failed',
    error: 'cached failure',
    attempt_count: 1,
    created_at: '2026-06-04T00:00:00.000Z',
    updated_at: '2026-06-04T00:00:01.000Z',
    ...overrides,
  };
}

function deploymentList(items: WorkspaceDeploymentResponse[] = []): WorkspaceDeploymentListResponse {
  return {
    items,
  };
}

function setDeploymentsQuery(
  overrides: Partial<ReturnType<typeof hookMocks.useDeployments>> & {
    data?: WorkspaceDeploymentListResponse;
  },
) {
  hookMocks.useDeployments.mockReturnValue({
    data: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
    ...overrides,
  });
}

function renderHistory() {
  hookMocks.useStopDeployment.mockReturnValue({
    isPending: false,
    isError: false,
    variables: undefined,
    mutate: vi.fn(),
  });
  hookMocks.useRetryDeployment.mockReturnValue({
    isPending: false,
    isError: false,
    variables: undefined,
    mutate: vi.fn(),
  });

  return render(<DeploymentHistory conversationId="00000000-0000-4000-8000-000000000101" />);
}

describe('DeploymentHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state for a new conversation with no deployments', () => {
    setDeploymentsQuery({ data: deploymentList() });

    renderHistory();

    expect(screen.getByText(/暂无发布记录/)).toBeInTheDocument();
    expect(
      screen.queryByText('Deployment history could not refresh; showing the last known state.'),
    ).not.toBeInTheDocument();
  });

  it('keeps cached deployment data visible when a refresh fails', () => {
    setDeploymentsQuery({
      data: deploymentList([deployment()]),
      isError: true,
    });

    renderHistory();

    expect(
      screen.getByText('Deployment history could not refresh; showing the last known state.'),
    ).toBeInTheDocument();
    expect(screen.getByText('cached failure')).toBeInTheDocument();
  });

  it('shows a retryable primary error only when no deployment data is available', () => {
    const refetch = vi.fn();
    setDeploymentsQuery({
      isError: true,
      refetch,
    });

    renderHistory();

    screen.getByLabelText('重试加载发布记录').click();

    expect(refetch).toHaveBeenCalledOnce();
    expect(
      screen.queryByText('Deployment history could not refresh; showing the last known state.'),
    ).not.toBeInTheDocument();
  });
});

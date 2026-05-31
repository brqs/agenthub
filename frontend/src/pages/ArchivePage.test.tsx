import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ArchivePage } from './ArchivePage';
import { mockConversations, mockMessages } from '@/lib/mockData';
import { useChatStore } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';

const navigate = vi.fn();
const listConversations = vi.fn();

vi.mock('@/lib/adapters/conversations', () => ({
  listConversations: (...args: unknown[]) => listConversations(...args),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

function renderArchivePage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <ArchivePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ArchivePage', () => {
  beforeEach(() => {
    navigate.mockReset();
    listConversations.mockReset();
    useAuthStore.setState({
      token: 'token',
      user: {
        id: 'user-1',
        username: 'tester',
        avatar_url: null,
        created_at: '2026-05-31T00:00:00.000Z',
      },
    });
    useChatStore.setState({
      conversations: structuredClone(mockConversations),
      messagesByConversation: structuredClone(mockMessages),
      selectedConversationId: mockConversations[0]?.id ?? '',
      search: '',
      highlightedMessageId: null,
    });
  });

  it('shows an empty state when there are no archived conversations', async () => {
    listConversations.mockResolvedValue([]);
    renderArchivePage();

    expect(await screen.findByText('暂无归档会话')).toBeInTheDocument();
  });

  it('lists archived conversations returned by the backend and opens them', async () => {
    useChatStore.getState().toggleConversationArchive('conv-demo-flow');
    const archived = useChatStore
      .getState()
      .conversations.filter((conversation) => conversation.is_archived);
    listConversations.mockResolvedValue(archived);

    renderArchivePage();
    fireEvent.click(await screen.findByText('AgentHub 比赛演示'));

    expect(navigate).toHaveBeenCalledWith('/chat/conv-demo-flow');
  });
});

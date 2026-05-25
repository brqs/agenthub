import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ArchivePage } from './ArchivePage';
import { mockConversations, mockMessages } from '@/lib/mockData';
import { useChatStore } from '@/stores/chatStore';

const navigate = vi.fn();

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
    useChatStore.setState({
      conversations: structuredClone(mockConversations),
      messagesByConversation: structuredClone(mockMessages),
      selectedConversationId: mockConversations[0]?.id ?? '',
      search: '',
      highlightedMessageId: null,
    });
  });

  it('shows an empty state when there are no archived conversations', () => {
    renderArchivePage();

    expect(screen.getByText('暂无归档会话')).toBeInTheDocument();
  });

  it('lists archived conversations and opens them', () => {
    useChatStore.getState().toggleConversationArchive('conv-demo-flow');

    renderArchivePage();
    fireEvent.click(screen.getByText('AgentHub 比赛演示'));

    expect(navigate).toHaveBeenCalledWith('/chat/conv-demo-flow');
  });
});

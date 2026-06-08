import { fireEvent, render, screen, within } from '@testing-library/react';
import { ConversationSidebar } from './ConversationSidebar';
import type { DemoConversation } from '@/lib/mockData';

const conversations: DemoConversation[] = [
  {
    id: 'conv-pinned',
    title: 'Pinned Backend Debug',
    mode: 'single',
    agent_ids: ['claude-code'],
    is_pinned: true,
    is_archived: false,
    last_message_at: '2026-05-29T12:00:00.000Z',
    last_message_preview: 'pinned',
    created_at: '2026-05-29T12:00:00.000Z',
  },
  {
    id: 'conv-recent',
    title: 'Recent Frontend Polish',
    mode: 'group',
    agent_ids: ['orchestrator', 'opencode-helper'],
    is_pinned: false,
    is_archived: false,
    last_message_at: '2026-05-29T12:01:00.000Z',
    last_message_preview: 'recent',
    created_at: '2026-05-29T12:01:00.000Z',
  },
];

function renderSidebar(search = '') {
  const onSearch = vi.fn();
  const view = render(
    <ConversationSidebar
      conversations={conversations}
      selectedConversationId="conv-recent"
      search={search}
      onSearch={onSearch}
      onSelect={vi.fn()}
      onNewConversation={vi.fn()}
      onTogglePin={vi.fn()}
      onToggleArchive={vi.fn()}
    />,
  );
  return { ...view, onSearch };
}

describe('ConversationSidebar', () => {
  it('keeps pinned and recent conversations in separate sections', () => {
    renderSidebar();

    const pinnedSection = screen.getByRole('heading', { name: '置顶' }).closest('section');
    const recentSection = screen.getByRole('heading', { name: '最近' }).closest('section');

    expect(pinnedSection).not.toBeNull();
    expect(recentSection).not.toBeNull();
    expect(within(pinnedSection!).getByText('Pinned Backend Debug')).toBeInTheDocument();
    expect(within(recentSection!).getByText('Recent Frontend Polish')).toBeInTheDocument();
  });

  it('filters conversations by title and shows an empty search state', () => {
    const { rerender, onSearch } = renderSidebar('backend');

    expect(screen.getByText('Pinned Backend Debug')).toBeInTheDocument();
    expect(screen.queryByText('Recent Frontend Polish')).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('搜索会话'), {
      target: { value: 'missing' },
    });
    expect(onSearch).toHaveBeenCalledWith('missing');

    rerender(
      <ConversationSidebar
        conversations={conversations}
        selectedConversationId="conv-recent"
        search="missing"
        onSearch={onSearch}
        onSelect={vi.fn()}
        onNewConversation={vi.fn()}
      />,
    );

    expect(screen.getByText('没有匹配的会话')).toBeInTheDocument();
  });
});

import { fireEvent, render, screen } from '@testing-library/react';
import { ConversationItem } from './ConversationItem';
import { mockConversations } from '@/lib/mockData';
import { formatTime } from '@/lib/utils';

describe('ConversationItem', () => {
  it('shows the message time in the right-side slot by default', () => {
    const conversation = mockConversations[0];

    render(
      <ConversationItem
        conversation={conversation}
        active={false}
        onSelect={vi.fn()}
        onTogglePin={vi.fn()}
        onToggleArchive={vi.fn()}
      />,
    );

    expect(
      screen.getByLabelText(`最后消息时间 ${formatTime(conversation.last_message_at)}`),
    ).toBeInTheDocument();
  });

  it('renders pin and archive actions without selecting the conversation when clicked', () => {
    const onSelect = vi.fn();
    const onTogglePin = vi.fn();
    const onToggleArchive = vi.fn();

    render(
      <ConversationItem
        conversation={mockConversations[0]}
        active={false}
        onSelect={onSelect}
        onTogglePin={onTogglePin}
        onToggleArchive={onToggleArchive}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '取消置顶' }));
    fireEvent.click(screen.getByRole('button', { name: '归档会话' }));

    expect(onTogglePin).toHaveBeenCalledTimes(1);
    expect(onToggleArchive).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('uses restore archive action for archived conversations', () => {
    const archivedConversation = { ...mockConversations[0], is_archived: true };

    render(
      <ConversationItem
        conversation={archivedConversation}
        active={false}
        onSelect={vi.fn()}
        onTogglePin={vi.fn()}
        onToggleArchive={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: '取消归档' })).toBeInTheDocument();
  });

  it('exposes pin and archive actions from the mobile more menu', () => {
    const onTogglePin = vi.fn();
    const onToggleArchive = vi.fn();
    render(
      <ConversationItem
        conversation={{ ...mockConversations[0], is_pinned: false }}
        active={false}
        onSelect={vi.fn()}
        onTogglePin={onTogglePin}
        onToggleArchive={onToggleArchive}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '会话更多操作' }));
    fireEvent.click(screen.getAllByRole('button', { name: '置顶会话' })[1]!);
    fireEvent.click(screen.getByRole('button', { name: '会话更多操作' }));
    fireEvent.click(screen.getAllByRole('button', { name: '归档会话' })[1]!);

    expect(onTogglePin).toHaveBeenCalledOnce();
    expect(onToggleArchive).toHaveBeenCalledOnce();
  });
});

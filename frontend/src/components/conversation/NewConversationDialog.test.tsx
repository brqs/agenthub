import { fireEvent, render, screen } from '@testing-library/react';
import { NewConversationDialog } from './NewConversationDialog';
import { mockAgents } from '@/lib/mockData';

describe('NewConversationDialog', () => {
  it('creates a conversation and closes from its mobile layout', () => {
    const onCreate = vi.fn();
    const onClose = vi.fn();
    render(
      <NewConversationDialog
        open
        agents={mockAgents}
        isPending={false}
        onClose={onClose}
        onCreate={onCreate}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText('例如：React Todo 组件'), {
      target: { value: '移动端会话' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建会话' }));

    expect(onCreate).toHaveBeenCalledWith({
      title: '移动端会话',
      mode: 'single',
      agentIds: ['claude-code'],
    });

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

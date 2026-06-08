import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ModuleRail } from './ModuleRail';

describe('ModuleRail', () => {
  it('notifies chat navigation clicks so the conversation sidebar can reopen', () => {
    const onChatClick = vi.fn();

    render(
      <MemoryRouter initialEntries={['/chat/demo']}>
        <ModuleRail
          themePreference="system"
          resolvedTheme="light"
          chatHref="/chat/conv-active"
          onCycleTheme={vi.fn()}
          onOpenSettings={vi.fn()}
          onToggleUserMenu={vi.fn()}
          onChatClick={onChatClick}
        />
      </MemoryRouter>,
    );

    const chatLink = screen.getByTitle('聊天');
    expect(chatLink).toHaveAttribute('href', '/chat/conv-active');

    fireEvent.click(chatLink);

    expect(onChatClick).toHaveBeenCalledOnce();
  });
});

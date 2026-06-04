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
          onCycleTheme={vi.fn()}
          onOpenSettings={vi.fn()}
          onToggleUserMenu={vi.fn()}
          onChatClick={onChatClick}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTitle('聊天'));

    expect(onChatClick).toHaveBeenCalledOnce();
  });
});

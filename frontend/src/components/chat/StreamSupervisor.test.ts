import {
  isDesktopConversationForeground,
  isWorkspaceWritingTool,
  resolveDesktopNotificationKind,
} from './StreamSupervisor';

describe('StreamSupervisor workspace invalidation', () => {
  it('only treats explicit file mutation tools as workspace writes', () => {
    expect(isWorkspaceWritingTool('write')).toBe(true);
    expect(isWorkspaceWritingTool('write_file')).toBe(true);
    expect(isWorkspaceWritingTool('create-file')).toBe(true);
    expect(isWorkspaceWritingTool('delete_file')).toBe(true);
    expect(isWorkspaceWritingTool('edit')).toBe(true);
    expect(isWorkspaceWritingTool('save_file')).toBe(true);

    expect(isWorkspaceWritingTool('todowrite')).toBe(false);
    expect(isWorkspaceWritingTool('todo_write')).toBe(false);
    expect(isWorkspaceWritingTool('read_file')).toBe(false);
    expect(isWorkspaceWritingTool('list_files')).toBe(false);
    expect(isWorkspaceWritingTool('file_search')).toBe(false);
  });
});

describe('StreamSupervisor desktop notifications', () => {
  it('does not notify while the user is focused on the same conversation', () => {
    expect(
      isDesktopConversationForeground('conversation-a', 'conversation-a', 'visible', true),
    ).toBe(true);
    expect(
      isDesktopConversationForeground('conversation-a', 'conversation-b', 'visible', true),
    ).toBe(false);
    expect(
      isDesktopConversationForeground('conversation-a', 'conversation-a', 'hidden', false),
    ).toBe(false);
  });

  it('maps terminal states without exposing message content', () => {
    expect(resolveDesktopNotificationKind([], 'done')).toBe('done');
    expect(resolveDesktopNotificationKind([], 'error')).toBe('error');
    expect(
      resolveDesktopNotificationKind(
        [{ type: 'clarification', status: 'waiting' }],
        'done',
      ),
    ).toBe('attention');
  });
});

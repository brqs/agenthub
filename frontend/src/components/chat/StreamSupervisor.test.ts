import { isWorkspaceWritingTool } from './StreamSupervisor';

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

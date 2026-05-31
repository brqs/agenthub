import type { DemoMessage } from './mockData';

export function getWorkspaceFilesFromMessages(messages: DemoMessage[]): string[] {
  const paths = new Set<string>();
  messages.forEach((message) => {
    message.content.forEach((block) => {
      if (block.type !== 'tool_call') return;
      const path = block.arguments.path;
      if (typeof path === 'string') paths.add(path);
    });
  });
  return Array.from(paths);
}

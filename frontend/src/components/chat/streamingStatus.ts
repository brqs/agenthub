import { Activity, Code2, FileText, GitCompare, Globe2 } from 'lucide-react';
import type { DemoContentBlock, DemoMessage } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';

const BLOCK_LABEL: Record<string, string> = {
  text: '正在组织回复',
  code: '正在输出代码',
  diff: '正在生成 Diff',
  web_preview: '正在整理网页预览',
  file: '正在准备文件',
  task_card: '正在更新任务进度',
  agent_switch: '正在切换 Agent',
};

const BLOCK_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  text: FileText,
  code: Code2,
  diff: GitCompare,
  web_preview: Globe2,
  file: FileText,
  task_card: Activity,
  agent_switch: Activity,
};

export function getStreamingStatus(messages: DemoMessage[]) {
  const streamingMessage = [...messages].reverse().find((message) => message.status === 'streaming');
  if (!streamingMessage) return null;

  const agent = getAgent(streamingMessage.agent_id);
  const latestBlock = [...streamingMessage.content].reverse().find(Boolean) as
    | DemoContentBlock
    | undefined;
  const blockType = latestBlock?.type ?? 'text';

  return {
    agentName: agent?.name ?? 'Agent',
    blockType,
    label: BLOCK_LABEL[blockType] ?? '正在处理',
    Icon: BLOCK_ICON[blockType] ?? Activity,
  };
}

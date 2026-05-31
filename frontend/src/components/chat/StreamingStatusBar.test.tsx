import { render, screen } from '@testing-library/react';
import { StreamingStatusBar } from './StreamingStatusBar';
import { getStreamingStatus } from './streamingStatus';
import { mockAgents, type DemoMessage } from '@/lib/mockData';

const streamingMessage: DemoMessage = {
  id: 'msg-streaming',
  conversation_id: 'conv-test',
  role: 'agent',
  agent_id: 'codex-helper',
  content: [{ type: 'code', language: 'tsx', code: 'export {}' }],
  reply_to_id: null,
  status: 'streaming',
  is_pinned: false,
  created_at: new Date().toISOString(),
};

describe('StreamingStatusBar', () => {
  it('derives status from the latest streaming message', () => {
    expect(getStreamingStatus([streamingMessage], mockAgents)).toMatchObject({
      agentName: 'Codex Helper',
      blockType: 'code',
      label: '正在输出代码',
    });
  });

  it('renders streaming status', () => {
    render(<StreamingStatusBar messages={[streamingMessage]} agents={mockAgents} />);

    expect(screen.getByRole('status')).toHaveTextContent('Codex Helper 正在输出代码');
  });

  it('renders nothing when no message is streaming', () => {
    const { container } = render(
      <StreamingStatusBar messages={[{ ...streamingMessage, status: 'done' }]} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

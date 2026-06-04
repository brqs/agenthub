import { render, screen } from '@testing-library/react';
import { ReviewThreadTimeline } from './ReviewThreadTimeline';
import type { Agent, OrchestratorRunDetail } from '@/lib/types';

const agents: Agent[] = [
  {
    id: 'claude-code',
    name: 'Claude Code',
    provider: 'claude_code',
    avatar_url: '',
    capabilities: [],
    config: {},
    is_builtin: false,
    created_at: '2026-06-03T12:00:00Z',
  },
  {
    id: 'opencode-helper',
    name: 'OpenCode Helper',
    provider: 'opencode',
    avatar_url: '',
    capabilities: [],
    config: {},
    is_builtin: false,
    created_at: '2026-06-03T12:00:00Z',
  },
];

const detail = {
  run: {
    id: 'run-1',
    conversation_id: 'conv-1',
    status: 'done',
    user_request: '',
    plan_source: 'direct',
    final_summary: '',
    created_at: '2026-06-03T12:00:00Z',
    updated_at: '2026-06-03T12:00:00Z',
  },
  tasks: [
    {
      id: 'row-1',
      run_id: 'run-1',
      task_id: 'impl',
      agent_id: 'claude-code',
      title: '实现文档',
      instruction: '',
      depends_on: [],
      priority: 1,
      include_history: true,
      task_type: 'implementation',
      final_state: 'succeeded',
      created_at: '2026-06-03T12:00:00Z',
      updated_at: '2026-06-03T12:00:00Z',
    },
    {
      id: 'row-2',
      run_id: 'run-1',
      task_id: 'review',
      agent_id: 'opencode-helper',
      title: '复核文档',
      instruction: '',
      depends_on: ['impl'],
      priority: 2,
      include_history: true,
      task_type: 'review',
      review_of: ['impl'],
      final_state: 'failed',
      created_at: '2026-06-03T12:00:01Z',
      updated_at: '2026-06-03T12:00:01Z',
    },
  ],
  attempts: [
    {
      id: 'attempt-2',
      run_id: 'run-1',
      task_row_id: 'row-2',
      task_id: 'review',
      attempt_index: 1,
      agent_id: 'opencode-helper',
      state: 'failed',
      text_preview: '需要补充摘要',
      artifact_paths: [],
      missing_artifact_paths: [],
      review_outcome: 'needs_repair',
      created_at: '2026-06-03T12:00:02Z',
    },
  ],
  events: [],
} satisfies OrchestratorRunDetail;

describe('ReviewThreadTimeline', () => {
  it('renders review outcome and handoff relationships', () => {
    render(<ReviewThreadTimeline detail={detail} agents={agents} />);

    expect(screen.getByText('Review / Handoff Timeline')).toBeInTheDocument();
    expect(screen.getByText('Implementation')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText('需要修复')).toBeInTheDocument();
    expect(screen.getByText('review of impl')).toBeInTheDocument();
    expect(screen.getByText('需要补充摘要')).toBeInTheDocument();
  });
});

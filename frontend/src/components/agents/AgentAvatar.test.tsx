import { fireEvent, render, screen } from '@testing-library/react';
import { AgentAvatar } from './AgentAvatar';
import type { Agent } from '@/lib/types';

const openAiAgent: Agent = {
  id: 'codex-helper',
  name: 'Codex Helper',
  provider: 'openai',
  avatar_url: '',
  capabilities: ['前端实现'],
  system_prompt: null,
  config: {},
  is_builtin: true,
  created_at: new Date().toISOString(),
};

const customAgent: Agent = {
  ...openAiAgent,
  id: 'orchestrator',
  name: 'Orchestrator',
  provider: 'custom',
};

describe('AgentAvatar', () => {
  it('uses provider logo assets for supported AI companies', () => {
    render(<AgentAvatar agent={openAiAgent} />);

    expect(screen.getByAltText('Codex Helper logo')).toBeInTheDocument();
  });

  it('falls back to the initial when a logo cannot load', () => {
    render(<AgentAvatar agent={openAiAgent} />);

    fireEvent.error(screen.getByAltText('Codex Helper logo'));

    expect(screen.queryByAltText('Codex Helper logo')).not.toBeInTheDocument();
    expect(screen.getByText('C')).toBeInTheDocument();
  });

  it('uses role icons for known custom demo agents', () => {
    render(<AgentAvatar agent={customAgent} />);

    expect(screen.queryByAltText('Orchestrator logo')).not.toBeInTheDocument();
    expect(screen.queryByText('O')).not.toBeInTheDocument();
  });

  it('falls back to initials for unknown custom agents', () => {
    render(<AgentAvatar agent={{ ...customAgent, id: 'custom-writer', name: 'Writer Agent' }} />);

    expect(screen.queryByAltText('Writer Agent logo')).not.toBeInTheDocument();
    expect(screen.getByText('W')).toBeInTheDocument();
  });
});

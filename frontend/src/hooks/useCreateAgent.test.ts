import { buildAgentConfig } from './useCreateAgent';

describe('buildAgentConfig', () => {
  it('builds builtin runtime config', () => {
    expect(
      buildAgentConfig({
        name: 'Builtin',
        provider: 'builtin',
        model: 'deepseek-v4-flash',
        maxIterations: 12,
        capabilities: [],
        systemPrompt: '',
      }),
    ).toEqual({
      model_backend: 'deepseek',
      model_profile: {
        source: 'agenthub_default',
        provider: 'deepseek',
        model: 'deepseek-v4-flash',
      },
      max_iterations: 12,
      mcp_servers: [],
    });
  });

  it('maps no-code builder permissions into builtin config', () => {
    expect(
      buildAgentConfig({
        name: 'Builder',
        provider: 'builtin',
        model: 'deepseek',
        maxIterations: 10,
        capabilities: [],
        systemPrompt: '',
        permissions: {
          workspace_read: true,
          workspace_write: true,
          run_commands: 'ask',
          network: 'never',
          deploy: 'never',
          external_accounts: 'never',
        },
        memoryPolicy: 'conversation',
        builderProfile: {
          role: 'Reviewer',
          purpose: 'Review code',
          goals: ['Find bugs'],
          tone: 'concise',
          do_not_do: ['Do not rewrite'],
          clarification_policy: 'balanced',
          output_style: 'Findings first',
          starters: ['Review this'],
        },
      }),
    ).toEqual({
      model_backend: 'deepseek',
      model_profile: {
        source: 'agenthub_default',
        provider: 'deepseek',
        model: 'deepseek-v4-flash',
      },
      max_iterations: 10,
      mcp_servers: [],
      allowed_tools: ['read_file', 'write_file', 'bash'],
      memory_policy: 'conversation',
      permissions: {
        workspace_read: true,
        workspace_write: true,
        run_commands: 'ask',
        network: 'never',
        deploy: 'never',
        external_accounts: 'never',
      },
      builder_profile: {
        role: 'Reviewer',
        purpose: 'Review code',
        goals: ['Find bugs'],
        tone: 'concise',
        do_not_do: ['Do not rewrite'],
        clarification_policy: 'balanced',
        output_style: 'Findings first',
        starters: ['Review this'],
      },
    });
  });

  it('binds a user model account for builtin agents', () => {
    expect(
      buildAgentConfig({
        name: 'Custom Model',
        provider: 'builtin',
        model: 'gpt-4o-mini',
        capabilities: [],
        systemPrompt: '',
        modelProfile: {
          source: 'user_account',
          account_id: 'account-1',
          provider: 'openai',
          model: 'gpt-4o-mini',
        },
      }),
    ).toEqual({
      model_backend: 'openai',
      model_profile: {
        source: 'user_account',
        account_id: 'account-1',
        provider: 'openai',
        model: 'gpt-4o-mini',
      },
      max_iterations: 10,
      mcp_servers: [],
    });
  });

  it('builds claude code sdk options config', () => {
    expect(
      buildAgentConfig({
        name: 'Claude',
        provider: 'claude_code',
        model: 'claude-sonnet-4-6-latest',
        sdkOptions: { permissionMode: 'acceptEdits' },
        timeoutSeconds: 180,
        capabilities: [],
        systemPrompt: '',
      }),
    ).toEqual({
      sdk_options: {
        model: 'claude-sonnet-4-6-latest',
        permissionMode: 'acceptEdits',
      },
      timeout_seconds: 180,
    });
  });

  it('builds opencode cli config', () => {
    expect(
      buildAgentConfig({
        name: 'OpenCode',
        provider: 'opencode',
        model: 'opencode',
        command: 'opencode-cli',
        args: ['run', '--json'],
        timeoutSeconds: 90,
        capabilities: [],
        systemPrompt: '',
      }),
    ).toEqual({
      command: 'opencode-cli',
      args: ['run', '--json'],
      timeout_seconds: 90,
    });
  });
});

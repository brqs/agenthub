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
      max_iterations: 12,
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

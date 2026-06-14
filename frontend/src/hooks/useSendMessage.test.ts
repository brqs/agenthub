import { resolveTargetAgentId } from './useSendMessage';

describe('resolveTargetAgentId', () => {
  it('returns null for single-agent conversations', () => {
    expect(resolveTargetAgentId('hello', 'single', ['claude-code'])).toBeNull();
  });

  it('routes explicit group mentions to the mentioned agent', () => {
    expect(
      resolveTargetAgentId('请 @codex-helper 处理这段代码', 'group', [
        'orchestrator',
        'codex-helper',
      ]),
    ).toBe('codex-helper');
  });

  it('routes strict requirement alignment group messages to orchestrator', () => {
    expect(
      resolveTargetAgentId(
        '请 @codex-helper 处理这段代码',
        'group',
        ['orchestrator', 'codex-helper'],
        'strict',
      ),
    ).toBe('orchestrator');
  });

  it('falls back to orchestrator in group conversations without mentions', () => {
    expect(resolveTargetAgentId('帮我拆解任务', 'group', ['orchestrator', 'codex-helper'])).toBe(
      'orchestrator',
    );
  });

  it('falls back to the first group agent when orchestrator is unavailable', () => {
    expect(resolveTargetAgentId('帮我拆解任务', 'group', ['claude-code', 'codex-helper'])).toBe(
      'claude-code',
    );
  });
});

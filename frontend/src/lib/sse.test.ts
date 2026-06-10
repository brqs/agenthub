import { subscribeMessageStream } from './sse';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { setRuntimeApiBaseUrl } from './env';

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: vi.fn(),
}));

const fetchEventSourceMock = vi.mocked(fetchEventSource);

describe('subscribeMessageStream', () => {
  beforeEach(() => {
    vi.useRealTimers();
    fetchEventSourceMock.mockReset();
    setRuntimeApiBaseUrl('');
  });

  it('treats 409 stream responses as fatal instead of retryable', async () => {
    const onError = vi.fn();
    let thrown: unknown;
    fetchEventSourceMock.mockImplementation(async (_url, options) => {
      try {
        await options?.onopen?.(
          new Response(
            JSON.stringify({
              detail: {
                error: {
                  code: 'MESSAGE_ALREADY_STREAMING',
                  message: 'This agent message is already streaming',
                },
              },
            }),
            { status: 409, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      } catch (error) {
        thrown = error;
        options?.onerror?.(error);
      }
    });

    subscribeMessageStream('message-1', { onEvent: vi.fn(), onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalled());

    expect(String(thrown)).toContain('MESSAGE_ALREADY_STREAMING');
    expect(onError).toHaveBeenCalledWith(thrown);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('shares one underlying stream for multiple subscribers of the same message', async () => {
    vi.useFakeTimers();
    fetchEventSourceMock.mockImplementation(async () => {
      await new Promise(() => undefined);
    });

    const first = subscribeMessageStream('message-shared', { onEvent: vi.fn() });
    const second = subscribeMessageStream('message-shared', { onEvent: vi.fn() });

    expect(fetchEventSourceMock).toHaveBeenCalledTimes(1);

    first.abort();
    await vi.advanceTimersByTimeAsync(250);
    expect(fetchEventSourceMock).toHaveBeenCalledTimes(1);

    const third = subscribeMessageStream('message-shared', { onEvent: vi.fn() });
    expect(fetchEventSourceMock).toHaveBeenCalledTimes(1);

    second.abort();
    third.abort();
    await vi.advanceTimersByTimeAsync(600);
  });

  it('opens streams against the runtime backend URL', () => {
    vi.useFakeTimers();
    setRuntimeApiBaseUrl('http://localhost:8100');
    fetchEventSourceMock.mockImplementation(async () => {
      await new Promise(() => undefined);
    });

    const sub = subscribeMessageStream('message-runtime-url', { onEvent: vi.fn() });

    expect(fetchEventSourceMock).toHaveBeenCalledWith(
      'http://localhost:8100/api/v1/messages/message-runtime-url/stream',
      expect.any(Object),
    );

    sub.abort();
    vi.advanceTimersByTime(600);
  });
});

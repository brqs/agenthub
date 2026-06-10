import { api } from './api';
import { getApiBaseUrl, setRuntimeApiBaseUrl } from './env';

describe('api runtime base URL', () => {
  afterEach(() => {
    setRuntimeApiBaseUrl('');
  });

  it('updates axios defaults when the runtime backend URL changes', () => {
    setRuntimeApiBaseUrl('http://localhost:8100/');

    expect(getApiBaseUrl()).toBe('http://localhost:8100');
    expect(api.defaults.baseURL).toBe('http://localhost:8100');
  });
});

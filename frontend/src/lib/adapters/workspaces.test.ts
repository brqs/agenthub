import { api } from '@/lib/api';
import {
  getWorkspaceTree,
  readWorkspaceFile,
  writeWorkspaceFile,
} from './workspaces';

const { apiGet, apiPut } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {
    get: apiGet,
    put: apiPut,
  },
}));

describe('workspaces adapter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizes backend workspace tree nodes', async () => {
    apiGet.mockResolvedValueOnce({
      data: {
        root: '/workspaces/demo',
        tree: {
          type: 'directory',
          name: '.',
          path: '',
          children: [
            {
              type: 'file',
              name: 'index.html',
              path: 'dist/index.html',
              size: null,
              mime_type: null,
            },
          ],
        },
      },
    });

    await expect(getWorkspaceTree('conv-1')).resolves.toEqual({
      root: '/workspaces/demo',
      tree: {
        type: 'directory',
        name: '.',
        path: '',
        children: [
          {
            type: 'file',
            name: 'index.html',
            path: 'dist/index.html',
            size: 0,
            mime_type: 'application/octet-stream',
          },
        ],
      },
    });
  });

  it('reads text-like workspace files as strings', async () => {
    apiGet.mockResolvedValueOnce({
      data: {
        type: 'application/json',
        size: 11,
        text: () => Promise.resolve('{"ok":true}'),
      },
      headers: { 'content-type': 'application/json' },
    });

    await expect(readWorkspaceFile('conv-1', 'src/data.json')).resolves.toMatchObject({
      path: 'src/data.json',
      name: 'data.json',
      mime_type: 'application/json',
      content: '{"ok":true}',
    });
  });

  it('encodes nested workspace paths when writing files', async () => {
    apiPut.mockResolvedValueOnce({ data: undefined });

    await writeWorkspaceFile('conv-1', 'src/hello world.ts', 'export {};', 'text/plain');

    expect(api.put).toHaveBeenCalledWith(
      '/api/v1/workspaces/conv-1/files/src/hello%20world.ts',
      'export {};',
      { headers: { 'Content-Type': 'text/plain' } },
    );
  });
});

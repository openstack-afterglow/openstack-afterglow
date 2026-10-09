import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api, ApiError } from '../client';

// client.ts의 api 객체 직접 테스트 (fetch mock 필요)
const mockFetch = vi.fn();

vi.stubGlobal('fetch', mockFetch);

// 동적 import를 위해 env mock
vi.mock('$env/dynamic/public', () => ({
  env: { PUBLIC_API_BASE: 'http://localhost:8000' },
}));

describe('api client', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('GET 요청에 Authorization 헤더를 포함한다', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' }),
    });

    await api.get('/api/v1/health', 'my-token', 'proj-123');

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer my-token');
    expect(options.headers['X-Project-Id']).toBe('proj-123');
    expect(options.credentials).toBe('include');
  });

  it('204 응답에서 undefined를 반환한다', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => ({}),
    });

    const result = await api.delete('/api/v1/volumes/vol-1');
    expect(result).toBeUndefined();
  });

  it('오류 응답에서 ApiError를 던진다', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ detail: '리소스를 찾을 수 없습니다' }),
    });

    await expect(api.get('/api/v1/volumes/bad-id')).rejects.toBeInstanceOf(ApiError);
  });

  it.each(['invalid_token', null, 123])('preserves only string failure codes (%s)', async (code) => {
    mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Invalid personal key', code }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    }));
    await expect(api.post('/api/v1/auth/mcp-tokens/verify', { token: 'private-key' })).rejects.toMatchObject({
      status: 400, message: 'Invalid personal key', code: typeof code === 'string' ? code : undefined,
    });
  });

  it('PATCH 메서드가 올바르게 호출된다', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: 'img-1', name: 'updated' }),
    });

    await api.patch('/api/v1/images/img-1', { name: 'updated' });

    const [, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe('PATCH');
    expect(JSON.parse(options.body)).toEqual({ name: 'updated' });
  });
});

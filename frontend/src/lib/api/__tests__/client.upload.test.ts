import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE: 'http://localhost:8000' },
}));
vi.mock('$app/environment', () => ({ browser: true }));


const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// XHR mock — 테스트가 직접 이벤트를 트리거
let lastXhr: MockXhr;
class MockXhr {
	status = 200;
	responseText = '{}';
	statusText = 'OK';
	timeout = 0;
	upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
		onprogress: null,
	};
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	onabort: (() => void) | null = null;
	_headers: Record<string, string> = {};
	_method = '';
	_url = '';
	_body: unknown = null;

	open(method: string, url: string) {
		this._method = method;
		this._url = url;
	}
	setRequestHeader(k: string, v: string) {
		this._headers[k] = v;
	}
	send(body: unknown) {
		this._body = body;
	}
	abort() {
		this.onabort?.();
	}
	constructor() {
		// eslint-disable-next-line @typescript-eslint/no-this-alias
		lastXhr = this;
	}
}
vi.stubGlobal('XMLHttpRequest', MockXhr);
function jsonResponse(value: unknown): Response {
	return new Response(JSON.stringify(value), {
		status: 200,
		headers: { 'Content-Type': 'application/json' },
	});
}

// Tests reload the client to isolate its shared refresh and cache state.
afterEach(() => localStorage.clear());

describe('authenticated progress upload recovery', () => {
	beforeEach(() => {
		vi.resetModules();
		mockFetch.mockReset();
		localStorage.clear();
	});

	it('recovers an XHR 401 with the original upload body and reports retried progress', async () => {
		const { setAuth } = await import('$lib/stores/auth');
		setAuth({ token: 'old-token', refreshToken: 'refresh-token', accessExpiresAt: null });
		mockFetch.mockResolvedValueOnce(jsonResponse({ token: 'new-token', refresh_token: 'new-refresh' }));
		const { api } = await import('../client');
		const form = new FormData();
		form.append('file', new Blob(['data']), 'file.txt');
		const progress = vi.fn();
		const { promise } = api.uploadWithProgress<{ id: string }>('/api/v1/upload', form, progress, 'old-token', 'project');
		const rejectedXhr = lastXhr;
		rejectedXhr.status = 401;
		rejectedXhr.onload?.();
		await vi.waitFor(() => expect(lastXhr).not.toBe(rejectedXhr));
		expect(lastXhr._headers['Authorization']).toBe('Bearer new-token');
		expect(lastXhr._headers['X-Project-Id']).toBe('project');
		expect(lastXhr._body).toBe(form);
		lastXhr.upload.onprogress?.({ lengthComputable: true, loaded: 100, total: 100 });
		lastXhr.responseText = '{"id":"uploaded"}';
		lastXhr.onload?.();
		await expect(promise).resolves.toEqual({ id: 'uploaded' });
		expect(progress).toHaveBeenLastCalledWith({ loaded: 100, total: 100 });
		expect(mockFetch).toHaveBeenCalledOnce();
	});

	it('aborts during refresh without sending a second PUT or cancelling session rotation', async () => {
		const { setAuth } = await import('$lib/stores/auth');
		setAuth({ token: 'old-token', refreshToken: 'refresh-token', accessExpiresAt: null });
		const refreshResponse = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(refreshResponse.promise);
		const { api, refreshSession } = await import('../client');
		const { promise, abort } = api.putWithProgress('/api/v1/upload', new Blob(['data']), 'text/plain', vi.fn(), 'old-token');
		const rejectedXhr = lastXhr;
		rejectedXhr.status = 401;
		rejectedXhr.onload?.();
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const rotation = refreshSession();
		abort();
		await expect(promise).rejects.toMatchObject({ status: 0 });
		refreshResponse.resolve(jsonResponse({ token: 'new-token', refresh_token: 'new-refresh' }));
		await expect(rotation).resolves.toBe('new-token');
		expect(lastXhr).toBe(rejectedXhr);
	});
});


describe('api.upload', () => {
	beforeEach(() => {
		mockFetch.mockReset();
		vi.resetModules();
	});

	it('FormData POST에 올바른 헤더 설정', async () => {
		mockFetch.mockResolvedValueOnce({
			ok: true,
			status: 200,
			json: async () => ({ id: 'obj-1' }),
		});

		const { api } = await import('../client');
		const formData = new FormData();
		const result = await api.upload('/api/v1/upload', formData, 'my-token', 'proj-1');

		const [url, opts] = mockFetch.mock.calls[0];
		expect(url).toContain('/api/v1/upload');
		expect(opts.method).toBe('POST');
		expect(opts.headers['Authorization']).toBe('Bearer my-token');
		expect(opts.headers['X-Project-Id']).toBe('proj-1');
		expect(opts.headers['Content-Type']).toBeUndefined();
		expect(result).toEqual({ id: 'obj-1' });
	});

	it('204 응답 시 undefined 반환', async () => {
		mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
		const { api } = await import('../client');
		const result = await api.upload('/api/v1/upload', new FormData());
		expect(result).toBeUndefined();
	});

	it('오류 응답 시 ApiError 반환', async () => {
		mockFetch.mockResolvedValueOnce({
			ok: false,
			status: 413,
			statusText: 'Too Large',
			json: async () => ({ detail: '파일이 너무 큽니다' }),
		});
		const { api, ApiError } = await import('../client');
		await expect(api.upload('/api/v1/upload', new FormData())).rejects.toBeInstanceOf(ApiError);
	});
	it('invalidates a completed warm GET before and after an upload mutation', async () => {
		mockFetch
			.mockResolvedValueOnce(jsonResponse({ source: 'warm' }))
			.mockResolvedValueOnce(jsonResponse({ id: 'uploaded' }))
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));
		const { api } = await import('../client');

		await api.prefetch('/api/v1/items', 'token', 'project');
		await api.upload('/api/v1/upload', new FormData(), 'token', 'project');

		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

});

describe('api.uploadWithProgress', () => {
	beforeEach(() => {
		vi.resetModules();
	});

	it('XHR에 올바른 헤더 설정', async () => {
		const { api } = await import('../client');
		api.uploadWithProgress('/api/v1/upload', new FormData(), vi.fn(), 'tok', 'my-proj');

		expect(lastXhr._headers['Authorization']).toBe('Bearer tok');
		expect(lastXhr._headers['X-Project-Id']).toBe('my-proj');
		expect(lastXhr._method).toBe('POST');
	});

	it('onload 성공 시 JSON 파싱 결과 반환', async () => {
		const { api } = await import('../client');
		// uploadWithProgress 호출 후에 lastXhr 설정 (XHR 인스턴스가 생성된 뒤)
		const { promise } = api.uploadWithProgress('/api/v1/upload', new FormData(), vi.fn());
		lastXhr.status = 200;
		lastXhr.responseText = '{"id":"obj-1"}';
		lastXhr.onload?.();

		const result = await promise;
		expect(result).toEqual({ id: 'obj-1' });
	});

	it('204 응답 시 undefined 반환', async () => {
		const { api } = await import('../client');
		const { promise } = api.uploadWithProgress('/api/v1/upload', new FormData(), vi.fn());
		lastXhr.status = 204;
		lastXhr.onload?.();

		expect(await promise).toBeUndefined();
	});

	it('progress 이벤트 콜백 호출', async () => {
		const { api } = await import('../client');
		const onProgress = vi.fn();
		api.uploadWithProgress('/api/v1/upload', new FormData(), onProgress);

		lastXhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
		expect(onProgress).toHaveBeenCalledWith({ loaded: 50, total: 100 });
	});

	it('lengthComputable=false면 onProgress 호출 안 함', async () => {
		const { api } = await import('../client');
		const onProgress = vi.fn();
		api.uploadWithProgress('/api/v1/upload', new FormData(), onProgress);

		lastXhr.upload.onprogress?.({ lengthComputable: false, loaded: 0, total: 0 });
		expect(onProgress).not.toHaveBeenCalled();
	});

	it('abort()로 ApiError(0) reject', async () => {
		const { api, ApiError } = await import('../client');
		const { promise, abort } = api.uploadWithProgress('/api/v1/upload', new FormData(), vi.fn());
		abort();
		await expect(promise).rejects.toBeInstanceOf(ApiError);
		await expect(promise).rejects.toMatchObject({ status: 0 });
	});

	it('4xx onload 시 ApiError reject', async () => {
		const { api, ApiError } = await import('../client');
		const { promise } = api.uploadWithProgress('/api/v1/upload', new FormData(), vi.fn());
		lastXhr.status = 400;
		lastXhr.statusText = 'Bad Request';
		lastXhr.responseText = '{"detail":"잘못된 요청"}';
		lastXhr.onload?.();
		await expect(promise).rejects.toBeInstanceOf(ApiError);
	});

	it('onerror 시 네트워크 오류 reject', async () => {
		const { api } = await import('../client');
		const { promise } = api.uploadWithProgress('/api/v1/upload', new FormData(), vi.fn());
		lastXhr.onerror?.();
		await expect(promise).rejects.toThrow('네트워크 오류');
	});
	it('invalidates warm data around XHR progress uploads', async () => {
		mockFetch.mockReset().mockResolvedValueOnce(jsonResponse({ source: 'warm' }));
		const { api } = await import('../client');
		await api.prefetch('/api/v1/items', 'token', 'project');

		const { promise } = api.uploadWithProgress('/api/v1/upload', new FormData(), vi.fn(), 'token', 'project');
		lastXhr.status = 200;
		lastXhr.responseText = '{"ok":true}';
		lastXhr.onload?.();
		await promise;
		mockFetch.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));

		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

});

describe('api.putWithProgress', () => {
	beforeEach(() => {
		vi.resetModules();
	});

	it('PUT 메서드로 blob 전송', async () => {
		const { api } = await import('../client');
		const blob = new Blob(['data'], { type: 'text/plain' });
		api.putWithProgress('/api/v1/upload', blob, 'text/plain', vi.fn(), 'tok', 'proj');

		expect(lastXhr._method).toBe('PUT');
		expect(lastXhr._headers['Content-Type']).toBe('text/plain');
		expect(lastXhr._headers['Authorization']).toBe('Bearer tok');
		expect(lastXhr._body).toBe(blob);
	});

	it('성공 시 JSON 파싱', async () => {
		const { api } = await import('../client');
		const blob = new Blob(['data']);
		const { promise } = api.putWithProgress('/api/v1/upload', blob, 'application/octet-stream', vi.fn());
		lastXhr.status = 200;
		lastXhr.responseText = '{"etag":"abc"}';
		lastXhr.onload?.();

		expect(await promise).toEqual({ etag: 'abc' });
	});

	it('abort() 동작', async () => {
		const { api, ApiError } = await import('../client');
		const blob = new Blob(['data']);
		const { promise, abort } = api.putWithProgress('/api/v1/upload', blob, 'application/octet-stream', vi.fn());
		abort();
		await expect(promise).rejects.toBeInstanceOf(ApiError);
	});

	it('contentType 없으면 application/octet-stream 기본값', async () => {
		const { api } = await import('../client');
		const blob = new Blob(['data']);
		api.putWithProgress('/api/v1/upload', blob, '', vi.fn());
		expect(lastXhr._headers['Content-Type']).toBe('application/octet-stream');
	});
	it('invalidates warm data around absolute PUT progress uploads', async () => {
		mockFetch.mockReset().mockResolvedValueOnce(jsonResponse({ source: 'warm' }));
		const { api } = await import('../client');
		await api.prefetch('/api/v1/items', 'token', 'project');

		const { promise } = api.putWithProgress('https://upload.example.test/object', new Blob(['data']), 'text/plain', vi.fn(), 'token', 'project');
		lastXhr.status = 200;
		lastXhr.responseText = '{"etag":"abc"}';
		lastXhr.onload?.();
		await promise;
		mockFetch.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));

		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

});

describe('api.downloadBlob', () => {
	beforeEach(() => {
		mockFetch.mockReset();
		vi.resetModules();
	});

	it('Content-Disposition에서 filename 파싱', async () => {
		const blob = new Blob(['file content'], { type: 'text/plain' });
		mockFetch.mockResolvedValueOnce({
			ok: true,
			status: 200,
			headers: new Headers({ 'Content-Disposition': 'attachment; filename="report.pdf"' }),
			blob: async () => blob,
		});

		const { api } = await import('../client');
		const result = await api.downloadBlob('/api/v1/download');
		expect(result.filename).toBe('report.pdf');
		expect(result.blob).toBe(blob);
	});

	it('Content-Disposition 없으면 "download" 기본값', async () => {
		mockFetch.mockResolvedValueOnce({
			ok: true,
			status: 200,
			headers: new Headers(),
			blob: async () => new Blob(['x']),
		});

		const { api } = await import('../client');
		const result = await api.downloadBlob('/api/v1/download');
		expect(result.filename).toBe('download');
	});

	it('인증 헤더 전달', async () => {
		mockFetch.mockResolvedValueOnce({
			ok: true,
			status: 200,
			headers: new Headers(),
			blob: async () => new Blob(),
		});

		const { api } = await import('../client');
		await api.downloadBlob('/api/v1/download', 'tok', 'proj-1');

		const [, opts] = mockFetch.mock.calls[0];
		expect(opts.headers['Authorization']).toBe('Bearer tok');
		expect(opts.headers['X-Project-Id']).toBe('proj-1');
	});

	it('오류 응답 시 ApiError 반환', async () => {
		mockFetch.mockResolvedValueOnce({
			ok: false,
			status: 403,
			statusText: 'Forbidden',
			json: async () => ({ detail: '권한 없음' }),
		});

		const { api, ApiError } = await import('../client');
		await expect(api.downloadBlob('/api/v1/download')).rejects.toBeInstanceOf(ApiError);
	});
});

describe('api.postSse', () => {
	beforeEach(() => {
		mockFetch.mockReset();
		vi.resetModules();
	});

	function makeStreamResponse(chunks: string[]) {
		const encoder = new TextEncoder();
		let index = 0;
		const reader = {
			read: vi.fn(async () => {
				if (index < chunks.length) {
					return { done: false, value: encoder.encode(chunks[index++]) };
				}
				return { done: true, value: undefined };
			}),
		};
		return {
			ok: true,
			status: 200,
			body: { getReader: () => reader },
		};
	}

	it('data: 라인을 파싱해 onMessage 콜백 호출', async () => {
		const onMessage = vi.fn();
		mockFetch.mockResolvedValueOnce(
			makeStreamResponse(['data: {"status":"running"}\n', 'data: {"status":"done"}\n', ''])
		);

		const { api } = await import('../client');
		api.postSse('/api/v1/sse', { cmd: 'run' }, 'tok', 'proj', onMessage);

		// 비동기 스트림 처리 대기
		await new Promise((r) => setTimeout(r, 10));
		expect(onMessage).toHaveBeenCalledTimes(2);
		expect(onMessage.mock.calls[0][0]).toEqual({ status: 'running' });
		expect(onMessage.mock.calls[1][0]).toEqual({ status: 'done' });
	});

	it('JSON 파싱 실패는 조용히 무시', async () => {
		const onMessage = vi.fn();
		mockFetch.mockResolvedValueOnce(makeStreamResponse(['data: not-json\n', '']));

		const { api } = await import('../client');
		api.postSse('/api/v1/sse', {}, undefined, undefined, onMessage);
		await new Promise((r) => setTimeout(r, 10));
		expect(onMessage).not.toHaveBeenCalled();
	});

	it('fetch 오류 시 onError 콜백 호출', async () => {
		const onError = vi.fn();
		mockFetch.mockRejectedValueOnce(new Error('Network failure'));

		const { api } = await import('../client');
		api.postSse('/api/v1/sse', {}, undefined, undefined, undefined, onError);
		await new Promise((r) => setTimeout(r, 10));
		expect(onError).toHaveBeenCalledOnce();
	});

	it('인증 헤더 전달', async () => {
		mockFetch.mockResolvedValueOnce(makeStreamResponse(['']));

		const { api } = await import('../client');
		api.postSse('/api/v1/sse', { body: true }, 'my-tok', 'my-proj');
		await new Promise((r) => setTimeout(r, 10));

		const [, opts] = mockFetch.mock.calls[0];
		expect(opts.headers['Authorization']).toBe('Bearer my-tok');
		expect(opts.headers['X-Project-Id']).toBe('my-proj');
		expect(opts.headers['Accept']).toBe('text/event-stream');
	});
	it('invalidates warm data before and after POST SSE streams', async () => {
		mockFetch
			.mockResolvedValueOnce(jsonResponse({ source: 'warm' }))
			.mockResolvedValueOnce(makeStreamResponse(['']))
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));
		const { api } = await import('../client');
		await api.prefetch('/api/v1/items', 'token', 'project');

		api.postSse('/api/v1/stream', {}, 'token', 'project');

		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

});

describe('getBaseUrl', () => {
	beforeEach(() => {
		vi.resetModules();
	});

	it('runtime api_base가 설정되어 있으면 그것을 반환', async () => {
		const { initSiteConfig } = await import('$lib/config/site');
		initSiteConfig({
			site_name: 'Afterglow',
			site_description: '',
			logo_path: '/logo.png',
			favicon_path: '/favicon.ico',
			refresh_interval_ms: 5000,
			services: { magnum: false, manila: false, zun: false, k3s: false, trove: false, swift: false, barbican: false },
			runtime: { api_base: 'http://api.example.com', s3_base: '', grafana_base: '', librechat_base: '', gitlab_base: '' },
		});
		const { getBaseUrl } = await import('../client');
		expect(getBaseUrl()).toBe('http://api.example.com');
	});
});

describe('memoryCache', () => {
	it('Map 인스턴스 export', async () => {
		const { memoryCache } = await import('../client');
		expect(memoryCache).toBeInstanceOf(Map);
	});
});

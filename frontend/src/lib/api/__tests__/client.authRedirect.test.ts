import { beforeEach, describe, expect, it, vi } from 'vitest';

const { goto, clearAuth, mockFetch, auth, logoutInProgress, setAuth, session, logoutState } = vi.hoisted(() => {
	const session = {
		value: { token: 'expired-token', refreshToken: 'refresh-token' as string | null, accessExpiresAt: null as number | null },
	};
	const logoutState = { value: false };
	return {
		goto: vi.fn(),
		clearAuth: vi.fn(),
		mockFetch: vi.fn(),
		auth: {
			subscribe: (run: (value: typeof session.value) => void) => {
				run(session.value);
				return () => {};
			},
		},
		logoutInProgress: {
			subscribe: (run: (value: boolean) => void) => {
				run(logoutState.value);
				return () => {};
			},
		},
		setAuth: vi.fn((next: Partial<typeof session.value>) => {
			session.value = { ...session.value, ...next };
		}),
		session,
		logoutState,
	};
});

vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$lib/stores/auth', () => ({
	auth,
	clearAuth,
	getMockupProfile: () => null,
	isMockAuthActive: () => false,
	logoutInProgress,
	setAuth,
}));
vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE: 'http://localhost:8000' },
}));

vi.stubGlobal('fetch', mockFetch);

// Each case reloads client.ts to isolate its module-scoped refresh/redirect state.

describe('unauthorized API redirect', () => {
	let replace = vi.fn();

	beforeEach(() => {
		vi.resetModules();
		vi.clearAllMocks();
		mockFetch.mockReset();
		session.value = { token: 'expired-token', refreshToken: 'refresh-token', accessExpiresAt: null };
		logoutState.value = false;
		localStorage.clear();
		replace = vi.fn();
		goto.mockResolvedValue(undefined);
		vi.stubGlobal('window', {
			location: {
				pathname: '/dashboard',
				protocol: 'http:',
				hostname: 'localhost',
				replace,
			},
		});
		mockFetch.mockResolvedValue({
			ok: false,
			status: 401,
			statusText: 'Unauthorized',
			json: async () => ({ detail: '인증이 필요합니다' }),
			text: async () => '인증이 필요합니다',
		});
	});

	it('replaces history when an unauthorized request clears the session', async () => {
		const { api, ApiError } = await import('../client');

		await expect(api.get('/api/v1/protected', 'expired-token', 'project')).rejects.toBeInstanceOf(ApiError);
		await vi.waitFor(() => expect(clearAuth).toHaveBeenCalledOnce());

		expect(goto).toHaveBeenCalledWith('/login', { replaceState: true });
		expect(replace).not.toHaveBeenCalled();
	});

	it('uses location.replace when Svelte navigation rejects', async () => {
		goto.mockRejectedValueOnce(new Error('navigation failure'));
		const { api, ApiError } = await import('../client');

		await expect(api.get('/api/v1/protected', 'expired-token', 'project')).rejects.toBeInstanceOf(ApiError);
		await vi.waitFor(() => expect(replace).toHaveBeenCalledWith('/login'));
	});

	it('coalesces concurrent unauthorized redirects before dynamic imports resolve', async () => {
		session.value = { ...session.value, refreshToken: null };
		const { api } = await import('../client');

		await Promise.allSettled([
			api.get('/api/v1/protected-a', 'expired-token', 'project'),
			api.get('/api/v1/protected-b', 'expired-token', 'project'),
		]);

		await vi.waitFor(() => expect(clearAuth).toHaveBeenCalledOnce());
		expect(goto).toHaveBeenCalledOnce();
		expect(goto).toHaveBeenCalledWith('/login', { replaceState: true });
	});

	it('refreshes an expired session before dispatching concurrent dashboard requests without a timer', async () => {
		session.value.accessExpiresAt = Math.floor(Date.now() / 1000) - 1;
		const order: string[] = [];
		mockFetch.mockImplementation(async (url: string, init: RequestInit) => {
			if (url.endsWith('/auth/refresh')) {
				order.push('refresh');
				return Response.json({
					token: 'fresh-token',
					refresh_token: 'fresh-refresh',
					expires_at: new Date(Date.now() + 900_000).toISOString(),
				});
			}
			const authorization = new Headers(init.headers).get('Authorization');
			order.push(authorization ?? 'anonymous');
			return authorization === 'Bearer fresh-token'
				? Response.json({ ready: true })
				: Response.json({ detail: 'expired' }, { status: 401 });
		});
		const { api } = await import('../client');

		await expect(Promise.all([
			api.get('/api/v1/dashboard/summary', 'expired-token', 'project'),
			api.get('/api/v1/dashboard/quotas', 'expired-token', 'project'),
		])).resolves.toEqual([{ ready: true }, { ready: true }]);
		expect(order).toEqual(['refresh', 'Bearer fresh-token', 'Bearer fresh-token']);
		expect(clearAuth).not.toHaveBeenCalled();
	});

	it('refreshes the expired current session when a long-lived callback still holds an older token', async () => {
		session.value = { token: 'already-rotated-token', refreshToken: 'current-refresh', accessExpiresAt: 1 };
		mockFetch
			.mockResolvedValueOnce(Response.json({ token: 'fresh-token', refresh_token: 'fresh-refresh' }))
			.mockImplementation(async (_url: string, init: RequestInit) =>
				new Headers(init.headers).get('Authorization') === 'Bearer fresh-token'
					? Response.json({ recovered: true })
					: Response.json({ detail: 'expired' }, { status: 401 }));
		const { api } = await import('../client');
		await expect(api.get('/api/v1/dashboard/summary', 'older-captured-token')).resolves.toEqual({ recovered: true });
		expect(mockFetch).toHaveBeenCalledTimes(2);
		expect(clearAuth).not.toHaveBeenCalled();
	});

	it('recovers a download handshake 401 before returning bytes to the caller', async () => {
		mockFetch
			.mockResolvedValueOnce(Response.json({ detail: 'expired' }, { status: 401 }))
			.mockResolvedValueOnce(Response.json({
				token: 'fresh-token',
				refresh_token: 'fresh-refresh',
				expires_at: new Date(Date.now() + 900_000).toISOString(),
			}))
			.mockResolvedValueOnce(new Response('recovered file', {
				headers: { 'Content-Disposition': 'attachment; filename="report.txt"' },
			}));
		const { api } = await import('../client');

		const result = await api.downloadBlob('/api/v1/report', 'expired-token', 'project');
		const contents = Promise.withResolvers<string>();
		const reader = new FileReader();
		reader.onload = () => contents.resolve(String(reader.result));
		reader.onerror = () => contents.reject(reader.error);
		reader.readAsText(result.blob);
		expect(await contents.promise).toBe('recovered file');
		expect(result.filename).toBe('report.txt');
		expect(clearAuth).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
	});

	it('cancels a waiting request without cancelling the shared refresh or dispatching its body', async () => {
		const refreshResponse = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(refreshResponse.promise);
		const { fetchWithAuth, refreshSession } = await import('../client');
		const refresh = refreshSession();
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const controller = new AbortController();
		const request = fetchWithAuth('/api/v1/upload', {
			method: 'POST', body: new FormData(), signal: controller.signal,
		}, 'expired-token', 'project');
		controller.abort();
		await expect(request).rejects.toMatchObject({ name: 'AbortError' });
		refreshResponse.resolve(Response.json({ token: 'fresh-token', refresh_token: 'fresh-refresh' }));
		await expect(refresh).resolves.toBe('fresh-token');
		expect(mockFetch).toHaveBeenCalledOnce();
		expect(clearAuth).not.toHaveBeenCalled();
	});

	it('joins in-flight rotation before POST and preserves the body and project on dispatch', async () => {
		const refreshResponse = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(refreshResponse.promise);
		const { fetchWithAuth, refreshSession } = await import('../client');
		const refresh = refreshSession();
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const form = new FormData();
		form.append('file', new Blob(['contents']), 'example.txt');
		mockFetch.mockImplementation(async (_url: string, init: RequestInit) => {
			const headers = new Headers(init.headers);
			if (headers.get('Authorization') !== 'Bearer fresh-token'
				|| headers.get('X-Project-Id') !== 'chosen-project'
				|| init.body !== form || headers.has('Content-Type')) {
				return Response.json({ detail: 'bad upload' }, { status: 400 });
			}
			return Response.json({ id: 'uploaded' });
		});
		const upload = fetchWithAuth('/api/v1/upload', { method: 'POST', body: form }, 'expired-token', 'chosen-project');
		expect(mockFetch).toHaveBeenCalledOnce();
		refreshResponse.resolve(Response.json({ token: 'fresh-token', refresh_token: 'fresh-refresh' }));
		await refresh;
		const response = await upload;
		expect(await response.json()).toEqual({ id: 'uploaded' });
		expect(clearAuth).not.toHaveBeenCalled();
	});

	it('does not attach or refresh browser credentials for a public request', async () => {
		session.value.accessExpiresAt = Math.floor(Date.now() / 1000) - 1;
		mockFetch.mockResolvedValueOnce(Response.json({ site_name: 'Afterglow' }));
		const { fetchWithAuth } = await import('../client');
		const response = await fetchWithAuth('/api/v1/site-config');
		expect(await response.json()).toEqual({ site_name: 'Afterglow' });
		expect(mockFetch).toHaveBeenCalledOnce();
		expect(new Headers(mockFetch.mock.calls[0][1].headers).has('Authorization')).toBe(false);
	});

	it('keeps a transient preflight failure distinct from terminal authentication failure', async () => {
		session.value.accessExpiresAt = Math.floor(Date.now() / 1000) + 60;
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'temporarily unavailable' }, { status: 503 }));
		const { fetchWithAuth } = await import('../client');
		await expect(fetchWithAuth('/api/v1/dashboard/summary', {}, 'expired-token')).rejects.toMatchObject({ status: 503 });
		expect(mockFetch).toHaveBeenCalledOnce();
		expect(session.value.token).toBe('expired-token');
		expect(clearAuth).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
	});

	it('stops after a refreshed token is also rejected', async () => {
		mockFetch
			.mockResolvedValueOnce(Response.json({ detail: 'expired' }, { status: 401 }))
			.mockResolvedValueOnce(Response.json({ token: 'fresh-token', refresh_token: 'fresh-refresh' }))
			.mockResolvedValueOnce(Response.json({ detail: 'revoked' }, { status: 401 }));
		const { fetchWithAuth } = await import('../client');
		const response = await fetchWithAuth('/api/v1/protected', {}, 'expired-token');
		expect(response.status).toBe(401);
		await vi.waitFor(() => expect(clearAuth).toHaveBeenCalledOnce());
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	it('does not revive a session cleared while preflight refresh is in flight', async () => {
		session.value.accessExpiresAt = Math.floor(Date.now() / 1000) - 1;
		const refreshResponse = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(refreshResponse.promise);
		const { fetchWithAuth } = await import('../client');
		const request = fetchWithAuth('/api/v1/protected', {}, 'expired-token');
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		session.value = { token: '', refreshToken: null, accessExpiresAt: null };
		refreshResponse.resolve(Response.json({ token: 'late-token', refresh_token: 'late-refresh' }));
		await expect(request).rejects.toMatchObject({ status: 401 });
		expect(mockFetch).toHaveBeenCalledOnce();
		expect(setAuth).not.toHaveBeenCalled();
	});
	it('coalesces concurrent explicit refreshes through the public helper', async () => {
		mockFetch.mockResolvedValueOnce({
			ok: true,
			json: async () => ({
				token: 'rotated-token',
				refresh_token: 'rotated-refresh-token',
				expires_at: '2026-07-11T00:00:00Z',
			}),
		});
		const { refreshSession } = await import('../client');

		const [first, second] = await Promise.all([refreshSession(), refreshSession()]);

		expect(mockFetch).toHaveBeenCalledOnce();
		expect(mockFetch).toHaveBeenCalledWith(
			'http://localhost:8000/api/v1/auth/refresh',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ refresh_token: 'refresh-token' }),
			}),
		);
		expect(first).toBe('rotated-token');
		expect(second).toBe('rotated-token');
		expect(setAuth).toHaveBeenCalledWith(expect.objectContaining({
			token: 'rotated-token',
			refreshToken: 'rotated-refresh-token',
		}));
	});

	it('fences new refreshes while preserving a captured response for logout revocation', async () => {
		let resolveRefresh!: (response: {
			ok: boolean;
			json: () => Promise<{ token: string; refresh_token: string; expires_at: string }>;
		}) => void;
		mockFetch.mockImplementationOnce(() => new Promise((resolve) => {
			resolveRefresh = resolve;
		}));
		const { refreshSession, beginSessionRevocation, endSessionRevocation } = await import('../client');

		const pendingRefresh = refreshSession();
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const pendingRevocation = beginSessionRevocation();
		try {
			await expect(refreshSession()).resolves.toBeNull();
			resolveRefresh({
				ok: true,
				json: async () => ({
					token: 'rotated-token',
					refresh_token: 'rotated-refresh-token',
					expires_at: '2026-07-11T00:00:00Z',
				}),
			});

			await expect(pendingRefresh).resolves.toBe('rotated-token');
			await expect(pendingRevocation).resolves.toBe('rotated-token');
			expect(setAuth).toHaveBeenCalledWith(expect.objectContaining({
				token: 'rotated-token',
				refreshToken: 'rotated-refresh-token',
			}));
		} finally {
			endSessionRevocation();
		}
	});

	it('leaves logout-owned cleanup alone when an unrelated request receives 401', async () => {
		const { api, ApiError, beginSessionRevocation, endSessionRevocation } = await import('../client');
		logoutState.value = true;
		beginSessionRevocation();
		try {
			await expect(api.get('/api/v1/protected', 'expired-token', 'project')).rejects.toBeInstanceOf(ApiError);
			expect(clearAuth).not.toHaveBeenCalled();
			expect(goto).not.toHaveBeenCalled();
		} finally {
			endSessionRevocation();
		}
	});

	it('refreshes an expired token only to complete a fenced logout request', async () => {
		mockFetch
			.mockResolvedValueOnce({
				ok: false,
				status: 401,
				statusText: 'Unauthorized',
				json: async () => ({ detail: 'expired' }),
			})
			.mockResolvedValueOnce({
				ok: true,
				json: async () => ({
					token: 'logout-refresh-token',
					refresh_token: 'logout-refresh-refresh-token',
					expires_at: '2026-07-11T00:00:00Z',
				}),
			})
			.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: async () => ({ message: '로그아웃 완료' }),
			});
		const { api, beginSessionRevocation, endSessionRevocation } = await import('../client');
		logoutState.value = true;
		beginSessionRevocation();
		try {
			await expect(api.post('/api/v1/auth/logout', {}, 'expired-token', 'project')).resolves.toEqual({
				message: '로그아웃 완료',
			});

			expect(mockFetch).toHaveBeenCalledTimes(3);
			expect(mockFetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/auth/refresh');
			expect(mockFetch.mock.calls[2][0]).toBe('http://localhost:8000/api/v1/auth/logout');
			expect(mockFetch.mock.calls[2][1].headers.Authorization).toBe('Bearer logout-refresh-token');
		} finally {
			endSessionRevocation();
		}
	});

	it('adopts a cross-tab refresh winner before revoking the session', async () => {
		let resolveRefresh!: (response: {
			ok: boolean;
			json: () => Promise<{ token: string; refresh_token: string; expires_at: string }>;
		}) => void;
		mockFetch.mockImplementationOnce(() => new Promise((resolve) => {
			resolveRefresh = resolve;
		}));
		const { refreshSession, beginSessionRevocation, endSessionRevocation } = await import('../client');

		const pendingRefresh = refreshSession();
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const pendingRevocation = beginSessionRevocation();
		localStorage.setItem('afterglow_auth', JSON.stringify({
			token: 'winner-token',
			refreshToken: 'winner-refresh-token',
			accessExpiresAt: 1_783_920_000,
		}));
		try {
			resolveRefresh({
				ok: false,
				json: async () => ({
					token: '',
					refresh_token: '',
					expires_at: '',
				}),
			});

			await expect(pendingRefresh).resolves.toBe('winner-token');
			await expect(pendingRevocation).resolves.toBe('winner-token');
			expect(setAuth).toHaveBeenCalledWith({
				token: 'winner-token',
				refreshToken: 'winner-refresh-token',
				accessExpiresAt: 1_783_920_000,
			});
		} finally {
			endSessionRevocation();
			localStorage.clear();
		}
	});
	it('adopts a cross-tab winner token when current token changes while refresh 200 response is in flight', async () => {
		let resolveRefresh!: (response: {
			ok: boolean;
			json: () => Promise<{ token: string; refresh_token: string; expires_at: string }>;
		}) => void;
		mockFetch.mockImplementationOnce(() => new Promise((resolve) => {
			resolveRefresh = resolve;
		}));
		const { refreshSession } = await import('../client');

		const pendingRefresh = refreshSession();
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());

		session.value = {
			token: 'cross-tab-winner-token',
			refreshToken: 'winner-refresh-token',
			accessExpiresAt: null,
		};

		resolveRefresh({
			ok: true,
			json: async () => ({
				token: 'stale-token',
				refresh_token: 'stale-refresh-token',
				expires_at: '2026-07-11T00:00:00Z',
			}),
		});

		const result = await pendingRefresh;
		expect(result).toBe('cross-tab-winner-token');
		expect(setAuth).not.toHaveBeenCalled();
	});
	it('preserves browser auth and suppresses redirect when refresh endpoint returns 503', async () => {
		// Protected endpoint returns 401
		mockFetch.mockResolvedValueOnce({
			ok: false,
			status: 401,
			statusText: 'Unauthorized',
			json: async () => ({ detail: 'Access token expired' }),
			text: async () => 'Access token expired',
		});
		// Refresh endpoint returns 503 (transient error)
		mockFetch.mockResolvedValueOnce({
			ok: false,
			status: 503,
			statusText: 'Service Unavailable',
			json: async () => ({ detail: 'Keystone temporarily unavailable' }),
			text: async () => 'Keystone temporarily unavailable',
		});

		const { api, ApiError } = await import('../client');

		// Refresh 503 failure must propagate as ApiError with status 503 (current buggy code throws ApiError 401)
		const err = await api.get('/api/v1/protected-503', 'expired-token', 'project').catch((e: unknown) => e);
		expect(err).toBeInstanceOf(ApiError);
		expect((err as InstanceType<typeof ApiError>).status).toBe(503);

		// Flush microtasks to ensure any scheduled handleUnauthorized would have run
		await new Promise((r) => setTimeout(r, 0));

		// Browser auth must NOT be cleared and redirect must NOT be triggered
		expect(clearAuth).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
		expect(replace).not.toHaveBeenCalled();
		expect(session.value.token).toBe('expired-token');
	});

	it('preserves browser auth and suppresses redirect when refresh endpoint encounters a transport/network error', async () => {
		// Protected endpoint returns 401
		mockFetch.mockResolvedValueOnce({
			ok: false,
			status: 401,
			statusText: 'Unauthorized',
			json: async () => ({ detail: 'Access token expired' }),
			text: async () => 'Access token expired',
		});
		// Refresh fetch rejects with network error
		const networkError = new TypeError('Failed to fetch');
		mockFetch.mockRejectedValueOnce(networkError);

		const { api } = await import('../client');

		// Transport failure must propagate the original TypeError (current buggy code throws ApiError 401)
		const err = await api.get('/api/v1/protected-net-err', 'expired-token', 'project').catch((e: unknown) => e);
		expect(err).toBe(networkError);

		// Flush microtasks to ensure any scheduled handleUnauthorized would have run
		await new Promise((r) => setTimeout(r, 0));

		// Browser auth must NOT be cleared and redirect must NOT be triggered
		expect(clearAuth).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
		expect(replace).not.toHaveBeenCalled();
		expect(session.value.token).toBe('expired-token');
	});
	it('retries a late 401 using the rotated live token without initiating a second refresh', async () => {
		session.value = { token: 'expired-token', refreshToken: 'refresh-token', accessExpiresAt: null };

		let resolveReq1!: (response: any) => void;
		let resolveReq2!: (response: any) => void;
		let resolveRefresh!: (response: any) => void;

		const fetchCalls: Array<{ url: string; headers: Record<string, string> }> = [];

		mockFetch.mockImplementation((url: string, init?: RequestInit) => {
			const reqUrl = url.toString();
			const headers = (init?.headers ?? {}) as Record<string, string>;
			const authHeader = headers['Authorization'] || headers['authorization'];
			fetchCalls.push({ url: reqUrl, headers });

			if (reqUrl.includes('/api/v1/resource-1') && authHeader === 'Bearer expired-token') {
				return new Promise((resolve) => {
					resolveReq1 = resolve;
				});
			}
			if (reqUrl.includes('/api/v1/resource-2') && authHeader === 'Bearer expired-token') {
				return new Promise((resolve) => {
					resolveReq2 = resolve;
				});
			}
			if (reqUrl.includes('/api/v1/auth/refresh')) {
				return new Promise((resolve) => {
					resolveRefresh = resolve;
				});
			}
			if (reqUrl.includes('/api/v1/resource-1') && authHeader === 'Bearer rotated-token') {
				return Promise.resolve({
					ok: true,
					status: 200,
					statusText: 'OK',
					json: async () => ({ id: 'res-1', status: 'active' }),
				});
			}
			if (reqUrl.includes('/api/v1/resource-2') && authHeader === 'Bearer rotated-token') {
				return Promise.resolve({
					ok: true,
					status: 200,
					statusText: 'OK',
					json: async () => ({ id: 'res-2', status: 'active' }),
				});
			}

			return Promise.reject(new Error(`Unexpected fetch call: ${reqUrl}`));
		});

		const { api } = await import('../client');

		// Launch two api.get() calls using expired-token
		const req1Promise = api.get<{ id: string; status: string }>('/api/v1/resource-1', 'expired-token');
		const req2Promise = api.get<{ id: string; status: string }>('/api/v1/resource-2', 'expired-token');

		// Hold both original protected responses (verify both initial requests were issued)
		await vi.waitFor(() => expect(fetchCalls).toHaveLength(2));

		// Resolve the first original response to 401
		resolveReq1({
			ok: false,
			status: 401,
			statusText: 'Unauthorized',
			json: async () => ({ detail: 'Access token expired' }),
			text: async () => 'Access token expired',
		});

		// Wait for refresh endpoint call
		await vi.waitFor(() => expect(fetchCalls.some((c) => c.url.includes('/auth/refresh'))).toBe(true));

		// Resolve the single refresh response with rotated-token / rotated-refresh-token
		resolveRefresh({
			ok: true,
			status: 200,
			statusText: 'OK',
			json: async () => ({
				token: 'rotated-token',
				refresh_token: 'rotated-refresh-token',
				expires_at: '2026-08-26T12:00:00Z',
			}),
		});

		// Wait until setAuth publishes rotated-token
		await vi.waitFor(() =>
			expect(setAuth).toHaveBeenCalledWith(
				expect.objectContaining({ token: 'rotated-token' })
			)
		);

		// Only then resolve the second original response to 401
		resolveReq2({
			ok: false,
			status: 401,
			statusText: 'Unauthorized',
			json: async () => ({ detail: 'Access token expired' }),
			text: async () => 'Access token expired',
		});

		// Resolve both protected retries successfully
		const [res1Payload, res2Payload] = await Promise.all([req1Promise, req2Promise]);

		// Assert both payloads
		expect(res1Payload).toEqual({ id: 'res-1', status: 'active' });
		expect(res2Payload).toEqual({ id: 'res-2', status: 'active' });

		// Assert exactly one /api/v1/auth/refresh call
		const refreshCalls = fetchCalls.filter((c) => c.url.includes('/auth/refresh'));
		expect(refreshCalls).toHaveLength(1);

		// Assert both retries use Authorization: Bearer rotated-token
		const retry1Call = fetchCalls.find(
			(c) => c.url.includes('/api/v1/resource-1') && (c.headers['Authorization'] === 'Bearer rotated-token' || c.headers['authorization'] === 'Bearer rotated-token')
		);
		const retry2Call = fetchCalls.find(
			(c) => c.url.includes('/api/v1/resource-2') && (c.headers['Authorization'] === 'Bearer rotated-token' || c.headers['authorization'] === 'Bearer rotated-token')
		);
		expect(retry1Call).toBeDefined();
		expect(retry2Call).toBeDefined();

		// Assert clearAuth, goto, and location replacement are untouched
		expect(clearAuth).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
		expect(replace).not.toHaveBeenCalled();
	});
	it('coalesces failed refresh outcomes across staggered 401 requests within cooldown', async () => {
		session.value = { token: 'expired-token', refreshToken: 'refresh-token', accessExpiresAt: null };

		let baseTime = 1700000000000;
		const nowSpy = vi.spyOn(Date, 'now').mockImplementation(() => baseTime);

		try {
			let resolveReq1!: (response: any) => void;
			let resolveReq2!: (response: any) => void;
			let resolveReq3!: (response: any) => void;
			let resolveRefresh1!: (response: any) => void;
			let resolveRefresh2!: (response: any) => void;

			const fetchCalls: Array<{ url: string; headers: Record<string, string> }> = [];

			mockFetch.mockImplementation((url: string, init?: RequestInit) => {
				const reqUrl = url.toString();
				const headers = (init?.headers ?? {}) as Record<string, string>;
				const authHeader = headers['Authorization'] || headers['authorization'];
				fetchCalls.push({ url: reqUrl, headers });

				if (reqUrl.includes('/api/v1/resource-1') && authHeader === 'Bearer expired-token') {
					return new Promise((resolve) => {
						resolveReq1 = resolve;
					});
				}
				if (reqUrl.includes('/api/v1/resource-2') && authHeader === 'Bearer expired-token') {
					return new Promise((resolve) => {
						resolveReq2 = resolve;
					});
				}
				if (reqUrl.includes('/api/v1/resource-3') && authHeader === 'Bearer expired-token') {
					return new Promise((resolve) => {
						resolveReq3 = resolve;
					});
				}
				if (reqUrl.includes('/api/v1/auth/refresh')) {
					const refreshCallCount = fetchCalls.filter((c) => c.url.includes('/auth/refresh')).length;
					if (refreshCallCount === 1) {
						return new Promise((resolve) => {
							resolveRefresh1 = resolve;
						});
					} else {
						return new Promise((resolve) => {
							resolveRefresh2 = resolve;
						});
					}
				}

				return Promise.reject(new Error(`Unexpected fetch call: ${reqUrl}`));
			});

			const { api, ApiError } = await import('../client');

			const req1Promise = api.get<{ id: string }>('/api/v1/resource-1', 'expired-token');
			const req2Promise = api.get<{ id: string }>('/api/v1/resource-2', 'expired-token');
			const req3Promise = api.get<{ id: string }>('/api/v1/resource-3', 'expired-token');

			await vi.waitFor(() => expect(fetchCalls).toHaveLength(3));

			resolveReq1({
				ok: false,
				status: 401,
				statusText: 'Unauthorized',
				json: async () => ({ detail: 'Access token expired' }),
				text: async () => 'Access token expired',
			});

			await vi.waitFor(() => expect(fetchCalls.some((c) => c.url.includes('/auth/refresh'))).toBe(true));

			resolveRefresh1({
				ok: false,
				status: 429,
				statusText: 'Too Many Requests',
				headers: new Headers({ 'Retry-After': '10' }),
				json: async () => ({ detail: 'Rate limit exceeded' }),
				text: async () => 'Rate limit exceeded',
			});

			await expect(req1Promise).rejects.toSatisfy((err: any) => err instanceof ApiError && err.status === 429);

			resolveReq2({
				ok: false,
				status: 401,
				statusText: 'Unauthorized',
				json: async () => ({ detail: 'Access token expired' }),
				text: async () => 'Access token expired',
			});

			await expect(req2Promise).rejects.toSatisfy((err: any) => err instanceof ApiError && err.status === 429);

			let refreshCalls = fetchCalls.filter((c) => c.url.includes('/auth/refresh'));
			expect(refreshCalls).toHaveLength(1);

			expect(clearAuth).not.toHaveBeenCalled();
			expect(goto).not.toHaveBeenCalled();
			expect(replace).not.toHaveBeenCalled();
			expect(session.value.token).toBe('expired-token');

			baseTime += 10001;

			resolveReq3({
				ok: false,
				status: 401,
				statusText: 'Unauthorized',
				json: async () => ({ detail: 'Access token expired' }),
				text: async () => 'Access token expired',
			});

			await vi.waitFor(() => expect(fetchCalls.filter((c) => c.url.includes('/auth/refresh'))).toHaveLength(2));

			refreshCalls = fetchCalls.filter((c) => c.url.includes('/auth/refresh'));
			expect(refreshCalls).toHaveLength(2);

			resolveRefresh2({
				ok: false,
				status: 429,
				statusText: 'Too Many Requests',
				headers: new Headers({ 'Retry-After': '10' }),
				json: async () => ({ detail: 'Rate limit exceeded' }),
				text: async () => 'Rate limit exceeded',
			});

			await expect(req3Promise).rejects.toSatisfy((err: any) => err instanceof ApiError && err.status === 429);
		} finally {
			nowSpy.mockRestore();
		}
	});

});

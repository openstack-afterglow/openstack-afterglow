import { beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('$app/environment', () => ({ browser: true }));


const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(value: unknown): Response {
	return new Response(JSON.stringify(value), {
		status: 200,
		headers: { 'Content-Type': 'application/json' },
	});
}

describe('streamK3sProgress cache fencing', () => {
	beforeEach(() => {
		// Reload the client/cache/auth module boundary for each independent transport scenario.
		vi.resetModules();
		mockFetch.mockReset();
		localStorage.clear();
		sessionStorage.clear();
	});

	it('invalidates warm reads before opening and after closing the mutating stream', async () => {
		const emptyStream = new ReadableStream<Uint8Array>({
			start(controller) { controller.close(); },
		});
		mockFetch
			.mockResolvedValueOnce(jsonResponse({ source: 'warm' }))
			.mockResolvedValueOnce(new Response(emptyStream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }))
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));
		const { api } = await import('$lib/api/client');
		const { streamK3sProgress } = await import('../k3sSseStream');
		await api.prefetch('/api/v1/items', 'token', 'project');

		for await (const _message of streamK3sProgress('/api/v1/k3s/clusters/async', { method: 'POST', body: {}, token: 'token', projectId: 'project' })) {
			throw new Error('empty stream must not emit');
		}

		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	it.each([409, 503])('preserves the explicit native pre-admission refusal marker on HTTP %s', async status => {
		mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'drover_pre_admission_refused', message: 'Native quota unavailable before dispatch' } }), { status }));
		const { streamK3sProgress } = await import('../k3sSseStream');
		const consume = async () => { for await (const _ of streamK3sProgress('/api/v1/k3s/clusters/async', { method: 'POST', token: 'token', projectId: 'project' })) { /* refused before SSE */ } };
		await expect(consume()).rejects.toMatchObject({ status, code: 'drover_pre_admission_refused', message: 'Native quota unavailable before dispatch' });
	});

	it.each([409, 500, 502, 503, 504])('does not manufacture admission evidence from an untyped HTTP %s', async status => {
		mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Provider unavailable; outcome not specified' }), { status }));
		const { streamK3sProgress } = await import('../k3sSseStream');
		const consume = async () => { for await (const _ of streamK3sProgress('/api/v1/k3s/clusters/async', { method: 'POST', token: 'token', projectId: 'project' })) { /* no valid frame */ } };
		await expect(consume()).rejects.toMatchObject({ status, code: undefined });
	});

	it('retains only actual complete quota counts from the native structured refusal', async () => {
		const quota = { project_id: 'project', resource: 'security_group_rule', required: 7, available: 2, limit: 10, used: 8, reserved: 0 };
		mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'drover_pre_admission_refused', reason: 'security_group_quota_exceeded', message: 'Rule budget exhausted', quota } }), { status: 409 }));
		const { streamK3sProgress } = await import('../k3sSseStream');
		const consume = async () => { for await (const _ of streamK3sProgress('/api/v1/k3s/clusters/async', { method: 'POST', token: 'token', projectId: 'project' })) { /* refused */ } };
		await expect(consume()).rejects.toMatchObject({ reason: 'security_group_quota_exceeded', quota });
	});

	it('keeps a keyed/concurrent quota-shaped refusal without the definitive marker ambiguous', async () => {
		mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: {
			reason: 'security_group_quota_exceeded', message: 'Another same-key request may already be admitted',
			quota: { project_id: 'project', resource: 'security_group', required: 1, available: 0, limit: 1, used: 1, reserved: 0 },
		} }), { status: 409 }));
		const { streamK3sProgress } = await import('../k3sSseStream');
		const consume = async () => { for await (const _ of streamK3sProgress('/api/v1/k3s/clusters/async', { method: 'POST', token: 'token', projectId: 'project' })) { /* no valid frame */ } };
		await expect(consume()).rejects.toMatchObject({ status: 409, code: undefined });
	});

	it.each([
		{ project_id: 'project', resource: 'security_group_rule', required: 7, limit: 10, used: 8, reserved: 0 },
		{ project_id: 'project', resource: 'security_group_rule', required: 7.5, available: 2, limit: 10, used: 8, reserved: 0 },
	])('does not publish incomplete or non-integer native quota counts', async quota => {
		mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'drover_pre_admission_refused', reason: 'security_group_quota_exceeded', message: 'Native quota refusal', quota } }), { status: 409 }));
		const { streamK3sProgress } = await import('../k3sSseStream');
		const consume = async () => { for await (const _ of streamK3sProgress('/api/v1/k3s/clusters/async', { method: 'POST', token: 'token', projectId: 'project' })) { /* refused */ } };
		await expect(consume()).rejects.toMatchObject({ code: 'drover_pre_admission_refused', reason: 'security_group_quota_exceeded', quota: undefined });
	});
});

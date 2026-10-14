import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getInfrastructureTopology, submitInfrastructureTrace } from '../infrastructureTopology';
import { ApiError } from '../errors';
import { makeSnapshot, makeTrace } from '$lib/components/admin/infrastructure-topology/__tests__/fixtures';

const { fetchAuth } = vi.hoisted(() => ({ fetchAuth: vi.fn() }));
vi.mock('$lib/api/client', () => ({ fetchWithAuth: fetchAuth }));
const authority = { token: 'exact-token', userId: 'actor', projectId: 'exact-project', admin: true, ready: true };
beforeEach(() => fetchAuth.mockReset());

describe('infrastructure topology API boundary', () => {
	it('bypasses caching and uses the captured token/project authority', async () => {
		const snapshot = makeSnapshot(); fetchAuth.mockResolvedValue(new Response(JSON.stringify(snapshot), { status: 200 }));
		const abort = new AbortController(); expect(await getInfrastructureTopology(authority, abort.signal)).toEqual(snapshot);
		expect(fetchAuth).toHaveBeenCalledWith('/api/v1/admin/infrastructure-topology', expect.objectContaining({ method: 'GET', cache: 'no-store', credentials: 'include', signal: expect.any(AbortSignal) }), 'exact-token', 'exact-project');
	});
	it('encodes the host path and submits only the target, never command arguments', async () => {
		const job = makeTrace('queued'); fetchAuth.mockResolvedValue(new Response(JSON.stringify(job), { status: 200 }));
		await submitInfrastructureTrace('compute:host/a', '203.0.113.9', authority, new AbortController().signal);
		const [path, options] = fetchAuth.mock.calls[0]; expect(path).toBe('/api/v1/admin/infrastructure-topology/hosts/compute%3Ahost%2Fa/traces');
		expect(options.method).toBe('POST'); expect(JSON.parse(options.body)).toEqual({ target: '203.0.113.9' }); expect(options.cache).toBe('no-store');
	});
	it('forwards caller cancellation into the actual request signal', async () => {
		fetchAuth.mockResolvedValue(new Response(JSON.stringify(makeSnapshot()), { status: 200 }));
		const abort = new AbortController(); await getInfrastructureTopology(authority, abort.signal); abort.abort();
		expect(fetchAuth.mock.calls[0][1].signal.aborted).toBe(true);
	});
	it.each([401, 403, 409, 503])('preserves HTTP %s without displaying arbitrary upstream payloads', async status => {
		fetchAuth.mockResolvedValue(new Response(JSON.stringify({ detail: 'sensitive-upstream-value' }), { status }));
		await expect(getInfrastructureTopology(authority, new AbortController().signal)).rejects.toMatchObject({ status, message: 'topology_request_failed' });
		await expect(getInfrastructureTopology(authority, new AbortController().signal)).rejects.toBeInstanceOf(ApiError);
	});
	it.each([
		[422, 'trace_target_not_allowed'], [429, 'trace_rate_limited'], [404, 'observer_not_configured'], [409, 'trace_already_active'],
	] as const)('retains the safe backend detail code for trace HTTP %s', async (status, code) => {
		fetchAuth.mockResolvedValue(new Response(JSON.stringify({ detail: code }), { status }));
		await expect(submitInfrastructureTrace('compute:node-a', '203.0.113.9', authority, new AbortController().signal)).rejects.toMatchObject({ status, code, message: code });
	});
});

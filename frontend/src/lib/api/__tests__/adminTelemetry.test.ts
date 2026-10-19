import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('$lib/api/client', () => ({ getBaseUrl: () => 'https://console.invalid' }));
import { adminTelemetryRequest, TelemetryError } from '$lib/api/adminTelemetry';

const authority = { token: 'test-access', projectId: 'test-project' };
const fetchMock = vi.fn();
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); });
afterEach(() => vi.unstubAllGlobals());

describe('native telemetry transport', () => {
	it('reads directly without cache and keeps explicit bearer and project ownership', async () => {
		fetchMock.mockResolvedValue(new Response(JSON.stringify({ status: 'not_configured' })));
		expect(await adminTelemetryRequest('/aodh', authority)).toEqual({ status: 'not_configured' });
		expect(fetchMock).toHaveBeenCalledExactlyOnceWith('https://console.invalid/api/v1/admin/telemetry/aodh', expect.objectContaining({
			cache: 'no-store', credentials: 'include', redirect: 'error', method: 'GET',
			headers: expect.objectContaining({ Authorization: 'Bearer test-access', 'X-Project-Id': 'test-project' }),
		}));
	});
	it.each([401, 403, 503])('never retries native mutations after HTTP %s', async status => {
		fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'telemetry_forbidden' } }), { status }));
		await expect(adminTelemetryRequest('/aodh/alarms', authority, { method: 'POST', body: { name: 'alarm' } }))
			.rejects.toMatchObject({ status, uncertain: status >= 500 });
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
	it('reports response loss as uncertain rather than resending a write', async () => {
		fetchMock.mockRejectedValue(new TypeError('network body might contain a private URL'));
		await expect(adminTelemetryRequest('/aodh/alarms/id', authority, { method: 'PUT', body: {} }))
			.rejects.toEqual(new TelemetryError(503, 'telemetry_unavailable', true));
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
	it('never publishes arbitrary native error details', async () => {
		fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'https://secret.invalid/token' }), { status: 502 }));
		await expect(adminTelemetryRequest('/gnocchi', authority)).rejects.toMatchObject({ code: 'telemetry_unavailable', message: 'telemetry_unavailable', uncertain: false });
	});
	it('handles native delete 204 without attempting a JSON reread or replay', async () => {
		fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
		expect(await adminTelemetryRequest('/aodh/alarms/id', authority, { method: 'DELETE' })).toBeUndefined();
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
	it('treats a malformed successful write response as ambiguous', async () => {
		fetchMock.mockResolvedValue(new Response('not-json', { status: 200 }));
		await expect(adminTelemetryRequest('/aodh/alarms', authority, { method: 'POST', body: {} })).rejects.toMatchObject({ uncertain: true });
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
});

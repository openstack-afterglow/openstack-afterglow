import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adminVolumeTransfers, VolumeTransferError } from '../adminVolumeTransfers';
vi.mock('$lib/api/client', () => ({ getBaseUrl: () => 'http://127.0.0.1:8099', clearPrefetchCache: vi.fn() }));
const fetchMock = vi.fn();
const actor = { token: 'original-human-jwt', projectId: 'original-home' };
const transferId = '11111111-1111-4111-8111-111111111111';
beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); });
afterEach(() => vi.unstubAllGlobals());

describe('administrator volume transfer no-replay transport', () => {
	it('sends selected domain/project as data, retaining the actual caller header and no-store', async () => {
		fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: transferId, volume_id: 'volume' }), { status: 200 }));
		await adminVolumeTransfers.accept(actor, transferId, 'supplied-secret', 'foreign-domain', 'foreign-project');
		expect(fetchMock).toHaveBeenCalledTimes(1);
		const [url, options] = fetchMock.mock.calls[0];
		expect(url).toBe(`http://127.0.0.1:8099/api/v1/admin/volumes/transfer/${transferId}/accept`);
		expect(url).not.toContain('supplied-secret');
		expect(options).toMatchObject({ method: 'POST', cache: 'no-store', credentials: 'include', redirect: 'error', headers: { Authorization: 'Bearer original-human-jwt', 'X-Project-Id': 'original-home' } });
		expect(JSON.parse(options.body)).toEqual({ auth_key: 'supplied-secret', target_domain_id: 'foreign-domain', target_project_id: 'foreign-project' });
	});
	it.each([401, 403, 413, 500, 502])('does not refresh or replay native/auth failure %s', async (status) => {
		fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'denied' }), { status }));
		await expect(adminVolumeTransfers.accept(actor, transferId, 'secret', 'domain', 'target')).rejects.toMatchObject({ status, uncertain: status >= 500 });
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
	it('keeps ambiguous committed writes uncertain without automatic cleanup', async () => {
		fetchMock.mockRejectedValue(new TypeError('network lost secret'));
		try { await adminVolumeTransfers.create(actor, 'source-volume'); throw new Error('expected denial'); }
		catch (cause) { expect(cause).toBeInstanceOf(VolumeTransferError); expect(cause).toMatchObject({ uncertain: true }); expect(String(cause)).not.toContain('secret'); }
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
	it('uses exact volume recovery and explicit native cancellation with no cache', async () => {
		fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([{ id: transferId, volume_id: 'volume' }]), { status: 200 })).mockResolvedValueOnce(new Response(null, { status: 204 }));
		expect(await adminVolumeTransfers.pending(actor, 'volume')).toHaveLength(1);
		await adminVolumeTransfers.cancel(actor, transferId);
		expect(fetchMock.mock.calls.map(call => call[1].method)).toEqual(['GET', 'DELETE']);
		for (const [, options] of fetchMock.mock.calls) expect(options.cache).toBe('no-store');
	});
});

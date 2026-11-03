// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../client', () => ({ api: { get: mocks.get } }));
import { getChatSourceAsset, getChatSourceDownloadLink, getRegisteredChatSource } from '../chatSources';

const scope = { token: 'owner-token', projectId: 'project-1' };
const assetId = 'e83a2892-41f0-4ca2-a453-4e23118f32ba';
beforeEach(() => vi.clearAllMocks());
describe('authenticated stable source reads', () => {
	it('uses the existing chat BFF and no-store for registered sources', async () => {
		const source = { type: 'citation', citation_id: 'c1', source_kind: 'tool_result', source_id: 's1', title: 'Read result', snippet: 'Evidence' };
		mocks.get.mockResolvedValue(source);
		expect(await getRegisteredChatSource('run-1', 'c1', scope)).toEqual(source);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/runs/run-1/sources/c1', scope.token, scope.projectId, expect.objectContaining({ cache: 'no-store' }));
	});
	it('does not disclose mismatched registered evidence or interpolate path traversal', async () => {
		mocks.get.mockResolvedValue({ type: 'citation', citation_id: 'foreign', source_kind: 'web', url: 'https://example.org' });
		await expect(getRegisteredChatSource('run-1', 'c1', scope)).rejects.toThrow('Mismatched');
		mocks.get.mockClear();
		await expect(getRegisteredChatSource('../foreign', 'c1', scope)).rejects.toThrow('identifier');
		expect(mocks.get).not.toHaveBeenCalled();
	});
	it('reads exact metadata and issues a fresh signed download URL for each explicit request', async () => {
		mocks.get.mockResolvedValueOnce({ id: assetId, name: 'file.pdf', mime_type: 'application/pdf', size_bytes: 42 });
		expect(await getChatSourceAsset(assetId, scope)).toMatchObject({ id: assetId });
		mocks.get.mockResolvedValueOnce({ url: 'https://objects.example/file?signature=one', expires_in: 60 });
		expect(await getChatSourceDownloadLink(assetId, scope)).toContain('signature=one');
		mocks.get.mockResolvedValueOnce({ url: 'https://objects.example/file?signature=two', expires_in: 60 });
		expect(await getChatSourceDownloadLink(assetId, scope)).toContain('signature=two');
		expect(mocks.get).toHaveBeenLastCalledWith(`/api/v1/chat/assets/${assetId}/download-link`, scope.token, scope.projectId, expect.objectContaining({ cache: 'no-store' }));
	});
	it.each(['javascript:alert(1)', 'data:text/html,secret', 'https://user:secret@objects.example/file'])('rejects unsafe signed destinations %s', async (url) => {
		mocks.get.mockResolvedValue({ url, expires_in: 60 });
		await expect(getChatSourceDownloadLink(assetId, scope)).rejects.toThrow('Invalid');
	});
});

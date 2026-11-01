import { beforeEach, describe, expect, it, vi } from 'vitest';
const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
vi.mock('../client', () => ({ api }));
import { computePools, parseComputeLimits, type ComputeAuthority } from '../computePools';
const authority = (overrides: Partial<ComputeAuthority> = {}): ComputeAuthority => ({ token: () => 'token', projectId: () => undefined, isCurrent: () => true, canSubmit: () => true, ...overrides });
beforeEach(() => vi.resetAllMocks());

describe('shared compute policy API boundaries', () => {
	it('blocks stale reads and writes synchronously and blocks writes during authority revalidation', async () => {
		const stale = computePools('domain', true, authority({ isCurrent: () => false }));
		await expect(stale.load()).rejects.toMatchObject({ name: 'AbortError' });
		await expect(stale.save(0, true, {})).rejects.toMatchObject({ name: 'AbortError' });
		const readOnly = computePools('domain', false, authority({ canSubmit: () => false }));
		await readOnly.load();
		await expect(readOnly.saveProject('project', 0, {})).rejects.toMatchObject({ name: 'AbortError' });
		expect(api.put).not.toHaveBeenCalled();
	});
	it('discards late private snapshots after authority replacement', async () => {
		let current = true; const pending = Promise.withResolvers<unknown>(); api.get.mockReturnValue(pending.promise);
		const reading = computePools('domain', true, authority({ isCurrent: () => current })).load();
		current = false; pending.resolve({ domain_id: 'domain', revision: 8 });
		await expect(reading).rejects.toMatchObject({ name: 'AbortError' });
	});
});

describe('compute ceiling drafts', () => {
	it('preserves measured zero, unlimited and explicitly omitted optional ceilings', () => {
		expect(parseComputeLimits({ CPU: '0', MEMORY_MB: '-1', CUSTOM_PCI_10DE_2236: '' })).toEqual({ CPU: 0, MEMORY_MB: -1 });
		expect(parseComputeLimits({ CPU: '16', MEMORY_MB: '' }, { CPU: 16, MEMORY_MB: 8192 })).toEqual({ CPU: 16 });
	});
	it('keeps native CPU/RAM quotas independent when only GPUs are allocated', () => {
		const pool = { CUSTOM_PCI_10DE_2504: 2 };
		expect(parseComputeLimits({ CPU: '128', MEMORY_MB: '-1', CUSTOM_PCI_10DE_2504: '2' }, pool)).toEqual({ CPU: 128, MEMORY_MB: -1, CUSTOM_PCI_10DE_2504: 2 });
		expect(parseComputeLimits({ CPU: '1' }, { ...pool, CPU: 0 })).toBeNull();
		expect(parseComputeLimits({ CUSTOM_PCI_10DE_2684: '1' }, pool)).toBeNull();
	});
	it.each(['1.5', '-2', 'Infinity', '1e3', '9007199254740992'])('rejects invalid limit %s', input => expect(parseComputeLimits({ CPU: input })).toBeNull());
	it('does not allocate capacity by summing optional project ceilings', () => {
		expect(parseComputeLimits({ CPU: '16' }, { CPU: 16 })).toEqual({ CPU: 16 });
		expect(parseComputeLimits({ CPU: '17' }, { CPU: 16 })).toBeNull();
		expect(parseComputeLimits({ CPU: '-1' }, { CPU: 16 })).toBeNull();
		expect(parseComputeLimits({ CPU: '-1' }, { CPU: -1 })).toEqual({ CPU: -1 });
		expect(parseComputeLimits({ CUSTOM_PCI_10DE_2236: '1' }, { CPU: -1 })).toBeNull();
	});
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/instance';

const mocks = vi.hoisted(() => ({ get: vi.fn(), confirm: vi.fn(), error: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get }, ApiError: class extends Error { status = 503; } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: mocks.error } }));

import { confirmInstanceDeletion } from './instanceDeleteConfirmation';

beforeEach(() => {
	vi.clearAllMocks();
	mocks.get.mockResolvedValue([]);
	mocks.confirm.mockResolvedValue(true);
});

describe('fresh instance deletion confirmation', () => {
	it.each([false, true])('reads every target with exact transport scope and requires typing if any volume is auto-deleted, adminMode=%s', async adminMode => {
		mocks.get.mockResolvedValueOnce([{ volume_id: 'retained', name: 'data', delete_on_termination: false }]);
		mocks.get.mockResolvedValueOnce([{ volume_id: 'root', name: 'system', delete_on_termination: true }]);
		const result = await confirmInstanceDeletion('Delete selected instances?', {
			targets: [{ id: 'vm-a', name: 'first' }, { id: 'vm-b', name: 'second' }],
			adminMode, token: 'actor-token', projectId: 'actor-project', isCurrent: () => true,
		});
		expect(result).toBe(true);
		for (const id of ['vm-a', 'vm-b']) {
			expect(mocks.get).toHaveBeenCalledWith(`/api/v1/${adminMode ? 'admin/' : ''}instances/${id}/volumes`, 'actor-token', 'actor-project', { refresh: true, cache: 'no-store' });
		}
		const requiredText = t('controller.delete.requiredText');
		expect(mocks.confirm).toHaveBeenCalledExactlyOnceWith(`Delete selected instances?\nsecond: ${t('controller.delete.autoDeleteVolumes', { volumes: 'system' })}`, {
			requiredText, requiredTextLabel: t('controller.delete.requiredTextLabel', { text: requiredText }),
		});
	});

	it.each([{ volumes: [] }, { volumes: [{ volume_id: 'data', delete_on_termination: false }] }])('keeps the one-argument dialog when no volumes auto-delete: %j', async ({ volumes }) => {
		mocks.get.mockResolvedValue(volumes);
		await confirmInstanceDeletion('Delete?', { targets: [{ id: 'vm' }], adminMode: false, token: 'token', projectId: 'project', isCurrent: () => true });
		expect(mocks.confirm).toHaveBeenCalledExactlyOnceWith('Delete?');
	});

	it.each([undefined, null, 'true', 'false', 0, 1])('fails closed for non-boolean delete_on_termination=%s', async flag => {
		mocks.get.mockResolvedValue([{ volume_id: 'unknown', delete_on_termination: flag }]);
		const result = await confirmInstanceDeletion('Delete?', { targets: [{ id: 'vm' }], adminMode: false, token: 'token', projectId: 'project', isCurrent: () => true });
		expect(result).toBe(false);
		expect(mocks.confirm).not.toHaveBeenCalled();
		expect(mocks.error).toHaveBeenCalledOnce();
	});

	it('fails closed if any target attachment read fails', async () => {
		mocks.get.mockResolvedValueOnce([]).mockRejectedValueOnce(new Error('unavailable'));
		const result = await confirmInstanceDeletion('Delete?', { targets: [{ id: 'vm-a' }, { id: 'vm-b' }], adminMode: true, token: 'token', projectId: 'project', isCurrent: () => true });
		expect(result).toBe(false);
		expect(mocks.confirm).not.toHaveBeenCalled();
		expect(mocks.error).toHaveBeenCalledOnce();
	});

	it('discards a stale attachment response without opening a dialog or showing an error', async () => {
		let current = true;
		const pending = Promise.withResolvers<unknown[]>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const result = confirmInstanceDeletion('Delete?', { targets: [{ id: 'vm' }], adminMode: false, token: 'token', projectId: 'project', isCurrent: () => current });
		current = false;
		pending.resolve([{ volume_id: 'root', delete_on_termination: true }]);
		expect(await result).toBe(false);
		expect(mocks.confirm).not.toHaveBeenCalled();
		expect(mocks.error).not.toHaveBeenCalled();
	});
});

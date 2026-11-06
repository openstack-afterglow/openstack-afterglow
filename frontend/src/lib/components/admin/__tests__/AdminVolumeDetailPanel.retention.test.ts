import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { t as commonT } from '$lib/i18n/ns/common';
import { t as storageT } from '$lib/i18n/ns/admin-storage';
import type { AdminVolumeDetail } from '$lib/types/volume';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, withExperience() { return this; } }, ApiError: class extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'auth-token', sessionId: 'session', userId: 'admin', projectId: 'home', isSystemAdmin: true }), projectSwitching: writable(false) }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: writable(new Map<string, string>()) }));
import Panel from '../../AdminVolumeDetailPanel.svelte';

const volume: AdminVolumeDetail = {
	id: 'volume', name: 'Volume', status: 'in-use', size: 20, volume_type: 'fast', project_id: 'tenant',
	created_at: null, description: '', bootable: false, encrypted: false, multiattach: false,
	attachments: [{ id: 'a', server_id: 'vm-keep', device: '/dev/vda' }, { id: 'b', server_id: 'vm-drop', device: '/dev/vdb' }],
	metadata: { keep: 'Keep', drop: 'Drop' },
};
beforeEach(() => { mocks.get.mockReset().mockResolvedValue(volume); });
afterEach(cleanup);

it('retains nested regex, facets and sort through same-owner empty/error reloads but resets them for a different project', async () => {
	const view = render(Panel, { volumeId: 'volume', token: 'token-1', projectId: 'tenant' });
	await screen.findByText('Keep');
	const metadataInput = () => document.querySelector<HTMLInputElement>('#admin-volume-metadata-search')!;
	const attachmentInput = () => document.querySelector<HTMLInputElement>('#admin-volume-attachments-search')!;
	await fireEvent.input(metadataInput(), { target: { value: '^(keep|drop)$' } });
	await fireEvent.input(attachmentInput(), { target: { value: '^vm-keep$' } });
	const key = commonT('table.key');
	const sortButton = (direction: 'none' | 'ascending' | 'descending') => screen.getByRole('button', { name: commonT('table.sortColumn', { column: key, direction: commonT(`table.${direction}`) }) });
	await fireEvent.click(sortButton('none'));
	await fireEvent.click(sortButton('ascending'));
	const filterLabel = commonT('table.filterColumn', { column: key });
	await fireEvent.click(screen.getByRole('button', { name: filterLabel }));
	const menu = within(screen.getByRole('dialog', { name: filterLabel }));
	await fireEvent.click(menu.getByRole('checkbox', { name: 'drop' }));
	await fireEvent.click(menu.getByRole('button', { name: commonT('actions.close') }));
	expectVisibleKeep();
	mocks.get.mockResolvedValueOnce({ ...volume, attachments: [], metadata: {} });
	await view.rerender({ volumeId: 'volume', token: 'token-2', projectId: 'tenant' });
	await waitFor(() => expect(screen.queryByText('Keep')).toBeNull());
	await view.rerender({ volumeId: 'volume', token: 'token-3', projectId: 'tenant' });
	await screen.findByText('Keep');
	await fireEvent.click(screen.getByRole('button', { name: filterLabel }));
	expect(screen.getByRole('dialog', { name: filterLabel })).toBeTruthy();
	mocks.get.mockRejectedValueOnce(new Error('unavailable'));
	await view.rerender({ volumeId: 'volume', token: 'token-4', projectId: 'tenant' });
	await screen.findByText(storageT('volumeDetail.loadFailed'));
	expect(screen.queryByRole('dialog', { name: filterLabel })).toBeNull();
	await view.rerender({ volumeId: 'volume', token: 'token-5', projectId: 'tenant' });
	await screen.findByText('Keep');
	expect(metadataInput().value).toBe('^(keep|drop)$');
	expect(attachmentInput().value).toBe('^vm-keep$');
	expect(sortButton('descending')).toBeTruthy();
	expectVisibleKeep();
	await view.rerender({ volumeId: 'volume', token: 'token-6', projectId: 'other-tenant' });
	await screen.findByText('Drop');
	expect(metadataInput().value).toBe('');
	expect(attachmentInput().value).toBe('');
});

function expectVisibleKeep() {
	expect(screen.getByText('Keep')).toBeTruthy();
	expect(screen.queryByText('Drop')).toBeNull();
}

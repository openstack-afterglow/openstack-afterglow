import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import K3sCreateClusterModal from '../K3sCreateClusterModal.svelte';

function grant(...leaves: string[]) {
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(leaf => leaves.includes(leaf));
}
beforeEach(() => {
	vi.resetAllMocks();
	grant();
	mocks.get.mockImplementation(async (path: string) => path === '/api/v1/keypairs' ? [{ name: 'node-root-key' }] : []);
});

describe('Drover create SSH credential boundary', () => {
	it('does not open or request dependencies for a plain native member or access-only user', () => {
		grant('drover-access_user');
		render(K3sCreateClusterModal, { open: true, token: 'token', projectId: 'project', onCreate: vi.fn() });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(mocks.get).not.toHaveBeenCalled();
	});
	it('lets a cluster editor create without a key and never requires or fetches SSH keys', async () => {
		grant('drover-clusters_editor');
		const onCreate = vi.fn();
		const { container } = render(K3sCreateClusterModal, { open: true, token: 'token', projectId: 'project', onCreate });
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(3));
		expect(screen.queryByText('키페어 (선택)')).toBeNull();
		const name = container.querySelector('[data-tour="drover-name"] input')!;
		await fireEvent.input(name, { target: { value: 'editor-cluster' } });
		const submit = container.querySelector('[data-tour="drover-create-submit"]') as HTMLButtonElement;
		expect(submit.disabled).toBe(false);
		await fireEvent.click(submit);
		expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ name: 'editor-cluster', key_name: '' }));
		expect(mocks.get.mock.calls.map(call => call[0])).not.toContain('/api/v1/keypairs');
	});
	it('offers node SSH injection only with explicit access-admin and removes submission on downgrade', async () => {
		grant('drover-clusters_editor', 'drover-access_admin');
		const onCreate = vi.fn();
		render(K3sCreateClusterModal, { open: true, token: 'token', projectId: 'project', onCreate });
		await screen.findByRole('option', { name: 'node-root-key' });
		expect(screen.getByText('키페어 (선택)')).toBeTruthy();
		grant('drover-access_admin');
		await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(onCreate).not.toHaveBeenCalled();
	});
});

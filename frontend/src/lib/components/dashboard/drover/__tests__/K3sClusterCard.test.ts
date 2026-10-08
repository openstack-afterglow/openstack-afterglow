import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import type { K3sCluster } from '$lib/types/k3s';
import { t } from '$lib/i18n/ns/drover-pages';
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import K3sClusterCard from '../K3sClusterCard.svelte';

const cluster: K3sCluster = {
	id: 'c', name: 'demo', status: 'ACTIVE', status_reason: null, server_vm_id: 'server',
	agent_vm_ids: [], agent_count: 0, api_address: null, server_ip: null, network_id: null,
	key_name: null, k3s_version: null, created_at: null, updated_at: null,
	deleted_at: null, deleted_by_user_id: null, deleted_reason: null,
};
function grant(...leaves: string[]) {
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(leaf => leaves.includes(leaf));
}
beforeEach(() => grant());

describe('cluster action controls', () => {
	it('offers inventory navigation but no privileged actions during pending/error or without service grants', async () => {
		const onDelete = vi.fn();
		const onDownloadKubeconfig = vi.fn();
		const onSelect = vi.fn();
		render(K3sClusterCard, { cluster, deleting: false, onSelect, onDelete, onDownloadKubeconfig });
		const download = screen.getByRole('button', { name: 'kubeconfig' }) as HTMLButtonElement;
		const remove = screen.getByRole('button', { name: '삭제' }) as HTMLButtonElement;
		expect(download.disabled).toBe(true);
		expect(remove.disabled).toBe(true);
		await fireEvent.click(download);
		await fireEvent.click(remove);
		expect(onDelete).not.toHaveBeenCalled();
		expect(onDownloadKubeconfig).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('actions.details') }));
		expect(onSelect).toHaveBeenCalledWith('c');
	});
	it('lets access_user download, but not delete; immediately disables download on scope revocation', async () => {
		grant('drover-access_user');
		const onDownloadKubeconfig = vi.fn();
		render(K3sClusterCard, { cluster, deleting: false, onSelect: vi.fn(), onDelete: vi.fn(), onDownloadKubeconfig });
		const download = screen.getByRole('button', { name: 'kubeconfig' }) as HTMLButtonElement;
		expect(download.disabled).toBe(false);
		expect((screen.getByRole('button', { name: '삭제' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(download);
		expect(onDownloadKubeconfig).toHaveBeenCalledWith('c', 'demo');
		grant();
		await vi.waitFor(() => expect(download.disabled).toBe(true));
		await fireEvent.click(download);
		expect(onDownloadKubeconfig).toHaveBeenCalledTimes(1);
	});
	it('does not expose delete or credentials to a narrow cluster editor', () => {
		grant('drover-clusters_editor');
		render(K3sClusterCard, { cluster, deleting: false, onSelect: vi.fn(), onDelete: vi.fn(), onDownloadKubeconfig: vi.fn() });
		expect((screen.getByRole('button', { name: 'kubeconfig' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: '삭제' }) as HTMLButtonElement).disabled).toBe(true);
	});
	it('lets a cluster administrator delete without granting credentials and stops after revocation', async () => {
		grant('drover-clusters_admin');
		const onDelete = vi.fn();
		render(K3sClusterCard, { cluster, deleting: false, onSelect: vi.fn(), onDelete, onDownloadKubeconfig: vi.fn() });
		const remove = screen.getByRole('button', { name: t('actions.delete') }) as HTMLButtonElement;
		expect(remove.disabled).toBe(false);
		expect((screen.getByRole('button', { name: 'kubeconfig' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(remove);
		expect(onDelete).toHaveBeenCalledWith('c', 'demo');
		grant();
		await vi.waitFor(() => expect(remove.disabled).toBe(true));
		await fireEvent.click(remove);
		expect(onDelete).toHaveBeenCalledTimes(1);
	});
	it.each([
		['CREATING', false, false, true],
		['DELETING', false, false, false],
		['ACTIVE', true, true, false],
	] as const)('guards callbacks for status %s with deleting=%s', async (status, deleting, downloadAllowed, deleteAllowed) => {
		grant('drover-access_user', 'drover-clusters_admin');
		const onDownloadKubeconfig = vi.fn();
		const onDelete = vi.fn();
		render(K3sClusterCard, { cluster: { ...cluster, status }, deleting, onSelect: vi.fn(), onDelete, onDownloadKubeconfig });
		const download = screen.getByRole('button', { name: 'kubeconfig' }) as HTMLButtonElement;
		const remove = screen.getByRole('button', { name: deleting ? t('state.deleting') : t('actions.delete') }) as HTMLButtonElement;
		expect(download.disabled).toBe(!downloadAllowed);
		expect(remove.disabled).toBe(!deleteAllowed);
		await fireEvent.click(download);
		await fireEvent.click(remove);
		expect(onDownloadKubeconfig).toHaveBeenCalledTimes(Number(downloadAllowed));
		expect(onDelete).toHaveBeenCalledTimes(Number(deleteAllowed));
	});
	it('keeps deleted cluster navigation unavailable even under direct dispatch', async () => {
		const onSelect = vi.fn();
		render(K3sClusterCard, { cluster: { ...cluster, status: 'DELETED', deleted_at: '2026-10-06T00:00:00Z' }, deleting: false, onSelect, onDelete: vi.fn(), onDownloadKubeconfig: vi.fn() });
		const details = screen.getByRole('button', { name: t('actions.details') }) as HTMLButtonElement;
		expect(details.disabled).toBe(true);
		await fireEvent.click(details);
		expect(onSelect).not.toHaveBeenCalled();
		expect(screen.queryByRole('button', { name: t('actions.delete') })).toBeNull();
	});
});

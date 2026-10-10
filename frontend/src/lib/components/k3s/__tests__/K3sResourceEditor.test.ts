import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import K3sResourceEditor from '../K3sResourceEditor.svelte';

function grant(...leaves: string[]) {
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(leaf => leaves.includes(leaf));
}
beforeEach(() => grant());

describe('resource editor uses the native workload write leaves', () => {
	it.each(['drover-access_user', 'drover-clusters_editor', 'drover-clusters_admin'])('does not let %s save a ConfigMap when mounted directly', async leaf => {
		grant(leaf);
		const onSave = vi.fn();
		render(K3sResourceEditor, { title: 'settings', resourceName: 'settings', namespace: 'private', initialData: { key: 'value' }, onSave, onClose: vi.fn() });
		const save = screen.getByRole('button', { name: '저장' }) as HTMLButtonElement;
		expect(save.disabled).toBe(true);
		await fireEvent.click(save);
		expect(onSave).not.toHaveBeenCalled();
	});
	it('permits workload editor saves but closes the editing boundary immediately on downgrade', async () => {
		grant('drover-workloads_editor');
		const onSave = vi.fn().mockResolvedValue(undefined);
		render(K3sResourceEditor, { title: 'settings', resourceName: 'settings', namespace: 'private', initialData: { key: 'value' }, onSave, onClose: vi.fn() });
		const save = screen.getByRole('button', { name: '저장' }) as HTMLButtonElement;
		await fireEvent.click(save);
		expect(onSave).toHaveBeenCalledWith({ key: 'value' });
		grant('drover-access_user');
		await vi.waitFor(() => expect(save.disabled).toBe(true));
		await fireEvent.click(save);
		expect(onSave).toHaveBeenCalledOnce();
	});
	it('requires access-admin for non-Opaque Secret writes', () => {
		grant('drover-workloads_editor');
		const { unmount } = render(K3sResourceEditor, { title: 'TLS', mode: 'secret', secretType: 'kubernetes.io/tls', resourceName: 'tls', namespace: 'private', onSave: vi.fn(), onClose: vi.fn() });
		expect((screen.getByRole('button', { name: '저장' }) as HTMLButtonElement).disabled).toBe(true);
		unmount();
		grant('drover-access_admin');
		render(K3sResourceEditor, { title: 'TLS', mode: 'secret', secretType: 'kubernetes.io/tls', resourceName: 'tls', namespace: 'private', onSave: vi.fn(), onClose: vi.fn() });
		expect((screen.getByRole('button', { name: '저장' }) as HTMLButtonElement).disabled).toBe(false);
	});
});

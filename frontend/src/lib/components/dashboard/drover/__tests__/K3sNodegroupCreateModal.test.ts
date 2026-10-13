import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class extends Error {} }));
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import K3sNodegroupCreateModal from '../K3sNodegroupCreateModal.svelte';

const gpuFlavor = { id: 'gpu-flavor', name: 'gpu.3060', vcpus: 8, ram: 16384, disk: 0, extra_specs: { 'pci_passthrough:alias': 'RTX-3060-LHR:1' } };

beforeEach(() => {
	vi.resetAllMocks();
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(leaf => leaf === 'drover-clusters_editor');
	mocks.get.mockResolvedValue([gpuFlavor]);
	mocks.post.mockImplementation(async (_path: string, body: Record<string, unknown>) => ({ id: 'ng', ...body }));
});

async function fill(container: HTMLElement) {
	await fireEvent.input(container.querySelector('input[type="text"]')!, { target: { value: 'gpu-workers' } });
	await screen.findByRole('option', { name: /gpu\.3060/ });
	const select = container.querySelector('select')!;
	select.value = 'gpu-flavor';
	await fireEvent.change(select);
}

describe('Drover nodegroup creation autoscaling default', () => {
	it('creates an autoscaled group by default and an explicit non-autoscaled group when switched off', async () => {
		const onSaved = vi.fn();
		const { container, unmount } = render(K3sNodegroupCreateModal, { clusterId: 'cluster-1', onClose: vi.fn(), onSaved });
		await fill(container);
		const toggle = screen.getByRole('switch');
		expect(toggle.getAttribute('aria-checked')).toBe('true');
		await fireEvent.click(screen.getByRole('button', { name: '생성' }));
		await vi.waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
		expect(mocks.post).toHaveBeenLastCalledWith('/api/v1/k3s/clusters/cluster-1/nodegroups', expect.objectContaining({
			flavor_id: 'gpu-flavor', stampede_enabled: true, min_size: 0, max_size: 5,
		}), undefined, undefined);
		unmount();

		const second = render(K3sNodegroupCreateModal, { clusterId: 'cluster-1', onClose: vi.fn(), onSaved });
		await fill(second.container);
		await fireEvent.click(screen.getByRole('switch'));
		await fireEvent.click(screen.getByRole('button', { name: '생성' }));
		await vi.waitFor(() => expect(onSaved).toHaveBeenCalledTimes(2));
		const body = mocks.post.mock.lastCall![1];
		expect(body.stampede_enabled).toBe(false);
		expect(body).not.toHaveProperty('min_size');
	});
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import type { K3sCluster, K3sInterfaceInfo, K3sNetwork } from '$lib/types/k3s';
import { writable, type Writable } from 'svelte/store';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));

type MockController = {
	cluster: K3sCluster;
	isActive: boolean;
	interfaces: Record<string, K3sInterfaceInfo[]>;
	networks: K3sNetwork[];
	interfaceActioning: string | null;
	loadInterfaces: () => Promise<void>;
	loadNetworks: () => Promise<void>;
	attachInterface: () => Promise<void>;
	detachInterface: () => Promise<void>;
};

const mocks = vi.hoisted(() => ({
	controller: null as MockController | null,
}));
vi.mock('$lib/stores/k3sClusterDetailController.svelte', () => ({
	useK3sClusterDetailController: () => mocks.controller,
}));

import K3sClusterNetworksCard from '../K3sClusterNetworksCard.svelte';

const cluster = (status: string): K3sCluster => ({
	id: 'cluster-1',
	name: 'cluster-1',
	status,
	status_reason: null,
	server_vm_id: 'server-1',
	agent_vm_ids: [],
	agent_count: 0,
	api_address: null,
	server_ip: null,
	network_id: 'net-primary',
	key_name: null,
	k3s_version: null,
	created_at: null,
	updated_at: null,
	deleted_at: null,
	deleted_by_user_id: null,
	deleted_reason: null,
});

const iface = (overrides: Partial<K3sInterfaceInfo>): K3sInterfaceInfo => ({
	port_id: 'port-secondary',
	net_id: 'net-secondary',
	fixed_ips: [],
	vm_id: 'server-1',
	node_role: 'server',
	is_primary: false,
	...overrides,
});

const networks: K3sNetwork[] = [
	{ id: 'net-primary', name: 'Primary', is_external: false },
	{ id: 'net-secondary', name: 'Secondary', is_external: false },
	{ id: 'net-third', name: 'Third', is_external: false },
];

function renderCard(status = 'ACTIVE', interfaces: K3sInterfaceInfo[] = [
	iface({ port_id: 'port-secondary', net_id: 'net-secondary', is_primary: false }),
	iface({ port_id: 'port-primary', net_id: 'net-primary', is_primary: true }),
]) {
	mocks.controller = {
		cluster: cluster(status),
		isActive: status === 'ACTIVE',
		interfaces: { 'server-1': interfaces },
		networks,
		interfaceActioning: null,
		loadInterfaces: vi.fn().mockResolvedValue(undefined),
		loadNetworks: vi.fn().mockResolvedValue(undefined),
		attachInterface: vi.fn().mockResolvedValue(undefined),
		detachInterface: vi.fn().mockResolvedValue(undefined),
	};
	return render(K3sClusterNetworksCard);
}

describe('K3sClusterNetworksCard primary network controls', () => {
	beforeEach(() => {
		mocks.controller = null;
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => ['drover-clusters_editor', 'drover-clusters_admin'].includes(leaf));
	});

	it('hides attach controls for non-ACTIVE clusters', () => {
		renderCard('CREATING');
		expect(screen.queryByRole('button', { name: '+ 네트워크 연결' })).toBeNull();
	});

	it('filters every attached network from the selector', async () => {
		renderCard();
		await fireEvent.click(screen.getByRole('button', { name: '+ 네트워크 연결' }));
		const selector = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
		const optionValues = [...selector.options].map((option) => option.value);
		expect(optionValues).toEqual(['', 'net-third']);
	});

	it('uses is_primary instead of interface order for labels and detach availability', () => {
		renderCard();
		const primaryLabel = screen.getByText('기본 인터페이스');
		expect(primaryLabel).toBeTruthy();
		const detachButtons = screen.getAllByRole('button', { name: '제거' }) as HTMLButtonElement[];
		expect(detachButtons).toHaveLength(2);
		expect(detachButtons[0].disabled).toBe(false);
		expect(detachButtons[1].disabled).toBe(true);
	});
	it('shows inventory but disables network mutations for access-only users', async () => {
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'drover-access_user');
		renderCard();
		expect(screen.queryByRole('button', { name: '+ 네트워크 연결' })).toBeNull();
		for (const button of screen.getAllByRole('button', { name: '제거' }) as HTMLButtonElement[]) {
			expect(button.disabled).toBe(true);
			await fireEvent.click(button);
		}
		expect(mocks.controller!.detachInterface).not.toHaveBeenCalled();
	});
	it('allows editor attach but reserves detach for the administrator leaf', async () => {
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'drover-clusters_editor');
		renderCard();
		await fireEvent.click(screen.getByRole('button', { name: '+ 네트워크 연결' }));
		const selector = screen.getAllByRole('combobox')[1];
		await fireEvent.change(selector, { target: { value: 'net-third' } });
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		expect(mocks.controller!.attachInterface).toHaveBeenCalledWith('server-1', 'net-third');
		for (const button of screen.getAllByRole('button', { name: '제거' }) as HTMLButtonElement[]) {
			expect(button.disabled).toBe(true);
		}
		expect(mocks.controller!.detachInterface).not.toHaveBeenCalled();
	});
});

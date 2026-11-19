import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/drover';
import { t as isoText } from '$lib/i18n/ns/iso-view';
import type { K3sCluster, ServiceInfo } from '$lib/types/k3s';
import type { K3sGridNodeData } from '../k3sIsoScene';
import K3sClusterGrid from '../K3sClusterGrid.svelte';

const mocks = vi.hoisted(() => ({ controller: {} as Record<string, unknown> }));
vi.mock('$lib/stores/k3sClusterDetailController.svelte', () => ({
	useK3sClusterDetailController: () => mocks.controller,
}));

afterEach(() => {
	cleanup();
	localStorage.removeItem('drover.cluster.view');
	vi.unstubAllGlobals();
});

it('opens an inspector from the real grid and keeps the list preference across mounts', async () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
	const cluster: K3sCluster = {
		id: 'cluster', name: 'example', status: 'ACTIVE', status_reason: null, server_vm_id: 'vm-1', agent_vm_ids: [], agent_count: 0,
		api_address: null, server_ip: null, network_id: null, key_name: null, k3s_version: null, created_at: null, updated_at: null,
		deleted_at: null, deleted_by_user_id: null, deleted_reason: null,
	};
	const service: ServiceInfo = {
		name: 'gateway', namespace: 'default', type: 'LoadBalancer', cluster_ip: '10.43.0.3', external_ips: ['192.0.2.9'],
		ports: [{ name: 'https', port: 443, target_port: 8443, node_port: 30443, protocol: 'TCP' }], selector: {}, created_at: '',
	};
	const node: Partial<K3sGridNodeData> = { instance: { name: 'demo-control', status: 'ACTIVE', image_id: null }, volumes: null };
	mocks.controller = {
		cluster, isActive: true, gridLoading: false, gridNodeData: { 'vm-1': node }, gridNodegroups: [], gridNetworks: [], gridFloating: null,
		gridServices: { items: [service], failedNamespaces: [] }, loadGridInventory: vi.fn(), loadGridNodes: vi.fn(), stopGridReads: vi.fn(),
	};
	const list = createRawSnippet(() => ({ render: () => '<p>VM inventory</p>' }));
	const { unmount } = render(K3sClusterGrid, { list });
	const canvas = screen.getByRole('group', { name: t('grid.title') });
	const serviceButton = within(canvas).getByRole('button', { name: /default\/gateway/ });
	await fireEvent.click(serviceButton);
	const inspector = screen.getByRole('region', { name: 'default/gateway' });
	expect(within(inspector).getByText('192.0.2.9')).toBeTruthy();
	expect(within(inspector).getByText(/30443/).textContent).toContain('8443');
	expect(serviceButton.getAttribute('aria-pressed')).toBe('true');
	await fireEvent.click(within(canvas).getByRole('button', { name: /demo-control/ }));
	expect(within(screen.getByRole('region', { name: 'demo-control' })).getAllByText(t('grid.unknown')).length).toBeGreaterThan(0);

	await fireEvent.click(screen.getByRole('button', { name: isoText('view.list') }));
	expect(screen.getByText('VM inventory')).toBeTruthy();
	expect(screen.queryByRole('group', { name: t('grid.title') })).toBeNull();
	expect(localStorage.getItem('drover.cluster.view')).toBe('list');
	expect(mocks.controller.stopGridReads).toHaveBeenCalled();
	unmount();
	render(K3sClusterGrid, { list });
	expect(screen.getByText('VM inventory')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: isoText('view.grid') }));
	expect(screen.getByRole('group', { name: t('grid.title') })).toBeTruthy();
});

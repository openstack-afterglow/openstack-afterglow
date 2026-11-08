import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/instance';
import type { Instance } from '$lib/types/compute';
import type { PortInfo } from '$lib/types/networks';

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn(), mockDelete: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: mockDelete, withExperience() { return this; } },
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', userId: 'user', projectId: 'project', roles: ['member'], isSystemAdmin: false });
	return { auth, canWrite: writable(true) };
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [30], setBoost: vi.fn() }),
}));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));

import { auth } from '$lib/stores/auth';
import Wrapper from './_WaygateDetailWrapper.svelte';

let waygateManaged = true;
const iface: PortInfo = {
	id: 'port', network_id: 'network', mac_address: 'fa:16:3e:00:00:01', name: null, device_owner: 'compute:nova',
	project_id: 'project', fixed_ips: [{ ip_address: '192.0.2.10' }], security_group_ids: [], status: 'ACTIVE',
};
const attachment = {
	file_storage_id: 'share', name: 'share', share_proto: 'NFS', access_id: 'rule', access_type: 'ip', access_to: '192.0.2.10',
	access_level: 'rw', state: 'active', association_state: 'tracked', managed: true, exports: [], share_network_id: null, share_network: null,
};

function installApi() {
	mockGet.mockImplementation((path: string) => {
		const base = path.replace('/api/v1/admin/instances/vm', '/api/v1/instances/vm');
		if (base === '/api/v1/instances/vm') return Promise.resolve({
			id: 'vm', name: 'gateway', status: 'SHUTOFF', image_name: null, flavor_name: 'small', flavor_id: 'small',
			ip_addresses: [{ addr: '192.0.2.10', type: 'fixed', network_name: 'private' }], created_at: null,
			union_libraries: [], union_strategy: null, project_id: 'project', user_id: 'user', waygate_managed: waygateManaged,
		} satisfies Instance);
		if (base.endsWith('/interfaces')) return Promise.resolve([iface]);
		if (base === '/api/v1/instances/vm/volumes') return Promise.resolve([{ volume_id: 'data', name: 'data', device: '/dev/vdb', delete_on_termination: false, size: 10, status: 'in-use' }]);
		if (base.endsWith('/security-groups')) return Promise.resolve({ ports: [iface], security_groups: [] });
		if (base.endsWith('/owner')) return Promise.resolve({ display: '' });
		if (base.endsWith('/storage-attachments')) return Promise.resolve([attachment]);
		return Promise.resolve([]);
	});
}

function button(name: string) {
	return screen.getAllByRole('button', { name })[0] as HTMLButtonElement;
}

beforeEach(() => {
	initLocale('ko');
	vi.clearAllMocks();
	waygateManaged = true;
	auth.update(state => ({ ...state, token: 'token', userId: 'user', projectId: 'project', roles: ['member'], isSystemAdmin: false }));
	vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() })));
	installApi();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const lockedButtons = () => [
	t('rename.title'), t('header.shelve'), t('header.delete'), t('header.resize'),
	t('network.addInterface'), t('network.addFloatingIp'), t('network.remove'), t('network.edit'),
	t('volumes.addAttachment'), t('volumes.detach'), t('volumes.keep'),
	t('storageAttachments.openGrant'), t('storageAttachments.revoke'),
];

describe('Waygate-managed instance detail UI', () => {
	it('disables locked actions with the localized tooltip and links to Waygate', async () => {
		render(Wrapper);
		await screen.findByText(t('storageAttachments.revoke'));
		const note = screen.getByTestId('waygate-managed-note');
		expect(note.textContent).toBe(t('waygate.managedNote'));
		expect(screen.getByRole('link', { name: t('waygate.openLink') }).getAttribute('href')).toBe('/dashboard/network/waygate');
		for (const name of lockedButtons()) {
			const control = button(name);
			expect(control.disabled, name).toBe(true);
			expect(control.getAttribute('title'), name).toBe(t('waygate.managedNote'));
		}
		expect(button(t('header.start')).disabled).toBe(false);
		// Even a forced click reaches the controller guard, which refuses without a network call.
		await fireEvent.click(button(t('header.shelve')));
		await fireEvent.click(button(t('header.delete')));
		await fireEvent.click(button(t('network.remove')));
		expect(mockPost).not.toHaveBeenCalled();
		expect(mockDelete).not.toHaveBeenCalled();
	});

	it('keeps an ordinary instance unaffected', async () => {
		waygateManaged = false;
		render(Wrapper);
		await screen.findByText(t('storageAttachments.revoke'));
		expect(screen.queryByTestId('waygate-managed-note')).toBeNull();
		for (const name of lockedButtons()) {
			const control = button(name);
			expect(control.disabled, name).toBe(false);
			expect(control.getAttribute('title') ?? '', name).not.toBe(t('waygate.managedNote'));
		}
	});

	it('leaves a gateway controllable in admin mode', async () => {
		auth.update(state => ({ ...state, token: 'token', userId: 'admin', projectId: 'admin-project', roles: ['admin'], isSystemAdmin: true }));
		render(Wrapper, { adminMode: true });
		await screen.findByText(t('storageAttachments.revoke'));
		expect(screen.queryByTestId('waygate-managed-note')).toBeNull();
		for (const name of [t('header.shelve'), t('header.delete'), t('network.remove'), t('volumes.detach'), t('storageAttachments.revoke')]) {
			await waitFor(() => expect(button(name).disabled, name).toBe(false));
		}
	});
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type { Instance } from '$lib/types/compute';
import { initLocale } from '$lib/i18n/runtime.svelte';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'admin-token', projectId: 'personal', userId: 'actor', isSystemAdmin: true }),
	canWrite: writable(true),
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), info: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60], setBoost: vi.fn() }),
}));
// Keep the real panel, controller, header and synchronous controller option reads.
// Subordinate rendering is tested separately; none of these mocks replaces transport ownership.
vi.mock('$lib/components/instance/MetricsPanel.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/InfoSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/ConsoleSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/NetworkSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/VolumesSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/StorageAttachmentsSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/UnionInfoSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));

import InstanceDetailPanel from '../InstanceDetailPanel.svelte';

function nativeServer(id: string): Instance {
	return { id, name: `native-${id}`, project_id: 'foreign-project', user_id: 'creator', status: 'SHUTOFF',
		image_name: null, flavor_name: null, ip_addresses: [], created_at: null, union_libraries: [], union_strategy: null };
}

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	get.mockImplementation(async (path: string) => {
		if (/^\/api\/v1\/admin\/instances\/(vm-a|vm-b)$/.test(path)) return nativeServer(path.split('/').at(-1)!);
		if (path.includes('/metrics-summary?')) return { monitoring_available: false, stats: {}, recommendation: null };
		if (path.endsWith('/security-groups')) return { ports: [], security_groups: [] };
		if (path.endsWith('/owner')) return { display: 'Creator' };
		if (path.endsWith('/migration-status')) return { host: null, migration: null, error: null };
		if (path.endsWith('/admin-password/precheck')) return { supported: false, reason: null, server_status: 'SHUTOFF' };
		return [];
	});
});

describe('instance panel with its real controller', () => {
	it.each(['foreign-project', null])('mounts administrator detail with project hint %s without circular initialization or consumer fallback', async adminProjectId => {
		render(InstanceDetailPanel, { instanceId: 'vm-a', adminMode: true, adminProjectId });
		await screen.findByText('native-vm-a');
		await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/admin/instances/vm-a', 'admin-token', 'personal'));
		await tick();
		await tick();
		expect(get.mock.calls.every(([path]) => path.startsWith('/api/v1/admin/instances/'))).toBe(true);
		const initialDetailReads = get.mock.calls.filter(([path]) => path === '/api/v1/admin/instances/vm-a').length;
		expect(initialDetailReads).toBeGreaterThan(0);
		// One owner-context transition is allowed; a new native object must not cause a fetch loop.
		expect(initialDetailReads).toBeLessThanOrEqual(2);
		await tick();
		expect(get.mock.calls.filter(([path]) => path === '/api/v1/admin/instances/vm-a')).toHaveLength(initialDetailReads);
	});

	it('keeps the next administrator selection on native owner context when its list hint is absent', async () => {
		const view = render(InstanceDetailPanel, { instanceId: 'vm-a', adminMode: true, adminProjectId: null });
		await screen.findByText('native-vm-a');
		await view.rerender({ instanceId: 'vm-b', adminMode: true, adminProjectId: null });
		await screen.findByText('native-vm-b');
		expect(get).toHaveBeenCalledWith('/api/v1/admin/instances/vm-b', 'admin-token', 'personal');
		expect(get.mock.calls.some(([path]) => path.startsWith('/api/v1/instances/'))).toBe(false);
	});
});

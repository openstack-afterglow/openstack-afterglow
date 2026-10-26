import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { auth, projectSwitching } from '$lib/stores/auth';
import type { AuthState } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/dashboard-home';
import { t as shared } from '$lib/i18n/ns/shared';
import { RESOURCE_CATEGORIES } from '$lib/types/userDashboard';
import type { ProjectResourceInventory, ResourceCategory, ResourceItem, UserDashboardSummary } from '$lib/types/userDashboard';
const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	refresh: null as (() => void | Promise<void>) | null,
}));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	return { auth: writable(null), projectSwitching: writable(false) };
});
vi.mock('$lib/api/client', () => ({ api: { get: mocks.apiGet }, ApiError: class extends Error {} }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: (force?: boolean) => void | Promise<void>) => {
		mocks.refresh = callback;
		return { active: false, intervalSeconds: 30, intervalOptions: [10, 30, 60], refresh: () => callback(true) };
	},
}));

import Page from '../+page.svelte';

function identity(overrides: Partial<AuthState> = {}): AuthState {
	return {
		token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'User',
		projectId: 'project', projectName: 'Project', availableProjects: [], roles: [],
		isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false, ...overrides,
	};
}

// These are genuine consumer destinations, including subnets' owning network route.
const routes: Record<ResourceCategory, string> = {
	instances: '/dashboard/compute/instances/vm', volumes: '/dashboard/volumes/volume',
	floating_ips: '/dashboard/network/floating-ips', networks: '/dashboard/network/networks/network',
	subnets: '/dashboard/network/networks/owning-network', routers: '/dashboard/network/routers/router',
	security_groups: '/dashboard/network/security-groups', load_balancers: '/dashboard/network/loadbalancers/lb',
	images: '/dashboard/compute/images', keypairs: '/dashboard/compute/keypairs',
	database_instances: '/dashboard/database/instances/db', database_backups: '/dashboard/database/backups',
	k3s_clusters: '/dashboard/drover/cluster', waygate_gateways: '/dashboard/network/waygate',
	containers: '/dashboard/containers/instances/container', magnum_clusters: '/dashboard/containers/clusters/cluster',
	shares: '/dashboard/file-storage/share', share_snapshots: '/dashboard/file-storage/snapshots',
	share_networks: '/dashboard/file-storage/networks', security_services: '/dashboard/file-storage/security-services',
	buckets: '/dashboard/object-storage/buckets/bucket', volume_snapshots: '/dashboard/volumes/snapshots',
	volume_backups: '/dashboard/volumes/backups', packages: '/palimpsest/packages', secrets: '/dashboard/secrets',
};

function item(category: ResourceCategory, index = 0, projectId = 'project'): ResourceItem {
	return {
		id: `${category}-${index}`, name: `${category} item ${index}`, status: 'ACTIVE',
		project_id: projectId, project_name: projectId === 'project' ? 'Project' : 'Other project',
		owner_scope: category === 'keypairs' ? 'user' : 'project',
		owner_id: category === 'keypairs' ? 'user' : projectId, href: routes[category],
		...(category === 'volumes' ? { size: 10, volume_type: 'ssd' } : {}),
	};
}

function project(projectId = 'project', count = 1): ProjectResourceInventory {
	return {
		project_id: projectId, project_name: projectId === 'project' ? 'Project' : 'Other project',
		resources: Object.fromEntries(RESOURCE_CATEGORIES.map(category => [category, {
			state: 'ready', count, items: Array.from({ length: count }, (_, index) => item(category, index, projectId)),
		}])) as ProjectResourceInventory['resources'],
		usage: { vcpus: 2, ram_mb: 1024, storage_gb: 10 },
	};
}

function summary(count = 1, state = identity()): UserDashboardSummary {
	return {
		user_id: state.userId!, current_project_id: state.projectId!, projects: [project(state.projectId!, count)],
		totals: {
			resources: Object.fromEntries(RESOURCE_CATEGORIES.map(category => [category, {
				state: 'ready', count, known_count: count,
			}])) as UserDashboardSummary['totals']['resources'],
			usage: { vcpus: 2, ram_mb: 1024, storage_gb: 10 },
		},
	};
}

function deferred() {
	let resolve!: (value: UserDashboardSummary) => void;
	let reject!: (reason: Error) => void;
	const promise = new Promise<UserDashboardSummary>((done, fail) => { resolve = done; reject = fail; });
	return { promise, resolve, reject };
}

function card(container: HTMLElement, category: ResourceCategory): HTMLElement {
	return container.querySelector<HTMLElement>(`[data-resource-category="${category}"]`)!;
}
async function snapshot(container: HTMLElement) {
	await waitFor(() => expect(container.querySelector('[data-resource-snapshot]')).not.toBeNull());
}

beforeEach(() => {
	mocks.apiGet.mockReset();
	mocks.refresh = null;
	auth.set(identity());
	projectSwitching.set(false);
});
afterEach(() => cleanup());

describe('my resources inventory consumer', () => {
	it('renders all 25 real catalogs, five-item previews, show-more and route links', async () => {
		mocks.apiGet.mockResolvedValueOnce(summary(7));
		const { container } = render(Page);
		await snapshot(container);
		expect(container.querySelectorAll('[data-resource-category]')).toHaveLength(25);
		expect(container.querySelectorAll('[data-total-category]')).toHaveLength(25);
		for (const category of RESOURCE_CATEGORIES) {
			const section = card(container, category);
			expect(within(section).getByRole('heading', { name: t(`myResources.category.${category}`) })).toBeTruthy();
			expect(section.querySelectorAll('[data-resource-item]')).toHaveLength(5);
			expect(section.querySelector('[data-resource-count]')!.textContent).toBe('7');
			expect(within(section).getByRole('link', { name: `${category} item 0` }).getAttribute('href')).toBe(routes[category]);
			const reveal = section.querySelector<HTMLButtonElement>('[data-resource-show-more] button')!;
			expect(reveal.getAttribute('aria-expanded')).toBe('false');
			await fireEvent.click(reveal);
			expect(reveal.getAttribute('aria-expanded')).toBe('true');
			expect(section.querySelectorAll('[data-resource-item]')).toHaveLength(7);
			expect(within(section).getByText(`${category} item 6`)).toBeTruthy();
			await fireEvent.click(reveal);
			expect(section.querySelectorAll('[data-resource-item]')).toHaveLength(5);
		}
		expect(mocks.apiGet).toHaveBeenCalledWith('/api/v1/user-dashboard/summary', 'token', 'project', undefined);
	});

	it('keeps all enabled-empty categories visible with honest zero counts', async () => {
		mocks.apiGet.mockResolvedValueOnce(summary(0));
		const { container } = render(Page);
		await snapshot(container);
		for (const category of RESOURCE_CATEGORIES) {
			const section = card(container, category);
			expect(section.querySelector('[data-resource-empty]')).not.toBeNull();
			expect(section.querySelector('[data-resource-count]')!.textContent).toBe('0');
			expect(section.querySelector('[data-resource-item]')).toBeNull();
			expect(section.querySelector('[data-resource-show-more]')).toBeNull();
		}
	});

	it.each(['disabled', 'denied', 'failed'] as const)('keeps every catalog visible and unknown when %s', async state => {
		const response = summary(0);
		for (const category of RESOURCE_CATEGORIES) {
			response.projects[0].resources[category] = { state, count: null, items: [] };
			response.totals.resources[category] = { state, count: null, known_count: 0 };
		}
		mocks.apiGet.mockResolvedValueOnce(response);
		const { container } = render(Page);
		await snapshot(container);
		for (const category of RESOURCE_CATEGORIES) {
			const section = card(container, category);
			expect(section.querySelector('[data-resource-count]')!.textContent).toBe(t('myResources.unknown'));
			expect(section.querySelector(`[data-inventory-state="${state}"]`)).not.toBeNull();
			expect(section.querySelector('[data-resource-item]')).toBeNull();
			expect(section.querySelector('[data-resource-empty]')).toBeNull();
			const cell = container.querySelector(`[data-usage-category="${category}"]`)!;
			expect(cell.getAttribute('data-usage-state')).toBe(state);
			expect(cell.textContent).toContain(t('myResources.unknown'));
		}
	});

	it('reports all nullable usage metrics as unknown rather than zero', async () => {
		const response = summary(0);
		response.projects[0].usage = { vcpus: null, ram_mb: null, storage_gb: null };
		response.totals.usage = { vcpus: null, ram_mb: null, storage_gb: null };
		mocks.apiGet.mockResolvedValueOnce(response);
		const { container } = render(Page);
		await snapshot(container);
		for (const metric of ['vcpus', 'ram_mb', 'storage_gb']) {
			expect(container.querySelector(`[data-total-usage="${metric}"] dd`)!.textContent).toBe(t('myResources.unknown'));
			expect(container.querySelector(`[data-usage-metric="${metric}"]`)!.textContent).toBe(t('myResources.unknown'));
		}
	});

	it('distinguishes disabled, denied, failed, partial known counts and nullable usage', async () => {
		const response = summary(0);
		response.projects.push(project('other', 0));
		for (const [category, state] of [['containers', 'disabled'], ['secrets', 'denied'], ['shares', 'failed']] as const) {
			response.projects[0].resources[category] = { state, count: null, items: [], ...(state === 'failed' ? { error: 'Inventory unavailable' } : {}) };
			response.projects[1].resources[category] = { state, count: null, items: [] };
			response.totals.resources[category] = { state, count: null, known_count: 0 };
		}
		response.projects[0].resources.instances = { state: 'ready', count: 2, items: [item('instances'), item('instances', 1)] };
		response.projects[1].resources.instances = { state: 'denied', count: null, items: [] };
		response.totals.resources.instances = { state: 'partial', count: null, known_count: 2 };
		response.projects[0].usage = { vcpus: null, ram_mb: 0, storage_gb: null };
		response.totals.usage = { vcpus: null, ram_mb: 0, storage_gb: null };
		mocks.apiGet.mockResolvedValueOnce(response);
		const { container } = render(Page);
		await snapshot(container);
		for (const [category, state] of [['containers', 'disabled'], ['secrets', 'denied'], ['shares', 'failed']] as const) {
			const section = card(container, category);
			expect(section.querySelector(`[data-inventory-state="${state}"]`)).not.toBeNull();
			expect(section.querySelector('[data-project-count]')!.textContent).toBe(t('myResources.unknown'));
			expect(section.querySelector('[data-resource-empty]')).toBeNull();
			expect(container.querySelector(`[data-total-category="${category}"] [data-total-count]`)!.textContent).toBe(t('myResources.unknown'));
		}
		expect(within(card(container, 'shares')).getByText('Inventory unavailable')).toBeTruthy();
		const partial = container.querySelector('[data-total-category="instances"]')!;
		expect(partial.getAttribute('data-total-state')).toBe('partial');
		expect(partial.querySelector('[data-total-count]')!.textContent).toBe(t('myResources.unknown'));
		expect(partial.querySelector('[data-known-count]')!.textContent).toBe(t('myResources.knownCount', { count: 2 }));
		expect(card(container, 'instances').querySelector('[data-known-count]')).not.toBeNull();
		expect(container.querySelector('[data-total-usage="vcpus"] dd')!.textContent).toBe(t('myResources.unknown'));
		expect(container.querySelector('[data-total-usage="ram_mb"] dd')!.textContent).toBe('0');
		expect(container.querySelector('[data-usage-project="project"] [data-usage-metric="storage_gb"]')!.textContent).toBe(t('myResources.unknown'));
		const region = container.querySelector('[data-project-usage-scroll]')!;
		expect(region.getAttribute('role')).toBe('region');
		expect(region.getAttribute('tabindex')).toBe('0');
		expect(region.querySelectorAll('tbody tr')).toHaveLength(2);
		expect(region.querySelectorAll('tbody tr:first-child [data-usage-category]')).toHaveLength(25);
		for (const group of ['infrastructure', 'network', 'logical', 'storage'] as const) {
			expect(screen.getByRole('heading', { name: t(`myResources.group.${group}`) })).toBeTruthy();
		}
		expect(screen.getByText(t('myResources.countingHelp'))).toBeTruthy();
	});

	it('never links another project directly and labels account-scoped keypair visibility honestly', async () => {
		const response = summary(1);
		response.projects.push(project('other', 1));
		for (const category of RESOURCE_CATEGORIES) response.totals.resources[category] = { state: 'ready', count: category === 'keypairs' ? 1 : 2, known_count: category === 'keypairs' ? 1 : 2 };
		mocks.apiGet.mockResolvedValueOnce(response);
		const { container } = render(Page);
		await snapshot(container);
		for (const category of RESOURCE_CATEGORIES) {
			const section = card(container, category);
			const rows = section.querySelectorAll('[data-resource-item]');
			expect(rows).toHaveLength(2);
			expect(rows[0].querySelector('a')!.getAttribute('href')).toBe(routes[category]);
			expect(rows[1].querySelector('a')).toBeNull();
			expect(rows[1].querySelector('[data-select-project-first]')!.textContent).toBe(t(category === 'keypairs' ? 'myResources.selectContextFirst' : 'myResources.selectProjectFirst', { project: 'Other project' }));
		}
		const keypairs = card(container, 'keypairs');
		expect(keypairs.querySelector('[data-keypair-context]')!.textContent).toBe(t('myResources.keypairContext'));
		expect(keypairs.querySelector('[data-resource-count]')!.textContent).toBe('1');
		expect(keypairs.textContent).toContain(t('myResources.owner.user', { owner: 'user' }));
		expect(keypairs.textContent).toContain(t('myResources.visibilityContext', { project: 'Other project' }));
		expect(keypairs.textContent).not.toContain(t('myResources.owner.project', { owner: 'other' }));
	});

	it('retains existing keyed resource and project rows while refreshing and reordering data', async () => {
		mocks.apiGet.mockResolvedValueOnce(summary(2));
		const { container } = render(Page);
		const first = await screen.findByText('instances item 0');
		const volume = screen.getByText('volumes item 0');
		const projectRow = container.querySelector('[data-usage-project="project"]');
		const pending = deferred();
		mocks.apiGet.mockReturnValueOnce(pending.promise);
		const refresh = mocks.refresh!();
		expect(screen.getByText('instances item 0')).toBe(first);
		expect(screen.getByText('volumes item 0')).toBe(volume);
		const response = summary(2);
		response.projects[0].resources.instances.items.reverse();
		response.projects[0].resources.volumes.items[0].size = 20;
		pending.resolve(response);
		await refresh;
		await tick();
		expect(screen.getByText('20 GB · ssd')).toBeTruthy();
		expect(screen.getByText('instances item 0')).toBe(first);
		expect(screen.getByText('volumes item 0')).toBe(volume);
		expect(container.querySelector('[data-usage-project="project"]')).toBe(projectRow);
		expect(card(container, 'instances').querySelector('[data-resource-item]')!.getAttribute('data-resource-item')).toBe('instances-1');
	});

	it('passes bypass on manual refresh and clears old data on failure, then recovers', async () => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		const { container } = render(Page);
		await snapshot(container);
		const pending = deferred();
		mocks.apiGet.mockReturnValueOnce(pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: shared('autoRefresh.refresh') }));
		expect(mocks.apiGet).toHaveBeenLastCalledWith('/api/v1/user-dashboard/summary', 'token', 'project', expect.objectContaining({ refresh: true }));
		expect(container.querySelector('[data-resource-snapshot]')).not.toBeNull();
		pending.reject(new Error('offline'));
		await waitFor(() => expect(container.querySelector('[data-resource-error]')).not.toBeNull());
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		mocks.apiGet.mockResolvedValueOnce(summary(0));
		await mocks.refresh!();
		await snapshot(container);
		expect(container.querySelector('[data-resource-error]')).toBeNull();
	});

	it.each(['user', 'project'] as const)('rejects a response with mismatched %s identity', async field => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		const { container } = render(Page);
		await snapshot(container);
		const wrong = summary();
		if (field === 'user') wrong.user_id = 'another-user';
		else wrong.current_project_id = 'another-project';
		mocks.apiGet.mockResolvedValueOnce(wrong);
		await mocks.refresh!();
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		expect(container.querySelector('[data-resource-error]')).not.toBeNull();
	});

	it.each([
		['user switch', { userId: 'next-user' }],
		['project switch', { projectId: 'next-project' }],
		['token rotation', { token: 'next-token' }],
	] as const)('masks old data and fences deferred responses on %s', async (_label, change) => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		const { container } = render(Page);
		await snapshot(container);
		const stale = deferred();
		const fresh = deferred();
		mocks.apiGet.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);
		const oldRefresh = mocks.refresh!();
		const next = identity(change);
		auth.set(next);
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		expect(container.querySelector('[data-resource-loading]')).not.toBeNull();
		expect(mocks.apiGet).toHaveBeenLastCalledWith('/api/v1/user-dashboard/summary', next.token, next.projectId, undefined);
		stale.resolve(summary(7));
		await oldRefresh;
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		fresh.resolve(summary(0, next));
		await snapshot(container);
		expect(card(container, 'instances').querySelector('[data-resource-count]')!.textContent).toBe('0');
	});

	it('gates project switching synchronously and reloads when it completes', async () => {
		const initial = deferred();
		const afterSwitch = deferred();
		mocks.apiGet.mockReturnValueOnce(initial.promise).mockReturnValueOnce(afterSwitch.promise);
		const { container } = render(Page);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(1));
		projectSwitching.set(true);
		await tick();
		expect(container.querySelector('[data-resource-auth-gate]')).not.toBeNull();
		initial.resolve(summary(7));
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		projectSwitching.set(false);
		await tick();
		expect(mocks.apiGet).toHaveBeenCalledTimes(2);
		afterSwitch.resolve(summary(0));
		await snapshot(container);
	});

	it('clears a mounted snapshot on logout and ignores a pending refresh', async () => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		const { container } = render(Page);
		await snapshot(container);
		const pending = deferred();
		mocks.apiGet.mockReturnValueOnce(pending.promise);
		const refresh = mocks.refresh!();
		auth.set(identity({ token: null, userId: null, projectId: null }));
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		expect(container.querySelector('[data-resource-auth-gate]')).not.toBeNull();
		pending.resolve(summary());
		await refresh;
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		await mocks.refresh!();
		expect(mocks.apiGet).toHaveBeenCalledTimes(2);
	});

	it.each(['auth', 'switching'] as const)('fences same-batch A→B→A through %s subscriptions', async source => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		const { container } = render(Page);
		await snapshot(container);
		const oldA = deferred();
		const b = deferred();
		const newA = deferred();
		mocks.apiGet.mockReturnValueOnce(oldA.promise);
		const refresh = mocks.refresh!();
		if (source === 'auth') {
			mocks.apiGet.mockReturnValueOnce(b.promise).mockReturnValueOnce(newA.promise);
			auth.set(identity({ projectId: 'other' }));
			auth.set(identity());
		} else {
			mocks.apiGet.mockReturnValueOnce(newA.promise);
			projectSwitching.set(true);
			projectSwitching.set(false);
		}
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		oldA.resolve(summary(7));
		await refresh;
		if (source === 'auth') b.resolve(summary(7, identity({ projectId: 'other' })));
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		newA.resolve(summary(0));
		await snapshot(container);
		expect(card(container, 'instances').querySelector('[data-resource-count]')!.textContent).toBe('0');
	});

	it.each(['success', 'failure'] as const)('lets the latest refresh win over a stale %s', async staleOutcome => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		const { container } = render(Page);
		await snapshot(container);
		const older = deferred();
		const newer = deferred();
		mocks.apiGet.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
		const oldRefresh = mocks.refresh!();
		const newRefresh = mocks.refresh!();
		newer.resolve(summary(0));
		await newRefresh;
		await tick();
		if (staleOutcome === 'success') older.resolve(summary(7));
		else older.reject(new Error('stale failure'));
		await oldRefresh;
		await tick();
		expect(card(container, 'instances').querySelector('[data-resource-count]')!.textContent).toBe('0');
		expect(container.querySelector('[data-resource-error]')).toBeNull();
	});

	it('does not resurrect old data after the newest refresh fails', async () => {
		mocks.apiGet.mockResolvedValueOnce(summary());
		const { container } = render(Page);
		await snapshot(container);
		const older = deferred();
		const newer = deferred();
		mocks.apiGet.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
		const first = mocks.refresh!();
		const second = mocks.refresh!();
		newer.reject(new Error('newest failed'));
		await second;
		older.resolve(summary(7));
		await first;
		await tick();
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
		expect(container.querySelector('[data-resource-error]')).not.toBeNull();
	});

	it.each(['success', 'failure'] as const)('ignores late %s after unmount and unsubscribes owners', async outcome => {
		const pending = deferred();
		mocks.apiGet.mockReturnValueOnce(pending.promise);
		const { container, unmount } = render(Page);
		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledTimes(1));
		unmount();
		if (outcome === 'success') pending.resolve(summary());
		else pending.reject(new Error('late failure'));
		await tick();
		auth.set(identity({ token: 'new-token' }));
		projectSwitching.set(true);
		projectSwitching.set(false);
		await mocks.refresh!();
		await tick();
		expect(mocks.apiGet).toHaveBeenCalledTimes(1);
		expect(container.querySelector('[data-resource-snapshot]')).toBeNull();
	});

	it.each(['token', 'userId', 'projectId'] as const)('does not fetch without %s', async field => {
		auth.set(identity({ [field]: null }));
		const { container } = render(Page);
		await tick();
		expect(container.querySelector('[data-resource-auth-gate]')).not.toBeNull();
		await mocks.refresh!();
		expect(mocks.apiGet).not.toHaveBeenCalled();
	});

	it('shows a membership-empty state without inventing resources', async () => {
		const response = summary(0);
		response.projects = [];
		mocks.apiGet.mockResolvedValueOnce(response);
		const { container } = render(Page);
		await snapshot(container);
		expect(screen.getByText(t('myResources.noProjects'))).toBeTruthy();
		expect(container.querySelector('[data-project-usage]')).toBeNull();
		expect(container.querySelector('[data-resource-item]')).toBeNull();
	});
});

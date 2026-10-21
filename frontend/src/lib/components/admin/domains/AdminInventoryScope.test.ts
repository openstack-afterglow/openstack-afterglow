import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import { auth } from '$lib/stores/auth';
import { adminInventoryScope, setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import { projectNames } from '$lib/stores/projectNames';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import Harness from './_AdminSubnetScopeHarness.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), prefetch: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', async () => ({ api: mocks, ...(await vi.importActual<{ ApiError: typeof ApiError }>('$lib/api/errors')) }));
const initial = get(auth);
const projects = [
	{ id: 'project-a', name: 'Project Alpha', domain_id: 'domain-a' },
	{ id: 'project-b', name: 'Project Beta', domain_id: 'domain-b' },
];
interface SubnetFixture { id: string; name: string; network_id: string; cidr: string; gateway_ip: string | null; project_id: string }
const subnet = (id: string, project_id = 'project-a'): SubnetFixture => ({ id, name: id, network_id: `network-${id}`, cidr: '10.0.0.0/24', gateway_ip: '10.0.0.1', project_id });
function metadata(path: string) {
	if (path === '/api/v1/admin/domains') return { items: [{ id: 'domain-a', name: 'Domain Alpha', enabled: true }, { id: 'domain-b', name: 'Domain Beta', enabled: true }] };
	if (path === '/api/v1/admin/projects/names') return projects;
	return null;
}
async function choose(label: 'Domain' | 'Project', name: RegExp) {
	await waitFor(() => expect((screen.getByRole('button', { name: label }) as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.click(screen.getByRole('button', { name: label }));
	await fireEvent.click(screen.getByRole('option', { name }));
}
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set({ ...initial, token: 'operator-token', sessionId: 'operator-session', userId: 'operator', projectId: 'operator-project', domainId: 'operator-home', isSystemAdmin: true });
	projectNames.invalidate(); setAdminInventoryScope('', '');
	mocks.get.mockImplementation((path: string) => Promise.resolve(metadata(path) ?? [subnet('initial-row')]));
});
afterEach(() => { cleanup(); auth.set(initial); projectNames.invalidate(); initLocale('ko'); });

describe('administrator independent inventory scope', () => {
	it('defaults to all domains, filters dependent projects, preserves workspace and resets pagination and stale rows', async () => {
		const pending = Promise.withResolvers<SubnetFixture[]>();
		mocks.get.mockImplementation((path: string) => {
			const value = metadata(path); if (value) return Promise.resolve(value);
			if (path.includes('domain_id=domain-a')) return pending.promise;
			if (path.includes('domain_id=domain-b')) return Promise.resolve([subnet('beta-row', 'project-b')]);
			return Promise.resolve(Array.from({ length: 21 }, (_, i) => subnet(`initial-${i}`)));
		});
		render(Harness);
		await screen.findByText('initial-0');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/all-subnets', 'operator-token', 'operator-project');
		await fireEvent.click(screen.getByRole('button', { name: /^Next/ }));
		await screen.findByText('initial-20');
		await choose('Domain', /Domain Alpha/);
		expect(screen.queryByText('initial-20')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Project' }));
		expect(screen.getByRole('option', { name: /Project Alpha/ })).toBeTruthy();
		expect(screen.queryByRole('option', { name: /Project Beta/ })).toBeNull();
		await fireEvent.click(screen.getByRole('option', { name: /Project Alpha/ }));
		expect(get(adminInventoryScope).projectId).toBe('project-a');
		await choose('Domain', /Domain Beta/);
		expect(get(adminInventoryScope).projectId).toBe('');
		await screen.findByText('beta-row');
		expect(screen.getByText('1 / 1')).toBeTruthy();
		pending.resolve([subnet('late-alpha-row')]);
		await tick(); await Promise.resolve(); await tick();
		await waitFor(() => expect(screen.queryByText('late-alpha-row')).toBeNull());
		expect(get(auth).projectId).toBe('operator-project');
		expect(get(auth).domainId).toBe('operator-home');
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('fences A→B→A reads and auth transitions while keeping selected filters independent of the active project', async () => {
		const oldA = Promise.withResolvers<SubnetFixture[]>();
		let alphaRequests = 0;
		mocks.get.mockImplementation((path: string) => {
			const value = metadata(path); if (value) return Promise.resolve(value);
			if (path.includes('domain_id=domain-a')) return ++alphaRequests === 1 ? oldA.promise : Promise.resolve([subnet('fresh-alpha-row')]);
			return Promise.resolve([subnet('baseline-row')]);
		});
		render(Harness); await screen.findByText('baseline-row');
		await choose('Domain', /Domain Alpha/);
		await choose('Domain', /Domain Beta/);
		await choose('Domain', /Domain Alpha/);
		await screen.findByText('fresh-alpha-row');
		oldA.resolve([subnet('stale-alpha-row')]);
		await tick(); await Promise.resolve(); await tick();
		await waitFor(() => expect(screen.queryByText('stale-alpha-row')).toBeNull());
		auth.update(state => ({ ...state, sessionId: 'other-session', userId: 'other-operator', token: 'other-token' }));
		await screen.findByText('baseline-row');
		expect(screen.queryByText('fresh-alpha-row')).toBeNull();
		expect(get(adminInventoryScope).domainId).toBe('');
	});

	it('shows native inventory denial and metadata denial instead of a successful empty list', async () => {
		mocks.get.mockImplementation((path: string) => path === '/api/v1/admin/projects/names'
			? Promise.reject(new ApiError(403, 'project_directory_native_denied'))
			: path === '/api/v1/admin/all-subnets' ? Promise.reject(new ApiError(403, 'subnet_native_denied')) : Promise.resolve(metadata(path)));
		render(Harness);
		await screen.findByText('subnet_native_denied');
		await screen.findByText('project_directory_native_denied');
		expect(screen.queryByText('No subnets')).toBeNull();
		expect(get(auth).isSystemAdmin).toBe(true);
	});

	it('explicit metadata refresh bypasses both directory reads without clearing a valid selected filter', async () => {
		render(Harness); await screen.findByText('initial-row');
		await choose('Domain', /Domain Alpha/);
		await choose('Project', /Project Alpha/);
		const refresh = screen.getAllByRole('button', { name: 'Refresh' })[0];
		await fireEvent.click(refresh);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/projects/names', 'operator-token', 'operator-project', { refresh: true }));
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains', 'operator-token', 'operator-project', { refresh: true });
		expect(get(adminInventoryScope).projectId).toBe('project-a');
	});
});

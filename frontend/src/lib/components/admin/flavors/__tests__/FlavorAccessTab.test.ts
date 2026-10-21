import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	put: vi.fn(),
	post: vi.fn(),
	delete: vi.fn(),
	listDomains: vi.fn(),
	metadata: vi.fn(),
	success: vi.fn(),
	error: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		put: mocks.put,
		post: mocks.post,
		delete: mocks.delete,
	},
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/toast', () => ({
	toast: { success: mocks.success, error: mocks.error },
}));
vi.mock('$lib/api/domains', () => ({ domainsApi: { list: mocks.listDomains } }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { loadMetadata: mocks.metadata } }));

import FlavorAccessTab from '../FlavorAccessTab.svelte';
import { t as td } from '$lib/i18n/ns/domain-admin';

const flavor = () => ({
	id: 'fl-service',
	name: 'amphora',
	vcpus: 1,
	ram: 1024,
	disk: 5,
	is_public: true,
	description: null,
	extra_specs: { 'afterglow:frontend_visible': 'false' },
	frontend_visible: false,
	is_gpu: false,
	gpu_count: 0,
});

describe('FlavorAccessTab frontend visibility', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.get.mockResolvedValue([]);
		mocks.listDomains.mockResolvedValue({ items: [{ id: 'a', name: 'Domain A' }, { id: 'b', name: 'Domain B' }] });
		mocks.metadata.mockResolvedValue({ failed: false, projects: [{ id: 'pa', name: 'Project A', domain_id: 'a' }, { id: 'pb', name: 'Project B', domain_id: 'b' }] });
		mocks.put.mockResolvedValue({ flavor_id: 'fl-service', frontend_visible: true });
		auth.set({
			token: 'token',
			refreshToken: null,
			accessExpiresAt: null,
			userId: 'admin',
			username: 'admin',
			projectId: 'admin-project',
			projectName: 'Admin',
			availableProjects: [],
			roles: ['admin'],
			isSystemAdmin: true,
			federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false,
		});
	});
	afterEach(cleanup);

	it('shows the effective hidden state and enables the flavor without changing Nova access', async () => {
		const current = flavor();
		render(FlavorAccessTab, { flavor: current });

		expect(screen.getByRole('button', { name: '사용자에게 숨김' }).getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(screen.getByRole('button', { name: '사용자에게 노출' }));

		await waitFor(() => expect(mocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/flavors/fl-service/frontend-visibility',
			{ visible: true },
			'token',
			'admin-project',
		));
		expect(current.frontend_visible).toBe(true);
		expect(current.extra_specs['afterglow:frontend_visible']).toBe('true');
	});

	it('announces visibility saving only until the actual request settles', async () => {
		const request = Promise.withResolvers<{ flavor_id: string; frontend_visible: boolean }>();
		mocks.put.mockReturnValueOnce(request.promise);
		render(FlavorAccessTab, { flavor: flavor() });

		await fireEvent.click(screen.getByRole('button', { name: '사용자에게 노출' }));
		expect(screen.getByRole('status').textContent).toContain('노출 설정 저장 중…');
		expect((screen.getByRole('button', { name: '사용자에게 노출' }) as HTMLButtonElement).disabled).toBe(true);

		request.resolve({ flavor_id: 'fl-service', frontend_visible: true });
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect(screen.getByRole('button', { name: '사용자에게 노출' }).getAttribute('aria-pressed')).toBe('true');
	});

	it('stops announcing a failed visibility write and preserves the effective setting', async () => {
		const request = Promise.withResolvers<never>();
		mocks.put.mockReturnValueOnce(request.promise);
		render(FlavorAccessTab, { flavor: flavor() });

		await fireEvent.click(screen.getByRole('button', { name: '사용자에게 노출' }));
		expect(screen.getByRole('status').textContent).toContain('노출 설정 저장 중…');
		request.reject(new Error('write failed'));
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect(screen.getByRole('button', { name: '사용자에게 숨김' }).getAttribute('aria-pressed')).toBe('true');
		expect(mocks.error).toHaveBeenCalled();
	});
	it('narrows exact project choices by domain and clears a previous project choice', async () => {
		render(FlavorAccessTab, { flavor: { ...flavor(), is_public: false } });
		const project = await screen.findByRole('button', { name: td('scope.project') });
		await waitFor(() => expect((project as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(project);
		await fireEvent.click(await screen.findByRole('option', { name: /Project A/ }));
		await fireEvent.click(screen.getByRole('button', { name: td('scope.domain') }));
		await fireEvent.click(await screen.findByRole('option', { name: /Domain B/ }));
		expect((screen.getByRole('button', { name: '추가' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(project);
		expect(screen.queryByRole('option', { name: /Project A/ })).toBeNull();
		await fireEvent.click(await screen.findByRole('option', { name: /Project B/ }));
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/flavors/fl-service/access', { project_id: 'pb' }, 'token', 'admin-project');
	});
	it('does not replace a current directory with a late response from a previous authority', async () => {
		const old = Promise.withResolvers<unknown>(); mocks.metadata.mockReturnValueOnce(old.promise);
		render(FlavorAccessTab, { flavor: { ...flavor(), is_public: false } });
		await waitFor(() => expect(mocks.metadata).toHaveBeenCalledTimes(1));
		auth.update(state => ({ ...state, token: 'new-token' }));
		await waitFor(() => expect(mocks.metadata).toHaveBeenCalledTimes(2));
		old.resolve({ failed: false, projects: [{ id: 'stale', name: 'Stale Project', domain_id: 'a' }] });
		await fireEvent.click(screen.getByRole('button', { name: td('scope.project') }));
		expect(screen.queryByRole('option', { name: /Stale Project/ })).toBeNull();
		expect(await screen.findByRole('option', { name: /Project A/ })).toBeTruthy();
	});
	it('keeps directory lookup failure distinct from an empty successful project directory', async () => {
		mocks.metadata.mockResolvedValue({ failed: true, projects: [] });
		render(FlavorAccessTab, { flavor: { ...flavor(), is_public: false } });
		await screen.findByText(td('scope.projectsFailed'));
		expect((screen.getByRole('button', { name: td('scope.project') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it('does not publish a completed visibility write after caller-project ABA', async () => {
		const pending = Promise.withResolvers<unknown>(); mocks.put.mockReturnValueOnce(pending.promise);
		const current = flavor(); render(FlavorAccessTab, { flavor: current });
		await fireEvent.click(screen.getByRole('button', { name: '사용자에게 노출' }));
		auth.update(state => ({ ...state, projectId: 'other' })); auth.update(state => ({ ...state, projectId: 'admin-project' }));
		pending.resolve({});
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect(current.frontend_visible).toBe(false);
		expect(mocks.success).not.toHaveBeenCalled();
	});
});

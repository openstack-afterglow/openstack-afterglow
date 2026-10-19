import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/domain-admin';
import SystemAdminGrantModal from '../SystemAdminGrantModal.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));

const domains = [
	{ id: 'domain-a', name: 'Tenant A', enabled: true },
	{ id: 'domain-b', name: 'Tenant B', enabled: true },
];
const alice = { id: 'alice', name: 'Alice', email: 'alice@example.test', enabled: true };
const bob = { id: 'bob', name: 'Bob', email: 'bob@example.test', enabled: true };

async function selectDomain(name: string) {
	const selector = await screen.findByRole('button', { name: t('scope.domain') });
	await waitFor(() => expect((selector as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.click(selector);
	await fireEvent.click(await screen.findByRole('option', { name: new RegExp(name) }));
}

beforeEach(() => {
	vi.resetAllMocks();
	initLocale('ko');
	auth.update(state => ({ ...state, token: 'system-token', projectId: 'operator-project', isSystemAdmin: true }));
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/admin/domains') return { items: domains };
		return { items: [alice], next_marker: null };
	});
	mocks.post.mockResolvedValue({ status: 'granted' });
});
afterEach(cleanup);

describe('system administrator grants across explicit domains', () => {
	it('waits for explicit domain selection and preserves the native grant request body', async () => {
		const onGranted = vi.fn();
		const onClose = vi.fn();
		render(SystemAdminGrantModal, { onGranted, onClose });
		await screen.findByText(t('scope.required'));
		expect(mocks.get).toHaveBeenCalledTimes(1);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains', 'system-token', 'operator-project');
		await selectDomain('Tenant A');
		expect(await screen.findByText('Alice')).toBeTruthy();
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/users?limit=100&domain_id=domain-a', 'system-token', 'operator-project');
		await fireEvent.click(screen.getByRole('button', { name: t('systemGrant.grant') }));
		await waitFor(() => expect(onGranted).toHaveBeenCalledOnce());
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/identity/system-roles/grant', { user_id: 'alice' }, 'system-token', 'operator-project');
		expect(onClose).toHaveBeenCalledOnce();
	});

	it('renders native domain and user list failures rather than a misleading empty result', async () => {
		mocks.get.mockRejectedValueOnce(new Error('native domains forbidden'));
		render(SystemAdminGrantModal, { onGranted: vi.fn(), onClose: vi.fn() });
		expect(await screen.findByText('native domains forbidden')).toBeTruthy();
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/domains') return { items: domains };
			throw new Error('422 native domain filter required');
		});
		await fireEvent.click(screen.getByRole('button', { name: t('actions.refresh') }));
		await selectDomain('Tenant A');
		expect(await screen.findByText('422 native domain filter required')).toBeTruthy();
		expect(screen.queryByText('사용자 없음')).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('marks a partial user directory until all explicitly requested pages are loaded', async () => {
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/domains') return { items: domains };
			const params = new URL(path, 'https://afterglow.test').searchParams;
			expect(params.get('domain_id')).toBe('domain-a');
			if (params.get('marker')) return { items: [bob], next_marker: null };
			return { items: [alice], next_marker: 'next /+' };
		});
		render(SystemAdminGrantModal, { onGranted: vi.fn(), onClose: vi.fn() });
		await selectDomain('Tenant A');
		expect(await screen.findByText(t('systemGrant.partial'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('systemGrant.loadMore') }));
		expect(await screen.findByText('Bob')).toBeTruthy();
		expect(screen.getByText('Alice')).toBeTruthy();
		expect(screen.queryByText(t('systemGrant.partial'))).toBeNull();
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/users?limit=100&marker=next+%2F%2B&domain_id=domain-a', 'system-token', 'operator-project');
	});

	it('discards a late user list from a previously selected domain', async () => {
		const pending = Promise.withResolvers<{ items: typeof alice[]; next_marker: null }>();
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/domains') return Promise.resolve({ items: domains });
			if (path.includes('domain-a')) return pending.promise;
			return Promise.resolve({ items: [bob], next_marker: null });
		});
		render(SystemAdminGrantModal, { onGranted: vi.fn(), onClose: vi.fn() });
		await selectDomain('Tenant A');
		await selectDomain('Tenant B');
		expect(await screen.findByText('Bob')).toBeTruthy();
		pending.resolve({ items: [alice], next_marker: null });
		await tick();
		expect(screen.queryByText('Alice')).toBeNull();
		expect(screen.getByText('Bob')).toBeTruthy();
	});

	it.each(['token', 'projectId'] as const)('clears domain and user selection when %s changes and rejects stale user responses', async field => {
		const pending = Promise.withResolvers<{ items: typeof alice[]; next_marker: null }>();
		mocks.get.mockImplementation((path: string) => path === '/api/v1/admin/domains'
			? Promise.resolve({ items: domains }) : pending.promise);
		render(SystemAdminGrantModal, { onGranted: vi.fn(), onClose: vi.fn() });
		await selectDomain('Tenant A');
		auth.update(state => ({ ...state, [field]: 'changed-authority' }));
		await screen.findByText(t('scope.required'));
		pending.resolve({ items: [alice], next_marker: null });
		await tick();
		expect(screen.queryByText('Alice')).toBeNull();
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/domains', field === 'token' ? 'changed-authority' : 'system-token', field === 'projectId' ? 'changed-authority' : 'operator-project');
	});

	it('keeps a native grant denial visible without publishing success', async () => {
		mocks.post.mockRejectedValue(new Error('native system grant forbidden'));
		const onGranted = vi.fn();
		const onClose = vi.fn();
		render(SystemAdminGrantModal, { onGranted, onClose });
		await selectDomain('Tenant A');
		await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: t('systemGrant.grant') }));
		expect(await screen.findByText('native system grant forbidden')).toBeTruthy();
		expect(onGranted).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
	});

	it.each(['domain', 'token', 'projectId'] as const)('discards a late grant completion after %s changes', async field => {
		const pending = Promise.withResolvers<{ status: string }>();
		mocks.post.mockReturnValue(pending.promise);
		const onGranted = vi.fn();
		const onClose = vi.fn();
		render(SystemAdminGrantModal, { onGranted, onClose });
		await selectDomain('Tenant A');
		await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: t('systemGrant.grant') }));
		if (field === 'domain') await selectDomain('Tenant B');
		else {
			auth.update(state => ({ ...state, [field]: 'changed-authority' }));
			await screen.findByText(t('scope.required'));
		}
		pending.resolve({ status: 'granted' });
		await tick();
		expect(onGranted).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
	});
});

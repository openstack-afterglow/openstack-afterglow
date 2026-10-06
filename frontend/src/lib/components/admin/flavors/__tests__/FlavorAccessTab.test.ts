import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	put: vi.fn(),
	post: vi.fn(),
	delete: vi.fn(),
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

import FlavorAccessTab from '../FlavorAccessTab.svelte';

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
			federated: false,
		});
	});

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
});

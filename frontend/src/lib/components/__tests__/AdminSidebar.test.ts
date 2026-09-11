import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ url: new URL('http://localhost/admin/chat/quotas'), data: {} }) };
});

import { auth } from '$lib/stores/auth';
import { initSiteConfig, siteConfig } from '$lib/config/site';
import AdminSidebar from '../AdminSidebar.svelte';

describe('AdminSidebar chat service entries', () => {
	beforeEach(() => {
		auth.set({
			token: 'token', refreshToken: null, accessExpiresAt: null,
			userId: 'u-admin', username: 'admin', projectId: 'project-1', projectName: 'Project',
			availableProjects: [], roles: ['admin'], isSystemAdmin: true, federated: false
		});
	});

	afterEach(() => {
		cleanup();
		siteConfig.update((current) => ({ ...current, services: { ...current.services, chat: false } }));
	});

	it('exposes the user quota page when the chat service is enabled', () => {
		initSiteConfig({ services: { chat: true } });
		render(AdminSidebar);

		const link = screen.getByRole('link', { name: '사용자 쿼터' });
		expect(link.getAttribute('href')).toBe('/admin/chat/quotas');
	});

	it('hides chat administration entries when the chat service is disabled', () => {
		initSiteConfig({ services: { chat: false } });
		render(AdminSidebar);

		expect(screen.queryByRole('link', { name: '사용자 쿼터' })).toBeNull();
		expect(screen.queryByRole('link', { name: '채팅 통계' })).toBeNull();
	});
});

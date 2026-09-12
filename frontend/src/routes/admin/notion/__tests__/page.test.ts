import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as ClientModule from '$lib/api/client';

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }));

vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe(run: (value: { token: string; projectId: string }) => void) {
			run({ token: 'token', projectId: 'admin-project' });
			return () => {};
		}
	}
}));
vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof ClientModule>();
	return { ...actual, api: apiMocks };
});
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn() } }));

import NotionAdminPage from '../+page.svelte';

describe('Notion admin global synchronization gate', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		apiMocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/notion/targets') return Promise.resolve([]);
			if (path === '/api/v1/admin/runtime-settings') {
				return Promise.resolve([{ key: 'notion.sync_enabled', value: false }]);
			}
			return Promise.resolve([]);
		});
		apiMocks.put.mockResolvedValue({ key: 'notion.sync_enabled', value: true });
	});

	it('loads and updates the persisted global synchronization gate', async () => {
		render(NotionAdminPage);
		const toggle = await screen.findByRole('button', { name: '동기화 꺼짐' });
		await fireEvent.click(toggle);

		await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/runtime-settings/notion.sync_enabled',
			{ value: true },
			'token',
			'admin-project'
		));
		expect(await screen.findByRole('button', { name: '동기화 켜짐' })).toBeTruthy();
	});
});

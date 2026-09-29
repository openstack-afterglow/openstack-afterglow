import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import type { Volume } from '$lib/types/volume';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), prefetch: vi.fn() }));

vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		status: number;
		constructor(status: number, message: string) {
			super(message);
			this.status = status;
		}
	}
	return { ApiError, api: mocks, memoryCache: new Map() };
});
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project-a', isSystemAdmin: false }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));
// vi.mock factories are hoisted above static imports, so the store module is loaded inside.
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	return { page: writable({ params: { id: 'vol-1' }, url: new URL('http://localhost/dashboard/volumes/vol-1'), data: {} }) };
});

import { ApiError } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import ListPage from '../+page.svelte';
import DetailRoute from '../[id]/+page.svelte';

const projectAuth = auth as unknown as Writable<{ token: string; projectId: string | null; isSystemAdmin: boolean }>;
let serverVolume: Volume;

function volumeWithName(name: string): Volume {
	return {
		id: 'vol-1',
		name,
		status: 'in-use',
		size: 20,
		volume_type: 'ssd',
		attachments: [{ server_id: 'server-a', device: '/dev/vdb' }],
	};
}

beforeAll(() => {
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	window.matchMedia ??= ((query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addEventListener: () => {},
		removeEventListener: () => {},
		addListener: () => {},
		removeListener: () => {},
		dispatchEvent: () => false,
	})) as unknown as typeof window.matchMedia;
});

beforeEach(() => {
	vi.clearAllMocks();
	projectAuth.set({ token: 'token', projectId: 'project-a', isSystemAdmin: false });
	serverVolume = volumeWithName('data-disk');
	mocks.get.mockImplementation((path: string) => {
		if (path === '/api/v1/volumes') return Promise.resolve([serverVolume]);
		if (path === '/api/v1/volumes/vol-1') return Promise.resolve(serverVolume);
		if (path === '/api/v1/instances/server-a') return Promise.resolve({ id: 'server-a', name: 'web-01' });
		if (path === '/api/v1/dashboard/quotas') return Promise.reject(new ApiError(503, 'unavailable'));
		return Promise.resolve([]);
	});
	mocks.post.mockResolvedValue([]);
	mocks.patch.mockImplementation((_path: string, body: { name: string }) => {
		serverVolume = volumeWithName(body.name);
		return Promise.resolve(serverVolume);
	});
});

describe('volume detail parity and list rename', () => {
	it('renders the direct route through the shared detail surface with the attached instance name', async () => {
		render(DetailRoute);

		expect(await screen.findByRole('heading', { name: 'data-disk' })).toBeTruthy();
		expect(screen.getByRole('link', { name: '← 볼륨 목록' }).getAttribute('href')).toBe('/dashboard/volumes');
		const attachments = screen.getByRole('list', { name: '연결된 인스턴스' });
		expect(await within(attachments).findByRole('link', { name: 'web-01' })).toBeTruthy();
		expect(within(attachments).getByText('server-a')).toBeTruthy();
		expect(screen.getByText('ssd')).toBeTruthy();
		expect(screen.getByRole('button', { name: '이름 변경' })).toBeTruthy();
	});

	it('renames from the list action menu and updates both the row and the open detail panel', async () => {
		render(ListPage);

		await fireEvent.click(await screen.findByRole('button', { name: /^data-disk\s*vol-1/ }));
		const heading = await screen.findByRole('heading', { name: 'data-disk' });
		expect(heading).toBeTruthy();
		expect(await screen.findByRole('link', { name: 'web-01' })).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: 'data-disk 볼륨 작업' }));
		const menu = await screen.findByRole('group', { name: 'data-disk 볼륨 작업 옵션' });
		await fireEvent.click(within(menu).getByRole('button', { name: '이름 변경' }));

		const dialog = await screen.findByRole('dialog', { name: '볼륨 이름 변경' });
		const input = within(dialog).getByRole('textbox');
		await fireEvent.input(input, { target: { value: 'renamed-disk' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));

		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/volumes/vol-1', { name: 'renamed-disk' }, 'token', 'project-a');
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '볼륨 이름 변경' })).toBeNull());
		expect(await screen.findByRole('button', { name: 'renamed-disk 볼륨 작업' })).toBeTruthy();
		expect(await screen.findByRole('heading', { name: 'renamed-disk' })).toBeTruthy();
		expect(screen.queryByText('data-disk')).toBeNull();
	});

	it('shows the rename error in the list dialog and leaves the row unchanged', async () => {
		mocks.patch.mockRejectedValue(new ApiError(403, '볼륨을 변경할 권한이 없습니다'));
		render(ListPage);

		await fireEvent.click(await screen.findByRole('button', { name: 'data-disk 볼륨 작업' }));
		const menu = await screen.findByRole('group', { name: 'data-disk 볼륨 작업 옵션' });
		await fireEvent.click(within(menu).getByRole('button', { name: '이름 변경' }));
		const dialog = await screen.findByRole('dialog', { name: '볼륨 이름 변경' });
		await fireEvent.input(within(dialog).getByRole('textbox'), { target: { value: 'renamed-disk' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));

		expect(await within(dialog).findByText('볼륨을 변경할 권한이 없습니다')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'data-disk 볼륨 작업' })).toBeTruthy();
	});
});

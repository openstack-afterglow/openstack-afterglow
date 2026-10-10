import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type { FileStorage } from '$lib/types/fileStorage';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	delete: vi.fn(),
	autoRefreshTick: null as null | (() => unknown),
	confirmDialog: vi.fn(),
	setPage: null as null | ((id: string) => void),
}));

vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		status = 500;
	}
	return { ApiError, api: { get: mocks.get, post: mocks.post, delete: mocks.delete }, memoryCache: new Map() };
});
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project-a' }),
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirmDialog }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (tick: () => unknown) => {
		mocks.autoRefreshTick = tick;
		return { active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] };
	},
}));
// vi.mock factories are hoisted above static imports, so the store module is loaded inside.
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	const page = writable({ params: { id: 'share-1' }, url: new URL('http://localhost/dashboard/file-storage/share-1'), data: {} });
	mocks.setPage = (id) => page.set({ params: { id }, url: new URL(`http://localhost/dashboard/file-storage/${id}`), data: {} });
	return { page };
});

import Page from '../+page.svelte';

const share: FileStorage = {
	id: 'share-1',
	name: 'data-share',
	status: 'available',
	size: 10,
	share_proto: 'NFS',
	export_locations: [],
	metadata: {},
	project_id: 'project-a',
	created_at: null,
	is_public: false,
	library_name: null,
	library_version: null,
	built_at: null,
	progress: null,
	user_id: null,
	user_name: null,
	access_rules_status: null,
	host: null,
	availability_zone: null,
	share_type_name: null,
	share_network_id: null,
	export_location_details: [],
};

const rule = { id: 'rule-1', access_to: '10.0.0.0/24', access_level: 'ro', state: 'active', access_key: null };

afterEach(cleanup);

describe('file storage detail auto refresh', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.autoRefreshTick = null;
		mocks.setPage!('share-1');
		mocks.confirmDialog.mockResolvedValue(true);
	});

	it('keeps the loaded detail and access rules on screen while a background refresh is in flight', async () => {
		let releaseRefresh: (value: FileStorage) => void = () => {};
		let shareReads = 0;
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/file-storage/share-1') {
				shareReads += 1;
				if (shareReads === 1) return Promise.resolve(share);
				return new Promise<FileStorage>((resolve) => { releaseRefresh = resolve; });
			}
			if (path === '/api/v1/file-storage/share-1/access-rules') return Promise.resolve([rule]);
			return Promise.resolve([]);
		});

		render(Page);
		await screen.findByRole('heading', { name: 'data-share' });
		await screen.findByText('10.0.0.0/24');

		void mocks.autoRefreshTick?.();
		await waitFor(() => expect(shareReads).toBe(2));
		await tick();
		const refreshButton = screen.getByTitle('로딩 중…') as HTMLButtonElement;
		expect(refreshButton.disabled).toBe(true);

		// The refresh must not swap the page back to its first-load placeholder.
		expect(screen.getByRole('heading', { name: 'data-share' })).toBeTruthy();
		expect(screen.getByText('10.0.0.0/24')).toBeTruthy();
		expect(screen.queryByRole('status', { name: '불러오는 중' })).toBeNull();
		expect(screen.queryByText('로딩 중...')).toBeNull();

		releaseRefresh({ ...share, name: 'renamed-share' });
		await screen.findByRole('heading', { name: 'renamed-share' });
		await waitFor(() => expect((screen.getByTitle('지금 새로고침') as HTMLButtonElement).disabled).toBe(false));
	});

	it('hides previous share keys and cancels its pending revoke after route reuse', async () => {
		let releaseRules!: (value: typeof rule[]) => void;
		const pendingRules = new Promise<typeof rule[]>((resolve) => { releaseRules = resolve; });
		let confirm!: (value: boolean) => void;
		mocks.confirmDialog.mockReturnValue(new Promise<boolean>((resolve) => { confirm = resolve; }));
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/file-storage/share-1') return Promise.resolve({ ...share, share_proto: 'CEPHFS' });
			if (path === '/api/v1/file-storage/share-1/access-rules') return Promise.resolve([
				{ ...rule, access_to: 'alpha-client', access_key: 'alpha-secret-key' },
			]);
			if (path === '/api/v1/file-storage/share-2') return Promise.resolve({ ...share, id: 'share-2', name: 'beta-share', share_proto: 'CEPHFS' });
			if (path === '/api/v1/file-storage/share-2/access-rules') return pendingRules;
			return Promise.resolve([]);
		});
		render(Page);
		const row = (await screen.findByText('alpha-client')).closest('tr')!;
		await screen.findByText(/^alpha-secret-key/);
		await fireEvent.click(within(row).getByRole('button', { name: '삭제' }));
		mocks.setPage!('share-2');
		await screen.findByRole('heading', { name: 'beta-share' });
		expect(screen.queryByText('alpha-client')).toBeNull();
		expect(screen.queryByText(/^alpha-secret-key/)).toBeNull();
		confirm(true);
		await tick();
		expect(mocks.delete).not.toHaveBeenCalled();
		releaseRules([{ ...rule, id: 'rule-2', access_to: 'beta-client', access_key: null }]);
		await screen.findByText('beta-client');
		expect(screen.queryByText('alpha-client')).toBeNull();
	});
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type { FileStorage } from '$lib/types/fileStorage';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	delete: vi.fn(),
	autoRefreshTick: null as null | (() => unknown),
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
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (tick: () => unknown) => {
		mocks.autoRefreshTick = tick;
		return { active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] };
	},
}));
// vi.mock factories are hoisted above static imports, so the store module is loaded inside.
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	return { page: writable({ params: { id: 'share-1' }, url: new URL('http://localhost/dashboard/file-storage/share-1'), data: {} }) };
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

describe('file storage detail auto refresh', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.autoRefreshTick = null;
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
});

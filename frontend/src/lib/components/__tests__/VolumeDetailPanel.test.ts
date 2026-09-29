import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable, type Writable } from 'svelte/store';
import type { Volume } from '$lib/types/volume';

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() }));

vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		status: number;
		constructor(status: number, message: string) {
			super(message);
			this.status = status;
		}
	}
	return { ApiError, api: mocks };
});
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project-a' }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));

import { ApiError } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import VolumeDetailPanel from '../VolumeDetailPanel.svelte';

const projectAuth = auth as unknown as Writable<{ token: string; projectId: string | null }>;

const attachedVolume = (overrides: Partial<Volume> = {}): Volume => ({
	id: 'vol-1',
	name: 'data-disk',
	status: 'in-use',
	size: 20,
	volume_type: 'ssd',
	attachments: [
		{ server_id: 'server-a', device: '/dev/vdb' },
		{ server_id: 'server-a', device: '/dev/vdc' },
		{ server_id: 'server-gone', device: '/dev/vdd' },
	],
	...overrides,
});

function routeGets(volume: Volume, instanceNames: Record<string, string>) {
	mocks.get.mockImplementation((path: string) => {
		if (path === `/api/v1/volumes/${volume.id}`) return Promise.resolve(volume);
		if (path.startsWith('/api/v1/volume-snapshots')) return Promise.resolve([]);
		const match = path.match(/^\/api\/v1\/instances\/(.+)$/);
		if (match) {
			const name = instanceNames[decodeURIComponent(match[1])];
			return name ? Promise.resolve({ id: match[1], name }) : Promise.reject(new ApiError(404, 'not found'));
		}
		return Promise.reject(new Error(`unexpected GET ${path}`));
	});
}

function instanceGetCount(serverId: string): number {
	return mocks.get.mock.calls.filter(([path]) => path === `/api/v1/instances/${serverId}`).length;
}

describe('VolumeDetailPanel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		projectAuth.set({ token: 'token', projectId: 'project-a' });
	});

	it('shows the attached instance name with its UUID and labels unreadable instances instead of guessing', async () => {
		routeGets(attachedVolume(), { 'server-a': 'web-01' });
		render(VolumeDetailPanel, { props: { volumeId: 'vol-1' } });

		const list = await screen.findByRole('list', { name: '연결된 인스턴스' });
		const link = await within(list).findAllByRole('link', { name: 'web-01' });
		expect(link[0].getAttribute('href')).toBe('/dashboard/instances/server-a');
		expect(within(list).getAllByText('server-a')).toHaveLength(2);
		expect(await within(list).findByText('인스턴스 이름을 확인할 수 없음')).toBeTruthy();
		expect(within(list).getByText('server-gone')).toBeTruthy();
		// Both attachments of the same server resolve through a single project-scoped request.
		expect(instanceGetCount('server-a')).toBe(1);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/instances/server-a', 'token', 'project-a');
	});

	it('keeps loaded details visible when a background refresh fails', async () => {
		const volume = attachedVolume({ attachments: [{ server_id: 'server-a' }] });
		routeGets(volume, { 'server-a': 'web-01' });
		const view = render(VolumeDetailPanel, { props: { volumeId: 'vol-1', refreshKey: 0 } });
		await screen.findByRole('link', { name: 'web-01' });

		mocks.get.mockImplementation((path: string) => path.startsWith('/api/v1/volume-snapshots')
			? Promise.resolve([])
			: Promise.reject(new ApiError(503, '볼륨 조회 실패')));
		await view.rerender({ volumeId: 'vol-1', refreshKey: 1 });

		await screen.findByText('볼륨 조회 실패');
		expect(screen.getByRole('heading', { name: 'data-disk' })).toBeTruthy();
		expect(screen.getByRole('link', { name: 'web-01' })).toBeTruthy();
	});

	it('ignores an older refresh that resolves after a newer volume response', async () => {
		const old = Promise.withResolvers<Volume>();
		let volumeReads = 0;
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/volumes/vol-1') {
				volumeReads += 1;
				if (volumeReads === 2) return old.promise;
				return Promise.resolve(attachedVolume({ name: volumeReads === 1 ? 'initial' : 'current', attachments: [] }));
			}
			if (path.startsWith('/api/v1/volume-snapshots')) return Promise.resolve([]);
			return Promise.reject(new Error(`unexpected GET ${path}`));
		});
		const view = render(VolumeDetailPanel, { props: { volumeId: 'vol-1', refreshKey: 0 } });
		await screen.findByRole('heading', { name: 'initial' });
		await view.rerender({ volumeId: 'vol-1', refreshKey: 1 });
		await waitFor(() => expect(volumeReads).toBe(2));
		await view.rerender({ volumeId: 'vol-1', refreshKey: 2 });
		await screen.findByRole('heading', { name: 'current' });

		old.resolve(attachedVolume({ name: 'stale', attachments: [] }));
		await tick();
		expect(screen.getByRole('heading', { name: 'current' })).toBeTruthy();
		expect(screen.queryByRole('heading', { name: 'stale' })).toBeNull();
	});

	it('does not refetch resolved instance names on refresh', async () => {
		routeGets(attachedVolume(), { 'server-a': 'web-01' });
		const view = render(VolumeDetailPanel, { props: { volumeId: 'vol-1', refreshKey: 0 } });
		await screen.findAllByRole('link', { name: 'web-01' });

		await view.rerender({ volumeId: 'vol-1', refreshKey: 1 });
		await waitFor(() => expect(mocks.get.mock.calls.filter(([p]) => p === '/api/v1/volumes/vol-1').length).toBeGreaterThanOrEqual(2));
		expect(instanceGetCount('server-a')).toBe(1);
	});

	it('ignores an instance name that resolves after the project changed', async () => {
		const volume = attachedVolume({ attachments: [{ server_id: 'server-a' }] });
		const pendingName = Promise.withResolvers<{ id: string; name: string }>();
		mocks.get.mockImplementation((path: string, _token: string, projectId: string) => {
			if (path === '/api/v1/volumes/vol-1') return Promise.resolve(volume);
			if (path.startsWith('/api/v1/volume-snapshots')) return Promise.resolve([]);
			if (path === '/api/v1/instances/server-a') {
				return projectId === 'project-a' ? pendingName.promise : Promise.resolve({ id: 'server-a', name: 'project-b-vm' });
			}
			return Promise.reject(new Error(`unexpected GET ${path}`));
		});
		render(VolumeDetailPanel, { props: { volumeId: 'vol-1' } });
		await screen.findByText('이름 확인 중…');

		projectAuth.set({ token: 'token', projectId: 'project-b' });
		expect(await screen.findByRole('link', { name: 'project-b-vm' })).toBeTruthy();
		pendingName.resolve({ id: 'server-a', name: 'other-tenant-vm' });
		await tick();
		await tick();
		expect(screen.queryByText('other-tenant-vm')).toBeNull();
		expect(screen.getByRole('link', { name: 'project-b-vm' })).toBeTruthy();
	});

	it('renames an attached volume, blocks blank names, and reports the update', async () => {
		const volume = attachedVolume({ attachments: [{ server_id: 'server-a' }] });
		routeGets(volume, { 'server-a': 'web-01' });
		mocks.patch.mockResolvedValue({ ...volume, name: 'renamed-disk' });
		const onRenamed = vi.fn();
		render(VolumeDetailPanel, { props: { volumeId: 'vol-1', onRenamed } });

		await fireEvent.click(await screen.findByRole('button', { name: '이름 변경' }));
		const input = screen.getByRole('textbox');
		expect((input as HTMLInputElement).value).toBe('data-disk');
		await fireEvent.input(input, { target: { value: '   ' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));
		expect(screen.getByRole('alert').textContent).toContain('볼륨 이름을 입력하세요.');
		expect(mocks.patch).not.toHaveBeenCalled();

		await fireEvent.input(input, { target: { value: '  renamed-disk  ' } });
		routeGets({ ...volume, name: 'renamed-disk' }, { 'server-a': 'web-01' });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/volumes/vol-1', { name: 'renamed-disk' }, 'token', 'project-a');
		await waitFor(() => expect(screen.getByRole('heading', { name: 'renamed-disk' })).toBeTruthy());
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(onRenamed).toHaveBeenCalledWith(expect.objectContaining({ id: 'vol-1', name: 'renamed-disk' }));
	});

	it('keeps the dialog open with the server error when rename fails', async () => {
		routeGets(attachedVolume(), {});
		mocks.patch.mockRejectedValue(new ApiError(409, '볼륨 상태 때문에 이름을 변경할 수 없습니다'));
		const onRenamed = vi.fn();
		render(VolumeDetailPanel, { props: { volumeId: 'vol-1', onRenamed } });

		await fireEvent.click(await screen.findByRole('button', { name: '이름 변경' }));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'next-name' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		expect(await screen.findByText('볼륨 상태 때문에 이름을 변경할 수 없습니다')).toBeTruthy();
		expect(screen.getByRole('dialog')).toBeTruthy();
		expect(screen.getByRole('heading', { name: 'data-disk' })).toBeTruthy();
		expect(onRenamed).not.toHaveBeenCalled();
	});
});

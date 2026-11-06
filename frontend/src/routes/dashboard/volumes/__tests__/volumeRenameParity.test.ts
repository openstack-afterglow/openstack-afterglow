import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { get, writable, type Writable } from 'svelte/store';
import type { Volume } from '$lib/types/volume';
import { captureFlowExperience, type CapturedFlowExperience } from '$lib/stores/__tests__/experienceFlowHarness';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), prefetch: vi.fn() }));

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
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project-a', isSystemAdmin: false }),
	canWrite: writable(true),
	authReady: writable(true),
	projectSwitching: writable(false),
	getAuthVerificationEpoch: () => 1,
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: (force: boolean) => Promise<void>) => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60], refresh: () => refresh(true) }),
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
		expect((screen.getByRole('button', { name: '볼륨 삭제' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'data-disk 볼륨 작업' }));
		const actions = screen.getByRole('group', { name: 'data-disk 볼륨 작업 옵션' });
		expect(within(actions).getByRole('button', { name: '이름 변경' })).toBeTruthy();
		expect(within(actions).getByRole('button', { name: '용량 확장' })).toBeTruthy();
		expect(within(actions).getByRole('button', { name: '백업 생성' })).toBeTruthy();
		expect(within(actions).getByRole('link', { name: '자동 백업 설정' }).getAttribute('href')).toBe('/dashboard/volumes/backups?auto-backup=vol-1');
	});

	it('renames from the list action menu and updates both the row and the open detail panel', async () => {
		render(ListPage);

		await fireEvent.click(await screen.findByRole('button', { name: 'data-disk' }));
		const heading = await screen.findByRole('heading', { name: 'data-disk' });
		expect(heading).toBeTruthy();
		expect(await screen.findByRole('link', { name: 'web-01' })).toBeTruthy();
		const detail = await screen.findByRole('dialog', { name: '볼륨 상세' });
		await fireEvent.click(within(detail).getByRole('button', { name: 'data-disk 볼륨 작업' }));
		const detailMenu = await screen.findByRole('group', { name: 'data-disk 볼륨 작업 옵션' });
		expect(within(detailMenu).getByRole('button', { name: '용량 확장' })).toBeTruthy();
		expect(within(detailMenu).getByRole('button', { name: '백업 생성' })).toBeTruthy();
		expect(within(detailMenu).getByRole('link', { name: '자동 백업 설정' }).getAttribute('href')).toBe('/dashboard/volumes/backups?auto-backup=vol-1');
		await fireEvent.click(within(detail).getByRole('button', { name: 'data-disk 볼륨 작업' }));

		await fireEvent.click(within(document.getElementById('volume-resource-panel')!).getByRole('button', { name: 'data-disk 볼륨 작업' }));
		const menu = await screen.findByRole('group', { name: 'data-disk 볼륨 작업 옵션' });
		await fireEvent.click(within(menu).getByRole('button', { name: '이름 변경' }));

		const dialog = await screen.findByRole('dialog', { name: '볼륨 이름 변경' });
		const input = within(dialog).getByRole('textbox');
		await fireEvent.input(input, { target: { value: 'renamed-disk' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));

		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/volumes/vol-1', { name: 'renamed-disk' }, 'token', 'project-a');
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '볼륨 이름 변경' })).toBeNull());
		expect(await screen.findAllByRole('button', { name: 'renamed-disk 볼륨 작업' })).toHaveLength(2);
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

	it.each([['list', ListPage], ['direct detail', DetailRoute]])('extends an unattached disk from the %s with the selected project', async (_surface, Component) => {
		serverVolume = { ...serverVolume, status: 'available', attachments: [] };
		mocks.post.mockResolvedValue({ ...serverVolume, status: 'extending' });
		render(Component);
		await fireEvent.click(await screen.findByRole('button', { name: 'data-disk 볼륨 작업' }));
		const menu = await screen.findByRole('group', { name: 'data-disk 볼륨 작업 옵션' });
		await fireEvent.click(within(menu).getByRole('button', { name: '용량 확장' }));
		const dialog = await screen.findByRole('dialog', { name: '볼륨 용량 확장' });
		await fireEvent.click(within(dialog).getByRole('button', { name: '확장' }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/volumes/vol-1/extend', { new_size: 30 }, 'token', 'project-a'));
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/volumes/vol-1', 'token', 'project-a', { refresh: true });
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '볼륨 용량 확장' })).toBeNull());
	});

	it('loads only project-scoped volume resources and reaches settings without a policy mutation', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		expect(screen.getByRole('link', { name: '자동 백업 설정' }).getAttribute('href')).toBe('/dashboard/volumes/backups?auto-backup=vol-1');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/volumes', 'token', 'project-a', undefined);
		expect(mocks.get.mock.calls.map(call => call.slice(0, 3))).toContainEqual(['/api/v1/dashboard/quotas', 'token', 'project-a']);
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'data-disk 볼륨 작업' }));
		const menu = screen.getByRole('group', { name: 'data-disk 볼륨 작업 옵션' });
		const link = within(menu).getByRole('link', { name: '자동 백업 설정' });
		expect(link.getAttribute('href')).toBe('/dashboard/volumes/backups?auto-backup=vol-1');
		link.addEventListener('click', (event) => event.preventDefault(), { once: true });
		await fireEvent.click(link);
		expect(screen.queryByRole('group', { name: 'data-disk 볼륨 작업 옵션' })).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.patch).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
	});
});

describe('volume creation semantic experience through the real modal, page callback and controller', () => {
	let captured: CapturedFlowExperience;
	const createdVolume = { id: 'vol-created', name: 'created-disk', status: 'creating', size: 10, volume_type: null, attachments: [] };
	beforeEach(() => {
		captured = captureFlowExperience('/dashboard/volumes', () => ({
			token: get(projectAuth).token, userId: 'user', projectId: get(projectAuth).projectId, domainId: 'domain',
		}));
	});
	afterEach(() => {
		captured.collector.destroy();
		vi.restoreAllMocks();
	});

	async function submitCreation() {
		await fireEvent.click(document.querySelector('[data-tour=\"volume-create-open\"]')!);
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(within(dialog).getByLabelText('이름'), { target: { value: 'private-volume-name' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: '생성' }));
	}

	it('awaits the create callback readback, distinguishes list commit from native availability, and retains context on later polling', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		const readback = Promise.withResolvers<Volume[]>();
		mocks.post.mockResolvedValue({ id: createdVolume.id, status: 'creating' });
		mocks.get.mockImplementationOnce(() => readback.promise);
		await submitCreation();
		await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
		const context = mocks.post.mock.calls[0][4].experience;
		await waitFor(() => expect(mocks.get.mock.calls.some(call => call[3]?.experience === context)).toBe(true));
		expect(screen.queryByRole('dialog')).toBeNull();
		await captured.flush();
		expect(captured.events.some(event => event.payload.state === 'ready' && event.payload.step === 3)).toBe(false);
		readback.resolve([serverVolume, createdVolume]);
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		expect(captured.events.some(event => event.event_type === 'result.committed' && event.action_id === context.actionId)).toBe(true);
		expect(captured.events.some(event => event.payload.state === 'ready' && event.payload.step === 3)).toBe(false);

		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, { ...createdVolume, status: 'available' }]));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await waitFor(() => expect(mocks.get.mock.calls.filter(call => call[3]?.experience === context).length).toBe(2));
		await captured.flush();
		expect(captured.events.filter(event => event.payload.state === 'ready' && event.payload.step === 3)).toHaveLength(1);
		expect(new Set(captured.events.filter(event => event.feature === 'block_storage' && event.action_id).map(event => event.action_id))).toEqual(new Set([context.actionId]));
		expect(JSON.stringify(captured.events)).not.toContain('private-volume-name');
		expect(JSON.stringify(captured.events)).not.toContain('vol-created');
	});

	it('discards an older poll after a newer authoritative available state without rewinding the list or outcome', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		const older = Promise.withResolvers<Volume[]>();
		const newer = Promise.withResolvers<Volume[]>();
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => older.promise);
		await submitCreation();
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		mocks.get.mockImplementationOnce(() => newer.promise);
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		newer.resolve([serverVolume, { ...createdVolume, status: 'available' }]);
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		older.resolve([serverVolume, { ...createdVolume, name: 'stale-private-name', status: 'creating' }]);
		await waitFor(() => expect(screen.queryByRole('button', { name: 'stale-private-name 볼륨 작업' })).toBeNull());
		await captured.flush();
		expect(captured.events.some(event => event.event_type === 'result.discarded' && event.payload.reason === 'stale')).toBe(true);
		expect(captured.events.filter(event => event.payload.state === 'ready' && event.payload.step === 3)).toHaveLength(1);
		expect(screen.getByRole('button', { name: 'created-disk 볼륨 작업' })).toBeTruthy();
	});

	it('keeps a hidden pending POST correlated through authoritative readiness without claiming cancellation or replay', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		const post = Promise.withResolvers<{ id: string }>();
		mocks.post.mockImplementationOnce(() => post.promise);
		await submitCreation();
		await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '취소' }));
		await captured.flush();
		expect(captured.events.some(event => event.event_type === 'result.discarded' && event.payload.reason === 'aborted')).toBe(false);
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, { ...createdVolume, status: 'available' }]));
		post.resolve({ id: createdVolume.id });
		await waitFor(() => expect(mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes')).toHaveLength(2));
		await captured.flush();
		expect(captured.events.some(event => event.payload.state === 'error')).toBe(false);
		expect(captured.events.some(event => event.payload.state === 'ready' && event.payload.step === 3)).toBe(true);
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it('does not apply a previous project readback after scope change', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		const readback = Promise.withResolvers<Volume[]>();
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => readback.promise);
		await submitCreation();
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		await captured.flush();
		const actionId = mocks.post.mock.calls[0][4].experience.actionId;
		const commits = captured.events.filter(event => event.action_id === actionId && event.event_type === 'result.committed').length;
		mocks.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/dashboard/quotas' ? null : []));
		projectAuth.set({ token: 'token-b', projectId: 'project-b', isSystemAdmin: false });
		await waitFor(() => expect(mocks.get.mock.calls.some(call => call[2] === 'project-b')).toBe(true));
		readback.resolve([{ ...createdVolume, status: 'available' }]);
		await captured.flush();
		expect(screen.queryByRole('button', { name: 'created-disk 볼륨 작업' })).toBeNull();
		expect(captured.events.filter(event => event.action_id === actionId && event.event_type === 'result.committed')).toHaveLength(commits);
		expect(captured.events.some(event => event.payload.state === 'ready' && event.payload.step === 3)).toBe(false);
	});

	it('preserves the existing 503 error UI while leaving native creation outcome unknown', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		mocks.post.mockRejectedValueOnce(new ApiError(503, 'temporary gateway failure'));
		await submitCreation();
		await within(screen.getByRole('dialog')).findByText('temporary gateway failure');
		await captured.flush();
		expect(captured.events.some(event => event.event_type === 'result.discarded' && event.payload.reason === 'unknown')).toBe(true);
		expect(captured.events.some(event => event.payload.state === 'error' || event.payload.state === 'ready')).toBe(false);
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it('preserves the successful POST callback after an owner change without attributing it to the new owner', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		const post = Promise.withResolvers<{ id: string }>();
		mocks.post.mockImplementationOnce(() => post.promise);
		await submitCreation();
		await captured.flush();
		const actionId = mocks.post.mock.calls[0][4].experience.actionId;
		mocks.get.mockImplementation((path: string) => path === '/api/v1/dashboard/quotas'
			? Promise.reject(new ApiError(503, 'unavailable')) : Promise.resolve([]));
		projectAuth.set({ token: 'token-b', projectId: 'project-b', isSystemAdmin: false });
		await waitFor(() => expect(mocks.get.mock.calls.some(call => call[0] === '/api/v1/volumes' && call[2] === 'project-b')).toBe(true));
		const before = mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes' && call[2] === 'project-b').length;
		post.resolve({ id: createdVolume.id });
		await waitFor(() => expect(mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes' && call[2] === 'project-b')).toHaveLength(before + 1));
		await captured.flush();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(captured.events.some(event => event.action_id === actionId && event.payload.state === 'ready')).toBe(false);
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it('releases creating immediately after POST even when the creation callback list read is still pending', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		const readback = Promise.withResolvers<Volume[]>();
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => readback.promise);
		await submitCreation();
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		await fireEvent.click(document.querySelector('[data-tour=\"volume-create-open\"]')!);
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(within(dialog).getByLabelText('이름'), { target: { value: 'another-volume' } });
		expect((within(dialog).getByRole('button', { name: '생성' }) as HTMLButtonElement).disabled).toBe(false);
		expect(mocks.post).toHaveBeenCalledTimes(1);
		readback.resolve([serverVolume, createdVolume]);
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
	});

	it.each(['in-use', 'reserved', 'deleting', 'unknown-provider-state'])('ends create correlation honestly at %s without changing later product polling', async (status) => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, { ...createdVolume, status }]));
		await submitCreation();
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		const actionId = mocks.post.mock.calls[0][4].experience.actionId;
		expect(captured.events.some(event => event.action_id === actionId && event.event_type === 'result.discarded' && event.payload.reason === 'unknown')).toBe(true);
		expect(captured.events.some(event => event.action_id === actionId && event.payload.state === 'ready')).toBe(false);
		mocks.get.mockImplementationOnce(() => Promise.resolve([{ ...createdVolume, name: 'later-list-name', status: 'available' }]));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await screen.findByRole('button', { name: 'later-list-name 볼륨 작업' });
		await captured.flush();
		const reads = mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes');
		expect(reads[reads.length - 1][3]?.experience?.actionId).toBeUndefined();
		expect(captured.events.some(event => event.action_id === actionId && event.payload.state === 'ready')).toBe(false);
	});

	it.each(['error', 'error_deleting', 'error_restoring'])('records authoritative %s once and drops the creation context on subsequent polls', async (status) => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, { ...createdVolume, status }]));
		await submitCreation();
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		const actionId = mocks.post.mock.calls[0][4].experience.actionId;
		expect(captured.events.filter(event => event.action_id === actionId && event.payload.state === 'error' && event.payload.step === 3)).toHaveLength(1);
		mocks.get.mockImplementationOnce(() => Promise.resolve([{ ...createdVolume, status: 'available' }]));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await captured.flush();
		const reads = mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes');
		expect(reads[reads.length - 1][3]?.experience?.actionId).toBeUndefined();
		expect(captured.events.some(event => event.action_id === actionId && event.payload.state === 'ready')).toBe(false);
	});

	it.each(['creating', 'downloading'])('deduplicates unchanged %s observations and ends with unknown when a previously seen row disappears', async (status) => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		const observedVolume = { ...createdVolume, status };
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, observedVolume]));
		await submitCreation();
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		const actionId = mocks.post.mock.calls[0][4].experience.actionId;
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, observedVolume]));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await captured.flush();
		expect(captured.events.filter(event => event.action_id === actionId && event.payload.state === 'loading' && event.payload.step === 3)).toHaveLength(1);
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume]));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await waitFor(() => expect(screen.queryByRole('button', { name: 'created-disk 볼륨 작업' })).toBeNull());
		await captured.flush();
		expect(captured.events.some(event => event.action_id === actionId && event.event_type === 'result.discarded' && event.payload.reason === 'unknown')).toBe(true);
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, { ...createdVolume, status: 'available' }]));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		const reads = mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes');
		expect(reads[reads.length - 1][3]?.experience?.actionId).toBeUndefined();
		expect(captured.events.some(event => event.action_id === actionId && event.payload.state === 'ready')).toBe(false);
	});

	it('expires a never-listed creation observation after five minutes without suppressing the actual list result', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume]));
		await submitCreation();
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		await captured.flush();
		const actionId = mocks.post.mock.calls[0][4].experience.actionId;
		const now = performance.now();
		vi.spyOn(performance, 'now').mockReturnValue(now + 5 * 60_000 + 1);
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, { ...createdVolume, status: 'available' }]));
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		const reads = mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes');
		expect(reads[reads.length - 1][3]?.experience?.actionId).toBeUndefined();
		expect(captured.events.some(event => event.action_id === actionId && event.event_type === 'result.discarded' && event.payload.reason === 'unknown')).toBe(true);
		expect(captured.events.some(event => event.action_id === actionId && event.payload.state === 'ready')).toBe(false);
	});

	it('fences creation correlation when the owner segment changes even if the project ID stays the same', async () => {
		render(ListPage);
		await screen.findByRole('button', { name: 'data-disk 볼륨 작업' });
		mocks.post.mockResolvedValue({ id: createdVolume.id });
		mocks.get.mockImplementationOnce(() => Promise.resolve([serverVolume, createdVolume]));
		await submitCreation();
		await screen.findByRole('button', { name: 'created-disk 볼륨 작업' });
		await captured.flush();
		const actionId = mocks.post.mock.calls[0][4].experience.actionId;
		mocks.get.mockImplementation((path: string) => path === '/api/v1/dashboard/quotas'
			? Promise.reject(new ApiError(503, 'unavailable'))
			: Promise.resolve(path === '/api/v1/volumes' ? [{ ...createdVolume, status: 'available' }] : []));
		projectAuth.set({ token: 'different-owner-token', projectId: 'project-a', isSystemAdmin: false });
		await waitFor(() => expect(mocks.get.mock.calls.some(call => call[0] === '/api/v1/volumes' && call[1] === 'different-owner-token')).toBe(true));
		await captured.flush();
		const reads = mocks.get.mock.calls.filter(call => call[0] === '/api/v1/volumes');
		expect(reads[reads.length - 1][3]?.experience?.actionId).toBeUndefined();
		expect(captured.events.some(event => event.action_id === actionId && event.payload.state === 'ready')).toBe(false);
	});
});

import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Volume } from '$lib/types/volume';
import { initLocale } from '$lib/i18n/runtime.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), prefetch: vi.fn() }));
vi.mock('$lib/api/client', () => {
	class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
	return { api: mocks, ApiError };
});
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'caller-token', userId: 'user-a', projectId: 'destination', projectName: 'Destination project', canWrite: true, isSystemAdmin: false }),
	canWrite: writable(true), projectSwitching: writable(false),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));
vi.mock('$app/stores', () => ({
	page: writable({ params: { id: 'disk-a' }, url: new URL('http://localhost/dashboard/volumes/disk-a'), data: {} }),
}));
import ListPage from '../+page.svelte';
import DetailRoute from '../[id]/+page.svelte';

const transferId = '11111111-1111-4111-8111-111111111111';
const disk: Volume = { id: 'disk-a', name: 'Transfer data', status: 'available', size: 20, volume_type: 'ssd', attachments: [] };
const issued = { id: transferId, name: 'handoff', volume_id: disk.id, created_at: null, auth_key: 'one-time-key' };
let inventory: Volume[];
let pending: typeof issued[];

beforeAll(() => {
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	window.matchMedia ??= ((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false })) as unknown as typeof window.matchMedia;
});
beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	inventory = [];
	pending = [];
	mocks.get.mockImplementation((path: string) => {
		if (path === '/api/v1/volumes') return Promise.resolve([...inventory]);
		if (path === '/api/v1/volumes/disk-a') return Promise.resolve(inventory[0] ?? disk);
		if (path === '/api/v1/volumes/transfers') return Promise.resolve(pending.map(({ id, name, volume_id, created_at }) => ({ id, name, volume_id, created_at })));
		if (path === '/api/v1/dashboard/quotas') return Promise.resolve({ storage: { gigabytes: { limit: 100, in_use: 20 }, volumes: { limit: 10, in_use: inventory.length }, snapshots: { limit: 10, in_use: 0 } } });
		if (path === `/api/v1/volumes/transfer/${transferId}`) return Promise.resolve({
			id: transferId, name: issued.name, volume_id: disk.id, created_at: null,
			volume_name: disk.name, size: disk.size, volume_type: disk.volume_type, status: 'awaiting-transfer',
			source_project: { id: 'full-source-project-id', name: 'Origin project' },
			source_domain: { id: 'full-source-domain-id', name: 'Origin domain' },
		});
		return Promise.resolve([]);
	});
	mocks.post.mockImplementation((path: string) => {
		if (path === `/api/v1/volumes/transfer/${transferId}/accept`) { inventory = [disk]; return Promise.resolve({ id: transferId, name: issued.name, volume_id: disk.id }); }
		if (path === '/api/v1/volumes/disk-a/transfer') {
			inventory = [{ ...disk, status: 'awaiting-transfer' }];
			pending = [issued];
			return Promise.resolve(issued);
		}
		return Promise.resolve({});
	});
	mocks.delete.mockImplementation(() => { pending = []; inventory = [disk]; return Promise.resolve(undefined); });
});

describe('volume transfer inventory lifecycle', () => {
	it('receives into an empty destination after exact lookup and origin review, then refreshes its inventory', async () => {
		render(ListPage);
		await fireEvent.click(screen.getByRole('button', { name: '볼륨 수신' }));
		const dialog = screen.getByRole('dialog', { name: '볼륨 수신' });
		expect(within(dialog).getByText('Destination project')).toBeTruthy();
		expect(within(dialog).getByText('destination')).toBeTruthy();
		await fireEvent.input(within(dialog).getByLabelText('이전 ID'), { target: { value: transferId } });
		await fireEvent.submit(within(dialog).getByLabelText('이전 ID').closest('form')!);
		expect(await within(dialog).findByText('Origin domain')).toBeTruthy();
		expect(within(dialog).getByText('full-source-domain-id')).toBeTruthy();
		expect(within(dialog).getByText('Origin project')).toBeTruthy();
		expect(within(dialog).getByText('full-source-project-id')).toBeTruthy();
		await fireEvent.input(within(dialog).getByLabelText('인증 키'), { target: { value: 'sender-key' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: '볼륨 수신' }));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '볼륨 수신' })).toBeNull());
		expect(await screen.findByRole('button', { name: /Transfer data\s*disk-a/ })).toBeTruthy();
	});

	it.each([['list', ListPage], ['direct detail', DetailRoute]])('retains issued credentials across source inventory refresh from the %s entry', async (_entry, Component) => {
		inventory = [disk];
		render(Component);
		await fireEvent.click(await screen.findByRole('button', { name: 'Transfer data 볼륨 작업' }));
		const actions = screen.getByRole('group', { name: 'Transfer data 볼륨 작업 옵션' });
		await fireEvent.click(within(actions).getByRole('button', { name: '이전' }));
		const dialog = screen.getByRole('dialog', { name: '이전 생성' });
		await fireEvent.click(within(dialog).getByRole('button', { name: '이전 생성' }));
		expect(await screen.findByText('one-time-key')).toBeTruthy();
		expect(await screen.findByText('awaiting-transfer')).toBeTruthy();
		expect(screen.getByRole('dialog', { name: '이전 생성 완료' })).toBeTruthy();
		expect(screen.getByText('one-time-key')).toBeTruthy();
		expect(screen.getByRole('button', { name: '이전 ID 복사' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '인증 키 복사' })).toBeTruthy();
	});

	it('cancels its own pending transfer without requiring an existing volume row and refreshes the source', async () => {
		pending = [issued];
		render(ListPage);
		await fireEvent.click(screen.getByRole('button', { name: '대기 중인 이전' }));
		const dialog = screen.getByRole('dialog', { name: '대기 중인 이전' });
		await fireEvent.click(await within(dialog).findByRole('button', { name: `이전 ${transferId} 취소` }));
		await within(dialog).findByText('이 프로젝트에 대기 중인 이전이 없습니다.');
		await fireEvent.click(within(dialog).getByRole('button', { name: '닫기' }));
		expect(await screen.findByRole('button', { name: /Transfer data\s*disk-a/ })).toBeTruthy();
	});

	it.each(['in-use', 'available'])('never offers transfer creation for an attached %s volume after inventory publication', async (status) => {
		inventory = [{ ...disk, status, attachments: [{ server_id: 'server-a' }] }];
		render(ListPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'Transfer data 볼륨 작업' }));
		const actions = screen.getByRole('group', { name: 'Transfer data 볼륨 작업 옵션' });
		expect(within(actions).queryByRole('button', { name: '이전' })).toBeNull();
	});
});

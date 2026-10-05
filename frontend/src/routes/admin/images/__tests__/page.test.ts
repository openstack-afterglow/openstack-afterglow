import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { AdminImage } from '$lib/types/adminImage';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { status = 500; } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { subscribe: writable(new Map([['project', 'Project']])).subscribe, load: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }),
}));
import { auth } from '$lib/stores/auth';
import Page from '../+page.svelte';

function image(id: string, repository: string, tag: string, created_at: string, extra: Partial<AdminImage> = {}): AdminImage {
	return { id, repository, tag, name: `${repository}:${tag}`, status: 'active', size: 1024 ** 3,
		min_disk: 0, min_ram: 0, disk_format: 'raw', os_distro: 'ubuntu', visibility: 'public',
		owner: 'project', created_at, protected: false, verification_status: 'unverified', verified_at: null, ...extra };
}
const ubuntuOld = image('u-old', 'ubuntu', '22.04', '2026-07-01T00:00:00Z');
const debian = image('d-new', 'debian', '13', '2026-09-01T00:00:00Z', { os_distro: 'debian' });
const ubuntuNew = image('u-new', 'ubuntu', '24.04', '2026-09-26T00:00:00Z', { verification_status: 'verified', verified_at: '2026-09-26T01:00:00Z' });

// Compile the real lazy panel during setup; cold transforms are not a click deadline.
beforeAll(async () => { await vi.importActual('$lib/components/ImageDetailPanel.svelte'); });

beforeEach(() => {
	vi.clearAllMocks();
	mocks.get.mockReset();
	mocks.put.mockReset();
	auth.update((state) => ({ ...state, token: 'token', projectId: 'project' }));
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('prefers-reduced-motion'), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('administrator image catalog', () => {
	it('groups versions across API pages and orders repositories by their newest upload', async () => {
		mocks.get.mockImplementation(async (path: string) => path.includes('marker=')
			? { items: [ubuntuNew], next_marker: null }
			: { items: [debian, ubuntuOld], next_marker: 'u-old' });
		render(Page);
		const list = await screen.findByLabelText('이미지 repository 목록');
		const ubuntuButton = within(list).getByRole('button', { name: 'ubuntu' });
		const debianButton = within(list).getByRole('button', { name: 'debian' });
		expect(ubuntuButton.compareDocumentPosition(debianButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		await fireEvent.click(ubuntuButton);
		const tags = screen.getByLabelText('이미지 tag 카드');
		expect(within(tags).getByRole('button', { name: 'ubuntu:24.04 (u-new) 상세' })).toBeTruthy();
		expect(within(tags).getByRole('button', { name: 'ubuntu:22.04 (u-old) 상세' })).toBeTruthy();
	});

	it('keeps duplicate uploads distinct across pages and marks filtered older versions as previous', async () => {
		const old = image('old-uuid-1234', 'ubuntu', '24.04', '2026-09-26T09:00:00.123456+09:00', {
			visibility: 'public', protected: true, updated_at: '2030-01-01T00:00:00Z', os_hash_algo: 'sha512', os_hash_value: 'a'.repeat(128),
		});
		const current = image('new-uuid-5678', 'ubuntu', '24.04', '2026-09-26T00:00:00.123457Z', {
			visibility: 'private', os_hash_algo: 'sha512', os_hash_value: 'a'.repeat(128),
		});
		const alias = image('alias-uuid', 'ubuntu', 'latest', '2026-08-01T00:00:00Z');
		mocks.get.mockImplementation(async (path: string) => {
			if (path.startsWith('/api/v1/images/')) return {
				...(path.endsWith(alias.id) ? alias : old), properties: {}, tags: [],
				virtual_size: 0, container_format: 'bare', checksum: null,
			};
			return path.includes('marker=')
				? { items: [current, old], next_marker: null }
				: { items: [old, alias], next_marker: old.id };
		});
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'ubuntu' }));
		const tags = within(screen.getByLabelText('이미지 tag 카드'));
		const oldDetail = tags.getByRole('button', { name: 'ubuntu:24.04 (old-uuid) 상세' });
		const newDetail = tags.getByRole('button', { name: 'ubuntu:24.04 (new-uuid) 상세' });
		expect(within(oldDetail.parentElement!).getByText('이전')).toBeTruthy();
		expect(within(newDetail.parentElement!).getByText('현재')).toBeTruthy();
		expect(tags.getAllByRole('button', { name: /ubuntu:24\.04 .* 상세/ })).toHaveLength(2);
		expect(within(tags.getByLabelText('ubuntu:24.04 (old-uuid) 관리')).queryByRole('button', { name: '삭제' })).toBeNull();
		expect(within(tags.getByLabelText('ubuntu:24.04 (new-uuid) 관리')).getByRole('button', { name: '삭제' })).toBeTruthy();
		await fireEvent.click(tags.getByRole('button', { name: 'ubuntu:latest (alias-uu) 상세' }));
		expect(await screen.findByText(alias.id, { selector: 'dd' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '패널 닫기 버튼' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Tags' }));
		await fireEvent.change(screen.getByLabelText('공개 범위'), { target: { value: 'public' } });
		const publicTags = within(screen.getByLabelText('이미지 tag 카드'));
		const previous = publicTags.getByRole('button', { name: 'ubuntu:24.04 (old-uuid) 상세' });
		expect(within(previous.parentElement!).getByText('이전')).toBeTruthy();
		expect(publicTags.queryByRole('button', { name: 'ubuntu:24.04 (new-uuid) 상세' })).toBeNull();
		await fireEvent.click(previous);
		expect(await screen.findByText(old.id, { selector: 'dd' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '패널 닫기 버튼' }));
		const actions = publicTags.getByLabelText('ubuntu:24.04 (old-uuid) 관리');
		await fireEvent.click(within(actions).getByRole('button', { name: '검증 승인' }));
		await vi.waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/api/v1/admin/images/old-uuid-1234/verification', { verified: true }, 'token', 'project'));
		expect(within(publicTags.getByRole('button', { name: 'ubuntu:24.04 (old-uuid) 상세' }).parentElement!).getByText('이전')).toBeTruthy();
	});

	it('approves and revokes a public tag through explicit administrator actions', async () => {
		let verified = false;
		mocks.get.mockImplementation(async () => ({ items: [image('u-old', 'ubuntu', '22.04', ubuntuOld.created_at!, {
			verification_status: verified ? 'verified' : 'unverified', verified_at: verified ? '2026-09-26T01:00:00Z' : null,
		})], next_marker: null }));
		mocks.put.mockImplementation(async (_path: string, body: { verified: boolean }) => { verified = body.verified; return {}; });
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'ubuntu' }));
		const tags = screen.getByLabelText('이미지 tag 카드');
		const actions = within(tags).getByLabelText('ubuntu:22.04 (u-old) 관리');
		expect(within(actions).queryByRole('button', { name: '검증 해제' })).toBeNull();
		await fireEvent.click(within(actions).getByRole('button', { name: '검증 승인' }));
		await fireEvent.click(await within(actions).findByRole('button', { name: '검증 해제' }));
		expect(await within(actions).findByRole('button', { name: '검증 승인' })).toBeTruthy();
		expect(within(actions).queryByRole('button', { name: '검증 해제' })).toBeNull();
	});

	it('keeps the complete catalog on a failed refresh rather than showing a partial page', async () => {
		mocks.get.mockResolvedValueOnce({ items: [ubuntuOld, debian], next_marker: null });
		render(Page);
		expect(await screen.findByRole('button', { name: 'debian' })).toBeTruthy();
		mocks.get.mockResolvedValueOnce({ items: [ubuntuNew], next_marker: 'u-new' }).mockRejectedValueOnce(new Error('다음 페이지 조회 실패'));
		await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
		expect(await screen.findByText('다음 페이지 조회 실패')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'debian' })).toBeTruthy();
		expect(screen.queryByText(':24.04')).toBeNull();
	});

	it('does not publish a late catalog from a previous project', async () => {
		const oldRequest = Promise.withResolvers<{ items: AdminImage[]; next_marker: null }>();
		mocks.get.mockReturnValueOnce(oldRequest.promise).mockResolvedValue({ items: [debian], next_marker: null });
		render(Page);
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledOnce());
		auth.update((state) => ({ ...state, token: 'token', projectId: 'new-project' }));
		expect(await screen.findByRole('button', { name: 'debian' })).toBeTruthy();
		oldRequest.resolve({ items: [ubuntuOld], next_marker: null });
		await oldRequest.promise;
		await fireEvent.click(screen.getByRole('button', { name: 'Tags' }));
		const tags = within(screen.getByLabelText('이미지 tag 카드'));
		expect(tags.queryByRole('button', { name: 'ubuntu:22.04 (u-old) 상세' })).toBeNull();
		expect(tags.getByRole('button', { name: 'debian:13 (d-new) 상세' })).toBeTruthy();
	});
});

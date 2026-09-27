import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { ImageInfo } from '$lib/types/compute';
import type { ImageRepositoryGroup } from '$lib/stores/imageCatalog.svelte';
import ImageRepositoryCard from '../ImageRepositoryCard.svelte';
import ImageRepositoryDetail from '../ImageRepositoryDetail.svelte';

const images: ImageInfo[] = [
	{ id: 'one', name: 'ubuntu:one', repository: 'ubuntu', tag: 'one', status: 'active', verification_status: 'verified', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' },
	{ id: 'two', name: 'ubuntu:two', repository: 'ubuntu', tag: 'two', status: 'active', verification_status: 'unavailable', created_at: '2025-12-01T00:00:00Z' },
	{ id: 'three', name: 'ubuntu:three', repository: 'ubuntu', tag: 'three', status: 'active', visibility: 'public', created_at: '2025-11-01T00:00:00Z' },
	{ id: 'five', name: 'ubuntu:five', repository: 'ubuntu', tag: 'five', status: 'active', verification_status: 'unverified' },
	{ id: 'four', name: 'ubuntu:four', repository: 'ubuntu', status: 'active', verification_status: 'verified' },
	{ id: 'six', name: 'ubuntu:six', repository: 'ubuntu', tag: 'six', status: 'active', verification_status: 'unavailable' },
];
const group: ImageRepositoryGroup = {
	repository: 'ubuntu', images, latest: images[0],
	tags: [
		{ tag: 'one', latest: images[0], current: images[0], images: [images[0]] },
		{ tag: 'two', latest: images[1], current: images[1], images: [images[1]] },
		{ tag: 'three', latest: images[2], current: images[2], images: [images[2]] },
		{ tag: 'five', latest: images[3], current: images[3], images: [images[3]] },
		{ tag: 'four', latest: images[4], current: images[4], images: [images[4]] },
		{ tag: 'six', latest: images[5], current: images[5], images: [images[5]] },
	],
};

function tagButton(tag: string): HTMLButtonElement {
	return screen.getByRole('button', { name: new RegExp(`:${tag}.*`) }) as HTMLButtonElement;
}

describe('repository trust', () => {
	it('counts every tag including unpreviewed images and labels each preview independently', async () => {
		const onOpen = vi.fn();
		const onOpenTag = vi.fn();
		render(ImageRepositoryCard, { group, onOpen, onOpenTag });
		expect(screen.getByText('검증됨 2')).toBeTruthy();
		expect(screen.getByText('미검증 2')).toBeTruthy();
		expect(screen.getByText('검증 불가 2')).toBeTruthy();
		expect(within(tagButton('one')).getByText('검증됨')).toBeTruthy();
		expect(within(tagButton('two')).getByText('검증 불가')).toBeTruthy();
		expect(within(tagButton('three')).getByText('미검증')).toBeTruthy();
		expect(within(tagButton('four')).getByText('검증됨')).toBeTruthy();
		expect(screen.getByText('+1')).toBeTruthy();
		await fireEvent.click(tagButton('two'));
		await fireEvent.click(screen.getByRole('button', { name: '모든 tag 조회' }));
		expect(onOpenTag).toHaveBeenCalledWith('two');
		expect(onOpen).toHaveBeenCalledOnce();
	});

	it('shows trust for each row and displays upload time rather than update time', async () => {
		const onOpenTag = vi.fn();
		render(ImageRepositoryDetail, {
			group,
			onBack: vi.fn(), onOpenTag,
		});
		const row = screen.getByText(':one').closest('tr')!;
		expect(within(row).getByText('검증됨')).toBeTruthy();
		expect(within(row).getByText('2026-01-01')).toBeTruthy();
		expect(within(screen.getByText(':two').closest('tr')!).getByText('검증 불가')).toBeTruthy();
		expect(within(screen.getByText(':three').closest('tr')!).getByText('미검증')).toBeTruthy();
		await fireEvent.click(within(row).getByRole('button', { name: '상세 보기' }));
		expect(onOpenTag).toHaveBeenCalledWith('one');
	});

	it('reveals older uploads with their full SHA-512 and UUID and opens each concrete image', async () => {
		const newestHash = 'a'.repeat(128);
		const olderHash = 'b'.repeat(128);
		const newest: ImageInfo = {
			id: '11111111-1111-4111-8111-111111111111', name: 'ubuntu:one', repository: 'ubuntu', tag: 'one',
			status: 'active', verification_status: 'verified', created_at: '2026-03-01T00:00:00Z',
			os_hash_algo: 'sha512', os_hash_value: newestHash,
		};
		const older: ImageInfo = {
			id: '22222222-2222-4222-8222-222222222222', name: 'ubuntu:one', repository: 'ubuntu', tag: 'one',
			status: 'active', verification_status: 'unverified', created_at: '2026-01-01T00:00:00Z',
			os_hash_algo: 'sha512', os_hash_value: olderHash,
		};
		const duplicateGroup: ImageRepositoryGroup = {
			repository: 'ubuntu', images: [newest, older], latest: newest,
			tags: [{ tag: 'one', latest: newest, current: newest, images: [newest, older] }],
		};
		const onOpenTag = vi.fn();
		render(ImageRepositoryDetail, { group: duplicateGroup, onBack: vi.fn(), onOpenTag });

		const currentRow = screen.getByLabelText(`이미지 ID: ${newest.id}`).closest('tr')!;
		expect(within(currentRow).getByText('현재')).toBeTruthy();
		expect(within(currentRow).getByLabelText(`SHA-512: ${newestHash}`).getAttribute('title')).toBe(`SHA-512: ${newestHash}`);
		expect(screen.getAllByRole('button', { name: '상세 보기' })).toHaveLength(1);
		expect(screen.queryByLabelText(`이미지 ID: ${older.id}`)).toBeNull();
		expect(screen.queryByLabelText(`SHA-512: ${olderHash}`)).toBeNull();
		const disclosure = screen.getByRole('button', { name: ':one 이전 업로드 1개 보기' });
		expect(disclosure.getAttribute('aria-expanded')).toBe('false');
		await fireEvent.click(disclosure);

		expect(screen.getByRole('button', { name: ':one 이전 업로드 1개 접기' }).getAttribute('aria-expanded')).toBe('true');
		expect(screen.getAllByRole('button', { name: '상세 보기' })).toHaveLength(2);
		const olderId = screen.getByLabelText(`이미지 ID: ${older.id}`);
		const olderRow = olderId.closest('tr')!;
		expect(olderId.getAttribute('title')).toBe(older.id);
		expect(within(olderRow).getByText('이전')).toBeTruthy();
		expect(within(olderRow).getByText('미검증')).toBeTruthy();
		expect(within(olderRow).getByLabelText(`SHA-512: ${olderHash}`).getAttribute('title')).toBe(`SHA-512: ${olderHash}`);
		await fireEvent.click(within(currentRow).getByRole('button', { name: '상세 보기' }));
		await fireEvent.click(within(olderRow).getByRole('button', { name: '상세 보기' }));
		expect(onOpenTag).toHaveBeenNthCalledWith(1, newest.id);
		expect(onOpenTag).toHaveBeenNthCalledWith(2, older.id);
		await fireEvent.click(screen.getByRole('button', { name: ':one 이전 업로드 1개 접기' }));
		expect(screen.queryByLabelText(`이미지 ID: ${older.id}`)).toBeNull();
	});

	it('previews a filtered older upload as previous while keeping the latest alias separate from recent upload', async () => {
		const canonical: ImageInfo = {
			id: '33333333-3333-4333-8333-333333333333', name: 'ubuntu:stable', repository: 'ubuntu', tag: 'stable',
			status: 'active', created_at: '2026-04-01T00:00:00Z',
		};
		const visibleOlder: ImageInfo = {
			id: '44444444-4444-4444-8444-444444444444', name: 'ubuntu:stable', repository: 'ubuntu', tag: 'stable',
			status: 'active', created_at: '2026-03-01T00:00:00Z',
		};
		const defaultAlias: ImageInfo = {
			id: '55555555-5555-4555-8555-555555555555', name: 'ubuntu:latest', repository: 'ubuntu', tag: 'latest',
			status: 'active', created_at: '2026-02-01T00:00:00Z',
		};
		const filteredGroup: ImageRepositoryGroup = {
			repository: 'ubuntu', images: [visibleOlder, defaultAlias], latest: visibleOlder,
			tags: [
				{ tag: 'stable', latest: visibleOlder, current: canonical, images: [visibleOlder] },
				{ tag: 'latest', latest: defaultAlias, current: defaultAlias, images: [defaultAlias] },
			],
		};
		const onOpenTag = vi.fn();
		render(ImageRepositoryCard, { group: filteredGroup, onOpen: vi.fn(), onOpenTag });

		expect(screen.getByText('최근 업로드').nextElementSibling?.textContent).toBe(':stable');
		expect(screen.getByText('2026-03-01')).toBeTruthy();
		expect(within(tagButton('stable')).getByText('이전')).toBeTruthy();
		expect(within(tagButton('stable')).queryByText('기본')).toBeNull();
		expect(within(tagButton('latest')).getByText('현재')).toBeTruthy();
		expect(within(tagButton('latest')).getByText('기본')).toBeTruthy();
		await fireEvent.click(tagButton('stable'));
		await fireEvent.click(tagButton('latest'));
		expect(onOpenTag).toHaveBeenNthCalledWith(1, visibleOlder.id);
		expect(onOpenTag).toHaveBeenNthCalledWith(2, defaultAlias.id);
	});
});

const listing: Record<string, unknown[]> = {
	'': [
		{ name: 'docs/', bytes: 0, content_type: 'application/directory', last_modified: '', etag: '', is_dir: true },
		{ name: 'photo.png', bytes: 2048, content_type: 'image/png', last_modified: '2026-09-01T00:00:00Z', etag: 'e-png' },
		{ name: 'bundle.zip', bytes: 4096, content_type: 'application/zip', last_modified: '2026-09-01T00:00:00Z', etag: 'e-zip' },
	],
	'docs/': [
		{ name: 'docs/manual.pdf', bytes: 1024, content_type: 'application/pdf', last_modified: '2026-09-02T00:00:00Z', etag: 'e-pdf' },
	],
};

const { fetchWithAuth } = vi.hoisted(() => ({
	fetchWithAuth: vi.fn(async (_url: string) => ({ ok: true, blob: async () => new Blob(['thumb']) })),
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: vi.fn(async (path: string) => {
			const prefix = new URL(path, 'http://test').searchParams.get('prefix') ?? '';
			return listing[prefix] ?? [];
		}),
		post: vi.fn(async () => ({})),
		delete: vi.fn(async () => {}),
		downloadBlob: vi.fn(),
	},
	ApiError: class ApiError extends Error {},
	fetchWithAuth,
	getBaseUrl: () => '',
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn(async () => true) }));

import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ObjectCardGridHarness from './ObjectCardGridHarness.svelte';

const createObjectURL = vi.fn(() => 'blob:thumb');
const revokeObjectURL = vi.fn();

beforeEach(() => {
	vi.clearAllMocks();
	vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
});

async function renderGrid() {
	render(ObjectCardGridHarness);
	await screen.findByRole('button', { name: '폴더 docs' });
}

describe('ObjectCardGrid', () => {
	it('separates folders from files and shows file metadata', async () => {
		await renderGrid();

		expect(screen.getByRole('heading', { name: '폴더' })).toBeTruthy();
		expect(screen.getByRole('heading', { name: '파일' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '파일 photo.png' })).toBeTruthy();
		expect(screen.getByRole('button', { name: '파일 bundle.zip' })).toBeTruthy();
		// 그리드는 현재 폴더의 직속 자식만 보여준다 — 하위 폴더 내용은 진입해야 나온다.
		expect(screen.queryByRole('button', { name: /manual\.pdf/ })).toBeNull();
	});

	it('enters a folder on double click and on Enter', async () => {
		await renderGrid();

		await fireEvent.dblClick(screen.getByRole('button', { name: '폴더 docs' }));
		await waitFor(() => expect(screen.getByTestId('prefix').textContent).toBe('docs/'));
		await screen.findByRole('button', { name: '파일 manual.pdf' });
	});

	it('enters a folder with the keyboard', async () => {
		await renderGrid();

		await fireEvent.keyDown(screen.getByRole('button', { name: '폴더 docs' }), { key: 'Enter' });
		await waitFor(() => expect(screen.getByTestId('prefix').textContent).toBe('docs/'));
	});

	it('selects a card with a single click without navigating', async () => {
		await renderGrid();

		await fireEvent.click(screen.getByRole('button', { name: '파일 photo.png' }));
		expect(screen.getByTestId('selected-names').textContent).toBe('photo.png');
		expect(screen.getByTestId('prefix').textContent).toBe('');
	});

	it('select-all covers exactly the visible grid rows', async () => {
		await renderGrid();

		const selectAll = screen.getByRole('checkbox', { name: '표시된 오브젝트 전체 선택' });
		await fireEvent.click(selectAll.closest('label')!);

		expect(screen.getByTestId('selected-names').textContent).toBe('docs/,bundle.zip,photo.png');
	});

	it('requests thumbnails only for renderable files', async () => {
		await renderGrid();

		await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled());
		const requested = fetchWithAuth.mock.calls.map(([url]) => url);
		expect(requested.some((url) => url.includes('photo.png/thumbnail'))).toBe(true);
		expect(requested.some((url) => url.includes('bundle.zip'))).toBe(false);
		expect(requested.some((url) => url.includes('docs'))).toBe(false);
	});

	it('shows a rendered thumbnail and falls back to an icon otherwise', async () => {
		await renderGrid();

		const imageCard = screen.getByRole('button', { name: '파일 photo.png' });
		await waitFor(() => expect(within(imageCard).getByRole('presentation')).toBeTruthy());
		expect(within(imageCard).getByRole('presentation').getAttribute('src')).toBe('blob:thumb');
		expect(within(screen.getByRole('button', { name: '파일 bundle.zip' })).queryByRole('presentation')).toBeNull();
	});

	it('revokes thumbnail object URLs when leaving a folder', async () => {
		await renderGrid();
		await waitFor(() => expect(createObjectURL).toHaveBeenCalled());

		await fireEvent.dblClick(screen.getByRole('button', { name: '폴더 docs' }));
		await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:thumb'));
	});

	it('discards a thumbnail that resolves after the user left the folder', async () => {
		type ThumbResponse = { ok: boolean; blob: () => Promise<Blob> };
		const deferred = Promise.withResolvers<ThumbResponse>();
		fetchWithAuth.mockImplementationOnce(() => deferred.promise);
		await renderGrid();
		await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled());

		await fireEvent.dblClick(screen.getByRole('button', { name: '폴더 docs' }));
		await waitFor(() => expect(screen.getByTestId('prefix').textContent).toBe('docs/'));

		createObjectURL.mockReturnValueOnce('blob:stale');
		deferred.resolve({ ok: true, blob: async () => new Blob(['late']) });
		await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:stale'));

		// 늦게 도착한 이전 폴더의 결과가 현재 카드로 새지 않는다.
		const cards = screen.getAllByRole('button', { name: /^파일 / });
		for (const card of cards) {
			const img = within(card).queryByRole('presentation');
			expect(img?.getAttribute('src')).not.toBe('blob:stale');
		}
	});
});

const initialListing = (): Record<string, unknown[]> => ({
	'': [
		{ name: 'docs/', bytes: 0, content_type: 'application/directory', last_modified: '', etag: '', is_dir: true },
		{ name: 'photo.png', bytes: 2048, content_type: 'image/png', last_modified: '2026-09-01T00:00:00Z', etag: 'e-png' },
		{ name: 'bundle.zip', bytes: 4096, content_type: 'application/zip', last_modified: '2026-09-01T00:00:00Z', etag: 'e-zip' },
	],
});
let listing = initialListing();

vi.mock('$lib/api/client', () => ({
	api: {
		get: vi.fn(async (path: string) => {
			const prefix = new URL(path, 'http://test').searchParams.get('prefix') ?? '';
			return [...(listing[prefix] ?? [])];
		}),
		post: vi.fn(async () => ({})),
		delete: vi.fn(async () => {}),
		downloadBlob: vi.fn(),
	},
	ApiError: class ApiError extends Error {},
	fetchWithAuth: vi.fn(async () => ({ ok: true, blob: async () => new Blob(['img']), text: async () => '' })),
	getBaseUrl: () => '',
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn(async () => true) }));

import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '$lib/api/client';
import ObjectDownloadBusyHarness from './ObjectDownloadBusyHarness.svelte';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
	return { promise, resolve, reject };
}

function rowFor(name: string): HTMLElement {
	return screen.getByRole('row', { name: (accessibleName) => accessibleName.includes(name) });
}

function downloadButton(scope: HTMLElement, name: string): HTMLButtonElement {
	return within(scope).getByRole('button', { name }) as HTMLButtonElement;
}

beforeEach(() => {
	vi.clearAllMocks();
	listing = initialListing();
	vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:object'), revokeObjectURL: vi.fn() }));
});

describe('object download preparation', () => {
	it('marks only the object being prepared as busy in the tree view', async () => {
		const token = deferred<{ url: string; expires_in: number }>();
		vi.mocked(api.post).mockImplementationOnce(() => token.promise);
		render(ObjectDownloadBusyHarness, { view: 'tree' });
		const photo = await screen.findByRole('row', { name: /photo\.png/ });
		const bundle = rowFor('bundle.zip');

		const busy = downloadButton(photo, '다운로드');
		await fireEvent.click(busy);

		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');
		const other = downloadButton(bundle, '다운로드');
		expect(other.disabled).toBe(false);
		expect(other.getAttribute('aria-busy')).not.toBe('true');

		token.resolve({ url: '#download', expires_in: 60 });
		await waitFor(() => expect(busy.disabled).toBe(false));
		expect(busy.getAttribute('aria-busy')).not.toBe('true');
	});

	it('marks only the object being prepared as busy in the admin table and clears it on failure', async () => {
		const blob = deferred<{ blob: Blob; filename: string }>();
		vi.mocked(api.downloadBlob).mockImplementationOnce(() => blob.promise);
		render(ObjectDownloadBusyHarness, { view: 'flat' });
		const photo = await screen.findByRole('row', { name: /photo\.png/ });
		const bundle = rowFor('bundle.zip');

		const busy = downloadButton(photo, '다운로드');
		await fireEvent.click(busy);

		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');
		expect(downloadButton(bundle, '다운로드').disabled).toBe(false);

		blob.reject(new Error('gone'));
		await waitFor(() => expect(busy.disabled).toBe(false));
		expect(busy.getAttribute('aria-busy')).not.toBe('true');
	});

	it('keeps a visible status on the card after its action menu closes', async () => {
		const token = deferred<{ url: string; expires_in: number }>();
		vi.mocked(api.post).mockImplementationOnce(() => token.promise);
		render(ObjectDownloadBusyHarness, { view: 'grid' });
		const card = await screen.findByRole('button', { name: '파일 photo.png' });
		const bundle = screen.getByRole('button', { name: '파일 bundle.zip' });

		await fireEvent.click(within(card).getByRole('button', { name: 'photo.png 파일 작업' }));
		await fireEvent.click(downloadButton(card, '다운로드'));

		expect(within(card).queryByRole('group')).toBeNull();
		expect(card.getAttribute('aria-busy')).toBe('true');
		expect(within(card).getByRole('status').textContent?.trim()).toBeTruthy();
		expect(bundle.getAttribute('aria-busy')).not.toBe('true');
		expect(within(bundle).queryByRole('status')).toBeNull();

		await fireEvent.click(within(card).getByRole('button', { name: 'photo.png 파일 작업' }));
		const busy = within(card).getByRole('button', { busy: true }) as HTMLButtonElement;
		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');

		await fireEvent.click(within(bundle).getByRole('button', { name: 'bundle.zip 파일 작업' }));
		expect(downloadButton(bundle, '다운로드').disabled).toBe(false);

		token.resolve({ url: '#download', expires_in: 60 });
		await waitFor(() => expect(card.getAttribute('aria-busy')).not.toBe('true'));
		expect(within(card).queryByRole('status')).toBeNull();
	});

	it('shows the preparation state on the preview download button', async () => {
		const token = deferred<{ url: string; expires_in: number }>();
		vi.mocked(api.post).mockImplementationOnce(() => token.promise);
		render(ObjectDownloadBusyHarness, { view: 'tree' });
		const photo = await screen.findByRole('row', { name: /photo\.png/ });
		const otherDownload = downloadButton(rowFor('bundle.zip'), '다운로드');

		await fireEvent.click(within(photo).getByRole('button', { name: '미리보기' }));
		const dialog = await screen.findByRole('dialog', { name: 'photo.png 미리보기' });
		await waitFor(() => expect(within(dialog).queryByRole('status')).toBeNull());
		const busy = downloadButton(dialog, '다운로드');
		await fireEvent.click(busy);

		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');
		expect(within(dialog).getByRole('status').textContent?.trim()).toBeTruthy();
		expect(otherDownload.disabled).toBe(false);

		token.resolve({ url: '#download', expires_in: 60 });
		await waitFor(() => expect(busy.disabled).toBe(false));
		expect(busy.getAttribute('aria-busy')).not.toBe('true');
		expect(within(dialog).queryByRole('status')).toBeNull();
	});
});

describe('object table entrances', () => {
	it.each(['tree', 'flat'] as const)('%s view fades rows in on first arrival only', async (view) => {
		render(ObjectDownloadBusyHarness, { view });
		const first = await screen.findByRole('row', { name: /photo\.png/ });
		expect(first.classList.contains('motion-fade')).toBe(true);

		await fireEvent.click(screen.getByRole('button', { name: 'harness refresh' }));
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		const refreshed = await screen.findByRole('row', { name: /photo\.png/ });
		expect(refreshed).not.toBe(first);
		expect(refreshed.classList.contains('motion-fade')).toBe(false);

		listing[''].push({ name: 'notes.txt', bytes: 12, content_type: 'text/plain', last_modified: '2026-09-03T00:00:00Z', etag: 'e-txt' });
		await fireEvent.click(screen.getByRole('button', { name: 'harness poll' }));
		const added = await screen.findByRole('row', { name: /notes\.txt/ });
		expect(added.classList.contains('motion-fade')).toBe(true);
		expect(rowFor('photo.png').classList.contains('motion-fade')).toBe(false);
	});
});

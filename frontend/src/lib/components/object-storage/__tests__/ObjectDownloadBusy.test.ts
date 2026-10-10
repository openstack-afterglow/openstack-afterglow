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

function rowOf(nameButton: HTMLElement): HTMLElement {
	return nameButton.closest('tr') as HTMLElement;
}

function downloadButton(scope: HTMLElement): HTMLButtonElement {
	return within(scope).getByRole('button', { name: /^다운로드/ }) as HTMLButtonElement;
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
		const photo = rowOf(await screen.findByRole('button', { name: 'photo.png' }));
		const bundle = rowOf(screen.getByRole('button', { name: 'bundle.zip' }));

		await fireEvent.click(downloadButton(photo));

		const busy = downloadButton(photo);
		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');
		const other = downloadButton(bundle);
		expect(other.disabled).toBe(false);
		expect(other.getAttribute('aria-busy')).not.toBe('true');

		token.resolve({ url: '#download', expires_in: 60 });
		await waitFor(() => expect(downloadButton(photo).disabled).toBe(false));
		expect(downloadButton(photo).getAttribute('aria-busy')).not.toBe('true');
		expect(other.disabled).toBe(false);
		expect(other.getAttribute('aria-busy')).not.toBe('true');
	});

	it('marks only the object being prepared as busy in the admin table and clears it on failure', async () => {
		const blob = deferred<{ blob: Blob; filename: string }>();
		vi.mocked(api.downloadBlob).mockImplementationOnce(() => blob.promise);
		render(ObjectDownloadBusyHarness, { view: 'flat' });
		const photo = rowOf(await screen.findByRole('button', { name: 'photo.png' }));
		const bundle = rowOf(screen.getByRole('button', { name: 'bundle.zip' }));

		await fireEvent.click(downloadButton(photo));

		const busy = downloadButton(photo);
		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');
		const other = downloadButton(bundle);
		expect(other.disabled).toBe(false);
		expect(other.getAttribute('aria-busy')).not.toBe('true');

		blob.reject(new Error('gone'));
		await waitFor(() => expect(downloadButton(photo).disabled).toBe(false));
		expect(downloadButton(photo).getAttribute('aria-busy')).not.toBe('true');
		expect(other.disabled).toBe(false);
		expect(other.getAttribute('aria-busy')).not.toBe('true');
	});

	it('keeps a visible status on the card after its action menu closes', async () => {
		const token = deferred<{ url: string; expires_in: number }>();
		vi.mocked(api.post).mockImplementationOnce(() => token.promise);
		render(ObjectDownloadBusyHarness, { view: 'grid' });
		const card = await screen.findByRole('button', { name: '파일 photo.png' });
		const bundle = screen.getByRole('button', { name: '파일 bundle.zip' });

		await fireEvent.click(within(card).getByRole('button', { name: 'photo.png 파일 작업' }));
		await fireEvent.click(downloadButton(card));

		expect(within(card).queryByRole('group')).toBeNull();
		expect(card.getAttribute('aria-busy')).toBe('true');
		expect(within(card).getByRole('status').textContent?.trim()).toBeTruthy();
		expect(bundle.getAttribute('aria-busy')).not.toBe('true');
		expect(within(bundle).queryByRole('status')).toBeNull();

		await fireEvent.click(within(card).getByRole('button', { name: 'photo.png 파일 작업' }));
		const busy = downloadButton(within(card).getByRole('group'));
		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');

		await fireEvent.click(within(bundle).getByRole('button', { name: 'bundle.zip 파일 작업' }));
		expect(downloadButton(within(bundle).getByRole('group')).disabled).toBe(false);

		token.resolve({ url: '#download', expires_in: 60 });
		await waitFor(() => expect(card.getAttribute('aria-busy')).not.toBe('true'));
		expect(within(card).queryByRole('status')).toBeNull();
		expect(bundle.getAttribute('aria-busy')).not.toBe('true');
	});

	it('shows the preparation state on the preview download button', async () => {
		const token = deferred<{ url: string; expires_in: number }>();
		vi.mocked(api.post).mockImplementationOnce(() => token.promise);
		render(ObjectDownloadBusyHarness, { view: 'tree' });
		const photo = rowOf(await screen.findByRole('button', { name: 'photo.png' }));
		const otherDownload = downloadButton(rowOf(screen.getByRole('button', { name: 'bundle.zip' })));

		await fireEvent.click(within(photo).getByRole('button', { name: '미리보기' }));
		const dialog = await screen.findByRole('dialog', { name: 'photo.png 미리보기' });
		await waitFor(() => expect(within(dialog).queryByRole('status')).toBeNull());
		await fireEvent.click(downloadButton(dialog));

		const busy = downloadButton(dialog);
		expect(busy.disabled).toBe(true);
		expect(busy.getAttribute('aria-busy')).toBe('true');
		expect(within(busy).getByRole('status').textContent?.trim()).toBeTruthy();
		expect(downloadButton(photo).disabled).toBe(true);
		expect(downloadButton(photo).getAttribute('aria-busy')).toBe('true');
		expect(otherDownload.disabled).toBe(false);
		expect(otherDownload.getAttribute('aria-busy')).not.toBe('true');

		token.resolve({ url: '#download', expires_in: 60 });
		await waitFor(() => expect(downloadButton(dialog).disabled).toBe(false));
		expect(downloadButton(dialog).getAttribute('aria-busy')).not.toBe('true');
		expect(within(dialog).queryByRole('status')).toBeNull();
		expect(downloadButton(photo).disabled).toBe(false);
		expect(downloadButton(photo).getAttribute('aria-busy')).not.toBe('true');
		expect(otherDownload.disabled).toBe(false);
	});
});

describe('object table entrances', () => {
	it.each(['tree', 'flat'] as const)('%s view fades rows in on first arrival only', async (view) => {
		render(ObjectDownloadBusyHarness, { view });
		const first = rowOf(await screen.findByRole('button', { name: 'photo.png' }));
		expect(first.classList.contains('motion-fade')).toBe(true);

		await fireEvent.click(screen.getByRole('button', { name: 'harness refresh' }));
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		const refreshed = rowOf(await screen.findByRole('button', { name: 'photo.png' }));
		expect(refreshed).not.toBe(first);
		expect(refreshed.classList.contains('motion-fade')).toBe(false);

		listing[''].push({ name: 'notes.txt', bytes: 12, content_type: 'text/plain', last_modified: '2026-09-03T00:00:00Z', etag: 'e-txt' });
		await fireEvent.click(screen.getByRole('button', { name: 'harness poll' }));
		const added = rowOf(await screen.findByRole('button', { name: 'notes.txt' }));
		expect(added.classList.contains('motion-fade')).toBe(true);
		expect(rowOf(screen.getByRole('button', { name: 'photo.png' })).classList.contains('motion-fade')).toBe(false);
	});
});

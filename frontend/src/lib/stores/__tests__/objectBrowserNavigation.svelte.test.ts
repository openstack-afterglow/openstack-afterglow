const listing: Record<string, unknown[]> = {
	'': [{ name: 'docs/', bytes: 0, content_type: 'application/directory', last_modified: '', etag: '', is_dir: true }],
	'docs/': [{ name: 'docs/manual.pdf', bytes: 10, content_type: 'application/pdf', last_modified: '', etag: 'e1' }],
};

vi.mock('$lib/api/client', () => ({
	api: {
		get: vi.fn(async (path: string) => listing[new URL(path, 'http://t').searchParams.get('prefix') ?? ''] ?? []),
		post: vi.fn(async () => ({})),
		delete: vi.fn(async () => {}),
		downloadBlob: vi.fn(),
	},
	ApiError: class ApiError extends Error {},
	fetchWithAuth: vi.fn(),
	getBaseUrl: () => '',
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn(async () => true) }));

import { describe, expect, it, vi } from 'vitest';
import { flushSync } from 'svelte';
import { createObjectBrowserStore } from '$lib/stores/objectBrowser.svelte';

function withStore(run: (store: ReturnType<typeof createObjectBrowserStore>) => void) {
	const cleanup = $effect.root(() => {
		const store = createObjectBrowserStore({
			mode: () => 'user',
			containerName: () => 'sample-artifacts',
			token: () => 'token',
			projectId: () => 'project-a',
		});
		flushSync();
		run(store);
	});
	cleanup();
}

describe('objectBrowser navigation', () => {
	it('keeps the prefix after entering a folder', () => {
		withStore((store) => {
			store.navigatePrefix('docs/');
			flushSync();
			expect(store.prefix).toBe('docs/');
		});
	});

	it('returns to the root when navigating back up', () => {
		withStore((store) => {
			store.navigatePrefix('docs/');
			flushSync();
			store.navigatePrefix('');
			flushSync();
			expect(store.prefix).toBe('');
		});
	});

	it('persists the view mode and drops the tree-only search scope in grid view', () => {
		withStore((store) => {
			expect(store.viewMode).toBe('grid');
			store.viewMode = 'list';
			flushSync();
			expect(store.viewMode).toBe('list');
			expect(localStorage.getItem('objectBrowser.view')).toBe('list');

			store.searchScope = 'expanded';
			store.viewMode = 'grid';
			flushSync();
			expect(store.searchScope).toBe('current');
		});
		localStorage.removeItem('objectBrowser.view');
	});
});

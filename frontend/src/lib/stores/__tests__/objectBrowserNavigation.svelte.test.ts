const listing: Record<string, unknown[]> = {
	'': [{ name: 'docs/', bytes: 0, content_type: 'application/directory', last_modified: '', etag: '', is_dir: true }],
	'docs/': [{ name: 'docs/manual.pdf', bytes: 10, content_type: 'application/pdf', last_modified: '', etag: 'e1' }],
};
let allListingRequest: (() => Promise<unknown[]>) | undefined;

vi.mock('$lib/api/client', () => ({
	api: {
		withExperience() { return this; },
		get: vi.fn(async (path: string) => {
			const query = new URL(path, 'http://t').searchParams;
			if (query.has('delimiter') && query.get('delimiter') === '') return allListingRequest ? allListingRequest() : Object.values(listing).flat();
			return listing[query.get('prefix') ?? ''] ?? [];
		}),
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
import { flushSync, tick } from 'svelte';
import { createObjectBrowserStore, type ObjectBrowserStore } from '$lib/stores/objectBrowser.svelte';
import { api } from '$lib/api/client';

function withStore(run: (store: ReturnType<typeof createObjectBrowserStore>) => void) {
	const cleanup = $effect.root(() => {
		const store = createObjectBrowserStore({
			mode: () => 'user',
			containerName: () => 'sample-artifacts',
			token: () => 'token',
			projectId: () => 'project-a',
			ownerKey: () => 'navigation-fixture-owner',
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

	it('keeps ancestor context, regex and absent column selections through refresh', async () => {
		let store!: ObjectBrowserStore;
		const cleanup = $effect.root(() => {
			store = createObjectBrowserStore({
				mode: () => 'user',
				containerName: () => 'sample-artifacts',
				token: () => 'token',
				projectId: () => 'project-a',
				ownerKey: () => 'table-controls-fixture',
			});
		});
		const original = listing['docs/'];
		try {
			flushSync();
			await tick();
			await store.fetchDir('');
			store.viewMode = 'list';
			await store.toggleExpand('docs/');
			store.searchScope = 'expanded';
			store.filterText = '^manual\\.(pdf|txt)$';
			store.view.setFilter('bytes', ['10']);
			store.view.toggleSort('bytes');
			store.view.toggleSort('bytes');
			flushSync();
			expect(store.treeRows.map(row => [row.obj.name, row.depth])).toEqual([
				['docs/', 0], ['docs/manual.pdf', 1],
			]);
			listing['docs/'] = [{ name: 'docs/manual.pdf', bytes: 20, content_type: 'application/pdf', last_modified: '', etag: 'e2' }];
			await store.refreshAll();
			flushSync();
			expect(store.filterText).toBe('^manual\\.(pdf|txt)$');
			expect(store.view.sort).toEqual({ key: 'bytes', direction: 'desc' });
			expect(store.view.selected('bytes')).toEqual(['10']);
			expect(store.view.options('bytes')).toContainEqual({ value: '10', label: '10', count: 0 });
			expect(store.treeRows).toEqual([]);
			store.filterText = '[';
			flushSync();
			expect(store.view.error).toBe(true);
			expect(store.treeRows).toEqual([]);
		} finally {
			listing['docs/'] = original;
			cleanup();
			localStorage.removeItem('objectBrowser.view');
		}
	});

	it('sorts retained ancestors and their children independently of regex or facet membership', async () => {
		const originalRoot = listing[''];
		listing[''] = ['a/', 'z/'].map(name => ({ name, bytes: 0, content_type: 'application/directory', last_modified: '', etag: '', is_dir: true }));
		for (const parent of ['a/', 'z/']) {
			listing[parent] = ['alpha.pdf', 'zulu.pdf', 'unmatched.txt'].map(name => ({
				name: parent + name, bytes: 10, content_type: name.endsWith('.pdf') ? 'application/pdf' : 'text/plain', last_modified: '', etag: name,
			}));
		}
		let store!: ObjectBrowserStore;
		const cleanup = $effect.root(() => {
			store = createObjectBrowserStore({
				mode: () => 'user', containerName: () => 'sample-artifacts',
				token: () => 'token', projectId: () => 'project-a', ownerKey: () => 'two-parent-sort-fixture',
			});
		});
		try {
			flushSync();
			await tick();
			await store.fetchDir('');
			await store.fetchDir('a/');
			await store.fetchDir('z/');
			store.viewMode = 'list';
			store.searchScope = 'expanded';
			store.filterText = '\\.pdf$';
			store.view.setSort({ key: 'name', direction: 'desc' });
			flushSync();
			const descending = [
				['z/', 0], ['z/zulu.pdf', 1], ['z/alpha.pdf', 1],
				['a/', 0], ['a/zulu.pdf', 1], ['a/alpha.pdf', 1],
			];
			expect(store.treeRows.map(row => [row.obj.name, row.depth])).toEqual(descending);
			store.filterText = '';
			store.view.setFilter('type', ['application/pdf']);
			flushSync();
			expect(store.treeRows.map(row => [row.obj.name, row.depth])).toEqual(descending);
			store.view.setSort({ key: 'name', direction: 'asc' });
			flushSync();
			expect(store.treeRows.map(row => [row.obj.name, row.depth])).toEqual([
				['a/', 0], ['a/alpha.pdf', 1], ['a/zulu.pdf', 1],
				['z/', 0], ['z/alpha.pdf', 1], ['z/zulu.pdf', 1],
			]);
		} finally {
			cleanup();
			listing[''] = originalRoot;
			delete listing['a/'];
			delete listing['z/'];
			localStorage.removeItem('objectBrowser.view');
		}
	});

	it('keeps grid facets scoped to direct children despite cached matching descendants', async () => {
		let store!: ObjectBrowserStore;
		const cleanup = $effect.root(() => {
			store = createObjectBrowserStore({
				mode: () => 'user', containerName: () => 'sample-artifacts',
				token: () => 'token', projectId: () => 'project-a', ownerKey: () => 'grid-facet-fixture',
			});
		});
		try {
			flushSync();
			await tick();
			await store.fetchDir('');
			await store.fetchDir('docs/');
			store.viewMode = 'list';
			store.view.setFilter('type', ['application/pdf']);
			flushSync();
			expect(store.treeRows.map(row => row.obj.name)).toEqual(['docs/', 'docs/manual.pdf']);
			store.viewMode = 'grid';
			flushSync();
			expect(store.view.rows).toEqual([]);
			expect(store.gridRows).toEqual([]);
			expect(store.visibleObjectCount).toBe(0);
			store.toggleSelectAll();
			expect(store.selectedCount).toBe(0);
			store.searchScope = 'all';
			store.filterText = '\\.pdf$';
			await store.fetchAllObjects();
			flushSync();
			expect(store.gridRows.map(row => [row.obj.name, row.fullPath])).toEqual([['docs/manual.pdf', true]]);
			store.toggleSelectAll();
			expect([...store.selected]).toEqual(['docs/manual.pdf']);
		} finally {
			cleanup();
			localStorage.removeItem('objectBrowser.view');
		}
	});

	it.each(['regex', 'facet'])('excludes context-only directories from recursive bulk targets for a PDF-only %s projection', async (condition) => {
		const original = listing['docs/'];
		listing['docs/'] = [...original, { name: 'docs/notes.txt', bytes: 10, content_type: 'text/plain', last_modified: '', etag: 'txt' }];
		vi.mocked(api.post).mockClear();
		let store!: ObjectBrowserStore;
		const cleanup = $effect.root(() => {
			store = createObjectBrowserStore({
				mode: () => 'user', containerName: () => 'sample-artifacts',
				token: () => 'token', projectId: () => 'project-a', ownerKey: () => 'context-only-target-fixture',
			});
		});
		try {
			flushSync();
			await tick();
			await store.fetchDir('');
			await store.fetchDir('docs/');
			store.viewMode = 'list';
			if (condition === 'regex') {
				store.searchScope = 'expanded';
				store.filterText = '\\.pdf$';
			} else store.view.setFilter('type', ['application/pdf']);
			flushSync();
			expect(store.treeRows.map(row => [row.obj.name, row.contextOnly])).toEqual([
				['docs/', true], ['docs/manual.pdf', false],
			]);
			expect(store.visibleObjectCount).toBe(1);
			store.toggleSelect('docs/');
			expect(store.selectedCount).toBe(0);
			store.toggleSelectAll();
			expect([...store.selected]).toEqual(['docs/manual.pdf']);
			// A stale externally retained directory must also fail the final bulk-target projection.
			store.selected = new Set([...store.selected, 'docs/']);
			expect(store.selectedCount).toBe(1);
			await store.bulkDelete();
			expect(api.post).toHaveBeenCalledExactlyOnceWith(
				'/api/v1/object-storage/sample-artifacts/objects/bulk-delete',
				{ objects: ['docs/manual.pdf'], recursive: true }, 'token', 'project-a',
			);
		} finally {
			cleanup();
			listing['docs/'] = original;
			localStorage.removeItem('objectBrowser.view');
		}
	});

	it.each([' ', '\t'])('keeps literal whitespace query %j in all-scope matching without a current-folder fallback', async (whitespace) => {
		const originalRoot = listing[''];
		const originalDocs = listing['docs/'];
		const currentName = `current${whitespace}match.txt`;
		const remoteName = `docs/remote${whitespace}match.pdf`;
		listing[''] = [...originalRoot, { name: currentName, bytes: 10, content_type: 'text/plain', last_modified: '', etag: 'current' }];
		listing['docs/'] = [...originalDocs, { name: remoteName, bytes: 10, content_type: 'application/pdf', last_modified: '', etag: 'remote' }];
		const allResponse = Promise.withResolvers<unknown[]>();
		let store!: ObjectBrowserStore;
		const cleanup = $effect.root(() => {
			store = createObjectBrowserStore({
				mode: () => 'user', containerName: () => 'sample-artifacts',
				token: () => 'token', projectId: () => 'project-a', ownerKey: () => 'whitespace-all-fixture',
			});
		});
		try {
			flushSync();
			await tick();
			await store.fetchDir('');
			store.viewMode = 'grid';
			expect(store.gridRows.some(row => row.obj.name === currentName)).toBe(true);
			allListingRequest = () => allResponse.promise;
			store.searchScope = 'all';
			store.filterText = whitespace;
			flushSync();
			expect(store.allObjectsLoading).toBe(true);
			expect(store.view.rows).toEqual([]);
			expect(store.gridRows).toEqual([]);
			expect(api.get).toHaveBeenCalledWith('/api/v1/object-storage/sample-artifacts/objects?delimiter=', 'token', 'project-a');
			allResponse.resolve([...listing[''], ...listing['docs/']]);
			await allResponse.promise;
			await tick();
			expect(store.filterText).toBe(whitespace);
			expect(store.gridRows.map(row => [row.obj.name, row.fullPath])).toEqual([[currentName, true], [remoteName, true]]);
			expect(store.gridRows.every(row => !row.contextOnly)).toBe(true);
		} finally {
			allResponse.resolve([]);
			allListingRequest = undefined;
			cleanup();
			listing[''] = originalRoot;
			listing['docs/'] = originalDocs;
			localStorage.removeItem('objectBrowser.view');
		}
	});
});

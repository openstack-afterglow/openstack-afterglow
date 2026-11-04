const media = vi.hoisted(() => {
 const events = new EventTarget();
 const query = { matches: true, media: '(min-width: 1024px)', onchange: null, addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events), addListener: () => undefined, removeListener: () => undefined };
 vi.stubGlobal('matchMedia', () => query);
 return query;
});

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
		withExperience() { return this; },
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

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ObjectBrowserStore } from '$lib/stores/objectBrowser.svelte';
import ObjectCardGridHarness from './ObjectCardGridHarness.svelte';
import ObjectBrowser from '$lib/components/ObjectBrowser.svelte';
import { api } from '$lib/api/client';
import { captureFlowExperience, type CapturedFlowExperience } from '$lib/stores/__tests__/experienceFlowHarness';
import { get } from 'svelte/store';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, projectSwitching, setAuth } from '$lib/stores/auth';
import { authDisplayContext } from '$lib/stores/authDisplayContext';
import { siteConfig } from '$lib/config/site';
import { refreshAuthState } from '$lib/utils/authSession';

const createObjectURL = vi.fn(() => 'blob:thumb');
const revokeObjectURL = vi.fn();

beforeEach(() => {
	vi.clearAllMocks();
 media.matches = true;
 media.dispatchEvent(new Event('change'));
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

	it('fades cards in on first arrival only, never on refresh or filter typing', async () => {
		const rootListing = listing[''];
		let store!: ObjectBrowserStore;
		render(ObjectCardGridHarness, { onstore: (s: ObjectBrowserStore) => { store = s; } });
		const card = (name: string) => screen.getByRole('button', { name });
		const entering = (name: string) => card(name).parentElement!.classList.contains('motion-fade');
		try {
			await screen.findByRole('button', { name: '폴더 docs' });
			expect(entering('폴더 docs')).toBe(true);
			expect(entering('파일 photo.png')).toBe(true);

			// A manual refresh swaps in the skeleton and remounts every card.
			const before = card('파일 photo.png');
			await store.refreshAll();
			await tick();
			expect(card('파일 photo.png')).not.toBe(before);
			expect(entering('파일 photo.png')).toBe(false);
			expect(entering('폴더 docs')).toBe(false);

			store.filterText = 'bundle';
			await waitFor(() => expect(screen.queryByRole('button', { name: '파일 photo.png' })).toBeNull());
			store.filterText = '';
			await screen.findByRole('button', { name: '파일 photo.png' });
			expect(entering('파일 photo.png')).toBe(false);

			// Polling that brings a genuinely new object animates only that card.
			listing[''] = [
				...rootListing,
				{ name: 'report.csv', bytes: 512, content_type: 'text/csv', last_modified: '2026-09-03T00:00:00Z', etag: 'e-csv' },
			];
			await store.refreshAll({ silent: true });
			await screen.findByRole('button', { name: '파일 report.csv' });
			expect(entering('파일 report.csv')).toBe(true);
			expect(entering('파일 bundle.zip')).toBe(false);
		} finally {
			listing[''] = rootListing;
		}
	});
 it('retains selection and folder navigation when tablet cards replace the desktop grid', async () => {
  await renderGrid();
  await fireEvent.click(screen.getByRole('button', { name: '파일 photo.png' }));
  media.matches = false;
  media.dispatchEvent(new Event('change'));
  await waitFor(() => expect(screen.queryByRole('heading', { name: '폴더' })).toBeNull());
  await waitFor(() => expect(within(screen.getByRole('button', { name: '파일 photo.png' })).queryByRole('presentation')).toBeNull());
  expect(screen.getByTestId('selected-names').textContent).toBe('photo.png');
  expect(screen.getAllByRole('button', { name: '파일 photo.png' })).toHaveLength(1);
  await fireEvent.click(screen.getByRole('checkbox', { name: '표시된 오브젝트 전체 선택' }).closest('label')!);
  expect(screen.getByTestId('selected-names').textContent).toBe('docs/,bundle.zip,photo.png');
  await fireEvent.keyDown(screen.getByRole('button', { name: '폴더 docs' }), { key: 'Enter' });
  await waitFor(() => expect(screen.getByTestId('prefix').textContent).toBe('docs/'));
  expect(await screen.findByRole('button', { name: '파일 manual.pdf' })).toBeTruthy();
 });
});

describe('ObjectBrowser failed read boundaries', () => {
	let flow: CapturedFlowExperience;
	let failListing: boolean;
	const originalGet = vi.mocked(api.get).getMockImplementation()!;
	const originalAuth = get(auth), originalReady = get(authReady), originalSwitching = get(projectSwitching), originalSite = get(siteConfig);
	const retained = { name: 'retained.bin', bytes: 10, content_type: 'application/octet-stream', last_modified: '', etag: 'safe-etag' };
	beforeEach(() => {
		localStorage.setItem('objectBrowser.view', 'grid');
		failListing = false;
		auth.set({ ...originalAuth, sessionId: 'object-browser-session', token: 'token-a', refreshToken: 'refresh-a',
			userId: 'user-a', username: 'User A', projectId: 'project-a', projectName: 'Project A',
			domainId: 'domain-a', domainName: 'Domain A', identityDomainId: 'domain-a', identityDomainName: 'Domain A',
			roles: ['member'], canWrite: true, isSystemAdmin: false, isDomainManager: false, canCreateDomain: false, federated: false });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		projectSwitching.set(false);
		flow = captureFlowExperience('/dashboard/object-storage/buckets/:name', () => get(auth));
		vi.mocked(api.get).mockImplementation(async (path: string) => {
			if (!path.includes('/objects?')) return null;
			if (failListing) throw new Error('PRIVATE_PROVIDER_BODY_CANARY');
			return [retained];
		});
	});
	afterEach(() => {
		cleanup();
		flow.collector.destroy();
		vi.restoreAllMocks();
		vi.mocked(api.get).mockImplementation(originalGet);
		localStorage.removeItem('objectBrowser.view');
		auth.set(originalAuth);
		authReady.set(originalReady);
		projectSwitching.set(originalSwitching);
		siteConfig.set(originalSite);
	});

	it('shows an unavailable read instead of empty or no-results and records the real manual failure without draft content', async () => {
		failListing = true;
		render(ObjectBrowser, { mode: 'user', containerName: 'private-bucket', token: 'token-a', projectId: 'project-a' });
		await screen.findByRole('alert');
		expect(screen.queryByText('오브젝트가 없습니다')).toBeNull();
		const filter = screen.getByRole('searchbox');
		await fireEvent.input(filter, { target: { value: 'PRIVATE_FILTER_CANARY' } });
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await waitFor(() => expect(vi.mocked(api.get).mock.calls.filter(([path]) => path.includes('/objects?'))).toHaveLength(2));
		await tick();
		const events = await flow.flush();
		expect(screen.queryByText('검색 결과가 없습니다')).toBeNull();
		expect((filter as HTMLInputElement).value).toBe('PRIVATE_FILTER_CANARY');
		expect(events.some((event) => event.event_type === 'action.started' && event.feature === 'object_storage')).toBe(true);
		expect(events.some((event) => event.event_type === 'result.applied')).toBe(true);
		const started = events.find((event) => event.event_type === 'action.started' && event.feature === 'object_storage');
		expect(started?.action_id).toBeTruthy();
		const failedStates = events.filter((event) => event.event_type === 'view.state_changed'
			&& event.payload.state === 'error' && event.action_id === started?.action_id);
		expect(failedStates).toHaveLength(1);
		const failed = failedStates[0];
		const failedSpan = 'span_id' in failed ? failed.span_id : undefined;
		expect(typeof failedSpan).toBe('string');
		const failedSpanEvents = events.filter((event) => event.action_id === started?.action_id
			&& 'span_id' in event && event.span_id === failedSpan);
		expect(failedSpanEvents.some((event) => event.event_type === 'result.applied')).toBe(true);
		expect(failedSpanEvents.some((event) => event.payload.state === 'empty')).toBe(false);
		expect(JSON.stringify(events)).not.toMatch(/PRIVATE_FILTER_CANARY|PRIVATE_PROVIDER_BODY_CANARY|private-bucket/);
		expect(document.body.textContent).not.toContain('PRIVATE_PROVIDER_BODY_CANARY');
	});

	it('retains the valid same-owner row and filter when a later read fails', async () => {
		render(ObjectBrowser, { mode: 'user', containerName: 'private-bucket', token: 'token-a', projectId: 'project-a' });
		await screen.findByRole('button', { name: '파일 retained.bin' });
		const filter = screen.getByRole('searchbox');
		await fireEvent.input(filter, { target: { value: 'retained' } });
		failListing = true;
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await screen.findByRole('alert');
		expect(screen.getByRole('button', { name: '파일 retained.bin' })).toBeTruthy();
		expect((filter as HTMLInputElement).value).toBe('retained');
		expect(screen.queryByText('검색 결과가 없습니다')).toBeNull();
	});

	it('keeps the failed directory cache during a partial refresh while publishing successful sibling rows as an error-state listing', async () => {
		const directory = { name: 'docs/', bytes: 0, content_type: 'application/directory', last_modified: '', etag: '', is_dir: true };
		const child = { ...retained, name: 'docs/retained.bin' };
		let partialFailure = false;
		vi.mocked(api.get).mockImplementation(async (path: string) => {
			if (!path.includes('/objects?')) return null;
			const prefix = new URL(path, 'http://test').searchParams.get('prefix') ?? '';
			if (prefix === 'docs/') {
				if (partialFailure) throw new Error('PRIVATE_DIRECTORY_ERROR_CANARY');
				return [child];
			}
			return partialFailure ? [directory, retained, { ...retained, name: 'new.bin' }] : [directory, retained];
		});
		let store!: ObjectBrowserStore;
		render(ObjectCardGridHarness, { onstore: (value: ObjectBrowserStore) => { store = value; } });
		await screen.findByRole('button', { name: '폴더 docs' });
		await store.toggleExpand('docs/');
		store.viewMode = 'list';
		store.toggleSelect(child.name);
		await flow.flush();
		flow.events.length = 0;
		partialFailure = true;
		await store.refreshAll();
		await tick();
		expect(store.loadError).toBe(true);
		expect(store.treeRows.some((row) => row.obj.name === child.name)).toBe(true);
		expect(store.selected.has(child.name)).toBe(true);
		expect(screen.getByRole('button', { name: '파일 new.bin' })).toBeTruthy();
		const events = await flow.flush();
		expect(events.some((event) => event.payload.state === 'error')).toBe(true);
		expect(JSON.stringify(events)).not.toContain('PRIVATE_DIRECTORY_ERROR_CANARY');
	});

	it('keeps a verified rotation in the same logical owner without refetching or dropping its pending result or filter', async () => {
		const pending = Promise.withResolvers<unknown[]>();
		let reads = 0;
		vi.mocked(api.get).mockImplementation(async (path: string) => {
			if (!path.includes('/objects?')) return null;
			reads += 1;
			return reads === 1 ? [retained] : pending.promise;
		});
		const props = { mode: 'user' as const, containerName: 'private-bucket', token: 'token-a', projectId: 'project-a' };
		const view = render(ObjectBrowser, props);
		await screen.findByRole('button', { name: '파일 retained.bin' });
		const filter = screen.getByRole('searchbox');
		await fireEvent.input(filter, { target: { value: 'retained' } });
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await waitFor(() => expect(reads).toBe(2));
		const current = get(auth);
		const priorDisplayOwner = get(authDisplayContext).key;
		setAuth(refreshAuthState({
			token: 'rotated-token', refresh_token: 'rotated-refresh', user_id: current.userId!, username: 'User A',
			domain_id: 'domain-a', domain_name: 'Domain A', identity_domain_id: 'domain-a', identity_domain_name: 'Domain A',
			project_id: 'project-a', project_name: 'Project A', roles: ['member'], is_system_admin: false,
			can_write: true, is_domain_manager: false, can_create_domain: false,
			available_domains: [{ id: 'domain-a', name: 'Domain A' }], auth_method: 'password',
			expires_at: new Date(Date.now() + 3_600_000).toISOString(),
		}, current));
		expect(get(authReady)).toBe(true);
		expect(get(authDisplayContext).key).toBe(priorDisplayOwner);
		await view.rerender({ ...props, token: 'rotated-token' });
		pending.resolve([{ ...retained, name: 'retained-new.bin' }]);
		await screen.findByRole('button', { name: '파일 retained-new.bin' });
		expect((filter as HTMLInputElement).value).toBe('retained');
		expect(reads).toBe(2);
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it.each(['container', 'project', 'mode', 'opaque-credential', 'actor', 'home', 'authority', 'ready-ABA', 'base-ABA'] as const)(
		'does not retain or republish old rows after a %s owner transition and a failed new read',
		async (transition) => {
			const pending = Promise.withResolvers<unknown[]>();
			let reads = 0;
			vi.mocked(api.get).mockImplementation(async (path: string) => {
				if (!path.includes('/objects?')) return null;
				reads += 1;
				if (reads === 1) return [retained];
				if (reads === 2) return pending.promise;
				throw new Error('PRIVATE_NEW_OWNER_FAILURE');
			});
			const props = { mode: 'user' as 'user' | 'admin', containerName: 'private-bucket', token: 'token-a', projectId: 'project-a' };
			const view = render(ObjectBrowser, props);
			await screen.findByRole('button', { name: '파일 retained.bin' });
			await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
			await waitFor(() => expect(reads).toBe(2));
			const next = { ...props };
			if (transition === 'container') next.containerName = 'other-bucket';
			if (transition === 'project') next.projectId = 'other-project';
			if (transition === 'mode') next.mode = 'admin';
			if (transition === 'opaque-credential') next.token = 'unverified-prop-token';
			if (transition === 'actor') auth.update((state) => ({ ...state, userId: 'other-user' }));
			if (transition === 'home') auth.update((state) => ({ ...state, identityDomainId: 'other-home' }));
			if (transition === 'authority') auth.update((state) => ({ ...state, roles: ['reader'], canWrite: false }));
			if (transition === 'ready-ABA') { authReady.set(false); authReady.set(true); }
			if (transition === 'base-ABA') {
				const original = get(siteConfig);
				siteConfig.update((state) => ({ ...state, runtime: { ...state.runtime, api_base: 'http://unavailable.invalid' } }));
				siteConfig.set(original);
			}
			await view.rerender(next);
			await screen.findByRole('alert');
			pending.resolve([{ ...retained, name: 'LATE_OLD_OWNER_CANARY.bin' }]);
			await pending.promise;
			await tick(); await tick();
			expect(screen.queryByRole('button', { name: '파일 retained.bin' })).toBeNull();
			expect(document.body.textContent).not.toContain('LATE_OLD_OWNER_CANARY');
			expect(document.body.textContent).not.toContain('PRIVATE_NEW_OWNER_FAILURE');
		},
	);
});

import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api }));

async function loadModules(token: string) {
	// A new module graph models a page load, with a real logical login owner.
	const authModule = await import('$lib/stores/auth');
	authModule.setLoginAuth({ token, userId: 'alice', identityDomainId: 'home', domainId: 'work', projectId: 'project' });
	const statusModule = await import('../status');
	return { ...authModule, ...statusModule };
}

beforeEach(() => {
	vi.resetModules();
	api.get.mockReset();
	api.post.mockReset();
	localStorage.clear();
	sessionStorage.clear();
});

describe('tutorial status logical-session cache', () => {
	it('deduplicates concurrent and completed loads for an unchanged logical session', async () => {
		api.get.mockResolvedValue({ statuses: { 'admin-compute': 'completed' } });
		const modules = await loadModules('token-a');

		await Promise.all([modules.loadTutorialStatuses(), modules.loadTutorialStatuses()]);
		await modules.loadTutorialStatuses();

		expect(api.get).toHaveBeenCalledTimes(1);
		expect(get(modules.tutorialStatuses)).toEqual({ 'admin-compute': 'completed' });
		expect(get(modules.tutorialStatusesLoaded)).toBe(true);
	});

	it('loads a new logical login and ignores a late response from the previous login', async () => {
		const gateA = Promise.withResolvers<unknown>();
		const gateB = Promise.withResolvers<unknown>();
		api.get
			.mockReturnValueOnce(gateA.promise)
			.mockReturnValueOnce(gateB.promise);
		const modules = await loadModules('token-a');

		const first = modules.loadTutorialStatuses();
		modules.setLoginAuth({ token: 'token-b', userId: 'alice', identityDomainId: 'home', domainId: 'work', projectId: 'project' });
		const second = modules.loadTutorialStatuses();
		gateB.resolve({ statuses: { 'admin-storage': 'dismissed' } });
		await second;
		gateA.resolve({ statuses: { 'admin-compute': 'completed' } });
		await first;

		expect(api.get).toHaveBeenCalledTimes(2);
		expect(get(modules.tutorialStatuses)).toEqual({ 'admin-storage': 'dismissed' });
		expect(get(modules.tutorialStatusesLoaded)).toBe(true);
	});

	it('keeps pending and completed display history across bearer rotation', async () => {
		const pending = Promise.withResolvers<unknown>();
		api.get.mockReturnValueOnce(pending.promise);
		const modules = await loadModules('token-a');
		const first = modules.loadTutorialStatuses();
		modules.auth.update(state => ({ ...state, token: 'rotated' }));
		await modules.loadTutorialStatuses();
		pending.resolve({ statuses: { 'admin-compute': 'completed' } });
		await first;
		modules.auth.update(state => ({ ...state, token: 'rotated-again' }));
		await modules.loadTutorialStatuses();
		expect(api.get).toHaveBeenCalledOnce();
		expect(get(modules.tutorialStatuses)).toEqual({ 'admin-compute': 'completed' });
		expect(get(modules.tutorialStatusesLoaded)).toBe(true);
	});

	it.each(['sessionId', 'userId', 'identityDomainId', 'domainId', 'projectId'] as const)(
		'clears history synchronously and fences late %s ABA replies', async field => {
			const modules = await loadModules('token-a');
			api.get.mockResolvedValueOnce({ statuses: { 'admin-compute': 'completed' } });
			await modules.loadTutorialStatuses();
			const late = Promise.withResolvers<unknown>();
			api.get.mockReturnValueOnce(late.promise).mockResolvedValueOnce({ statuses: { 'admin-storage': 'dismissed' } });
			const old = modules.loadTutorialStatuses(true);
			const original = get(modules.auth);
			modules.auth.set({ ...original, [field]: 'other' });
			modules.auth.set(original);
			expect(get(modules.tutorialStatuses)).toEqual({});
			expect(get(modules.tutorialStatusesLoaded)).toBe(false);
			await modules.loadTutorialStatuses();
			late.resolve({ statuses: { 'admin-compute': 'completed' } }); await old;
			expect(api.get).toHaveBeenCalledTimes(3);
			expect(get(modules.tutorialStatuses)).toEqual({ 'admin-storage': 'dismissed' });
		});

	it('uses the latest bearer for manual refresh and protects newer reads and optimistic records', async () => {
		const modules = await loadModules('token-a');
		const old = Promise.withResolvers<unknown>();
		const latest = Promise.withResolvers<unknown>();
		api.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise);
		api.post.mockResolvedValue({});
		const first = modules.loadTutorialStatuses();
		modules.auth.update(state => ({ ...state, token: 'rotated' }));
		const second = modules.loadTutorialStatuses(true);
		await modules.recordTutorialStatus('admin-compute', 'completed');
		latest.resolve({ statuses: { 'admin-storage': 'dismissed' } }); await second;
		old.resolve({ statuses: {} }); await first;
		expect(api.get.mock.calls.map(call => call[1])).toEqual(['token-a', 'rotated']);
		expect(get(modules.tutorialStatuses)).toEqual({ 'admin-storage': 'dismissed', 'admin-compute': 'completed' });
	});

	it.each(['GET before POST', 'POST before GET'] as const)('preserves an already pending optimistic record when %s settles', async order => {
		const modules = await loadModules('token-a');
		const post = Promise.withResolvers<unknown>();
		const read = Promise.withResolvers<unknown>();
		api.post.mockReturnValueOnce(post.promise);
		api.get.mockReturnValueOnce(read.promise);
		const record = modules.recordTutorialStatus('admin-compute', 'completed');
		const reload = modules.loadTutorialStatuses(true);
		expect(get(modules.tutorialStatuses)).toEqual({ 'admin-compute': 'completed' });
		if (order === 'POST before GET') { post.resolve({}); await record; }
		read.resolve({ statuses: {} }); await reload;
		if (order === 'GET before POST') { post.resolve({}); await record; }
		await modules.loadTutorialStatuses();
		expect(api.get).toHaveBeenCalledOnce();
		expect(get(modules.tutorialStatuses)).toEqual({ 'admin-compute': 'completed' });
		expect(get(modules.tutorialStatusesLoaded)).toBe(true);
	});

	it('allows retry after a failed load', async () => {
		api.get
			.mockRejectedValueOnce(new Error('temporary'))
			.mockResolvedValueOnce({ statuses: { 'admin-system': 'completed' } });
		const modules = await loadModules('token-retry');

		await modules.loadTutorialStatuses();
		expect(get(modules.tutorialStatusesLoaded)).toBe(false);
		await modules.loadTutorialStatuses();

		expect(api.get).toHaveBeenCalledTimes(2);
		expect(get(modules.tutorialStatuses)).toEqual({ 'admin-system': 'completed' });
		expect(get(modules.tutorialStatusesLoaded)).toBe(true);
	});
});

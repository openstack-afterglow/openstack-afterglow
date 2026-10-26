import { beforeEach, describe, expect, it, vi } from 'vitest';
const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
vi.mock('../client', () => ({ api }));
import { workspaceIam, adminDomainBudgets, quotaBlocked, type DomainBudgets } from '../workspaceIam';
import type { IamSession } from '../domainIam';

const session = (overrides: Partial<IamSession> = {}): IamSession => ({ token: () => 'token', domainId: 'domain', userId: 'user', isCurrent: () => true, canSubmit: () => true, ...overrides });
beforeEach(() => vi.resetAllMocks());

describe('workspace quota API authority and mutation contracts', () => {
	it('blocks writes during revalidation but allows current observations', async () => {
		const client = workspaceIam(session({ canSubmit: () => false }));
		await client.budgets();
		await expect(client.defaults(0, {})).rejects.toMatchObject({ name: 'AbortError' });
		await expect(client.saveProject('project', { instances: 0 })).rejects.toMatchObject({ name: 'AbortError' });
		expect(api.put).not.toHaveBeenCalled();
	});
	it('fences stale successes and stale failures after revocation', async () => {
		for (const failure of [false, true]) {
			let current = true;
			const { promise, resolve, reject } = Promise.withResolvers<unknown>();
			api.get.mockReturnValue(promise);
			const read = workspaceIam(session({ isCurrent: () => current })).resources();
			current = false;
			if (failure) reject(new Error('stale forbidden')); else resolve({ private: 'stale data' });
			await expect(read).rejects.toMatchObject({ name: 'AbortError' });
		}
	});
	it('fences forecast responses after authority changes', async () => {
		let current = true;
		const pending = Promise.withResolvers<unknown>();
		api.get.mockReturnValue(pending.promise);
		const read = workspaceIam(session({ isCurrent: () => current })).forecast();
		current = false;
		pending.resolve({ domain_id: 'domain', entries: [] });
		await expect(read).rejects.toMatchObject({ name: 'AbortError' });
	});
	it('does not dispatch an admin action after the selected domain or authority changes', async () => {
		const client = adminDomainBudgets('domain', { token: () => 'token', projectId: () => undefined, isCurrent: () => false });
		await expect(client.load()).rejects.toMatchObject({ name: 'AbortError' });
		await expect(client.save(0, {})).rejects.toMatchObject({ name: 'AbortError' });
		await expect(client.reconcile('op')).rejects.toMatchObject({ name: 'AbortError' });
		expect(api.get).not.toHaveBeenCalled(); expect(api.put).not.toHaveBeenCalled(); expect(api.post).not.toHaveBeenCalled();
	});
	it('honors durable blockers independently of recent operation history', () => {
		const data = { allocation_blocked: true, operations: [] } as unknown as DomainBudgets;
		expect(quotaBlocked(data)).toBe(true);
		expect(quotaBlocked({ ...data, allocation_blocked: false })).toBe(false);
	});
});

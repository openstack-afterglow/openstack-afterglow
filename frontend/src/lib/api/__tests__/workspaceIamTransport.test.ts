import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { workspaceIam } from '../workspaceIam';

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE: 'http://localhost:8000' } }));
const fetchMock = vi.fn();
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); });
afterEach(() => vi.unstubAllGlobals());

it.each(['resources', 'forecast', 'budgets'] as const)('never rejoins an obsolete %s flight after domain A→B→A', async method => {
	const old = Promise.withResolvers<Response>();
	fetchMock.mockReturnValueOnce(old.promise);
	fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ revision: 'fresh' }), { status: 200 }));
	let current = true;
	const original = workspaceIam({ token: () => 'same-token', userId: 'same-user', domainId: 'domain-a', isCurrent: () => current, canSubmit: () => true });
	const stale = expect(original[method]()).rejects.toMatchObject({ name: 'AbortError' });
	current = false;
	const returned = workspaceIam({ token: () => 'same-token', userId: 'same-user', domainId: 'domain-a', isCurrent: () => true, canSubmit: () => true });
	await expect(returned[method]()).resolves.toMatchObject({ revision: 'fresh' });
	expect(fetchMock).toHaveBeenCalledTimes(2);
	old.resolve(new Response(JSON.stringify({ revision: 'obsolete' }), { status: 200 }));
	await stale;
});

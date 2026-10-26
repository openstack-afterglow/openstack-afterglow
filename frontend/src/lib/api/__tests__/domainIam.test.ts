import { beforeEach, describe, expect, it, vi } from 'vitest';
const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));
vi.mock('../client', () => ({ api }));
import { domainIam } from '../domainIam';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (cause: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
beforeEach(() => vi.resetAllMocks());
describe('domain IAM verification leases', () => {
	it('allows only context verification before authority is current', async () => {
		const client = domainIam({ token: () => 'token', domainId: 'domain', userId: 'user', isCurrent: () => false, canSubmit: () => true });
		api.get.mockResolvedValue({ domain_id: 'domain', domain_name: 'Domain', is_domain_manager: true });
		await expect(client.context()).resolves.toMatchObject({ domain_id: 'domain' });
		await expect(client.users()).rejects.toMatchObject({ name: 'AbortError' });
		await expect(client.invite('new@example.com', [])).rejects.toMatchObject({ name: 'AbortError' });
		expect(api.get).toHaveBeenCalledTimes(1); expect(api.post).not.toHaveBeenCalled();
	});
	it('rejects private data received after the verification lease is invalidated', async () => {
		let current = true;
		const client = domainIam({ token: () => 'token', domainId: 'domain', userId: 'user', isCurrent: () => current, canSubmit: () => true });
		const pending = deferred<unknown>(); api.get.mockReturnValue(pending.promise);
		const read = client.users(); current = false; pending.resolve({ items: [{ name: 'stale-user' }] });
		await expect(read).rejects.toMatchObject({ name: 'AbortError' });
	});
	it('prevents stale forbidden responses from revoking a newly verified view', async () => {
		let epoch = 1; const captured = epoch;
		const client = domainIam({ token: () => 'same-token', domainId: 'domain', userId: 'user', isCurrent: () => epoch === captured, canSubmit: () => true });
		const pending = deferred<unknown>(); api.get.mockReturnValue(pending.promise);
		const read = client.users(); epoch++;
		pending.reject(Object.assign(new Error('old denied'), { status: 403 }));
		await expect(read).rejects.toMatchObject({ name: 'AbortError' });
	});
	it('refuses an awaited destructive action before the stale component has unmounted', async () => {
		let current = true;
		const client = domainIam({ token: () => 'token', domainId: 'domain', userId: 'user', isCurrent: () => current, canSubmit: () => true });
		const decision = deferred<boolean>();
		const remove = async () => { if (await decision.promise) await client.deleteProvider('provider'); };
		const action = remove(); current = false; decision.resolve(true);
		await expect(action).rejects.toMatchObject({ name: 'AbortError' });
		expect(api.delete).not.toHaveBeenCalled();
	});
	it('blocks mutations while the same session is awaiting authority revalidation', async () => {
		const client = domainIam({ token: () => 'token', domainId: 'domain', userId: 'user', isCurrent: () => true, canSubmit: () => false });
		await expect(client.invite('joined@example.com', [])).rejects.toMatchObject({ name: 'AbortError' });
		expect(api.post).not.toHaveBeenCalled();
	});
});

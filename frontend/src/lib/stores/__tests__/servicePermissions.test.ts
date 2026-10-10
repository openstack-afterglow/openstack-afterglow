import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get, writable } from 'svelte/store';
const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
vi.mock('../auth', () => ({
	auth: writable({ token: 'a', projectId: 'a', userId: 'u', roles: ['member'], isSystemAdmin: false }),
	authReady: writable(true), projectSwitching: writable(false),
}));
import { auth, authReady, projectSwitching } from '../auth';
import { serviceCapabilities, serviceDenials, projectPermissions } from '../servicePermissions';
const settle = async () => { await Promise.resolve(); await Promise.resolve(); };
import type { ProjectPermissions } from '../servicePermissions';
const permissions = (leaves: string[]): ProjectPermissions => ({ is_owner: false, is_manager: false, can_write: true, service_permissions: { lumen: leaves } });
let stop: (() => void) | undefined;
beforeEach(() => { vi.resetAllMocks(); auth.update(state => ({ ...state, token: 'a', projectId: 'a', userId: 'u', roles: ['member'], isSystemAdmin: false })); authReady.set(true); projectSwitching.set(false); });
afterEach(() => { stop?.(); stop = undefined; });
describe('API leaf service capabilities', () => {
	it('never substitutes native member writes for service permission and honors narrow leaves', async () => {
		mocks.get.mockResolvedValue(permissions(['lumen-chat_user']));
		stop = serviceCapabilities.subscribe(() => {});
		expect(get(serviceCapabilities)('lumen-chat_user')).toBe(false);
		expect(get(serviceDenials)('lumen-chat_user')).toBe(false);
		await settle();
		expect(get(serviceCapabilities)('lumen-chat_user')).toBe(true);
		expect(get(serviceCapabilities)('lumen-images_user')).toBe(false);
		expect(get(serviceDenials)('lumen-images_user')).toBe(true);
		expect(get(serviceCapabilities)('lumen-tools_user')).toBe(false);
		expect(get(serviceCapabilities)('waygate-clients_editor')).toBe(false);
	});
	it('clears grants synchronously across A → B → A and ignores late responses', async () => {
		const old = Promise.withResolvers<ProjectPermissions>();
		const current = Promise.withResolvers<ProjectPermissions>();
		mocks.get.mockReturnValueOnce(old.promise).mockResolvedValueOnce(permissions([])).mockReturnValueOnce(current.promise);
		stop = serviceCapabilities.subscribe(() => {});
		auth.update(state => ({ ...state, projectId: 'b' }));
		auth.update(state => ({ ...state, projectId: 'a' }));
		old.resolve(permissions(['lumen-resources_admin'])); await settle();
		expect(get(serviceCapabilities)('lumen-resources_admin')).toBe(false);
		current.resolve(permissions(['lumen-chat_user'])); await settle();
		expect(get(serviceCapabilities)('lumen-chat_user')).toBe(true);
		projectSwitching.set(true);
		expect(get(serviceCapabilities)('lumen-chat_user')).toBe(false);
		expect(get(serviceDenials)('lumen-chat_user')).toBe(false);
	});
	it('fails closed on provider errors and does not invent a Palimpsest system-admin bypass', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: true }));
		mocks.get.mockRejectedValue(new Error('unavailable'));
		stop = serviceCapabilities.subscribe(() => {}); await settle();
		expect(get(projectPermissions).error).toBe('unavailable');
		expect(get(projectPermissions).loading).toBe(false);
		expect(get(serviceCapabilities)('palimpsest-keys_admin')).toBe(false);
		expect(get(serviceCapabilities)('drover-clusters_admin')).toBe(false);
		expect(get(serviceDenials)('drover-clusters_admin')).toBe(false);
	});
	it('blocks actions during same-identity token renewal without falsely reporting revocation', async () => {
		const pending = Promise.withResolvers<ProjectPermissions>();
		mocks.get.mockResolvedValueOnce(permissions(['lumen-audio_user'])).mockReturnValueOnce(pending.promise);
		stop = serviceCapabilities.subscribe(() => {}); await settle();
		expect(get(serviceCapabilities)('lumen-audio_user')).toBe(true);
		auth.update(state => ({ ...state, token: 'renewed' }));
		expect(get(serviceCapabilities)('lumen-audio_user')).toBe(false);
		expect(get(serviceDenials)('lumen-audio_user')).toBe(false);
		pending.resolve(permissions([])); await settle();
		expect(get(serviceCapabilities)('lumen-audio_user')).toBe(false);
		expect(get(serviceDenials)('lumen-audio_user')).toBe(true);
	});
	it('ignores the old project failure without settling a newer project request', async () => {
		const old = Promise.withResolvers<ProjectPermissions>();
		const current = Promise.withResolvers<ProjectPermissions>();
		mocks.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
		stop = serviceCapabilities.subscribe(() => {});
		auth.update(state => ({ ...state, projectId: 'b' }));
		old.reject(new Error('old project denied')); await settle();
		expect(get(projectPermissions)).toEqual({ permissions: null, loading: true, error: '' });
		current.resolve(permissions(['lumen-chat_user'])); await settle();
		expect(get(projectPermissions).loading).toBe(false);
		expect(get(projectPermissions).error).toBe('');
		expect(get(serviceCapabilities)('lumen-chat_user')).toBe(true);
	});
});

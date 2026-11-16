import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class extends Error {} }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'me', sessionId: 'session', identityDomainId: 'home', domainId: 'domain', projectId: 'project' }),
	authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false),
}));
import { auth } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/account';
import KeypairsSection from '../KeypairsSection.svelte';
let saved: string | null;
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en'); saved = null;
	auth.set({ token: 'token', userId: 'me', sessionId: 'session', identityDomainId: 'home', domainId: 'domain', projectId: 'project' } as never);
	mocks.get.mockImplementation(async (path: string) => path === '/api/v1/keypairs'
		? [{ name: 'main-key', fingerprint: 'fingerprint', type: 'ssh' }]
		: { keypair_name: saved });
	mocks.put.mockImplementation(async (_path, body) => { saved = body.keypair_name; return { keypair_name: saved }; });
	mocks.confirm.mockResolvedValue(true); mocks.delete.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); initLocale('ko'); });
describe('default SSH key', () => {
	it('sets a default, shows its badge, and clears it', async () => {
		render(KeypairsSection);
		const set = (await screen.findAllByRole('button', { name: t('keypairs.setDefault') }))[0];
		await waitFor(() => expect((set as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(set);
		await screen.findAllByText(t('keypairs.default'));
		expect(mocks.put).toHaveBeenCalledWith('/api/v1/profile/ssh-key-preference', { keypair_name: 'main-key' }, 'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
		await fireEvent.click(screen.getAllByRole('button', { name: t('keypairs.clearDefault') })[0]);
		await waitFor(() => expect(screen.queryAllByText(t('keypairs.default'))).toHaveLength(0));
		expect(saved).toBeNull();
	});
	it('loads the saved default and removes its badge after deletion', async () => {
		saved = 'main-key'; render(KeypairsSection);
		await screen.findAllByText(t('keypairs.default'));
		mocks.delete.mockImplementation(async () => { saved = null; });
		await fireEvent.click(screen.getAllByRole('button', { name: t('keypairs.delete') })[0]);
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/api/v1/keypairs/main-key', 'token', 'project'));
		await waitFor(() => expect(screen.queryAllByText(t('keypairs.default'))).toHaveLength(0));
	});
	it('requires reload after an uncertain preference write', async () => {
		mocks.put.mockRejectedValueOnce(new Error('lost response')); render(KeypairsSection);
		const set = (await screen.findAllByRole('button', { name: t('keypairs.setDefault') }))[0] as HTMLButtonElement;
		await waitFor(() => expect(set.disabled).toBe(false)); await fireEvent.click(set);
		await screen.findByRole('alert'); expect(set.disabled).toBe(true);
		expect(mocks.put).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('keypairs.defaultReload') }));
		await waitFor(() => expect((screen.getAllByRole('button', { name: t('keypairs.setDefault') })[0] as HTMLButtonElement).disabled).toBe(false));
	});
	it('discards a late preference response after owner ABA', async () => {
		const pending = Promise.withResolvers<{ keypair_name: string | null }>();
		let first = true;
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/keypairs') return Promise.resolve([{ name: 'main-key', fingerprint: 'fingerprint', type: 'ssh' }]);
			if (first) { first = false; return pending.promise; }
			return Promise.resolve({ keypair_name: null });
		});
		render(KeypairsSection);
		auth.update(value => ({ ...value, identityDomainId: 'foreign' }));
		auth.update(value => ({ ...value, identityDomainId: 'home' }));
		pending.resolve({ keypair_name: 'main-key' });
		await waitFor(() => expect(screen.queryAllByText(t('keypairs.default'))).toHaveLength(0));
	});
});

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'me', sessionId: 'session', identityDomainId: 'home', domainId: 'personal', projectId: 'project' }),
	authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false),
}));
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/account';
import LoginPreferenceSection from '../LoginPreferenceSection.svelte';
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set({ token: 'token', userId: 'me', sessionId: 'session', identityDomainId: 'home', domainId: 'personal', projectId: 'project' } as never);
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	mocks.get.mockResolvedValue({ remember_last_workspace: false }); mocks.put.mockResolvedValue({ remember_last_workspace: true });
});
afterEach(() => { cleanup(); initLocale('ko'); });
describe('account login preference', () => {
	it('is opt-in and saves only the explicit boolean without arbitrary browser target IDs', async () => {
		render(LoginPreferenceSection);
		const checkbox = await screen.findByRole('checkbox', { name: t('loginPreference.remember') }) as HTMLInputElement;
		await waitFor(() => expect(checkbox.disabled).toBe(false)); expect(checkbox.checked).toBe(false);
		await fireEvent.click(checkbox); await fireEvent.click(screen.getByRole('button', { name: t('loginPreference.save') }));
		expect(mocks.put).toHaveBeenCalledExactlyOnceWith('/api/v1/profile/login-preference', { remember_last_workspace: true }, 'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
		await screen.findByText(t('loginPreference.saved'));
	});
	it('requires an explicit reload after an uncertain save and never replays', async () => {
		mocks.put.mockRejectedValueOnce(new Error('private'));
		render(LoginPreferenceSection);
		const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
		await waitFor(() => expect(checkbox.disabled).toBe(false));
		await fireEvent.click(checkbox); await fireEvent.click(screen.getByRole('button', { name: t('loginPreference.save') }));
		await screen.findByRole('alert');
		expect((screen.getByRole('button', { name: t('loginPreference.save') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.put).toHaveBeenCalledTimes(1); expect(document.body.textContent).not.toContain('private');
		await fireEvent.click(screen.getByRole('button', { name: t('loginPreference.reload') }));
		await waitFor(() => expect(checkbox.disabled).toBe(false));
	});
	it.each(['identity', 'logout', 'readiness'] as const)('discards a late load after same-tick %s ABA', async kind => {
		const pending = Promise.withResolvers<{ remember_last_workspace: boolean }>(); mocks.get.mockReturnValueOnce(pending.promise);
		render(LoginPreferenceSection);
		if (kind === 'identity') { auth.update(state => ({ ...state, identityDomainId: 'foreign' })); auth.update(state => ({ ...state, identityDomainId: 'home' })); }
		else { const store = kind === 'logout' ? logoutInProgress : authReady; store.set(kind === 'logout'); store.set(kind !== 'logout'); }
		pending.resolve({ remember_last_workspace: true });
		await waitFor(() => expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(false));
		expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
	});
});

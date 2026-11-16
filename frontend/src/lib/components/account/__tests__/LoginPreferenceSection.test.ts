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
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/auth/domains') return [{ id: 'team', name: 'Team' }, { id: 'other', name: 'Other' }];
		if (path.includes('/api/v1/auth/workspaces')) return { projects: [{ id: 'work', name: 'Work' }] };
		return { remember_last_workspace: true };
	});
	mocks.put.mockResolvedValue({ remember_last_workspace: true });
});
afterEach(() => { cleanup(); initLocale('ko'); });
describe('account login preference', () => {
	it('defaults to reconnect and saves enabled without a browser-supplied target', async () => {
		render(LoginPreferenceSection);
		expect(screen.getByRole('heading', { level: 2, name: t('loginPreference.title') }).classList.contains('text-sm')).toBe(true);
		const checkbox = await screen.findByRole('checkbox', { name: t('loginPreference.remember') }) as HTMLInputElement;
		await waitFor(() => expect(checkbox.disabled).toBe(false)); expect(checkbox.checked).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('loginPreference.save') }));
		expect(mocks.put).toHaveBeenCalledExactlyOnceWith('/api/v1/profile/login-preference', { remember_last_workspace: true }, 'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
		expect((await screen.findByText(t('loginPreference.saved'))).closest('[role="status"]')?.classList.contains('alert-flat')).toBe(true);
	});
	it('requires a manual domain and project after unchecking and saves that exact pair', async () => {
		render(LoginPreferenceSection);
		const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
		await waitFor(() => expect(checkbox.disabled).toBe(false));
		await fireEvent.click(checkbox);
		const domain = await screen.findByRole('combobox', { name: t('loginPreference.domain') });
		await waitFor(() => expect((domain as HTMLSelectElement).disabled).toBe(false));
		const save = screen.getByRole('button', { name: t('loginPreference.save') }) as HTMLButtonElement;
		expect(save.disabled).toBe(true);
		await fireEvent.change(domain, { target: { value: 'team' } });
		const project = screen.getByRole('combobox', { name: t('loginPreference.project') });
		await waitFor(() => expect((project as HTMLSelectElement).disabled).toBe(false));
		expect(save.disabled).toBe(true);
		await fireEvent.change(project, { target: { value: 'work' } });
		await fireEvent.click(save);
		expect(mocks.put).toHaveBeenCalledExactlyOnceWith('/api/v1/profile/login-preference',
			{ remember_last_workspace: false, domain_id: 'team', project_id: 'work' },
			'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
		await waitFor(() => expect(checkbox.disabled).toBe(false));
		await fireEvent.click(checkbox);
		expect(screen.queryByRole('combobox')).toBeNull();
		await fireEvent.click(save);
		expect(mocks.put).toHaveBeenLastCalledWith('/api/v1/profile/login-preference',
			{ remember_last_workspace: true }, 'token', 'project', { cache: 'no-store', replayOnUnauthorized: false });
	});
	it('keeps a legacy opt-out incomplete until a fixed workspace is chosen', async () => {
		mocks.get.mockResolvedValueOnce({ remember_last_workspace: false });
		render(LoginPreferenceSection);
		const domain = await screen.findByRole('combobox', { name: t('loginPreference.domain') }) as HTMLSelectElement;
		await waitFor(() => expect(domain.disabled).toBe(false));
		expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
		expect(domain.value).toBe('');
		expect((screen.getByRole('button', { name: t('loginPreference.save') }) as HTMLButtonElement).disabled).toBe(true);
	});
	it('restores a fixed pair from fresh membership lists', async () => {
		mocks.get.mockResolvedValueOnce({ remember_last_workspace: false, domain_id: 'team', project_id: 'work' });
		render(LoginPreferenceSection);
		await waitFor(() => expect((screen.getByRole('button', { name: t('loginPreference.save') }) as HTMLButtonElement).disabled).toBe(false));
		expect((screen.getByRole('combobox', { name: t('loginPreference.domain') }) as HTMLSelectElement).value).toBe('team');
		expect((screen.getByRole('combobox', { name: t('loginPreference.project') }) as HTMLSelectElement).value).toBe('work');
	});
	it('discards late manual project choices after mode changes and requires a new selection', async () => {
		const pending = Promise.withResolvers<{ projects: { id: string; name: string }[] }>();
		let reads = 0;
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/auth/domains') return [{ id: 'team', name: 'Team' }];
			if (path.includes('/api/v1/auth/workspaces')) return ++reads === 1 ? pending.promise : { projects: [{ id: 'fresh', name: 'Fresh project' }] };
			return { remember_last_workspace: true };
		});
		render(LoginPreferenceSection);
		const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
		await waitFor(() => expect(checkbox.disabled).toBe(false));
		await fireEvent.click(checkbox);
		const domain = await screen.findByRole('combobox', { name: t('loginPreference.domain') });
		await waitFor(() => expect((domain as HTMLSelectElement).disabled).toBe(false));
		await fireEvent.change(domain, { target: { value: 'team' } });
		await fireEvent.click(checkbox);
		await fireEvent.click(checkbox);
		pending.resolve({ projects: [{ id: 'stale', name: 'Stale project' }] });
		await waitFor(() => expect((screen.getByRole('combobox', { name: t('loginPreference.domain') }) as HTMLSelectElement).disabled).toBe(false));
		await screen.findByRole('option', { name: /Fresh project/ });
		expect(screen.queryByRole('option', { name: /Stale project/ })).toBeNull();
		expect((screen.getByRole('button', { name: t('loginPreference.save') }) as HTMLButtonElement).disabled).toBe(true);
	});
	it('does not offer saving when the manual membership directory fails', async () => {
		mocks.get.mockResolvedValueOnce({ remember_last_workspace: false });
		mocks.get.mockRejectedValueOnce(new Error('private'));
		render(LoginPreferenceSection);
		await screen.findByRole('alert');
		expect((screen.getByRole('button', { name: t('loginPreference.save') }) as HTMLButtonElement).disabled).toBe(true);
		expect(document.body.textContent).not.toContain('private');
	});
	it('requires an explicit reload after an uncertain save and never replays', async () => {
		mocks.put.mockRejectedValueOnce(new Error('private'));
		render(LoginPreferenceSection);
		const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
		await waitFor(() => expect(checkbox.disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: t('loginPreference.save') }));
		expect((await screen.findByRole('alert')).classList.contains('alert-flat')).toBe(true);
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
		pending.resolve({ remember_last_workspace: false });
		await waitFor(() => expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(false));
		expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
	});
});

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get, writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), invalidate: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, put: mocks.put } }));
vi.mock('$lib/stores/workspaceController.svelte', () => ({ invalidateWorkspaceDisplaySnapshots: mocks.invalidate }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({}), authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false)
}));

import { auth, authReady, logoutInProgress, projectSwitching, type AuthState } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/account';
import PersonalProjectLabelSection from '../PersonalProjectLabelSection.svelte';

const path = '/api/v1/projects/project/display-name';
const nativeName = 'person-abcdefgh12345678';
const original = { project_id: 'project', display_name: nativeName, native_name: nativeName, can_edit: true };
const renamed = { ...original, display_name: 'My research' };
function fixture(): AuthState {
	return {
		token: 'token', refreshToken: 'refresh', accessExpiresAt: 123456789, userId: 'me', username: 'person', sessionId: 'session',
		identityDomainId: 'home', identityDomainName: 'Accounts', domainId: 'personal', domainName: 'Personal', projectId: 'project',
		projectName: nativeName, availableProjects: [{ id: 'project', name: nativeName }, { id: 'other', name: 'Other' }],
		roles: ['member'], isSystemAdmin: false, isDomainManager: false, canWrite: true, federated: false,
		availableDomains: [{ id: 'personal', name: 'Personal', kind: 'personal' }]
	};
}
async function edit(value = 'My research') {
	const input = await screen.findByRole('textbox', { name: t('personalLabel.name') }) as HTMLInputElement;
	await fireEvent.input(input, { target: { value } });
	return input;
}
async function submit(input: HTMLInputElement) { await fireEvent.submit(input.closest('form')!); }

beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set(fixture()); authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	mocks.get.mockResolvedValue(original); mocks.put.mockResolvedValue(renamed);
});
afterEach(() => { cleanup(); initLocale('ko'); });

describe('Personal project display name', () => {
	it('allows a native member owner to save only display metadata and publishes after fresh exact readback', async () => {
		const put = Promise.withResolvers<unknown>(), readback = Promise.withResolvers<unknown>();
		mocks.put.mockReturnValueOnce(put.promise);
		mocks.get.mockResolvedValueOnce(original).mockReturnValueOnce(readback.promise);
		const before = fixture(); render(PersonalProjectLabelSection);
		const input = await edit('  My research  ');
		await submit(input);
		const save = screen.getByRole('button', { name: t('personalLabel.save') }) as HTMLButtonElement;
		expect(save.disabled).toBe(true); expect(input.disabled).toBe(true);
		expect(mocks.put).toHaveBeenCalledExactlyOnceWith(path, { display_name: 'My research' }, 'token', 'project', {
			cache: 'no-store', replayOnUnauthorized: false, signal: expect.any(AbortSignal)
		});
		expect(get(auth)).toEqual(before);
		put.resolve(renamed);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		expect(get(auth)).toEqual(before); expect(mocks.invalidate).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenLastCalledWith(path, 'token', 'project', {
			refresh: true, cache: 'no-store', replayOnUnauthorized: false, signal: expect.any(AbortSignal)
		});
		readback.resolve(renamed);
		await screen.findByText(t('personalLabel.saved'));
		expect(get(auth)).toEqual({ ...before, projectName: 'My research', availableProjects: [{ id: 'project', name: 'My research' }, before.availableProjects[1]] });
		expect(mocks.invalidate).toHaveBeenCalledTimes(1);
		expect(input.value).toBe('My research'); expect(screen.getByText(nativeName)).toBeTruthy();
	});

	it.each([false, true])('renders a non-owner read-only without relying on system administrator status (%s)', async admin => {
		auth.update(state => ({ ...state, isSystemAdmin: admin }));
		mocks.get.mockResolvedValue({ ...original, display_name: 'Existing label', can_edit: false });
		const before = get(auth); render(PersonalProjectLabelSection);
		await screen.findByText('Existing label');
		expect(screen.queryByRole('textbox')).toBeNull(); expect(screen.queryByRole('button', { name: t('personalLabel.save') })).toBeNull();
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.invalidate).not.toHaveBeenCalled(); expect(get(auth)).toEqual(before);
	});

	it.each(['read-error', 'wrong-label', 'wrong-project', 'native-rename', 'owner-revoked', 'unknown-put'] as const)('requires explicit reload after an unconfirmed %s', async failure => {
		mocks.get.mockResolvedValueOnce(original);
		if (failure === 'read-error') mocks.get.mockRejectedValueOnce(new Error('private transport detail'));
		else if (failure === 'wrong-label') mocks.get.mockResolvedValueOnce(original);
		else if (failure === 'wrong-project') mocks.get.mockResolvedValueOnce({ ...renamed, project_id: 'foreign' });
		else if (failure === 'native-rename') mocks.get.mockResolvedValueOnce({ ...renamed, native_name: 'changed-native' });
		else if (failure === 'owner-revoked') mocks.get.mockResolvedValueOnce({ ...renamed, can_edit: false });
		else mocks.put.mockResolvedValueOnce({});
		const before = get(auth); render(PersonalProjectLabelSection);
		await submit(await edit());
		await screen.findByText(t('personalLabel.saveFailed'));
		expect(get(auth)).toEqual(before); expect(mocks.invalidate).not.toHaveBeenCalled(); expect(screen.queryByRole('textbox')).toBeNull();
		expect(screen.queryByText(t('personalLabel.saved'))).toBeNull(); expect(document.body.textContent).not.toContain('private transport detail');
		mocks.get.mockResolvedValue(original);
		await fireEvent.click(screen.getByRole('button', { name: t('personalLabel.reload') }));
		expect((await screen.findByRole('textbox') as HTMLInputElement).value).toBe(nativeName);
		expect(mocks.put).toHaveBeenCalledTimes(1);
	});

	it('does not publish or replay a failed mutation', async () => {
		mocks.put.mockRejectedValueOnce(new Error('private'));
		render(PersonalProjectLabelSection); await submit(await edit());
		await screen.findByText(t('personalLabel.saveFailed'));
		expect(get(auth).projectName).toBe(nativeName); expect(mocks.put).toHaveBeenCalledTimes(1); expect(mocks.get).toHaveBeenCalledTimes(1);
		expect(mocks.invalidate).not.toHaveBeenCalled();
	});

	it('keeps failed fresh reads distinct from read-only permission', async () => {
		mocks.get.mockRejectedValueOnce(new Error('unavailable'));
		render(PersonalProjectLabelSection); await screen.findByText(t('personalLabel.loadFailed'));
		expect(screen.queryByText(t('personalLabel.readOnly'))).toBeNull(); expect(screen.queryByRole('textbox')).toBeNull();
		expect(mocks.put).not.toHaveBeenCalled();
	});

	it.each(['', '  ', 'a'.repeat(65), 'x\u007fy', 'x\u200by'])('rejects invalid input without dispatching (%j)', async value => {
		render(PersonalProjectLabelSection); await submit(await edit(value));
		await screen.findByText(t('personalLabel.invalid')); expect(mocks.put).not.toHaveBeenCalled();
	});

	it('accepts 64 Unicode codepoints rather than counting surrogate halves', async () => {
		const label = '🧪'.repeat(64); const response = { ...original, display_name: label };
		mocks.put.mockResolvedValueOnce(response); mocks.get.mockResolvedValueOnce(original).mockResolvedValueOnce(response);
		render(PersonalProjectLabelSection); await submit(await edit(label));
		await screen.findByText(t('personalLabel.saved')); expect(get(auth).projectName).toBe(label);
	});

	const transitions = ['actor', 'home', 'project', 'domain', 'session', 'token', 'authority', 'readiness', 'logout', 'switch'] as const;
	function aba(kind: typeof transitions[number]) {
		if (kind === 'readiness') { authReady.set(false); authReady.set(true); }
		else if (kind === 'logout') { logoutInProgress.set(true); logoutInProgress.set(false); }
		else if (kind === 'switch') { projectSwitching.set(true); projectSwitching.set(false); }
		else {
			const key = { actor: 'userId', home: 'identityDomainId', project: 'projectId', domain: 'domainId', session: 'sessionId', token: 'token', authority: 'isSystemAdmin' }[kind] as keyof AuthState;
			const before = get(auth); auth.update(state => ({ ...state, [key]: kind === 'authority' ? true : 'foreign' })); auth.set(before);
		}
	}
	it.each(transitions)('discards a late initial read after same-tick %s ABA', async kind => {
		const pending = Promise.withResolvers<unknown>(); mocks.get.mockReturnValueOnce(pending.promise);
		render(PersonalProjectLabelSection); aba(kind); pending.resolve(renamed);
		const input = await screen.findByRole('textbox') as HTMLInputElement;
		await waitFor(() => expect(input.value).toBe(nativeName));
		expect(get(auth).projectName).toBe(nativeName); expect(mocks.invalidate).not.toHaveBeenCalled();
	});
	it.each(transitions.flatMap(kind => [{ kind, stage: 'put' }, { kind, stage: 'readback' }] as const))('discards late $stage after same-tick $kind ABA', async ({ kind, stage }) => {
		const pending = Promise.withResolvers<unknown>();
		if (stage === 'put') mocks.put.mockReturnValueOnce(pending.promise);
		else mocks.get.mockResolvedValueOnce(original).mockReturnValueOnce(pending.promise);
		render(PersonalProjectLabelSection); await submit(await edit());
		if (stage === 'readback') await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		aba(kind); pending.resolve(renamed); await pending.promise;
		await waitFor(() => expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe(nativeName));
		expect(get(auth).projectName).toBe(nativeName); expect(mocks.invalidate).not.toHaveBeenCalled();
		expect(screen.queryByText(t('personalLabel.saved'))).toBeNull(); expect(mocks.put).toHaveBeenCalledTimes(1);
	});

	it('does not start a request until exact actor/home/scope verification is ready', async () => {
		authReady.set(false); render(PersonalProjectLabelSection); expect(mocks.get).not.toHaveBeenCalled();
		authReady.set(true); await screen.findByRole('textbox'); expect(mocks.get).toHaveBeenCalledTimes(1);
	});
	it('discards a successful readback after unmount', async () => {
		const pending = Promise.withResolvers<unknown>(); mocks.get.mockResolvedValueOnce(original).mockReturnValueOnce(pending.promise);
		const view = render(PersonalProjectLabelSection); await submit(await edit());
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2)); view.unmount(); pending.resolve(renamed); await pending.promise;
		expect(get(auth).projectName).toBe(nativeName); expect(mocks.invalidate).not.toHaveBeenCalled();
	});
});

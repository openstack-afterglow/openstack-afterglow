import { cleanup, fireEvent, render as renderSvelte, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	apiPost: vi.fn(),
	apiDelete: vi.fn(),
}));

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => {
	return {
		api: {
			get: (path: string, ...args: unknown[]) => {
				const resource = wizardResource(path);
				return resource === undefined ? mocks.apiGet(path, ...args) : Promise.resolve(resource);
			},
			post: mocks.apiPost,
			delete: mocks.apiDelete,
		},
		ApiError: class ApiError extends Error {},
		fetchWithAuth: vi.fn(),
		getBaseUrl: () => '',
	};
});

import Wrapper from './_WizardConsumerWrapper.svelte';
import type { VmCreateStore } from '$lib/stores/vmCreateStore.svelte';
import { auth } from '$lib/stores/auth';
import { wizard } from '$lib/stores/wizard';

import { prepareWizardConsumer, wizardResource } from './wizardConsumerFixtures';
import type { GithubSshProfile } from '$lib/types/compute';
import { t } from '$lib/i18n/ns/vm-wizard';

let store: VmCreateStore;
function configCanNext(): boolean {
	return store.canNext;
}

async function renderConfig() {
	// Mount the consumer after authoritative options, as the panel's loading gate does.
	const sshDraft = get(wizard);
	wizard.update(w => ({ ...w, step: 5, sshAccessMode: 'keypair', githubUsername: '', githubProfile: null }));
	const view = renderSvelte(Wrapper, { component: 'footer', onStore: value => { store = value; } });
	await store.loadBootOptions();
	await store.loadFlavorOptions();
	await tick();
	wizard.update(w => ({ ...w, sshAccessMode: sshDraft.sshAccessMode, githubUsername: sshDraft.githubUsername, githubProfile: sshDraft.githubProfile }));
	await tick();
	await view.rerender({ component: 'config' });
	return view;
}

afterEach(cleanup);
beforeEach(() => {
	prepareWizardConsumer(5);
	mocks.apiGet.mockResolvedValue({ history: [], presets: [] });
});

function deferredProfile() {
	let resolve!: (profile: GithubSshProfile) => void;
	let reject!: (error: Error) => void;
	const promise = new Promise<GithubSshProfile>((resolvePromise, rejectPromise) => {
		resolve = resolvePromise;
		reject = rejectPromise;
	});
	return { promise, resolve, reject };
}

describe('WizardStep5Config ordinary root disk', () => {
	beforeEach(() => {
		prepareWizardConsumer(5);
		auth.update(a => ({ ...a, token: null }));
		wizard.update(w => ({ ...w, bootVolumeSizeGb: 32, deleteBootVolumeOnTermination: false }));
	});

	it('shows editable size and deletion controls for image boot', async () => {
		await renderConfig();

		const size = screen.getByRole('spinbutton', { name: `${t('config.rootDisk.label')} *` }) as HTMLInputElement;
		const deleteWithVm = screen.getByRole('checkbox', { name: t('config.rootDisk.deleteWithVm') }) as HTMLInputElement;
		expect(size.id).toBe('boot-volume-size');
		expect(size.value).toBe('32');
		expect(size.min).toBe('1');
		expect(size.max).toBe('16384');
		expect(deleteWithVm.checked).toBe(false);

		await fireEvent.input(size, { target: { value: '96' } });
		await fireEvent.click(deleteWithVm);
		expect(get(wizard).bootVolumeSizeGb).toBe(96);
		expect(get(wizard).deleteBootVolumeOnTermination).toBe(true);
	});

	it.each(['existing-root', null])('shows existing volume guidance without size or deletion controls for volume name %s', async volumeName => {
		wizard.update(w => ({ ...w, bootSource: 'volume', bootVolumeId: 'volume-a', bootVolumeName: volumeName }));
		const { container } = await renderConfig();

		expect(container.querySelector('#boot-volume-size')).toBeNull();
		expect(screen.queryByRole('checkbox', { name: t('config.rootDisk.deleteWithVm') })).toBeNull();
		expect(screen.getByText(volumeName ?? 'volume-a')).toBeTruthy();
		expect(get(wizard).bootVolumeSizeGb).toBe(32);
		expect(get(wizard).deleteBootVolumeOnTermination).toBe(false);
	});
});

describe('WizardStep5Config cloud-init library', () => {
	beforeEach(() => {
		prepareWizardConsumer(5);
		wizard.update(w => ({
			...w,
			bootSource: 'image',
			imageId: 'image-a',
			cloudInit: '#cloud-config\npackages: [htop]',
			keyName: 'test-keypair',
		}));
		auth.set({
			token: 'test-token',
			refreshToken: null,
			accessExpiresAt: null,
			userId: 'user-a',
			username: 'user-a',
			projectId: 'project-a',
			projectName: 'Project A',
			availableProjects: [],
			roles: [],
			isSystemAdmin: false,
			federated: false,
		});
		mocks.apiGet.mockReset();
		mocks.apiPost.mockReset();
		mocks.apiDelete.mockReset();
		mocks.apiPost.mockResolvedValue({ id: 1 });
	});

	it('loads a saved snippet into cloud-init and saves the edited content as a preset', async () => {
		mocks.apiGet.mockResolvedValue({
			history: [],
			presets: [{
				id: 1,
				kind: 'preset',
				name: 'bootstrap',
				content: '#cloud-config\npackages: [git]',
				created_at: '2026-07-20T00:00:00+00:00',
			}],
		});
		const { container } = await renderConfig();

		await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledWith(
			'/api/v1/instances/cloud-init/library', 'test-token', 'project-a',
		));
		await fireEvent.change(screen.getByLabelText('저장된 항목 불러오기'), { target: { value: '1' } });
		expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toContain('packages: [git]');

		await fireEvent.input(screen.getByLabelText('저장 이름'), { target: { value: 'git setup' } });
		await fireEvent.click(screen.getByRole('button', { name: '현재 내용 저장' }));
		await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledWith(
			'/api/v1/instances/cloud-init/presets',
			{ name: 'git setup', content: '#cloud-config\npackages: [git]' },
			'test-token',
			'project-a',
		));
	});
});

describe('WizardStep5Config GitHub SSH verification', () => {
	const verifiedProfile = {
		id: 583231,
		login: 'OctoCat',
		name: 'The Octocat',
		public_email: null,
		html_url: 'https://github.com/OctoCat',
		has_public_keys: true,
		verified_at: '2026-09-20T00:00:00+00:00',
	};

	beforeEach(() => {
		vi.useFakeTimers();
		prepareWizardConsumer(5);
		wizard.update(w => ({ ...w, bootSource: 'image', imageId: 'image-a', sshAccessMode: 'github' }));
		auth.set({
			token: 'test-token',
			refreshToken: null,
			accessExpiresAt: null,
			userId: 'user-a',
			username: 'user-a',
			projectId: 'project-a',
			projectName: 'Project A',
			availableProjects: [],
			roles: [],
			isSystemAdmin: false,
			federated: false,
		});
		mocks.apiGet.mockReset();
		mocks.apiPost.mockReset();
		mocks.apiDelete.mockReset();
		mocks.apiGet.mockImplementation((path: string) =>
			path === '/api/v1/instances/github-users/history'
				? Promise.resolve([
					{ id: 583231, login: 'OctoCat', verified_at: '2026-09-20T00:00:00+00:00' },
					{ id: 1, login: 'hubot', verified_at: '2026-09-20T00:00:00+00:00' },
				])
				: Promise.resolve({ history: [], presets: [] }),
		);
		mocks.apiPost.mockResolvedValue(verifiedProfile);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('verifies a typed username once and stores the canonical login for creation', async () => {
		await renderConfig();

		await fireEvent.input(screen.getByLabelText(/GitHub 사용자 ID/), { target: { value: 'octocat' } });
		await vi.advanceTimersByTimeAsync(400);

		expect(mocks.apiPost).toHaveBeenCalledTimes(1);
		expect(mocks.apiPost).toHaveBeenCalledWith(
			'/api/v1/instances/github-users/lookup',
			{ username: 'octocat' },
			'test-token',
			'project-a',
		);
		expect(get(wizard).githubUsername).toBe('OctoCat');
		expect(get(wizard).githubProfile).toEqual(verifiedProfile);
		expect(screen.getByText(/공개 SSH 키 확인됨/)).toBeTruthy();

		await vi.advanceTimersByTimeAsync(1000);
		expect(mocks.apiPost).toHaveBeenCalledTimes(1);
	});

	it('never calls the verification API for a malformed username', async () => {
		await renderConfig();

		await fireEvent.input(screen.getByLabelText(/GitHub 사용자 ID/), { target: { value: 'octo--cat' } });
		await vi.advanceTimersByTimeAsync(1000);

		expect(mocks.apiPost).not.toHaveBeenCalled();
		expect(get(wizard).githubProfile).toBeNull();
		expect(screen.getByText(/1~39자의 영문자, 숫자, 하이픈/)).toBeTruthy();
	});

	it('keeps readiness and the verified profile after repeated recent-user clicks', async () => {
		await renderConfig();
		await vi.advanceTimersByTimeAsync(0);

		await fireEvent.click(screen.getByRole('button', { name: '@OctoCat' }));
		expect(configCanNext()).toBe(false);
		await vi.advanceTimersByTimeAsync(400);
		expect(configCanNext()).toBe(true);
		expect(get(wizard).githubProfile).toEqual(verifiedProfile);

		// Whitespace/case changes refer to the same verified account.
		await fireEvent.input(screen.getByLabelText(/GitHub 사용자 ID/), { target: { value: ' octocat ' } });
		expect(configCanNext()).toBe(true);
		for (let click = 0; click < 2; click += 1) {
			await fireEvent.click(screen.getByRole('button', { name: '@OctoCat' }));
			expect(get(wizard).githubProfile).toEqual(verifiedProfile);
			expect(configCanNext()).toBe(true);
			expect(screen.getByText(/공개 SSH 키 확인됨/)).toBeTruthy();
		}
		await vi.advanceTimersByTimeAsync(1000);
		expect(mocks.apiPost).toHaveBeenCalledTimes(1);
	});

	it('recognizes the matching current profile on remount without another lookup', async () => {
		wizard.update(w => ({ ...w, githubUsername: ' octocat ', githubProfile: verifiedProfile }));
		const first = await renderConfig();
		await vi.advanceTimersByTimeAsync(1000);
		expect(configCanNext()).toBe(true);
		expect(screen.getByText(/공개 SSH 키 확인됨/)).toBeTruthy();
		first.unmount();

		await renderConfig();
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByRole('button', { name: '@OctoCat' }));
		await vi.advanceTimersByTimeAsync(1000);
		expect(get(wizard).githubProfile).toEqual(verifiedProfile);
		expect(configCanNext()).toBe(true);
		expect(screen.getByText(/공개 SSH 키 확인됨/)).toBeTruthy();
		expect(mocks.apiPost).not.toHaveBeenCalled();
	});

	it('clears readiness for a different recent user until that user is verified', async () => {
		wizard.update(w => ({ ...w, githubUsername: 'OctoCat', githubProfile: verifiedProfile }));
		const lookup = deferredProfile();
		mocks.apiPost.mockReturnValue(lookup.promise);
		await renderConfig();
		await vi.advanceTimersByTimeAsync(0);

		await fireEvent.click(screen.getByRole('button', { name: '@hubot' }));
		expect(get(wizard).githubUsername).toBe('hubot');
		expect(get(wizard).githubProfile).toBeNull();
		expect(configCanNext()).toBe(false);
		expect(screen.queryByText(/공개 SSH 키 확인됨/)).toBeNull();
		await vi.advanceTimersByTimeAsync(400);
		expect(configCanNext()).toBe(false);
		expect(mocks.apiPost).toHaveBeenCalledWith(
			'/api/v1/instances/github-users/lookup', { username: 'hubot' }, 'test-token', 'project-a',
		);

		const hubot = { ...verifiedProfile, id: 1, login: 'hubot', name: 'Hubot', html_url: 'https://github.com/hubot' };
		lookup.resolve(hubot);
		await vi.advanceTimersByTimeAsync(0);
		expect(get(wizard).githubProfile).toEqual(hubot);
		expect(configCanNext()).toBe(true);
		expect(screen.getByText(/공개 SSH 키 확인됨/).textContent).toContain('hubot');
	});

	it('does not let an old lookup replace a newer verified user', async () => {
		const oldLookup = deferredProfile();
		const currentLookup = deferredProfile();
		mocks.apiPost.mockReturnValueOnce(oldLookup.promise).mockReturnValueOnce(currentLookup.promise);
		await renderConfig();
		await fireEvent.input(screen.getByLabelText(/GitHub 사용자 ID/), { target: { value: 'octocat' } });
		await vi.advanceTimersByTimeAsync(400);
		await fireEvent.click(screen.getByRole('button', { name: '@hubot' }));
		await vi.advanceTimersByTimeAsync(400);
		const hubot = { ...verifiedProfile, id: 1, login: 'hubot', name: 'Hubot', html_url: 'https://github.com/hubot' };
		currentLookup.resolve(hubot);
		await vi.advanceTimersByTimeAsync(0);
		expect(configCanNext()).toBe(true);

		oldLookup.resolve(verifiedProfile);
		await vi.advanceTimersByTimeAsync(0);
		expect(get(wizard).githubUsername).toBe('hubot');
		expect(get(wizard).githubProfile).toEqual(hubot);
		expect(configCanNext()).toBe(true);
		expect(screen.getByText(/공개 SSH 키 확인됨/).textContent).toContain('hubot');
	});

	it('rejects stale success and failure after switching away and back to the same login', async () => {
		const firstOctocat = deferredProfile();
		const hubot = deferredProfile();
		const currentOctocat = deferredProfile();
		mocks.apiPost.mockReturnValueOnce(firstOctocat.promise)
			.mockReturnValueOnce(hubot.promise).mockReturnValueOnce(currentOctocat.promise);
		await renderConfig();
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByRole('button', { name: '@OctoCat' }));
		await vi.advanceTimersByTimeAsync(400);
		await fireEvent.click(screen.getByRole('button', { name: '@hubot' }));
		await vi.advanceTimersByTimeAsync(400);
		await fireEvent.click(screen.getByRole('button', { name: '@OctoCat' }));
		await vi.advanceTimersByTimeAsync(400);
		expect(mocks.apiPost).toHaveBeenCalledTimes(3);

		firstOctocat.resolve(verifiedProfile);
		hubot.reject(new Error('stale lookup failure'));
		await vi.advanceTimersByTimeAsync(0);
		expect(get(wizard).githubProfile).toBeNull();
		expect(configCanNext()).toBe(false);
		expect(screen.queryByText('stale lookup failure')).toBeNull();

		const freshProfile = { ...verifiedProfile, name: 'Fresh Octocat' };
		currentOctocat.resolve(freshProfile);
		await vi.advanceTimersByTimeAsync(0);
		expect(get(wizard).githubProfile).toEqual(freshProfile);
		expect(configCanNext()).toBe(true);
		expect(screen.getByText(/공개 SSH 키 확인됨/).textContent).toContain('Fresh Octocat');
	});

	it.each([
		{ ...verifiedProfile, has_public_keys: false },
		{ ...verifiedProfile, login: 'hubot' },
	])('does not accept an unkeyed or mismatched lookup profile', async (profile) => {
		mocks.apiPost.mockResolvedValue(profile);
		await renderConfig();
		await fireEvent.input(screen.getByLabelText(/GitHub 사용자 ID/), { target: { value: 'octocat' } });
		await vi.advanceTimersByTimeAsync(400);
		expect(get(wizard).githubProfile).toBeNull();
		expect(configCanNext()).toBe(false);
		expect(screen.queryByText(/공개 SSH 키 확인됨/)).toBeNull();
	});

	it.each([
		{ ...verifiedProfile, has_public_keys: false },
		{ ...verifiedProfile, login: 'hubot' },
	])('revalidates rather than recognizing a stale or unkeyed current profile on mount', async (profile) => {
		wizard.update(w => ({ ...w, githubUsername: 'octocat', githubProfile: profile }));
		const lookup = deferredProfile();
		mocks.apiPost.mockReturnValue(lookup.promise);
		await renderConfig();
		await vi.advanceTimersByTimeAsync(0);
		expect(get(wizard).githubProfile).toBeNull();
		expect(configCanNext()).toBe(false);
		expect(screen.queryByText(/공개 SSH 키 확인됨/)).toBeNull();
		await vi.advanceTimersByTimeAsync(400);
		expect(mocks.apiPost).toHaveBeenCalledTimes(1);
		expect(configCanNext()).toBe(false);

		lookup.resolve(verifiedProfile);
		await vi.advanceTimersByTimeAsync(0);
		expect(get(wizard).githubProfile).toEqual(verifiedProfile);
		expect(configCanNext()).toBe(true);
	});
});

describe('WizardStep5Config Windows consumers', () => {
	it.each(['image', 'volume'] as const)('replaces native masked %s password controls with an unsupported alert without Linux fallbacks', async bootSource => {
		wizard.update(w => ({ ...w, bootSource, imageId: 'windows-native', bootVolumeId: 'windows-native', keyName: 'test-keypair' }));
		const { container } = await renderConfig();
		const password = screen.getByLabelText(t('config.windows.password'), { exact: false }) as HTMLInputElement;
		const confirmation = screen.getByLabelText(t('config.windows.confirmation'), { exact: false }) as HTMLInputElement;
		expect(password.type).toBe('password');
		expect(confirmation.type).toBe('password');
		expect(screen.getByText('GuestAdmin')).toBeTruthy();
		await fireEvent.input(password, { target: { value: 'Secret-native-123!' } });
		await fireEvent.input(confirmation, { target: { value: 'Secret-native-123!' } });
		expect((screen.getByRole('button', { name: t('footer.next') }) as HTMLButtonElement).disabled).toBe(false);

		wizard.update(w => ({ ...w, imageId: 'windows-unsupported', bootVolumeId: 'windows-unsupported', cloudInit: '#cloud-config\nsecret: stale', dataMounts: [{ fileStorageId: 'storage-a', mountPoint: '/mnt/stale', readOnly: false }] }));
		await tick();
		await tick();
		const unsupported = screen.getByTestId('windows-unsupported-config');
		expect(within(unsupported).getByRole('alert').textContent?.trim()).toBeTruthy();
		expect(screen.queryByTestId('windows-password-config')).toBeNull();
		expect(container.querySelector('input[type="password"]')).toBeNull();
		expect(container.querySelector('#create-keypair')).toBeNull();
		expect(container.querySelector('#github-username')).toBeNull();
		expect(screen.queryByRole('group', { name: t('config.ssh.modeLabel') })).toBeNull();
		expect(container.querySelector('#cloud-init')).toBeNull();
		expect(screen.queryByRole('button', { name: t('config.mounts.add') })).toBeNull();
		expect(container.textContent).not.toContain('Secret-native-123!');
		expect((screen.getByRole('button', { name: t('footer.next') }) as HTMLButtonElement).disabled).toBe(true);

		wizard.update(w => ({ ...w, bootSource: 'image', imageId: 'image-a' }));
		await tick();
		expect(screen.queryByTestId('windows-unsupported-config')).toBeNull();
		expect(container.querySelector('#create-keypair')).toBeTruthy();
		expect(container.querySelector('#cloud-init')).toBeTruthy();
		expect(screen.getByRole('button', { name: t('config.mounts.add') })).toBeTruthy();
	});
});

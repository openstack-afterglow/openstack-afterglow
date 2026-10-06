import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
	apiGet: vi.fn(),
	apiPost: vi.fn(),
	apiDelete: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: { get: mocks.apiGet, post: mocks.apiPost, delete: mocks.apiDelete },
	ApiError: class ApiError extends Error {},
}));
const vmCreateState = vi.hoisted(() => ({ githubSshEligible: false }));

vi.mock('$lib/stores/vmCreateStore.svelte', () => ({
	useVmCreate: () => ({
		adminMode: false,
		get githubSshEligible() { return vmCreateState.githubSshEligible; },
		keypairs: [{ name: 'test-keypair' }],
		networks: [],
		securityGroups: [],
		defaultNetworkId: null,
		fileStorages: [],
		selectNetwork: vi.fn(),
		selectSshAccessMode: vi.fn(),
	}),
}));

import WizardStep5Config from '../WizardStep5Config.svelte';
import { auth } from '$lib/stores/auth';
import { resetWizard, wizard } from '$lib/stores/wizard';

import { isSshAccessReady } from '$lib/utils/instanceCreate';
import type { GithubSshProfile } from '$lib/types/compute';

// Step 5's canNext delegates to this same production readiness contract.
function configCanNext(): boolean {
	return isSshAccessReady({ ...get(wizard), adminMode: false });
}

function deferredProfile() {
	let resolve!: (profile: GithubSshProfile) => void;
	let reject!: (error: Error) => void;
	const promise = new Promise<GithubSshProfile>((resolvePromise, rejectPromise) => {
		resolve = resolvePromise;
		reject = rejectPromise;
	});
	return { promise, resolve, reject };
}
describe('WizardStep5Config cloud-init library', () => {
	beforeEach(() => {
		vmCreateState.githubSshEligible = false;
		resetWizard();
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
		const { container } = render(WizardStep5Config);

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
		vmCreateState.githubSshEligible = true;
		resetWizard();
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
		render(WizardStep5Config);

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
		render(WizardStep5Config);

		await fireEvent.input(screen.getByLabelText(/GitHub 사용자 ID/), { target: { value: 'octo--cat' } });
		await vi.advanceTimersByTimeAsync(1000);

		expect(mocks.apiPost).not.toHaveBeenCalled();
		expect(get(wizard).githubProfile).toBeNull();
		expect(screen.getByText(/1~39자의 영문자, 숫자, 하이픈/)).toBeTruthy();
	});

	it('keeps readiness and the verified profile after repeated recent-user clicks', async () => {
		render(WizardStep5Config);
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
		const first = render(WizardStep5Config);
		await vi.advanceTimersByTimeAsync(1000);
		expect(configCanNext()).toBe(true);
		expect(screen.getByText(/공개 SSH 키 확인됨/)).toBeTruthy();
		first.unmount();

		render(WizardStep5Config);
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
		render(WizardStep5Config);
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
		render(WizardStep5Config);
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
		render(WizardStep5Config);
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
		render(WizardStep5Config);
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
		render(WizardStep5Config);
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

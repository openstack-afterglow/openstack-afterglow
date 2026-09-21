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
				? Promise.resolve([{ id: 583231, login: 'OctoCat', verified_at: '2026-09-20T00:00:00+00:00' }])
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

	it('reuses a previously verified user from history and re-verifies it', async () => {
		render(WizardStep5Config);
		await vi.advanceTimersByTimeAsync(0);

		await fireEvent.click(screen.getByRole('button', { name: '@OctoCat' }));
		await vi.advanceTimersByTimeAsync(400);

		expect(get(wizard).githubUsername).toBe('OctoCat');
		expect(mocks.apiPost).toHaveBeenCalledWith(
			'/api/v1/instances/github-users/lookup',
			{ username: 'OctoCat' },
			'test-token',
			'project-a',
		);
	});
});

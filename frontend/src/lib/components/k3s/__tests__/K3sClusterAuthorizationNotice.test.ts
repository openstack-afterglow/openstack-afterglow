import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { K3sClusterAuthorization, K3sClusterCredential } from '$lib/types/k3s';
import { ApiError } from '$lib/api/errors';
import { serviceCapabilities } from '$lib/stores/servicePermissions';

vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));

const mocks = vi.hoisted(() => ({
	controller: null as { cluster: { id: string; status: string }; adminMode: boolean } | null,
	getClusterAuthorization: vi.fn(),
	reauthorizeCluster: vi.fn(),
	retireClusterCredentials: vi.fn(),
}));
vi.mock('$lib/stores/k3sClusterDetailController.svelte', () => ({
	useK3sClusterDetailController: () => mocks.controller,
}));
vi.mock('$lib/api/k3s', () => ({
	getClusterAuthorization: mocks.getClusterAuthorization,
	reauthorizeCluster: mocks.reauthorizeCluster,
	retireClusterCredentials: mocks.retireClusterCredentials,
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user-a' }),
}));

import K3sClusterAuthorizationNotice from '../K3sClusterAuthorizationNotice.svelte';

const credential = (owner: string, state = 'retiring'): K3sClusterCredential => ({
	app_credential_id: `cred-${owner}`,
	purpose: 'control',
	generation: 1,
	owner_user_id: owner,
	state,
});

const statusOf = (overrides: Partial<K3sClusterAuthorization> = {}): K3sClusterAuthorization => ({
	cluster_id: 'cluster-1',
	authorized: false,
	active_generation: null,
	staged_generations: [],
	owner_revocation_required: [],
	credentials: [],
	...overrides,
});

function grant(...leaves: string[]) {
	(serviceCapabilities as unknown as ReturnType<typeof writable>).set((leaf: string) => leaves.includes(leaf));
}

function renderNotice(status = 'ACTIVE', adminMode = false) {
	mocks.controller = { cluster: { id: 'cluster-1', status }, adminMode };
	return render(K3sClusterAuthorizationNotice);
}

describe('K3sClusterAuthorizationNotice', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		grant('drover-inventory_reader');
	});

	it('lets a current clusters-admin reauthorize a cluster without resource authority', async () => {
		grant('drover-inventory_reader', 'drover-clusters_admin');
		mocks.getClusterAuthorization
			.mockResolvedValueOnce(statusOf())
			.mockResolvedValueOnce(statusOf({ staged_generations: [2] }));
		mocks.reauthorizeCluster.mockResolvedValue({ cluster_id: 'cluster-1', generation: 2, operation_id: 'op', job_id: 'job', credentials: [], retired_credential_ids: [] });
		renderNotice();

		const button = await screen.findByRole('button', { name: '재인가' });
		await fireEvent.click(button);

		expect(mocks.reauthorizeCluster).toHaveBeenCalledWith('cluster-1', 'token-a', 'project-a');
		expect(await screen.findByText('재인가 진행 중')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '재인가' })).toBeNull();
	});

	it('explains the missing capability instead of offering the action', async () => {
		mocks.getClusterAuthorization.mockResolvedValue(statusOf());
		renderNotice();

		expect(await screen.findByText('재인가에는 drover-clusters_admin 권한이 필요합니다.')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '재인가' })).toBeNull();
	});

	it('keeps the action disabled for a cluster that is not ACTIVE', async () => {
		grant('drover-inventory_reader', 'drover-clusters_admin');
		mocks.getClusterAuthorization.mockResolvedValue(statusOf());
		renderNotice('UPDATE_IN_PROGRESS');

		const button = (await screen.findByRole('button', { name: '재인가' })) as HTMLButtonElement;
		expect(button.disabled).toBe(true);
		expect(screen.getByText('ACTIVE 상태의 클러스터만 재인가할 수 있습니다.')).toBeTruthy();
	});

	it('shows the native refusal reason when reauthorization is rejected', async () => {
		grant('drover-inventory_reader', 'drover-clusters_admin');
		mocks.getClusterAuthorization.mockResolvedValue(statusOf());
		mocks.reauthorizeCluster.mockRejectedValue(new ApiError(409, 'Another cluster mutation is in progress'));
		renderNotice();

		await fireEvent.click(await screen.findByRole('button', { name: '재인가' }));
		expect(await screen.findByText('요청 실패: Another cluster mutation is in progress')).toBeTruthy();
	});

	it('stays silent for healthy authority and for routes the caller cannot read', async () => {
		mocks.getClusterAuthorization.mockResolvedValueOnce(statusOf({ authorized: true, active_generation: 1 }));
		const healthy = renderNotice();
		await waitFor(() => expect(mocks.getClusterAuthorization).toHaveBeenCalledTimes(1));
		expect(healthy.container.textContent?.trim()).toBe('');
		healthy.unmount();

		mocks.getClusterAuthorization.mockRejectedValueOnce(new ApiError(403, 'forbidden'));
		const denied = renderNotice();
		await waitFor(() => expect(mocks.getClusterAuthorization).toHaveBeenCalledTimes(2));
		expect(denied.container.textContent?.trim()).toBe('');
	});

	it('offers retirement only for the caller-owned superseded credentials', async () => {
		mocks.getClusterAuthorization
			.mockResolvedValueOnce(statusOf({
				authorized: true,
				active_generation: 2,
				owner_revocation_required: [credential('user-a'), credential('user-b')],
			}))
			.mockResolvedValueOnce(statusOf({ authorized: true, active_generation: 2, owner_revocation_required: [credential('user-b')] }));
		mocks.retireClusterCredentials.mockResolvedValue({ cluster_id: 'cluster-1', deleted_credential_ids: ['cred-user-a'], owner_revocation_required: [credential('user-b')] });
		renderNotice();

		expect(await screen.findByText('교체된 본인 소유 자격 1개가 Keystone에 남아 있습니다. 회수하면 권한만 줄어들고 클러스터 동작에는 영향이 없습니다.')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '내 이전 자격 회수' }));

		expect(mocks.retireClusterCredentials).toHaveBeenCalledWith('cluster-1', 'token-a', 'project-a');
		await waitFor(() => expect(screen.queryByRole('button', { name: '내 이전 자격 회수' })).toBeNull());
	});

	it('does not query project authority from the system-admin console', async () => {
		renderNotice('ACTIVE', true);
		await Promise.resolve();
		expect(mocks.getClusterAuthorization).not.toHaveBeenCalled();
	});
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { get, writable } from 'svelte/store';
import { auth, authReady } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/drover-pages';
import { t as common } from '$lib/i18n/ns/common';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', async () => ({ api: { get: mocks.get }, ...(await vi.importActual('$lib/api/errors')) }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: Object.assign(writable(new Map()), { load: vi.fn().mockResolvedValue(new Map()) }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [15] }) }));
import Page from './+page.svelte';
const initial = get(auth);

beforeEach(() => {
	mocks.get.mockReset();
	auth.set({ ...initial, token: 'before', userId: 'user', sessionId: 'session', projectId: 'project', domainId: 'domain', identityDomainId: 'home', isSystemAdmin: true });
	authReady.set(true);
});

describe('administrator cluster read ownership', () => {
	it('settles a current read after ordinary same-session bearer rotation', async () => {
		const { promise, resolve: finish } = Promise.withResolvers<unknown[]>();
		mocks.get.mockReturnValue(promise);
		render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalled());
		auth.update(value => ({ ...value, token: 'rotated' }));
		finish([]);
		await waitFor(() => expect(screen.getByText(t('cluster.empty'))).toBeTruthy());
		expect((screen.getByRole('button', { name: common('autoRefresh.refreshNow') }) as HTMLButtonElement).disabled).toBe(false);
	});
	it('does not announce verified empty inventory after an initial read failure', async () => {
		mocks.get.mockRejectedValue(new Error('native unavailable'));
		render(Page);
		await waitFor(() => expect(screen.getByText(t('clusterError.loadFailed'))).toBeTruthy());
		expect(screen.queryByText(t('cluster.empty'))).toBeNull();
		expect((screen.getByRole('button', { name: t('clusterError.reload') }) as HTMLButtonElement).disabled).toBe(false);
	});
});

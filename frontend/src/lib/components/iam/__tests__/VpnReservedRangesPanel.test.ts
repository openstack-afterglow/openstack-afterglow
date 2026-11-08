import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import type { VpnReservedRanges } from '$lib/api/vpnReservedRanges';
import type { IamSession } from '$lib/api/domainIam';
import { t } from '$lib/i18n/ns/vpn-reserved-ranges';
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { constructor(public status: number, message: string, public code?: string) { super(message); } } }));
import { ApiError } from '$lib/api/client';
import { parseReservedRanges } from '$lib/api/vpnReservedRanges';
import VpnReservedRangesPanel from '../VpnReservedRangesPanel.svelte';
const original = get(auth);
const snapshot = (overrides: Partial<VpnReservedRanges> = {}): VpnReservedRanges => ({ domain_id: 'domain-a', vpn_reserved_cidrs: ['10.8.0.0/24'], default_vpn_reserved_cidrs: ['10.8.0.0/24'], revision: 0, configured: false, max_ranges: 16, ...overrides });
const session = (current = true): IamSession => ({ token: () => 'manager-token', domainId: 'domain-a', userId: 'manager', isCurrent: () => current, canSubmit: () => current });
beforeEach(() => {
	vi.resetAllMocks();
	auth.set({ ...original, token: 'admin-token', sessionId: 'session-a', userId: 'admin', identityDomainId: 'domain-a', domainId: 'domain-a', projectId: 'admin-project', isSystemAdmin: true });
	authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	mocks.get.mockResolvedValue(snapshot());
});
afterEach(() => { cleanup(); auth.set(original); });

describe('VPN reserved ranges panel', () => {
	it('parses one CIDR per line or comma separated, ignoring blanks', () => {
		expect(parseReservedRanges(' 10.8.0.0/24\n\n10.9.0.0/24, 2001:db8::/48 ')).toEqual(['10.8.0.0/24', '10.9.0.0/24', '2001:db8::/48']);
		expect(parseReservedRanges('  \n ')).toEqual([]);
	});

	it('lets a system admin edit an explicit domain with the loaded revision', async () => {
		mocks.put.mockResolvedValue(snapshot({ vpn_reserved_cidrs: ['10.8.0.0/24', '10.9.0.0/24'], revision: 1, configured: true }));
		render(VpnReservedRangesPanel, { domainId: 'domain-a', adminMode: true });
		const field = await screen.findByLabelText(t('ranges')) as HTMLTextAreaElement;
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains/domain-a/vpn-reserved-ranges', 'admin-token', 'admin-project', { cache: 'no-store' });
		expect(field.value).toBe('10.8.0.0/24');
		expect(screen.getByText(t('defaultInUse', { ranges: '10.8.0.0/24' }))).toBeTruthy();
		await fireEvent.input(field, { target: { value: '10.8.0.0/24\n10.9.0.0/24' } });
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/domains/domain-a/vpn-reserved-ranges', { revision: 0, vpn_reserved_cidrs: ['10.8.0.0/24', '10.9.0.0/24'] }, 'admin-token', 'admin-project', { replayOnUnauthorized: false, beforeDispatch: expect.any(Function) }));
		await screen.findByText(t('saved'));
		expect(screen.getByText(t('configured'))).toBeTruthy();
	});

	it('uses only the session domain endpoint for a domain manager', async () => {
		// An identity change invalidates verified readiness; the manager session re-verifies.
		auth.update(state => ({ ...state, isSystemAdmin: false, token: 'manager-token' })); authReady.set(true);
		mocks.put.mockResolvedValue(snapshot({ vpn_reserved_cidrs: [], revision: 1, configured: true }));
		render(VpnReservedRangesPanel, { domainId: 'domain-a', session: session() });
		const field = await screen.findByLabelText(t('ranges'));
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/iam/vpn-reserved-ranges', 'manager-token', undefined, { cache: 'no-store' });
		await fireEvent.input(field, { target: { value: '' } });
		expect(screen.getByText(t('emptyWarning'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/api/v1/iam/vpn-reserved-ranges', { revision: 0, vpn_reserved_cidrs: [] }, 'manager-token', undefined, expect.objectContaining({ replayOnUnauthorized: false })));
	});

	it('blocks saving more than the maximum number of ranges', async () => {
		render(VpnReservedRangesPanel, { domainId: 'domain-a', adminMode: true });
		const field = await screen.findByLabelText(t('ranges'));
		await fireEvent.input(field, { target: { value: Array.from({ length: 17 }, (_, index) => `10.${index}.0.0/16`).join('\n') } });
		expect(screen.getByText(t('tooMany', { max: 16 }))).toBeTruthy();
		const save = screen.getByRole('button', { name: t('save') }) as HTMLButtonElement;
		expect(save.disabled).toBe(true);
		await fireEvent.click(save);
		expect(mocks.put).not.toHaveBeenCalled();
	});

	it('maps validation and revision conflicts to stable messages', async () => {
		render(VpnReservedRangesPanel, { domainId: 'domain-a', adminMode: true });
		const field = await screen.findByLabelText(t('ranges'));
		mocks.put.mockRejectedValueOnce(new ApiError(422, 'raw', 'vpn_reserved_ranges_invalid'));
		await fireEvent.input(field, { target: { value: '0.0.0.0/0' } });
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		await screen.findByText(t('invalid'));
		expect(screen.queryByText(t('reloadRequired'))).toBeNull();
		mocks.put.mockRejectedValueOnce(new ApiError(409, 'raw', 'revision_conflict'));
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		await screen.findByText(t('conflict'));
		await screen.findByText(t('reloadRequired'));
		expect((screen.getByRole('button', { name: t('save') }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('refuses a snapshot for another domain and does not load without authority', async () => {
		mocks.get.mockResolvedValue(snapshot({ domain_id: 'domain-b' }));
		render(VpnReservedRangesPanel, { domainId: 'domain-a', adminMode: true });
		await screen.findByText(t('scopeMismatch'));
		expect(screen.queryByLabelText(t('ranges'))).toBeNull();
		cleanup(); vi.resetAllMocks();
		auth.update(state => ({ ...state, isSystemAdmin: false })); authReady.set(true);
		render(VpnReservedRangesPanel, { domainId: 'domain-a', adminMode: true });
		await Promise.resolve();
		expect(mocks.get).not.toHaveBeenCalled();
		render(VpnReservedRangesPanel, { domainId: 'domain-a', session: session(false) });
		await Promise.resolve();
		expect(mocks.get).not.toHaveBeenCalled();
	});
});

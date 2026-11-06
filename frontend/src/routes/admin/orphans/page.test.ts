import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type * as Reactivity from 'svelte/reactivity';
import type { OrphanScanResponse } from '$lib/types/orphan';
import type * as ApiClient from '$lib/api/client';
import { t } from '$lib/i18n/ns/admin-storage';

const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async importOriginal => {
	const original = await importOriginal<typeof Reactivity>();
	return { ...original, MediaQuery: class { get current() { return viewport.desktop; } } };
});
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', async importOriginal => {
	const original = await importOriginal<typeof ApiClient>();
	return { ...original, api };
});
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'admin-token', projectId: 'admin-project' }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [30, 60, 120] }) }));
import Page from './+page.svelte';

const scan: OrphanScanResponse = {
	floating_ips: [{ id: 'fip-old', address: '192.0.2.20', project_id: 'tenant-1', created_at: '2026-09-01T00:00:00Z', age_days: 30 }],
	volumes: [], manila_shares: [], security_groups: [],
};
const emptyScan: OrphanScanResponse = { floating_ips: [], volumes: [], manila_shares: [], security_groups: [] };

beforeEach(() => {
	api.get.mockReset(); api.post.mockReset();
	Element.prototype.animate = vi.fn().mockReturnValue({ finished: Promise.resolve(), cancel: vi.fn(), play: vi.fn() });
	window.matchMedia = vi.fn().mockImplementation((query: string) => ({
		matches: viewport.desktop, media: query, onchange: null,
		addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
	}));
});
afterEach(cleanup);

describe.each([true, false])('orphan scan submission fence (desktop=%s)', desktop => {
	it('keeps selected rows mounted while rescanning but cannot open cleanup until the scan completes', async () => {
		viewport.desktop = desktop;
		const { promise: pendingScan, resolve: completeScan } = Promise.withResolvers<OrphanScanResponse>();
		api.get.mockResolvedValue(scan).mockResolvedValueOnce(scan).mockReturnValueOnce(pendingScan).mockResolvedValueOnce(emptyScan);
		api.post.mockResolvedValue({ deleted: ['fip-old'], failed: [] });
		render(Page);

		const selectionName = t('orphanSection.selectItem', { id: 'fip-old' });
		const selection = await screen.findByRole('checkbox', { name: selectionName }) as HTMLInputElement;
		await fireEvent.click(selection);
		const cleanupName = t('orphanSection.cleanSelected', { count: 1 });
		expect((screen.getByRole('button', { name: cleanupName }) as HTMLButtonElement).disabled).toBe(false);

		const age = screen.getByRole('spinbutton', { name: t('orphanPage.minAgeDays') });
		await fireEvent.input(age, { target: { value: '28' } });
		await fireEvent.change(age);
		await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
		expect(api.get.mock.calls[1][0]).toBe('/api/v1/admin/orphans?min_age_days=28');
		expect(screen.getByRole('checkbox', { name: selectionName })).toBe(selection);
		expect(selection.checked).toBe(true);
		const cleanupButton = screen.getByRole('button', { name: cleanupName }) as HTMLButtonElement;
		expect(cleanupButton.disabled).toBe(true);
		await fireEvent.click(cleanupButton);
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(api.post).not.toHaveBeenCalled();

		completeScan(scan);
		await waitFor(() => expect(cleanupButton.disabled).toBe(false));
		expect(selection.checked).toBe(true);
		await fireEvent.click(cleanupButton);
		const dialog = await screen.findByRole('dialog');
		expect(within(dialog).getByText('fip-old')).toBeTruthy();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('orphanCleanup.clean') }));
		await waitFor(() => expect(api.post).toHaveBeenCalledExactlyOnceWith(
			'/api/v1/admin/orphans/cleanup', { kind: 'floating_ip', ids: ['fip-old'] }, 'admin-token', 'admin-project'
		));
		await waitFor(() => expect(api.get).toHaveBeenCalledTimes(3));
	});
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { SecurityGroup } from '$lib/types/securityGroup';

const mocks = vi.hoisted(() => {
	class MockApiError extends Error {
		constructor(public status: number, message: string, public code?: string) { super(message); }
	}
	return { get: vi.fn(), post: vi.fn(), delete: vi.fn(), toastError: vi.fn(), MockApiError };
});
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post, delete: mocks.delete }, ApiError: mocks.MockApiError }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project-a' }) }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: mocks.toastError } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [10, 15, 30, 60] }),
}));

import { t } from '$lib/i18n/ns/network-pages';
import Page from '../+page.svelte';

const rule = { id: 'rule-1', direction: 'ingress', protocol: 'udp', port_range_min: 51820, port_range_max: 51820, remote_ip_prefix: '0.0.0.0/0', remote_group_id: null, ethertype: 'IPv4' };
const groups: SecurityGroup[] = [
	{ id: 'sg-gw', name: 'afterglow-waygate-edge', description: '', rules: [rule], waygate_managed: true },
	{ id: 'sg-web', name: 'web', description: '', rules: [{ ...rule, id: 'rule-2', protocol: 'tcp', port_range_min: 443, port_range_max: 443 }], waygate_managed: false },
];
const panel = () => within(screen.getByRole('region', { name: t('securityGroupRules.rulesLabel') }).parentElement!);
const note = t('securityGroups.waygateManagedNote');

beforeEach(() => {
	vi.clearAllMocks();
	mocks.get.mockReset().mockImplementation(async (path: string) => {
		if (path === '/api/v1/security-groups') return structuredClone(groups);
		if (path === '/api/v1/security-groups/quota') return { security_group: { limit: 10, in_use: 2 }, security_group_rule: { limit: 20, in_use: 2 } };
		if (path.endsWith('/instances')) return [];
		throw new Error(`Unexpected GET ${path}`);
	});
	mocks.post.mockReset();
	mocks.delete.mockReset();
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('min-width: 768px'), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('Waygate-managed security groups', () => {
	it('disables group deletion and rule changes with the localized note and Waygate link', async () => {
		render(Page);
		await screen.findByTestId('waygate-sg-note');
		expect(screen.getByTestId('waygate-sg-note').textContent).toBe(note);
		expect(screen.getByRole('link', { name: t('securityGroups.openWaygate') }).getAttribute('href')).toBe('/dashboard/network/waygate');
		expect(screen.getByTestId('waygate-sg-badge').textContent).toBe(t('securityGroups.waygateBadge'));
		const locked = panel();
		for (const name of [t('securityGroupRules.delete'), t('securityGroupRules.add'), t('securityGroupRules.edit'), t('securityGroupRules.remove')]) {
			const control = locked.getAllByRole('button', { name })[0] as HTMLButtonElement;
			expect(control.disabled, name).toBe(true);
			expect(control.getAttribute('title'), name).toBe(note);
		}
		const checkbox = screen.getByRole('checkbox', { name: t('securityGroupList.select', { name: 'afterglow-waygate-edge' }) }) as HTMLInputElement;
		expect(checkbox.disabled).toBe(true);
		await fireEvent.click(locked.getAllByRole('button', { name: t('securityGroupRules.remove') })[0]);
		await fireEvent.click(locked.getByRole('button', { name: t('securityGroupRules.delete') }));
		expect(mocks.delete).not.toHaveBeenCalled();
	});

	it('keeps ordinary groups editable and maps a Waygate refusal to the localized note', async () => {
		render(Page);
		await screen.findByTestId('waygate-sg-note');
		await fireEvent.click(screen.getByRole('button', { name: /^web/ }));
		await waitFor(() => expect(screen.queryByTestId('waygate-sg-note')).toBeNull());
		const ordinary = panel();
		for (const name of [t('securityGroupRules.delete'), t('securityGroupRules.add'), t('securityGroupRules.edit'), t('securityGroupRules.remove')]) {
			expect((ordinary.getAllByRole('button', { name })[0] as HTMLButtonElement).disabled, name).toBe(false);
		}
		expect((screen.getByRole('checkbox', { name: t('securityGroupList.select', { name: 'web' }) }) as HTMLInputElement).disabled).toBe(false);
		mocks.delete.mockRejectedValueOnce(new mocks.MockApiError(409, 'This resource is managed by Waygate; change it through Waygate', 'waygate_managed_resource'));
		await fireEvent.click(ordinary.getAllByRole('button', { name: t('securityGroupRules.remove') })[0]);
		await waitFor(() => expect(mocks.toastError).toHaveBeenCalledExactlyOnceWith(t('securityGroups.deleteRuleFailed', { message: note })));
		expect(mocks.delete).toHaveBeenCalledWith('/api/v1/security-groups/sg-web/rules/rule-2', 'token', 'project-a');
	});
});

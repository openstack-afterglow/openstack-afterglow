import { writable } from 'svelte/store';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Instance } from '$lib/types/compute';
import { t } from '$lib/i18n/ns/instance';
import { t as tc } from '$lib/i18n/ns/common';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { getStatusLabel } from '$lib/config/statusColors';
import InstanceRow from '../InstanceRow.svelte';

const viewport = vi.hoisted(() => ({ mobile: true }));
vi.mock('$lib/stores/auth', () => ({ canWrite: writable(true) }));
vi.mock('$lib/utils/mobileViewport', () => ({
	mobileViewport: { get current() { return viewport.mobile; } },
}));

const instance: Instance = {
	id: 'instance-0123456789', name: 'card-instance', status: 'ACTIVE', image_name: 'Ubuntu 24.04',
	flavor_name: 'm1.small', flavor_display_name: 'cpu.2c_1.5g',
	ip_addresses: [{ addr: '10.0.0.5', network_name: 'private', type: 'fixed' }, { addr: '203.0.113.9', network_name: 'public', type: 'floating' }],
	created_at: null, union_libraries: ['torch'], union_strategy: 'prebuilt',
} as Instance;

function renderCard() {
	const onSelect = vi.fn();
	render(InstanceRow, { instance, compact: true, onSelect, onAction: async () => {}, onToggleSelect: vi.fn() });
	return { onSelect };
}

beforeEach(() => {
	viewport.mobile = true;
	initLocale('ko');
});
afterEach(() => cleanup());

describe('InstanceRow compact card', () => {
	it('shows only name, status, flavor, IP and actions on mobile', async () => {
		const { onSelect } = renderCard();
		expect(screen.getByRole('button', { name: 'card-instance' })).toBeTruthy();
		expect(screen.getByText(getStatusLabel('ACTIVE', 'server'))).toBeTruthy();
		expect(screen.getByText('2 vCPU · 1.5 GiB RAM')).toBeTruthy();
		expect(screen.getByText('203.0.113.9')).toBeTruthy();
		const trigger = screen.getByRole('button', { name: t('rowActions.instanceActions', { name: 'card-instance' }) });
		// The menu shares the name/status row; mobile cards have no footer row at all.
		expect(trigger.closest('div.flex')?.contains(screen.getByRole('button', { name: 'card-instance' }))).toBe(true);
		expect(document.querySelector('.compact-resource-footer')).toBeNull();
		expect(screen.getByRole('checkbox', { name: t('row.select', { name: 'card-instance' }) })).toBeTruthy();
		expect(screen.queryByText('Ubuntu 24.04')).toBeNull();
		expect(screen.queryByText(tc('resource.details'))).toBeNull();
		expect(screen.queryByRole('button', { name: `${tc('resource.copyId')}: ${instance.id}` })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'card-instance' }));
		expect(onSelect).toHaveBeenCalledWith(instance.id);
	});

	it('keeps image, ID and the details disclosure on tablet cards', () => {
		viewport.mobile = false;
		renderCard();
		expect(screen.getByText('Ubuntu 24.04')).toBeTruthy();
		expect(screen.getByText(tc('resource.details'))).toBeTruthy();
		expect(screen.getAllByTitle(instance.id).length).toBeGreaterThan(0);
		expect(screen.getAllByRole('button', { name: `${tc('resource.copyId')}: ${instance.id}` }).length).toBeGreaterThan(0);
		expect(screen.getByText('2 vCPU · 1.5 GiB RAM')).toBeTruthy();
		expect(screen.getByRole('button', { name: t('rowActions.instanceActions', { name: 'card-instance' }) }).closest('.compact-resource-footer')).not.toBeNull();
	});
});

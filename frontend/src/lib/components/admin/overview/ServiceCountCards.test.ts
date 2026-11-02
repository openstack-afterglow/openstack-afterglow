import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-ops';
import type { Overview } from '$lib/types/adminOverview';
import ServiceCountCards from './ServiceCountCards.svelte';

function snapshot(): Overview {
	return {
		collected_at: '2026-11-02T00:00:00Z', unavailable_sections: [], disabled_sections: [],
		hypervisor_count: 0, running_vms: 0, gpu_instances: 0,
		vcpus: { total: 0, allowed: 0, used: 0 }, ram_gb: { total: 0, used: 0 },
		disk_gb: { total: 0, used: 0, volumes: 0, images: 0 },
		containers_count: 0, file_storage_count: 0, database_instances_count: 0,
		object_storage_containers_count: 12, object_storage_unreadable_accounts: 10,
	};
}

beforeEach(() => initLocale('en'));
afterEach(() => { cleanup(); initLocale('ko'); });

describe('object storage account observations', () => {
	it('retains the readable count and labels unreadable accounts inside its card', () => {
		render(ServiceCountCards, { overview: snapshot() });
		const card = screen.getByRole('link', { name: /Object storage/ });
		expect(within(card).getByText('12')).toBeTruthy();
		expect(within(card).getByText('10 accounts could not be checked')).toBeTruthy();
	});
	it('shows explicit zero plus the note when every account is unreadable', () => {
		render(ServiceCountCards, { overview: { ...snapshot(), object_storage_containers_count: 0 } });
		const card = screen.getByRole('link', { name: /Object storage/ });
		expect(within(card).getByText('0')).toBeTruthy();
		expect(within(card).getByText('10 accounts could not be checked')).toBeTruthy();
	});
	it('does not show an unreadable note for complete inventory', () => {
		render(ServiceCountCards, { overview: { ...snapshot(), object_storage_unreadable_accounts: 0 } });
		expect(screen.queryByText(/could not be checked/)).toBeNull();
	});
	it('keeps total failure unknown rather than showing a partial count', () => {
		render(ServiceCountCards, { overview: { ...snapshot(), object_storage_containers_count: null,
			object_storage_unreadable_accounts: null, unavailable_sections: ['object_storage'] } });
		const card = screen.getByRole('link', { name: /Object storage/ });
		expect(within(card).getByText(t('overview.availability.unknown'))).toBeTruthy();
		expect(within(card).queryByText(/could not be checked/)).toBeNull();
	});
	it('keeps a disabled service distinct from unreadable accounts', () => {
		render(ServiceCountCards, { overview: { ...snapshot(), disabled_sections: ['object_storage'] } });
		const card = screen.getByRole('link', { name: /Object storage/ });
		expect(within(card).getByText(t('overview.availability.disabled'))).toBeTruthy();
		expect(within(card).queryByText(/could not be checked/)).toBeNull();
	});
	it('renders the Korean account note', () => {
		initLocale('ko');
		render(ServiceCountCards, { overview: snapshot() });
		expect(screen.getByText('일부 계정 10개 확인 불가')).toBeTruthy();
	});
});

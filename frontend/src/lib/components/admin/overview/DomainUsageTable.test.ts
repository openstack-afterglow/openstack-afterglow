import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as Reactivity from 'svelte/reactivity';
import { cleanup, render, screen, within } from '@testing-library/svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { DomainUsage } from '$lib/types/adminOverview';
const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async importOriginal => {
	const original = await importOriginal<typeof Reactivity>();
	return { ...original, MediaQuery: class { get current() { return viewport.desktop; } } };
});
import DomainUsageTable from './DomainUsageTable.svelte';

function domain(overrides: Partial<DomainUsage> = {}): DomainUsage {
	return { domain_id: 'domain-a', domain_name: 'Shared name', owner_status: 'known', project_ids: ['project-a'], project_count: 1,
		instances: 0, vcpus: 0, ram_mb: 0, gpu_instances: 0, volumes: 2, volume_gb: 1024, attached_volumes: 1, attached_gb: 256, available_volumes: 1, available_gb: 768, ...overrides };
}
beforeEach(() => {
	initLocale('en');
	viewport.desktop = true;
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: true, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); initLocale('ko'); vi.unstubAllGlobals(); });

describe('domain resource monitor', () => {
	it('keeps duplicate domain names distinct by full UUID and links to exact domain inventories, including volume-only domains', () => {
		render(DomainUsageTable, { loading: false, domains: [domain(), domain({ domain_id: 'domain-b' })] });
		const rows = screen.getAllByRole('row').slice(1);
		expect(rows).toHaveLength(2);
		for (const [index, id] of ['domain-a', 'domain-b'].entries()) {
			const row = within(rows[index]);
			expect(row.getByText(id)).toBeTruthy();
			expect(row.getByRole('link', { name: 'View instances' }).getAttribute('href')).toBe(`/admin/instances?domain_id=${id}`);
			expect(row.getByRole('link', { name: 'View volumes' }).getAttribute('href')).toBe(`/admin/volumes?domain_id=${id}`);
			expect(row.getByText('1,024 GiB')).toBeTruthy();
		}
		expect(screen.queryByRole('button')).toBeNull();
		expect(screen.queryByRole('meter')).toBeNull();
	});

	it('preserves separate deleted projects, unknown owner and deleted domain without guessing a home or unfiltered drilldown', () => {
		render(DomainUsageTable, { loading: false, domains: [
			domain({ domain_id: null, domain_name: null, owner_status: 'deleted_project', project_ids: ['deleted-project-a'] }),
			domain({ domain_id: null, domain_name: null, owner_status: 'deleted_project', project_ids: ['deleted-project-b'] }),
			domain({ domain_id: null, domain_name: null, owner_status: 'unknown_owner', project_ids: [], vcpus: null, ram_mb: null, gpu_instances: null }),
			domain({ domain_id: 'deleted-domain-id', domain_name: null, owner_status: 'deleted_domain' }),
		] });
		const rows = screen.getAllByRole('row').slice(1);
		expect(rows).toHaveLength(4);
		expect(within(rows[0]).getByText('deleted-project-a')).toBeTruthy();
		expect(within(rows[1]).getByText('deleted-project-b')).toBeTruthy();
		for (const row of rows.slice(0, 3)) expect(within(row).queryByRole('link')).toBeNull();
		expect(within(rows[2]).getAllByText('Unavailable')).toHaveLength(3);
		expect(within(rows[3]).getByRole('link', { name: 'View instances' }).getAttribute('href')).toBe('/admin/instances?domain_id=deleted-domain-id');
		expect(screen.queryByText(/accounts|personal|identity home/)).toBeNull();
	});

	it('does not present a failed summary as an empty inventory or convert missing flavor capacity into zero', () => {
		render(DomainUsageTable, { domains: [], loading: false, error: 'Summary unavailable' });
		expect(screen.getByRole('alert').textContent).toContain('Summary unavailable');
		expect(screen.queryByText('No data')).toBeNull();
	});

	it('keeps UUID attribution, domain drilldowns and secondary volume totals in compact cards', () => {
		viewport.desktop = false;
		const { container } = render(DomainUsageTable, { loading: false, domains: [domain()] });
		expect(screen.queryByRole('table')).toBeNull();
		const card = container.querySelector('article')!;
		expect(within(card).getByText('domain-a')).toBeTruthy();
		expect(within(card).getByRole('link', { name: 'View volumes' }).getAttribute('href')).toBe('/admin/volumes?domain_id=domain-a');
		const details = card.querySelector('details')!;
		expect(within(details).getByText('Attached')).toBeTruthy();
		expect(within(details).getByText('1 · 256 GiB')).toBeTruthy();
		expect(within(details).getByText('1 · 768 GiB')).toBeTruthy();
	});
});

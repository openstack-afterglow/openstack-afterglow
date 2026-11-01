import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { Overview } from '$lib/types/adminOverview';
import { t } from '$lib/i18n/ns/admin-ops';
vi.mock('$lib/components/charts/BklitChart.svelte', () => ({ default: () => ({}) }));
import ResourceDonutsCard from './ResourceDonutsCard.svelte';

function snapshot(): Overview {
	return {
		collected_at: '2026-10-29T14:00:00Z', unavailable_sections: [], disabled_sections: [],
		hypervisor_count: 2, running_vms: 12, gpu_instances: 1,
		instance_stats: { total: 14, active: 12, shutoff: 1, error: 1, other: 0 },
		vcpus: { used: 256, total: 212, allowed: 424 },
		ram_gb: { used: 32, total: 64 },
		disk_gb: { used: 120, total: 1000, volumes: 100, images: 20 },
		containers_count: 0, file_storage_count: 0, database_instances_count: 0, object_storage_containers_count: 0,
	};
}
beforeEach(() => initLocale('en'));
afterEach(() => { cleanup(); initLocale('ko'); });

describe('reported capacity semantics', () => {
	it('retains allocation above inventory capacity as informational, not a fault or a clipped percentage', () => {
		render(ResourceDonutsCard, { overview: snapshot() });
		const cpu = screen.getByRole('meter', { name: t('overview.capacity.cpu') });
		expect(Number(cpu.getAttribute('aria-valuenow'))).toBeCloseTo(256 / 212 * 100);
		expect(cpu.getAttribute('data-tone')).toBe('info');
		expect(cpu.textContent).toContain('120.8%');
		expect(screen.getByText('424')).toBeTruthy();
	});
	it('retains known storage components without inventing a combined value when a source fails', () => {
		const overview = snapshot();
		overview.disk_gb = { total: 1000, used: null, volumes: 100, images: null };
		overview.unavailable_sections = ['storage.image_gb'];
		render(ResourceDonutsCard, { overview });
		expect(screen.getByText('100 GiB')).toBeTruthy();
		expect(screen.queryByRole('meter', { name: /pool capacity/ })).toBeNull();
		expect(screen.getByRole('group', { name: /pool capacity/ })).toBeTruthy();
	});
});

import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-ops';
import MonitoringSummaryTab, { type MonitoringSummary, type NativeMeter, type SystemTelemetry } from './MonitoringSummaryTab.svelte';

beforeEach(() => { setLocale('en'); });
afterEach(() => { cleanup(); setLocale('ko'); });

const meter = (series: NativeMeter['series'], overrides: Partial<NativeMeter> = {}): NativeMeter => ({
	series, unit: '%', source: 'gnocchi', status: 'available', error: null, ...overrides,
});
const telemetry = (overrides: Partial<SystemTelemetry> = {}): SystemTelemetry => ({
	source: 'gnocchi', status: 'available', error: null, truncated: false, resources: [], ...overrides,
});

const summary: MonitoringSummary = {
	compute: {
		hypervisors_total: 1,
		hypervisors_up: 1,
		vcpus_used: 2,
		vcpus_total: 4,
		memory_used_mb: 1024,
		memory_total_mb: 2048,
		running_vms: 1,
		gpu_instances: 0,
		instance_stats: { total: 1, active: 1, shutoff: 0, error: 0, other: 0 },
	},
	storage: {
		volume_count: 0,
		volume_by_status: {},
		total_gb: 0,
		file_storage_count: 0,
	},
	network: {
		network_count: 0,
		router_count: 0,
		router_active: 0,
		floatingip_count: 0,
		floatingip_active: 0,
		port_count: 0,
	},
	containers: {
		zun_count: 0,
		k3s_count: 0,
		k3s_active: 0,
		k3s_available: false,
	},
};

describe('MonitoringSummaryTab', () => {
	it('labels unavailable Drover inventory instead of showing a misleading zero', () => {
		render(MonitoringSummaryTab, { props: { summary, loading: false, refreshing: false } });

		expect(screen.getByText(t('monitoring.summary.unavailable'))).toBeTruthy();
	});

	it.each(['not_configured', 'forbidden', 'unavailable', 'not_collected'] as const)('preserves allocation and inventory when native telemetry is %s', (status) => {
		render(MonitoringSummaryTab, { summary: { ...summary, telemetry: telemetry({ status }) }, loading: false, refreshing: false });
		const labelKeys = { not_configured: 'monitoring.telemetry.notConfigured', forbidden: 'monitoring.telemetry.forbidden', unavailable: 'monitoring.telemetry.unavailable', not_collected: 'monitoring.telemetry.notCollected' } as const;
		expect(screen.getByText(t(labelKeys[status]))).toBeTruthy();
		expect(screen.getByText(t('monitoring.summary.vcpuAllocation'))).toBeTruthy();
		expect(screen.getByText(t('monitoring.summary.ramAllocation'))).toBeTruthy();
		expect(screen.getByText(t('monitoring.summary.totalCapacity'))).toBeTruthy();
		expect(screen.getByText(t('monitoring.telemetry.noSamples'))).toBeTruthy();
		expect(screen.queryByText(`${t('monitoring.telemetry.latest')}: 0 %`)).toBeNull();
	});

	it('uses native sample timestamps, null gaps, units and true zero in recorded history', async () => {
		const samples = [{ ts: 180, value: 0 }, { ts: 60, value: 7 }, { ts: 120, value: null }];
		render(MonitoringSummaryTab, { summary: { ...summary, telemetry: telemetry({
			resources: [{ id: 'host-a', name: 'Compute A', type: 'compute_host', metrics: { 'hardware.cpu.util': meter(samples) } }],
		}) }, loading: false, refreshing: false });
		const group = screen.getByRole('group', { name: 'hardware.cpu.util' });
		expect(within(group).getByText(`${t('monitoring.telemetry.latest')}: 0 %`)).toBeTruthy();
		expect(within(group).getByText(`${t('monitoring.telemetry.source', { source: 'Gnocchi' })} · ${t('monitoring.telemetry.unit', { unit: '%' })}`)).toBeTruthy();
		const details = within(group).getByText(t('monitoring.telemetry.history')).closest('details')!;
		details.open = true;
		await fireEvent(details, new Event('toggle'));
		const chart = within(group).getByRole('group', { name: 'Compute A · hardware.cpu.util (%)' });
		const tableDisclosure = chart.querySelector('details')!;
		tableDisclosure.open = true;
		await fireEvent(tableDisclosure, new Event('toggle'));
		const values = [...chart.querySelectorAll('tbody tr')].map(row => row.querySelector('td')?.textContent);
		expect(values).toEqual(['7 %', '—', '0 %']);
	});

	it('shows policy-bounded partial host and storage coverage without making empty meters zero', () => {
		render(MonitoringSummaryTab, { summary: { ...summary, telemetry: telemetry({ status: 'partial', truncated: true,
			resources: [
				{ id: 'host-a', name: 'Compute A', type: 'compute_host', metrics: { 'hardware.memory.used': meter([], { unit: 'B', status: 'not_collected' }) } },
				{ id: 'store-a', name: 'Storage A', type: 'ceph_account', metrics: { 'storage.objects.size': meter([{ ts: 60, value: 2048 }], { unit: 'B' }) } },
			],
		}) }, loading: false, refreshing: false });
		expect(screen.getByText(t('monitoring.telemetry.partial'))).toBeTruthy();
		expect(screen.getByText(t('monitoring.telemetry.policyCoverage'))).toBeTruthy();
		expect(screen.getByText(t('monitoring.telemetry.limited'))).toBeTruthy();
		const empty = screen.getByRole('group', { name: 'hardware.memory.used' });
		expect(within(empty).getByText(`${t('monitoring.telemetry.latest')}: —`)).toBeTruthy();
		expect(within(empty).queryByText(t('monitoring.telemetry.history'))).toBeNull();
		expect(within(screen.getByRole('group', { name: 'storage.objects.size' })).getByText(`${t('monitoring.telemetry.latest')}: 2,048 B`)).toBeTruthy();
	});

	it('does not retain native resource measurements when refreshed summary has no telemetry', async () => {
		const { rerender } = render(MonitoringSummaryTab, { summary: { ...summary, telemetry: telemetry({
			resources: [{ id: 'private-host', name: 'Private host', type: 'compute_host', metrics: { 'hardware.cpu.util': meter([{ ts: 60, value: 91 }]) } }],
		}) }, loading: false, refreshing: false });
		expect(screen.getByText('Private host')).toBeTruthy();
		await rerender({ summary, loading: false, refreshing: false });
		expect(screen.queryByText('Private host')).toBeNull();
		expect(screen.queryByText(`${t('monitoring.telemetry.latest')}: 91 %`)).toBeNull();
		expect(screen.getByText(t('monitoring.summary.vcpuAllocation'))).toBeTruthy();
	});

	it('bounds resource and meter presentation while explicitly reporting omitted coverage', () => {
		const meters = Object.fromEntries(Array.from({ length: 13 }, (_, index) => [`meter-${index}`, meter([])]));
		const resources = Array.from({ length: 13 }, (_, index) => ({ id: `host-${index}`, name: `Host ${index}`, type: 'compute_host', metrics: index === 0 ? meters : {} }));
		render(MonitoringSummaryTab, { summary: { ...summary, telemetry: telemetry({ resources }) }, loading: false, refreshing: false });
		expect(screen.getByText(t('monitoring.telemetry.limited'))).toBeTruthy();
		expect(screen.getByText('Host 11')).toBeTruthy();
		expect(screen.queryByText('Host 12')).toBeNull();
		expect(screen.getByRole('group', { name: 'meter-11' })).toBeTruthy();
		expect(screen.queryByRole('group', { name: 'meter-12' })).toBeNull();
	});

	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('exposes named native measurements and allocation semantics in %s', (locale) => {
		setLocale(locale);
		render(MonitoringSummaryTab, { summary: { ...summary, telemetry: telemetry({ status: 'forbidden' }) }, loading: false, refreshing: false });
		expect(screen.getByRole('region', { name: t('monitoring.telemetry.title') })).toBeTruthy();
		expect(screen.getByText(t('monitoring.telemetry.forbidden'))).toBeTruthy();
		expect(screen.getByText(t('monitoring.summary.allocationNotice'))).toBeTruthy();
	});
});

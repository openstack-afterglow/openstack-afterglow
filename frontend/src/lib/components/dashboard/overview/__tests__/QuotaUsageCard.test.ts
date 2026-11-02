import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import QuotaUsageCard from '../QuotaUsageCard.svelte';
import { t as tp } from '$lib/i18n/ns/compute-pools';
import { t } from '$lib/i18n/ns/dashboard-home';

const quotas = {
	compute: {
		instances: { limit: 2, in_use: 1 },
		cores: { limit: 4, in_use: 1 },
		ram: { limit: 1024, in_use: 512 },
	},
	storage: { volumes: { limit: 2, in_use: 1 }, gigabytes: { limit: 20, in_use: 10 } },
	network: { floatingip: { limit: -1, in_use: 0 } },
	file_storage: null,
	alerts: [],
};

describe('QuotaUsageCard', () => {
	it('preserves the RAM usage ratio when converting MiB to GiB', () => {
		const { getByText } = render(QuotaUsageCard, { quotas, pending: false, error: null });
		const memory = getByText(t('quota.memory')).parentElement;
		expect(memory?.textContent?.replace(/\s+/g, '')).toContain('0.5/1');
		expect(memory?.textContent).toContain('50%');
	});

	it('omits file-storage capacity when the source is unavailable', () => {
		const { queryByRole } = render(QuotaUsageCard, { quotas, pending: false, error: null });
		expect(queryByRole('meter', { name: new RegExp(t('quota.shares')) })).toBeNull();
	});

	it.each([
		{ pool: -1, cap: null, native: -1, expected: tp('unlimited') },
		{ pool: 100, cap: 8, native: 16, expected: '8' },
		{ pool: 100, cap: null, native: 10, expected: '10' },
		{ pool: 4, cap: 8, native: -1, expected: '4' },
		{ pool: -1, cap: 0, native: -1, expected: '0' },
	])('shows project consumption with applicable limits: %j', ({ pool, cap, native, expected }) => {
		const scoped = { ...quotas, compute: { ...quotas.compute, cores: { limit: pool, in_use: 224, available: 2, quota_scope: 'domain' as const, domain_id: 'domain-a', project_limit: cap, project_in_use: 6, native_project_limit: native } } };
		const view = render(QuotaUsageCard, { quotas: scoped, pending: false, error: null });
		const row = view.getByText(tp('cpu')).parentElement;
		expect(row?.textContent?.replace(/\s+/g, '')).toContain(`6/${expected}`);
		expect(view.container.textContent).not.toContain('224');
		expect(view.getByText(`${tp('remaining')}:`).parentElement?.textContent).toContain('2');
	});

	it('does not substitute domain consumption when project use is unknown', () => {
		const scoped = { ...quotas, compute: { ...quotas.compute, cores: { limit: -1, in_use: 224, quota_scope: 'domain' as const, project_in_use: null } } };
		const view = render(QuotaUsageCard, { quotas: scoped, pending: false, error: null });
		expect(view.getByText(`${tp('cpu')}: ${tp('unknown')}`)).toBeTruthy();
		expect(view.container.textContent).not.toContain('224');
	});

	it.each(['paused', 'unavailable'] as const)('masks %s domain compute without inventing zero or hiding storage', state => {
		const scoped = { ...quotas, compute: { ...quotas.compute, cores: null, ram: null }, compute_pool: { state, domain_id: 'domain-a', limits: {}, usage: {}, available: {}, project_limits: {}, project_usage: {}, project_available: {} } };
		const view = render(QuotaUsageCard, { quotas: scoped, pending: false, error: null });
		expect(view.getByText(tp(state === 'paused' ? 'pauseHelp' : 'domainUnavailable'))).toBeTruthy();
		expect(view.queryByText('vCPU')).toBeNull();
		expect(view.container.textContent).toContain('10');
	});
});

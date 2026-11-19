import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { ChatUsage } from '$lib/api/chatTree';
import { auth, type AuthState } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/chat-panel';
import { t as settingsT } from '$lib/i18n/ns/chat-settings';
import ChatUsageWidget from '../ChatUsageWidget.svelte';

const usage: ChatUsage = {
	found: true, total_credited_cost: 12, lifetime_prompt_tokens: 80,
	lifetime_completion_tokens: 20, lifetime_request_count: 2,
	month_credited_cost: 12, week_credited_cost: 4, month_prompt_tokens: 80,
	month_completion_tokens: 20, month_request_count: 2,
	quota_used: 120, quota_max: 100, quota_weekly_max: 100,
};

afterEach(cleanup);

describe('chat quota usage display', () => {
	it('keeps over-limit usage in the visible readout', () => {
		const { container } = render(ChatUsageWidget, { props: { usage } });
		expect(container.textContent).toContain('120%');
	});


	it('does not imply a zero quota when no limit is configured', () => {
		const { container } = render(ChatUsageWidget, { props: { usage: { ...usage, quota_max: 0 } } });
		expect(container.textContent).not.toContain('0%');
	});
});

describe('chat header domain pool', () => {
	const pool = {
		domain_id: 'domain-1', exists: true, funded: true, balance_credits: '25.50000000', reserved_credits: '1.00000000',
		monthly_used_credits: '30.00000000', effective_monthly_limit_credits: '100.00000000',
	};
	// Lumen's self view: quota_* are the caller's own monthly limit, the pool travels separately.
	const selfView: ChatUsage = { ...usage, view: 'self', billing_scope: 'user', quota_used: 5, quota_max: 50, domain_pool: pool };
	function actor(domainId: string, isDomainManager: boolean) {
		auth.set({
			token: 'browser-token', refreshToken: null, accessExpiresAt: null, userId: 'user-1', username: 'tester',
			projectId: 'project-1', projectName: 'Project', availableProjects: [], roles: [], isSystemAdmin: false,
			federated: false, domainId, domainName: 'Domain', isDomainManager,
		} as AuthState);
	}
	beforeEach(() => actor('domain-1', false));

	it.each([false, true])('shows the pool balance and limit with the personal guard (manager: %s)', (isDomainManager) => {
		actor('domain-1', isDomainManager);
		render(ChatUsageWidget, { props: { usage: selfView } });
		expect(screen.getByText(settingsT('domainBilling.balance'))).toBeTruthy();
		expect(screen.getByText('25.5')).toBeTruthy();
		expect(screen.getByText(t('usage.poolLimit')).nextElementSibling?.textContent).toBe(t('usage.used', { percent: '30%' }));
		expect(screen.getByText(t('usage.personalLimit')).nextElementSibling?.textContent).toBe(t('usage.used', { percent: '10%' }));
		expect(screen.getByRole('img', { name: t('usage.poolUsage', { percent: '30%' }) })).toBeTruthy();
		expect(screen.queryByText(t('usage.monthQuota'))).toBeNull();
	});

	it('keeps the personal limit on the bar when the pool is unlimited', () => {
		const { container } = render(ChatUsageWidget, { props: { usage: { ...selfView, domain_pool: { ...pool, effective_monthly_limit_credits: null } } } });
		expect(screen.getByText(t('usage.poolLimit')).nextElementSibling?.textContent).toBe(settingsT('domainBilling.noLimit'));
		expect(screen.getByRole('img', { name: t('usage.quotaUsage', { percent: '10%' }) })).toBeTruthy();
		expect(container.querySelector('.usage')?.getAttribute('title')).toBe(t('usage.quotaTitle', { percent: '10%' }));
	});

	it.each([pool.effective_monthly_limit_credits, null])('marks an unfunded pool that still holds credits as inactive (limit: %s)', (limit) => {
		render(ChatUsageWidget, { props: { usage: { ...selfView, domain_pool: { ...pool, funded: false, effective_monthly_limit_credits: limit } } } });
		expect(screen.getByText(settingsT('domainBilling.inactiveLabel'))).toBeTruthy();
	});

	it('shows no pool line in a domain without a pool', () => {
		actor('personal-domain', false);
		const usageWithout = { ...selfView, domain_pool: { ...pool, domain_id: 'personal-domain', exists: false, funded: false, balance_credits: '0', reserved_credits: '0', monthly_used_credits: '0', effective_monthly_limit_credits: null } };
		render(ChatUsageWidget, { props: { usage: usageWithout } });
		expect(screen.queryByText(settingsT('domainBilling.balance'))).toBeNull();
		expect(screen.queryByText(t('usage.poolLimit'))).toBeNull();
		expect(screen.getByText(t('usage.monthQuota')).nextElementSibling?.textContent).toBe(t('usage.used', { percent: '10%' }));
	});

	it('keeps the older domain-billed summary behavior when domain_pool is absent', () => {
		const legacy: ChatUsage = { ...usage, billing_scope: 'domain', payer_domain_id: 'domain-1', balance_credits: '3', quota_used: 50, quota_max: 100 };
		render(ChatUsageWidget, { props: { usage: legacy } });
		expect(screen.getByText('3')).toBeTruthy();
		expect(screen.getByText(t('usage.monthQuota')).nextElementSibling?.textContent).toBe(t('usage.used', { percent: '50%' }));
		expect(screen.queryByText(t('usage.poolLimit'))).toBeNull();
		expect(screen.queryByText(t('usage.personalLimit'))).toBeNull();
	});
});

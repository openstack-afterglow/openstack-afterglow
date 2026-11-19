import { setVerifiedLumenActor } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/chat-settings';
import { ApiError } from '$lib/api/errors';

const mocks = vi.hoisted(() => ({ get: vi.fn(), goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error {}
}));

vi.mock('$app/navigation', () => ({ goto: mocks.goto }));

import ChatSettings from '../ChatSettings.svelte';

describe('ChatSettings', () => {
	beforeEach(() => {
		mocks.get.mockReset();
		auth.set({
			token: 'browser-token', refreshToken: null, accessExpiresAt: null,
			userId: 'user-1', username: 'tester', projectId: 'project-1', projectName: 'Project',
			availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false
		});
		mocks.goto.mockReset();
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/usage') {
				return Promise.resolve({
					month_prompt_tokens: 5000,
					month_completion_tokens: 3000,
					month_credited_cost: 73.73,
					month_request_count: 13,
					quota_used: 73.73,
					quota_max: 100000,
					week_credited_cost: 12,
					quota_weekly_max: 1000
				});
			}
			return Promise.resolve([]);
		});
	});

	it('shows a member their current domain prepaid balance and insufficient credits', async () => {
		mocks.get.mockImplementation(async (path: string) => path === '/api/v1/chat/usage' ? {
			billing_scope: 'domain', payer_domain_id: 'domain-1', balance_credits: '3', reserved_credits: '3',
			quota_used: 2, quota_max: 10, by_source: []
		} : {});
		render(ChatSettings);
		await screen.findByRole('heading', { name: t('domainBilling.title') });
		expect(screen.getByText(t('domainBilling.balance'))).toBeTruthy();
		expect(screen.getByText(t('domainBilling.reserved'))).toBeTruthy();
		expect(screen.getByText(t('domainBilling.insufficient'))).toBeTruthy();
		expect(mocks.get.mock.calls.some(([path]) => path.endsWith('/domain-pool'))).toBe(false);
	});

	it('renders all settings sections as a dedicated page and updates its deep link', async () => {
		const { container } = render(ChatSettings);

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.getByRole('heading', { level: 1, name: '채팅 설정' })).toBeTruthy();
		expect(screen.getByRole('heading', { level: 2, name: '이번 달 사용량' })).toBeTruthy();
		expect(container.querySelector('.eyebrow')).toBeNull();
		expect(await screen.findByText('주간 쿼터 12 / 1,000')).toBeTruthy();
		const sectionButtons = ['사용량', 'API 키', 'Agent Vault', 'MCP 서버', '도구', '스킬'].map(
			(name) => screen.getByRole('button', { name })
		);
		expect(sectionButtons).toHaveLength(6);
		expect(sectionButtons[0].classList.contains('active')).toBe(true);
		expect(sectionButtons[0].getAttribute('aria-current')).toBe('page');

		await fireEvent.click(screen.getByRole('button', { name: 'MCP 서버' }));
		expect(mocks.goto).toHaveBeenCalledWith('/dashboard/chat/settings?section=mcp', {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
		expect(screen.getByRole('button', { name: 'MCP 서버' }).classList.contains('active')).toBe(true);
		expect(screen.getByRole('heading', { level: 2, name: 'MCP 연결' })).toBeTruthy();
		expect(sectionButtons[0].hasAttribute('aria-current')).toBe(false);
		expect(screen.getByRole('button', { name: 'MCP 서버' }).getAttribute('aria-current')).toBe('page');
	});

	it('keeps the memory deep link for Agent Vault', async () => {
		render(ChatSettings, { initialSection: 'memory' });
		expect(await screen.findByRole('heading', { level: 2, name: 'Agent Vault' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Agent Vault' }).getAttribute('aria-current')).toBe('page');
	});
});

describe('ChatSettings usage views', () => {
	const payer = (billing_scope: 'user' | 'domain', credited_cost: number, request_count: number) =>
		({ billing_scope, credited_cost, prompt_tokens: 1, completion_tokens: 1, request_count });
	const summary = (view: 'self' | 'domain') => ({
		view, billing_scope: view === 'domain' ? 'domain' : 'user', payer_domain_id: view === 'domain' ? 'domain-1' : null,
		month_prompt_tokens: 10, month_completion_tokens: 5, month_credited_cost: 3, month_request_count: 2,
		quota_used: 3, quota_max: 0, quota_weekly_max: 0, by_source: [],
		by_payer: view === 'domain' ? [payer('domain', 7.5, 4)] : [payer('domain', 2, 1), payer('user', 1.25, 3)],
	});
	function actor(isDomainManager: boolean) {
		setVerifiedLumenActor({
			token: 'browser-token', refreshToken: null, accessExpiresAt: null,
			userId: 'user-1', username: 'tester', projectId: 'project-1', projectName: 'Project',
			availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager
		});
	}
	const usageCalls = () => mocks.get.mock.calls.map(([path]) => path as string).filter((path) => path.startsWith('/api/v1/chat/usage'));

	afterEach(cleanup);
	beforeEach(() => {
		mocks.get.mockReset();
		mocks.get.mockImplementation(async (path: string) => {
			const view = path.includes('scope=domain') ? 'domain' : 'self';
			if (path.startsWith('/api/v1/chat/usage/timeseries')) return { view, series: [
				{ bucket: '2026-11-01', source: 'web', total_tokens: 10, credited_cost: 3, request_count: 2, credited_cost_by_payer: { user: 1, domain: 2 } },
			] };
			if (path.startsWith('/api/v1/chat/usage/keys')) return { view, keys: [
				{ api_key_id: 4, name: view === 'domain' ? null : 'CLI', key_prefix: null, billing_scope: view === 'domain' ? 'domain' : 'user', total_tokens: 3, credited_cost: 1, request_count: 1 },
			] };
			if (path.startsWith('/api/v1/chat/usage')) return summary(view);
			return [];
		});
	});

	it('labels usage by payer and never offers the domain view to members', async () => {
		actor(false);
		render(ChatSettings);
		const payers = (await screen.findByRole('heading', { level: 3, name: t('usage.byPayerTitle') })).parentElement as HTMLElement;
		expect(within(payers).getByText(t('usage.payer.user'))).toBeTruthy();
		expect(within(payers).getByText(t('usage.payer.domain'))).toBeTruthy();
		expect(within(payers).getByText(t('usage.payerSummary', { credits: '1.25', requests: 3 }))).toBeTruthy();
		const split = [t('usage.payerCredits', { payer: t('usage.payer.user'), credits: '1' }), t('usage.payerCredits', { payer: t('usage.payer.domain'), credits: '2' })].join(' · ');
		expect(await screen.findByText(split)).toBeTruthy();
		const key = (await screen.findByText('CLI')).parentElement as HTMLElement;
		expect(within(key).getByText(t('usage.payer.user'))).toBeTruthy();
		expect(screen.queryByRole('group', { name: t('usage.viewLabel') })).toBeNull();
		expect(usageCalls().some((path) => path.includes('scope='))).toBe(false);
	});

	it('lets a domain manager switch every usage call to the domain view', async () => {
		actor(true);
		render(ChatSettings);
		const views = await screen.findByRole('group', { name: t('usage.viewLabel') });
		expect(within(views).getByRole('button', { name: t('usage.view.self') }).getAttribute('aria-pressed')).toBe('true');
		await screen.findByText('CLI');
		mocks.get.mockClear();
		await fireEvent.click(within(views).getByRole('button', { name: t('usage.view.domain') }));
		await waitFor(() => expect(usageCalls()).toHaveLength(4));
		expect(usageCalls().sort()).toEqual([
			'/api/v1/chat/usage/keys?scope=domain',
			'/api/v1/chat/usage/timeseries?bucket=day&range=30d&scope=domain',
			'/api/v1/chat/usage?scope=domain',
			'/api/v1/chat/usage?scope=domain',
		]);
		expect(within(views).getByRole('button', { name: t('usage.view.domain') }).getAttribute('aria-pressed')).toBe('true');
		await screen.findByRole('heading', { name: t('domainBilling.title') });
		const key = (await screen.findByText(t('usage.keyFallback', { id: 4 }))).parentElement as HTMLElement;
		expect(within(key).getByText(t('usage.payer.domain'))).toBeTruthy();
	});

	it('falls back to the personal view with a notice when Lumen refuses domain usage', async () => {
		actor(true);
		const personal = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string) => {
			if (path.includes('scope=domain')) throw new ApiError(403, 'domain_manager_required');
			return personal(path);
		});
		render(ChatSettings);
		const views = await screen.findByRole('group', { name: t('usage.viewLabel') });
		await fireEvent.click(within(views).getByRole('button', { name: t('usage.view.domain') }));
		await screen.findByText(t('usage.domainViewDenied'));
		expect(within(views).getByRole('button', { name: t('usage.view.self') }).getAttribute('aria-pressed')).toBe('true');
		await waitFor(() => expect(usageCalls().at(-1)).not.toContain('scope='));
		expect(await screen.findByText(t('usage.payerSummary', { credits: '1.25', requests: 3 }))).toBeTruthy();
	});
});

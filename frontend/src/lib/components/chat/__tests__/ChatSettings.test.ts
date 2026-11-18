import './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/chat-settings';

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
			if (path.endsWith('/memories/document')) {
				return Promise.resolve({
					filename: 'memory.md',
					content_type: 'text/markdown',
					content: '# Memory\n\n## Preferences\n\n- Prefers concise answers\n'
				});
			}
			if (path.endsWith('/memories')) return Promise.resolve([]);
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
		const sectionButtons = ['사용량', 'API 키', '메모리', 'MCP 서버', '도구', '스킬'].map(
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

	it('shows the automatically maintained memory.md and copies its plaintext content', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			configurable: true,
			value: { writeText }
		});
		render(ChatSettings, {
			initialSection: 'memory'
		});
		expect(await screen.findByRole('heading', { level: 2, name: 'memory.md' })).toBeTruthy();
		expect(screen.getAllByRole('heading').some((heading) => heading.tagName === 'H4')).toBe(false);

		const document = await screen.findByLabelText('memory.md 내용');
		expect(document.textContent).toContain('# Memory');
		expect(document.textContent).toContain('Prefers concise answers');
		expect(mocks.get).toHaveBeenCalledWith(
			'/api/v1/chat/memories/document',
			'browser-token',
			'project-1'
		);

		await fireEvent.click(screen.getByRole('button', { name: '복사' }));
		await waitFor(() =>
			expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Prefers concise answers'))
		);
	});
});

import { grantLumen } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/chat-settings';
import { initLocale } from '$lib/i18n/runtime.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, patch: mocks.patch, post: mocks.post },
	ApiError: class ApiError extends Error {}
}));

import ChatApiKeysManager from '../ChatApiKeysManager.svelte';

const discovery = {
	endpoints: {
		openai: { sdk_base_url: 'https://inference.example/tenant/v1' },
		anthropic: { sdk_base_url: 'https://inference.example/tenant' },
		gateway: { base_url: 'https://inference.example/tenant/v1/claude-gateway' }
	},
	clients: {
		codex: { base_url: 'https://inference.example/tenant/v1' }
	}
};

const apiKey = {
	id: 17,
	name: '내 CLI',
	key_prefix: 'lm_test',
	scopes: ['chat'],
	is_active: true,
	last_used_at: null,
	created_at: '2026-09-09T00:00:00Z',
	revoked_at: null,
	owner_monthly_credit_limit: null,
	admin_monthly_credit_limit: null,
	system_monthly_credit_limit: '1000',
	effective_monthly_credit_limit: '1000',
	month_credited_cost: '12.5',
	owner_weekly_credit_limit: null,
	system_weekly_credit_limit: '0',
	effective_weekly_credit_limit: '1000',
	week_credited_cost: '3.25'
};

function examples(container: HTMLElement): string {
	return Array.from(container.querySelectorAll('pre code'), (code) => code.textContent).join('\n');
}

describe('ChatApiKeysManager connection guide', () => {
	it('issues only selected scopes still allowed by the current grants', async () => {
		grantLumen('lumen-keys_editor', 'lumen-chat_user');
		mocks.post.mockResolvedValue({ key: 'one-time-secret', key_prefix: 'prefix' });
		render(ChatApiKeysManager);
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.create') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/api-keys', { name: '', scopes: ['compat:completions:write'] }, 'browser-token', 'project-1'));
	});
	it('permits key editing but not revocation with the keys editor leaf', async () => {
		grantLumen('lumen-keys_editor');
		render(ChatApiKeysManager);
		const rename = await screen.findByRole('button', { name: t('apiKeys.rename') });
		expect(rename.hasAttribute('disabled')).toBe(false);
		expect(screen.getByRole('button', { name: t('apiKeys.revoke') }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('checkbox', { name: 'compat:images:write' }).hasAttribute('disabled')).toBe(true);
	});
	beforeEach(() => {
		vi.resetAllMocks();
		initLocale('ko');
		auth.set({
			token: 'browser-token', refreshToken: null, accessExpiresAt: null,
			userId: 'user-1', username: 'tester', projectId: 'project-1', projectName: 'Project',
			availableProjects: [], roles: [], isSystemAdmin: false, federated: false
		});
		mocks.patch.mockResolvedValue({});
		mocks.get.mockImplementation((path: string) => Promise.resolve(
			path.endsWith('/compat') ? discovery : path.endsWith('/api-keys') ? [apiKey] : []
		));
	});

	afterEach(() => {
		cleanup();
		initLocale('ko');
	});

	it('switches a single accessible guide without refetching discovery', async () => {
		render(ChatApiKeysManager);
		const codexTab = await screen.findByRole('tab', { name: t('apiKeys.guide.codexTab') });
		const codexPanel = screen.getByRole('tabpanel', { name: t('apiKeys.guide.codexTab') });
		expect(codexTab.getAttribute('aria-controls')).toBe(codexPanel.id);
		const discoveryRequests = mocks.get.mock.calls.filter(([path]) => String(path).endsWith('/compat')).length;

		for (const key of ['apiKeys.guide.claudeCodeTab', 'apiKeys.guide.openaiTab', 'apiKeys.guide.claudeTab', 'apiKeys.guide.codexTab'] as const) {
			const name = t(key);
			await fireEvent.click(screen.getByRole('tab', { name }));
			expect(screen.getAllByRole('tabpanel')).toEqual([screen.getByRole('tabpanel', { name })]);
			expect(screen.getByRole('tab', { name }).getAttribute('aria-selected')).toBe('true');
		}
		expect(mocks.get.mock.calls.filter(([path]) => String(path).endsWith('/compat'))).toHaveLength(discoveryRequests);
	});

	it('keeps key management available but hides examples until discovery retry succeeds', async () => {
		let unavailable = true;
		mocks.get.mockImplementation((path: string) => {
			if (path.endsWith('/compat')) return unavailable ? Promise.reject(new Error('offline')) : Promise.resolve(discovery);
			return Promise.resolve([]);
		});
		const { container } = render(ChatApiKeysManager);
		await screen.findByRole('alert');
		expect(container.querySelector('pre')).toBeNull();
		expect(screen.getByRole('button', { name: t('apiKeys.create') })).toBeTruthy();
		unavailable = false;
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.guide.reload') }));
		await waitFor(() => expect(examples(container)).toContain(discovery.clients.codex.base_url));
		expect(screen.getByRole('tab', { name: t('apiKeys.guide.codexTab') }).getAttribute('aria-selected')).toBe('true');
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it.each([
		'https://user:password@inference.example/v1',
		'https://inference.example/v1?key=private',
		'https://inference.example/v1#private',
		'https://inference.example/v1\n',
		'https://inference.example\\private/v1'
	])('hides all executable examples for unsafe discovery URL %j', async (url) => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compat') ? {
			endpoints: {
				openai: { sdk_base_url: url },
				anthropic: discovery.endpoints.anthropic,
				gateway: discovery.endpoints.gateway
			},
			clients: discovery.clients,
		} : []));
		const { container } = render(ChatApiKeysManager);
		await screen.findByRole('alert');
		expect(container.querySelector('pre')).toBeNull();
		expect(container.textContent).not.toContain(url);
	});

	it('does not replace the current project endpoint with a late response from the previous project', async () => {
		let resolvePrevious!: (value: typeof discovery) => void;
		const previous = new Promise<typeof discovery>((resolve) => { resolvePrevious = resolve; });
		mocks.get.mockImplementation((path: string, _token: string, project: string) => {
			if (!path.endsWith('/compat')) return Promise.resolve([]);
			return project === 'project-1' ? previous : Promise.resolve(discovery);
		});
		const { container } = render(ChatApiKeysManager);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/compat', 'browser-token', 'project-1'));
		auth.update((state) => ({ ...state, projectId: 'project-2' }));
		await waitFor(() => expect(examples(container)).toContain(discovery.clients.codex.base_url));
		resolvePrevious({
			endpoints: {
				openai: { sdk_base_url: 'https://previous.example/v1' },
				anthropic: { sdk_base_url: 'https://previous.example' },
				gateway: { base_url: 'https://previous.example/v1/claude-gateway' }
			},
			clients: { codex: { base_url: 'https://previous.example/v1' } }
		});
		await previous;
		await tick();
		expect(examples(container)).toContain(discovery.clients.codex.base_url);
		expect(examples(container)).not.toContain('previous.example');
	});

	it('renames an active API key in place', async () => {
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.rename') }));
		const input = screen.getByRole('textbox', { name: t('apiKeys.nameLabel') });
		await fireEvent.input(input, { target: { value: '새 이름' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		await waitFor(() => {
			expect(mocks.patch).toHaveBeenCalledWith(
				'/api/v1/chat/api-keys/17',
				{ name: '새 이름' },
				'browser-token',
				'project-1'
			);
		});
	});

	it('rejects limits above the user quota and saves valid nullable limits', async () => {
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.setLimits') }));
		const monthly = screen.getByLabelText(t('apiKeys.monthlyLimit'));
		const weekly = screen.getByLabelText(t('apiKeys.weeklyLimit'));
		await fireEvent.input(monthly, { target: { value: '2000' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		expect(screen.getByRole('alert').id).toBe(`${monthly.id}-message`);
		expect(mocks.patch).not.toHaveBeenCalled();

		await fireEvent.input(monthly, { target: { value: '500' } });
		await fireEvent.input(weekly, { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		await waitFor(() => {
			expect(mocks.patch).toHaveBeenCalledWith(
				'/api/v1/chat/api-keys/17/limits',
				{ monthly_credit_limit: '500', weekly_credit_limit: null },
				'browser-token',
				'project-1'
			);
		});
	});

	it('blocks a limit above the administrator ceiling before sending a request', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(
			path.endsWith('/compat')
				? discovery
				: path.endsWith('/api-keys')
					? [{ ...apiKey, admin_monthly_credit_limit: '500', effective_monthly_credit_limit: '500' }]
					: []
		));
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: t('apiKeys.setLimits') }));
		const monthly = screen.getByLabelText(t('apiKeys.monthlyLimit'));
		await fireEvent.input(monthly, { target: { value: '800' } });
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.save') }));

		expect(screen.getByRole('alert').id).toBe(`${monthly.id}-message`);
		expect(mocks.patch).not.toHaveBeenCalled();
	});
});

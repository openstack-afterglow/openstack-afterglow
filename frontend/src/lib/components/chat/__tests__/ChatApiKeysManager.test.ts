import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, patch: mocks.patch },
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
	beforeEach(() => {
		vi.resetAllMocks();
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

	afterEach(cleanup);

	it('shows one selected guide at a time and uses every discovered SDK URL verbatim', async () => {
		const { container } = render(ChatApiKeysManager);
		const codexTab = await screen.findByRole('tab', { name: 'Codex' });
		const claudeCodeTab = screen.getByRole('tab', { name: 'Claude Code' });
		const openaiTab = screen.getByRole('tab', { name: 'OpenAI' });
		const claudeTab = screen.getByRole('tab', { name: 'Claude' });

		const codexPanel = screen.getByRole('tabpanel', { name: 'Codex' });
		expect(codexTab.getAttribute('aria-selected')).toBe('true');
		expect(codexTab.getAttribute('aria-controls')).toBe(codexPanel.id);
		expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
		expect(container.querySelectorAll('pre code')).toHaveLength(1);
		expect(examples(container)).toContain('model_provider = "lumen"');
		expect(examples(container)).toContain('base_url = "https://inference.example/tenant/v1"');
		expect(examples(container)).toContain('wire_api = "responses"');
		expect(examples(container)).toContain('env_key = "LUMEN_API_KEY"');
		expect(examples(container)).toContain('requires_openai_auth = false');
		const discoveryRequests = mocks.get.mock.calls.filter(([path]) => String(path).endsWith('/compat')).length;

		await fireEvent.click(claudeCodeTab);
		expect(screen.getByRole('tabpanel', { name: 'Claude Code' })).toBeTruthy();
		expect(examples(container)).toContain('export ANTHROPIC_BASE_URL="https://inference.example/tenant"');
		expect(examples(container)).toContain('export ANTHROPIC_AUTH_TOKEN="$LUMEN_API_KEY"');
		expect(examples(container)).toContain('export ANTHROPIC_MODEL="$LUMEN_MODEL"');
		expect(examples(container)).toContain('export ANTHROPIC_CUSTOM_HEADERS="X-Lumen-Provider: $LUMEN_PROVIDER"');
		expect(examples(container)).not.toContain('/claude-gateway');

		await fireEvent.click(openaiTab);
		expect(screen.getByRole('tabpanel', { name: 'OpenAI' })).toBeTruthy();
		expect(examples(container)).toContain('base_url="https://inference.example/tenant/v1"');
		expect(examples(container)).toContain('from openai import OpenAI');
		expect(examples(container)).toContain('{"provider": os.environ["LUMEN_PROVIDER"]}');

		await fireEvent.click(claudeTab);
		expect(screen.getByRole('tabpanel', { name: 'Claude' })).toBeTruthy();
		expect(examples(container)).toContain('base_url="https://inference.example/tenant"');
		expect(examples(container)).toContain('from anthropic import Anthropic');
		expect(examples(container)).toContain('{"provider": os.environ["LUMEN_PROVIDER"]}');
		expect(examples(container)).not.toContain('api.localhost');
		expect(examples(container)).not.toContain('messages=[...]');
		expect(mocks.get.mock.calls.filter(([path]) => String(path).endsWith('/compat'))).toHaveLength(discoveryRequests);
	});

	it('copies the complete template from each selected guide', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			configurable: true,
			value: { writeText }
		});
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: '설정 복사' }));
		const codexConfig = writeText.mock.calls.at(-1)?.[0] as string;
		expect(codexConfig).toContain('model_provider = "lumen"');
		expect(codexConfig).toContain('wire_api = "responses"');
		expect(codexConfig).toContain('base_url = "https://inference.example/tenant/v1"');
		expect(codexConfig).not.toContain('browser-token');

		await fireEvent.click(screen.getByRole('tab', { name: 'Claude Code' }));
		await fireEvent.click(screen.getByRole('button', { name: '명령 복사' }));
		const claudeSetup = writeText.mock.calls.at(-1)?.[0] as string;
		expect(claudeSetup).toContain('ANTHROPIC_BASE_URL="https://inference.example/tenant"');
		expect(claudeSetup).toContain('ANTHROPIC_AUTH_TOKEN="$LUMEN_API_KEY"');
		expect(claudeSetup).not.toContain('browser-token');
		expect(claudeSetup).not.toContain('/claude-gateway');

		await fireEvent.click(screen.getByRole('tab', { name: 'OpenAI' }));
		await fireEvent.click(screen.getByRole('button', { name: '예제 복사' }));
		expect(writeText.mock.calls.at(-1)?.[0]).toContain('client.chat.completions.create');

		await fireEvent.click(screen.getByRole('tab', { name: 'Claude' }));
		await fireEvent.click(screen.getByRole('button', { name: '예제 복사' }));
		expect(writeText.mock.calls.at(-1)?.[0]).toContain('client.messages.create');
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
		expect(screen.getByRole('button', { name: '+ 새 API 키 발급' })).toBeTruthy();
		unavailable = false;
		await fireEvent.click(screen.getByRole('button', { name: '연결 정보 다시 불러오기' }));
		await waitFor(() => expect(examples(container)).toContain(discovery.clients.codex.base_url));
		expect(screen.getByRole('tab', { name: 'Codex' }).getAttribute('aria-selected')).toBe('true');
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('does not publish code with a malformed or credential-bearing discovery URL', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compat') ? {
			endpoints: {
				openai: { sdk_base_url: 'https://user:password@inference.example/v1' },
				anthropic: discovery.endpoints.anthropic,
				gateway: discovery.endpoints.gateway
			},
			clients: discovery.clients,
		} : []));
		const { container } = render(ChatApiKeysManager);
		await screen.findByRole('alert');
		expect(container.querySelector('pre')).toBeNull();
		expect(container.textContent).not.toContain('user:password');
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

		await fireEvent.click(await screen.findByRole('button', { name: '이름 변경' }));
		const input = screen.getByRole('textbox', { name: 'API 키 이름' });
		await fireEvent.input(input, { target: { value: '새 이름' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

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

		await fireEvent.click(await screen.findByRole('button', { name: '한도 설정' }));
		const monthly = screen.getByLabelText('월 한도(크레딧)');
		const weekly = screen.getByLabelText('주간 한도(크레딧)');
		await fireEvent.input(monthly, { target: { value: '2000' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		expect(screen.getByText('사용자 쿼터(1,000)를 초과할 수 없습니다')).toBeTruthy();
		expect(mocks.patch).not.toHaveBeenCalled();

		await fireEvent.input(monthly, { target: { value: '500' } });
		await fireEvent.input(weekly, { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

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

		await fireEvent.click(await screen.findByRole('button', { name: '한도 설정' }));
		await fireEvent.input(screen.getByLabelText('월 한도(크레딧)'), { target: { value: '800' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		expect(screen.getByText('관리자 한도(500)를 초과할 수 없습니다')).toBeTruthy();
		expect(mocks.patch).not.toHaveBeenCalled();
	});
});

import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
	class ApiError extends Error {
		constructor(message: string, public status: number) {
			super(message);
		}
	}
	return {
		get: vi.fn(),
		post: vi.fn(),
		patch: vi.fn(),
		put: vi.fn(),
		deleteRequest: vi.fn(),
		confirmDialog: vi.fn(),
		ApiError
	};
});

vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe(run: (value: { token: string; projectId: string; isSystemAdmin: boolean }) => void) {
			run({ token: 'token', projectId: 'project', isSystemAdmin: true });
			return () => {};
		}
	}
}));
vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		post: mocks.post,
		patch: mocks.patch,
		put: mocks.put,
		delete: mocks.deleteRequest
	},
	ApiError: mocks.ApiError
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirmDialog }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { get, post, patch, put, deleteRequest, confirmDialog, ApiError } = mocks;

import ModelPage from '../models/+page.svelte';
import ProviderPage from '../+page.svelte';
import ToolPage from '../tools/+page.svelte';

const provider = {
	id: 1,
	name: 'OpenAI',
	provider_type: 'openai',
	api_base: null,
	has_api_key: true,
	models_dev_provider_id: 'openai',
	is_active: true,
	margin_multiplier: 1
};
const chatgptProvider = {
	...provider,
	id: 7,
	name: 'shared-chatgpt',
	provider_type: 'chatgpt',
	auth_mode: 'chatgpt_device' as const,
	has_api_key: false,
	has_credentials: false,
	auth_status: 'disconnected' as const,
	auth_expires_at: null
};

const claudeSubscriptionProvider = {
	...provider,
	id: 8,
	name: 'shared-claude',
	provider_type: 'anthropic',
	auth_mode: 'anthropic_subscription' as const,
	has_api_key: false,
	has_credentials: false,
	auth_status: 'disconnected' as const,
	auth_expires_at: null
};
const models = [
	{
		id: 10,
		provider_id: 1,
		model_name: 'openai/gpt-test',
		api_model_name: 'openai/gpt-test',
		api_provider: 'openai',
		display_name: 'Test',
		is_active: true,
		input_price_per_million: '2',
		output_price_per_million: '8',
		effective_input_price_per_million: '2',
		effective_output_price_per_million: '8',
		effective_price_source: 'models.dev',
		models_dev_model_id: 'openai/gpt-test',
		price_source: 'models.dev'
	},
	{
		id: 11,
		provider_id: 1,
		model_name: 'openai/manual',
		api_model_name: 'openai/manual',
		api_provider: 'openai',
		display_name: 'Manual',
		is_active: true,
		input_price_per_million: '3',
		output_price_per_million: '9',
		models_dev_model_id: null,
		price_source: 'manual',
		effective_input_price_per_million: '3',
		effective_output_price_per_million: '9',
		effective_price_source: 'manual'
	},
	{
		id: 12,
		provider_id: 1,
		model_name: 'perplexity/perplexity/sonar',
		api_model_name: 'perplexity/sonar',
		api_provider: 'perplexity',
		display_name: null,
		is_active: true,
		input_price_per_million: null,
		output_price_per_million: null,
		effective_input_price_per_million: '5.000000',
		effective_output_price_per_million: '22.500000',
		effective_price_source: 'litellm',
		models_dev_model_id: null,
		price_source: null
	}
];

function queueInitialLoads() {
	get.mockImplementation((path: string) => {
		if (path === '/api/v1/chat/admin/providers') return Promise.resolve(provider ? [provider] : []);
		if (path === '/api/v1/chat/admin/models') return Promise.resolve(models);
		if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
		return Promise.resolve([]);
	});
}

describe('admin chat model pricing', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		queueInitialLoads();
	});

	it('renders price values and their source', async () => {
		render(ModelPage);
		await screen.findByText('models.dev');
		expect(screen.getByText('수동')).toBeTruthy();
		expect(screen.getByText(/입력 2 · 출력 8 USD/)).toBeTruthy();
		expect(screen.getByText(/입력 5 · 출력 22\.5 USD/)).toBeTruthy();
	});

	it('shows canonical API metadata separately from the internal routing ID', async () => {
		const testModels = [
			...models,
			{
				id: 13,
				provider_id: 1,
				model_name: 'perplexity/perplexity/deepseek-v4-flash-0731',
				api_model_name: 'perplexity/deepseek-v4-flash-0731',
				api_provider: 'perplexity',
				display_name: null,
				is_active: true,
				capabilities: { web_search: true },
				input_price_per_million: null,
				output_price_per_million: null,
				effective_input_price_per_million: null,
				effective_output_price_per_million: null,
				effective_price_source: 'unpriced' as const,
				models_dev_model_id: null,
				price_source: null
			}
		];
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve(provider ? [provider] : []);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve(testModels);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			return Promise.resolve([]);
		});
		render(ModelPage);
		expect(await screen.findByText('sonar')).toBeTruthy();
		expect(screen.getByText('perplexity/sonar', { selector: 'code' })).toBeTruthy();
		expect(screen.getByText('deepseek-v4-flash-0731')).toBeTruthy();
		expect(screen.getByText('Search')).toBeTruthy();
		expect(screen.getByText('perplexity/perplexity/deepseek-v4-flash-0731')).toBeTruthy();
	});

	it('offers Perplexity Agent, Router, and Sonar transports with exact URL guidance', async () => {
		render(ProviderPage);
		const option = await screen.findByRole('option', { name: 'Perplexity (Agent API · Router · Sonar)' });
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'perplexity' } });

		expect(option).toBeTruthy();
		expect(await screen.findByText(/https:\/\/api\.perplexity\.ai\/v1/)).toBeTruthy();
		expect(screen.getByText(/https:\/\/api\.perplexity\.ai\/router/)).toBeTruthy();
	});

	it('loads and renders billing data only for supported providers', async () => {
		const providers = [
			{
				...provider,
				id: 2,
				name: 'OpenRouter',
				provider_type: 'openrouter',
				billing_capability: 'openrouter_key' as const
			},
			{
				...provider,
				id: 3,
				name: 'DeepSeek',
				provider_type: 'deepseek',
				billing_capability: 'deepseek_balance' as const
			},
			{ ...provider, id: 4, name: 'OpenAI' }
		];
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve(providers);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve([]);
			if (path === '/api/v1/chat/admin/providers/2/billing') {
				return Promise.resolve({
					provider_id: 2,
					provider_type: 'openrouter',
					capability: 'openrouter_key',
					status: 'available',
					reason: null,
					fetched_at: '2026-09-11T00:00:00Z',
					is_available: true,
					is_free_tier: false,
					limit: '100',
					remaining: '75',
					usage_total: '25',
					usage_daily: '1',
					usage_weekly: '5',
					usage_monthly: '20',
					balances: []
				});
			}
			if (path === '/api/v1/chat/admin/providers/3/billing') {
				return Promise.resolve({
					provider_id: 3,
					provider_type: 'deepseek',
					capability: 'deepseek_balance',
					status: 'available',
					reason: null,
					fetched_at: '2026-09-11T00:00:00Z',
					is_available: true,
					is_free_tier: null,
					limit: null,
					remaining: null,
					usage_total: null,
					usage_daily: null,
					usage_weekly: null,
					usage_monthly: null,
					balances: [{ currency: 'USD', total: '48.5', purchased: '40', granted: '8.5' }]
				});
			}
			return Promise.resolve([]);
		});

		render(ProviderPage);

		expect(await screen.findByText('남은 한도')).toBeTruthy();
		expect(screen.getByText('75')).toBeTruthy();
		expect(screen.getByText('구매 40 · 지급 8.5')).toBeTruthy();
		await waitFor(() => {
			expect(get).toHaveBeenCalledWith(
				'/api/v1/chat/admin/providers/2/billing',
				'token',
				'project'
			);
			expect(get).toHaveBeenCalledWith(
				'/api/v1/chat/admin/providers/3/billing',
				'token',
				'project'
			);
		});
		expect(get).not.toHaveBeenCalledWith(
			'/api/v1/chat/admin/providers/4/billing',
			expect.anything(),
			expect.anything()
		);
	});

	it('isolates MCP, skills, and custom HTTP tools on the tool settings route', async () => {
		render(ToolPage);
		expect(await screen.findByText('원격 MCP 서버')).toBeTruthy();
		expect(screen.getByText('커스텀 HTTP 툴')).toBeTruthy();
		expect(screen.getByText('스킬')).toBeTruthy();
		expect(screen.queryByText('LLM 프로바이더')).toBeNull();
	});

	it('saves a complete manual price pair with PATCH', async () => {
		render(ModelPage);
		await screen.findAllByText('가격 수정');
		await fireEvent.click(screen.getAllByText('가격 수정')[0]);
		const modal = screen.getByText('모델 가격 수정').parentElement!;
		const inputs = within(modal).getAllByPlaceholderText(/USD \/ 1M tokens/);
		await fireEvent.input(inputs[0], { target: { value: '3' } });
		await fireEvent.input(inputs[1], { target: { value: '9' } });
		await fireEvent.click(screen.getByText('저장'));
		await waitFor(() => expect(patch).toHaveBeenCalledWith('/api/v1/chat/admin/models/10', {
			input_price_per_million: '3', output_price_per_million: '9'
		}, 'token', 'project'));
	});

	it('preselects an exact catalog match but preserves manual prices', async () => {
		get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/chat/admin/models/pricing/models-dev/providers?')) return Promise.resolve({ providers: [{ id: 'openai', name: 'OpenAI', model_count: 2 }] });
			if (path.includes('/pricing/models-dev/providers/openai')) return Promise.resolve({ models: [
				{ id: 'openai/gpt-test', name: 'GPT Test', input_price_per_million: '2', output_price_per_million: '8', price_available: true, unsupported_price_fields: ['cost.tiers'] },
				{ id: 'openai/manual', name: 'Manual', input_price_per_million: '2', output_price_per_million: '8', price_available: true, unsupported_price_fields: [] }
			] });
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([provider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve(models);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			return Promise.resolve([]);
		});
		render(ModelPage);
		await screen.findAllByText('models.dev 가격');
		await fireEvent.click(screen.getAllByText('models.dev 가격')[0]);
		await screen.findByText('models.dev 추천 가격');
		await screen.findByText(/수동 가격 보존/);
		const checkboxes = screen.getAllByRole('checkbox');
		expect((checkboxes.at(-3) as HTMLInputElement | undefined)?.checked).toBe(true);
		expect((checkboxes.at(-2) as HTMLInputElement | undefined)?.disabled).toBe(true);
		expect(screen.getByText(/tier\/cache\/reasoning\/audio 단가는 적용하지 않습니다/)).toBeTruthy();
	});

	it('searches only the registered catalog candidates', async () => {
		get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/chat/admin/models/pricing/models-dev/providers?')) {
				return Promise.resolve({
					preferred_provider_ids: ['openai'],
					providers: [
						{ id: 'openai', name: 'OpenAI', model_count: 2 },
						{ id: 'anthropic', name: 'Anthropic', model_count: 15 }
					]
				});
			}
			if (path.includes('/pricing/models-dev/providers/openai')) return Promise.resolve({ models: [] });
			if (path.includes('/pricing/models-dev/providers/anthropic')) return Promise.resolve({ models: [] });
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([provider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve(models);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			return Promise.resolve([]);
		});
		render(ModelPage);
		await screen.findAllByText('models.dev 가격');
		await fireEvent.click(screen.getAllByText('models.dev 가격')[0]);
		const search = await screen.findByRole('searchbox', { name: '가격표 프로바이더 검색' });
		await fireEvent.input(search, { target: { value: 'anth' } });
		const providerSelect = screen.getByLabelText('가격표 프로바이더');
		await waitFor(() => expect(within(providerSelect).getByRole('option', { name: 'Anthropic (15)' })).toBeTruthy());
		expect(within(providerSelect).queryByRole('option', { name: 'OpenAI (2)' })).toBeNull();
		await fireEvent.input(search, { target: { value: 'missing' } });
		await screen.findByText('검색 조건에 맞는 가격표 프로바이더가 없습니다.');
		expect((screen.getByRole('button', { name: '선택 가격 적용' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.queryByText('가격표를 불러오는 중…')).toBeNull();
	});

	it('requires an explicit catalog choice when the current provider has no match', async () => {
		get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/chat/admin/models/pricing/models-dev/providers?')) {
				return Promise.resolve({
					preferred_provider_ids: [],
					providers: [{ id: 'anthropic', name: 'Anthropic', model_count: 15 }]
				});
			}
			if (path === '/api/v1/chat/admin/providers') {
				return Promise.resolve([{ ...provider, name: 'Custom gateway', provider_type: 'custom', models_dev_provider_id: null }]);
			}
			if (path === '/api/v1/chat/admin/models') return Promise.resolve(models);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			return Promise.resolve([]);
		});
		render(ModelPage);
		await screen.findAllByText('models.dev 가격');
		await fireEvent.click(screen.getAllByText('models.dev 가격')[0]);
		const providerSelect = await screen.findByLabelText('가격표 프로바이더') as HTMLSelectElement;
		expect(providerSelect.value).toBe('');
		expect((screen.getByRole('button', { name: '선택 가격 적용' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('keeps the modal open and shows a concrete error when import fails', async () => {
		post.mockRejectedValueOnce(new Error('catalog unavailable'));
		get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/chat/admin/models/pricing/models-dev/providers?')) return Promise.resolve({ providers: [{ id: 'openai', name: 'OpenAI', model_count: 1 }] });
			if (path.includes('/pricing/models-dev/providers/openai')) return Promise.resolve({ models: [{ id: 'openai/gpt-test', name: 'GPT Test', input_price_per_million: '2', output_price_per_million: '8', price_available: true, unsupported_price_fields: [] }] });
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([provider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve(models);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			return Promise.resolve([]);
		});
		render(ModelPage);
		await screen.findByText('Test');
		await fireEvent.click(screen.getByText('models.dev 가격'));
		await screen.findByText('선택 가격 적용');
		await fireEvent.click(screen.getByText('선택 가격 적용'));
		await screen.findByText('가격 import 실패');
		expect(screen.getByText('models.dev 추천 가격')).toBeTruthy();
	});

	it('clears hidden API credentials and creates a ChatGPT subscription with an explicit auth mode', async () => {
		post.mockResolvedValueOnce(chatgptProvider);
		render(ProviderPage);
		await screen.findByRole('option', { name: 'ChatGPT 구독 (실험)' });

		await fireEvent.input(screen.getByLabelText('API Base'), { target: { value: 'https://private.example/v1' } });
		await fireEvent.input(screen.getByLabelText('API 키'), { target: { value: 'must-be-cleared' } });
		const connection = screen.getByRole('combobox');
		await fireEvent.change(connection, { target: { value: 'chatgpt-subscription' } });
		expect(screen.queryByLabelText('API 키')).toBeNull();

		await fireEvent.change(connection, { target: { value: 'openai' } });
		expect((screen.getByLabelText('API Base') as HTMLInputElement).value).toBe('');
		expect((screen.getByLabelText('API 키') as HTMLInputElement).value).toBe('');
		await fireEvent.change(connection, { target: { value: 'chatgpt-subscription' } });
		await fireEvent.input(screen.getByPlaceholderText('예: openai-prod'), { target: { value: 'shared-chatgpt' } });
		await fireEvent.click(screen.getByRole('button', { name: '+ 프로바이더 추가' }));

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'/api/v1/chat/admin/providers',
				{
					name: 'shared-chatgpt',
					provider_type: 'chatgpt',
					auth_mode: 'chatgpt_device'
				},
				'token',
				'project'
			)
		);
		expect(await screen.findByText('ChatGPT 구독 연결')).toBeTruthy();
		expect(post).toHaveBeenCalledTimes(1);
	});

	it('keeps a created Claude provider available when token registration fails safely', async () => {
		const tokenValue = 'sk-ant-oat01-test-fixture-subscription-token';
		post.mockResolvedValueOnce(claudeSubscriptionProvider);
		put.mockRejectedValueOnce(new ApiError(JSON.stringify({ code: 'subscription_upstream_unavailable', message: '구독 인증 공급자에 연결할 수 없습니다' }), 503));
		render(ProviderPage);
		await screen.findByRole('option', { name: 'Claude 구독 (실험)' });

		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'claude-subscription' } });
		await fireEvent.input(screen.getByPlaceholderText('예: openai-prod'), { target: { value: 'shared-claude' } });
		await fireEvent.click(screen.getByRole('button', { name: '+ 프로바이더 추가' }));
		await screen.findByText('Claude 구독 토큰 등록');
		await fireEvent.input(screen.getByPlaceholderText('setup-token'), { target: { value: tokenValue } });
		await fireEvent.click(screen.getByRole('button', { name: '구독 토큰 등록' }));

		expect(await screen.findByText(/연결할 수 없습니다/)).toBeTruthy();
		expect(post).toHaveBeenCalledTimes(1);
		expect(put).toHaveBeenCalledWith(
			'/api/v1/chat/admin/providers/8/auth/token',
			{ token: tokenValue, expires_at: null },
			'token',
			'project'
		);
		expect(screen.queryByText(tokenValue)).toBeNull();
	});

	it('starts ChatGPT device auth explicitly and keeps polling single-flight', async () => {
		const { promise: pollResponse, resolve: resolvePoll } = Promise.withResolvers<unknown>();
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([chatgptProvider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve([]);
			return Promise.resolve([]);
		});
		post.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers/7/auth/device') {
				return Promise.resolve({
					attempt_id: 'attempt-opaque',
					status: 'pending',
					verification_uri: 'https://auth.openai.com/device',
					user_code: 'ABCD-EFGH',
					expires_at: new Date(Date.now() + 600_000).toISOString(),
					interval_seconds: 300
				});
			}
			if (path.endsWith('/poll')) return pollResponse;
			throw new Error(`unexpected POST ${path}`);
		});
		render(ProviderPage);
		await screen.findByText('shared-chatgpt');
		await fireEvent.click(screen.getByRole('button', { name: '연결' }));

		expect(screen.queryByText('ABCD-EFGH')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'ChatGPT 연결' }));
		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'/api/v1/chat/admin/providers/7/auth/device',
				{},
				'token',
				'project'
			)
		);
		expect(await screen.findByText('ABCD-EFGH')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '지금 확인' }));
		await fireEvent.click(screen.getByRole('button', { name: '확인 중…' }));
		expect(post.mock.calls.filter(([path]) => String(path).endsWith('/poll'))).toHaveLength(1);

		resolvePoll({
			attempt_id: 'attempt-opaque',
			status: 'connected',
			expires_at: new Date(Date.now() + 600_000).toISOString(),
			interval_seconds: 300
		});
		expect(await screen.findByText('연결 완료')).toBeTruthy();
	});

	it('ignores a late device-start response after the modal closes', async () => {
		const { promise: startResponse, resolve: resolveStart } = Promise.withResolvers<unknown>();
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([chatgptProvider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve([]);
			return Promise.resolve([]);
		});
		post.mockReturnValueOnce(startResponse);
		render(ProviderPage);
		await screen.findByText('shared-chatgpt');
		await fireEvent.click(screen.getByRole('button', { name: '연결' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ChatGPT 연결' }));
		await fireEvent.click(screen.getByRole('button', { name: '닫기' }));

		resolveStart({
			attempt_id: 'late-attempt',
			status: 'pending',
			verification_uri: 'https://auth.openai.com/device',
			user_code: 'LATE-CODE',
			expires_at: new Date(Date.now() + 600_000).toISOString(),
			interval_seconds: 1
		});
		await Promise.resolve();
		expect(screen.queryByText('LATE-CODE')).toBeNull();
		expect(screen.queryByText('ChatGPT 구독 연결')).toBeNull();
	});

	it('preserves opaque subscription model identifiers during registration', async () => {
		const opaqueModel = 'chatgpt/gpt-5.2-codex';
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([chatgptProvider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve([]);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			if (path === '/api/v1/chat/admin/providers/7/available-models') {
				return Promise.resolve({ models: [opaqueModel], source: 'litellm' });
			}
			return Promise.resolve([]);
		});
		post.mockResolvedValue({});
		render(ModelPage);
		await screen.findAllByRole('option', { name: 'shared-chatgpt' });
		await fireEvent.click(screen.getByRole('button', { name: '모델 불러오기' }));
		expect(await screen.findByText(/정적 카탈로그 후보/)).toBeTruthy();
		await fireEvent.click(screen.getByRole('checkbox', { name: opaqueModel }));
		await fireEvent.click(screen.getByRole('button', { name: '선택 모델 등록' }));

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'/api/v1/chat/admin/models',
				{ provider_id: 7, model_name: opaqueModel },
				'token',
				'project'
			)
		);
	});

	it('queries and renders billing only for providers with a supported capability', async () => {
		const openRouterProvider = {
			...provider,
			id: 9,
			name: 'OpenRouter',
			provider_type: 'openrouter',
			billing_capability: 'openrouter_key' as const
		};
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') {
				return Promise.resolve([provider, openRouterProvider]);
			}
			if (path === '/api/v1/chat/admin/models') return Promise.resolve([]);
			if (path === '/api/v1/chat/admin/providers/9/billing') {
				return Promise.resolve({
					provider_id: 9,
					provider_type: 'openrouter',
					capability: 'openrouter_key',
					status: 'available',
					reason: null,
					fetched_at: '2026-09-11T00:00:00Z',
					is_available: null,
					is_free_tier: false,
					limit: '100',
					remaining: '75',
					usage_total: '25',
					usage_daily: '1',
					usage_weekly: '5',
					usage_monthly: '20',
					balances: []
				});
			}
			return Promise.resolve([]);
		});

		render(ProviderPage);

		expect(await screen.findByText('남은 한도')).toBeTruthy();
		expect(screen.getByText('이번 달 사용')).toBeTruthy();
		expect(screen.getByText(/오늘 1 · 이번 주 5 · 유료 크레딧/)).toBeTruthy();
		expect(get).toHaveBeenCalledWith(
			'/api/v1/chat/admin/providers/9/billing',
			'token',
			'project'
		);
		expect(get).not.toHaveBeenCalledWith(
			'/api/v1/chat/admin/providers/1/billing',
			expect.anything(),
			expect.anything()
		);
	});
});

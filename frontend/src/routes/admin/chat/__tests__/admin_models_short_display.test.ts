import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ModelPage from '../models/+page.svelte';

const get = vi.fn();
vi.mock('$lib/api/client', () => ({
	api: {
		get: (...args: unknown[]) => get(...args),
		post: vi.fn(),
		patch: vi.fn(),
		delete: vi.fn()
	},
	ApiError: class extends Error {}
}));

vi.mock('$lib/stores/auth', () => {
	const { readable } = require('svelte/store');
	return {
		auth: readable({ token: 'mock-token', projectId: 'test-project', user: { is_admin: true } })
	};
});

const provider = {
	id: 1,
	name: 'Perplexity',
	provider_type: 'perplexity',
	api_base: 'https://api.perplexity.ai/v1',
	has_api_key: true,
	is_active: true
};
const googleProvider = {
	id: 2,
	name: 'google',
	provider_type: 'gemini',
	api_base: null,
	has_api_key: true,
	is_active: true
};

const geminiImageModels = [
	{
		id: 101,
		provider_id: 2,
		model_name: 'gemini/gemini-3.1-flash-lite',
		api_model_name: 'gemini-3.1-flash-lite',
		api_provider: 'gemini',
		display_name: null,
		is_active: true,
		is_title_model: false,
		capabilities: { vision: true, thinking: true, tools: true },
		effective_input_price_per_million: 0.25,
		effective_output_price_per_million: 1.5,
		price_source: null
	},
	{
		id: 102,
		provider_id: 2,
		model_name: 'gemini/gemini-3.8-flash',
		api_model_name: 'gemini-3.8-flash',
		api_provider: 'gemini',
		display_name: 'gemini/gemini-3.8-flash',
		is_active: true,
		is_title_model: false,
		capabilities: { vision: true, thinking: true, tools: true },
		effective_input_price_per_million: 0.75,
		effective_output_price_per_million: 3.75,
		price_source: null
	}
];

const image1Models = [
	{
		id: 1,
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
	},
	{
		id: 2,
		provider_id: 1,
		model_name: 'perplexity/perplexity/glm-5.3',
		api_model_name: 'perplexity/glm-5.3',
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
	},
	{
		id: 3,
		provider_id: 1,
		model_name: 'perplexity/perplexity/glm-5.3-flash',
		api_model_name: 'perplexity/glm-5.3-flash',
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
	},
	{
		id: 4,
		provider_id: 1,
		model_name: 'perplexity/perplexity/kimi-k3',
		api_model_name: 'perplexity/kimi-k3',
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
	},
	{
		id: 5,
		provider_id: 1,
		model_name: 'perplexity/perplexity/nemotron-3-ultra-550b-a55b',
		api_model_name: 'perplexity/nemotron-3-ultra-550b-a55b',
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
	},
	{
		id: 6,
		provider_id: 1,
		model_name: 'perplexity/perplexity/nemotron-3.5-lightning-30b-a3b',
		api_model_name: 'perplexity/nemotron-3.5-lightning-30b-a3b',
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
	},
	{
		id: 7,
		provider_id: 1,
		model_name: 'perplexity/perplexity/sonar',
		api_model_name: 'perplexity/sonar',
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

describe('admin chat models short name display', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([provider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve(image1Models);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			return Promise.resolve([]);
		});
	});

	it('renders clean shortened names without perplexity/perplexity/ in model titles', async () => {
		render(ModelPage);

		// Every model in Image #1 renders with its clean, shortened name
		expect((await screen.findAllByText('deepseek-v4-flash-0731')).length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('glm-5.3').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('glm-5.3-flash').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('kimi-k3').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('nemotron-3-ultra-550b-a55b').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('nemotron-3.5-lightning-30b-a3b').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('sonar').length).toBeGreaterThanOrEqual(1);

		// Capability badges render Search
		expect(screen.getAllByText('Search').length).toBe(7);

		// Internal routing IDs are clearly displayed as secondary metadata
		expect(screen.getByText('perplexity/perplexity/deepseek-v4-flash-0731')).toBeTruthy();
		expect(screen.getByText('perplexity/perplexity/sonar')).toBeTruthy();
	});

	it('renders clean shortened names without gemini/ prefix for Gemini models', async () => {
		get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/providers') return Promise.resolve([googleProvider]);
			if (path === '/api/v1/chat/admin/models') return Promise.resolve(geminiImageModels);
			if (path === '/api/v1/chat/admin/models/title') return Promise.resolve({ model_id: null });
			return Promise.resolve([]);
		});

		render(ModelPage);
		// Titles render with clean shortened names
		expect((await screen.findAllByText('gemini-3.1-flash-lite')).length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('gemini-3.8-flash').length).toBeGreaterThanOrEqual(1);

		// Internal routing IDs are rendered as secondary metadata
		expect(screen.getByText('gemini/gemini-3.1-flash-lite')).toBeTruthy();
		expect(screen.getByText('gemini/gemini-3.8-flash')).toBeTruthy();
	});
});

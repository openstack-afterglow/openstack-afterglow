import { fireEvent, render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import ModelPickerOverlay from '../ModelPickerOverlay.svelte';
import { t } from '$lib/i18n/ns/chat-studio';

const models = [
	{ id: 1, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'gpt-5', api_model_name: 'gpt-5', api_provider: 'openai', display_name: 'GPT 5', provider: 'OpenAI' },
	{ id: 2, provider_id: 2, provider_type: 'anthropic', provider_sort_order: 0, sort_order: 0, model_name: 'claude-sonnet', api_model_name: 'claude-sonnet', api_provider: 'anthropic', display_name: 'Claude Sonnet', provider: 'Anthropic' },
	{ id: 3, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'gpt-4.1', api_model_name: 'gpt-4.1', api_provider: 'openai', display_name: 'GPT 4.1', provider: 'OpenAI' },
	{ id: 4, provider_id: 3, provider_type: 'perplexity', provider_sort_order: 0, sort_order: 0, model_name: 'perplexity/perplexity/sonar', api_model_name: 'perplexity/sonar', api_provider: 'perplexity', display_name: 'Sonar', provider: 'Perplexity' }
];

function renderPicker(availableModels = models) {
	return render(ModelPickerOverlay, {
		open: true,
		models: availableModels,
		value: 'gpt-5',
		onSelect: vi.fn(),
		onClose: vi.fn()
	});
}

describe('ModelPickerOverlay provider navigation', () => {
	it('keeps identically labelled providers separate and selects the internal route identity', async () => {
		const onSelect = vi.fn();
		const sameLabel = [
			{ ...models[0], provider: 'Shared label' },
			{ ...models[1], provider: 'Shared label', api_model_name: models[0].api_model_name }
		];
		const view = render(ModelPickerOverlay, { open: true, models: sameLabel, value: models[0].model_name, onSelect, onClose: vi.fn() });
		const providerButtons = view.getAllByRole('button', { name: /Shared label/ });
		expect(providerButtons).toHaveLength(2);
		await fireEvent.click(providerButtons[1]);
		expect(view.queryByRole('button', { name: t('modelPicker.selectModel', { name: models[0].display_name }) })).toBeNull();
		await fireEvent.click(view.getByRole('button', { name: t('modelPicker.selectModel', { name: models[1].display_name }) }));
		expect(onSelect).toHaveBeenCalledWith(models[1].model_name);
	});

	it('shows a provider selector for multiple providers and filters the model list', async () => {
		const view = renderPicker();
		const navigation = view.getByRole('navigation', { name: '모델 프로바이더' });

		expect(view.getByRole('button', { name: 'GPT 5 모델 선택' })).toBeTruthy();
		expect(view.getByRole('button', { name: 'Claude Sonnet 모델 선택' })).toBeTruthy();
		await fireEvent.click(view.getByRole('button', { name: /OpenAI/ }));

		expect(navigation).toBeTruthy();
		expect(view.getByRole('button', { name: 'GPT 4.1 모델 선택' })).toBeTruthy();
		expect(view.queryByRole('button', { name: 'Claude Sonnet 모델 선택' })).toBeNull();
	});

	it('omits provider navigation when every model uses the same provider', () => {
		const view = renderPicker(models.filter((model) => model.provider === 'OpenAI'));

		expect(view.queryByRole('navigation', { name: '모델 프로바이더' })).toBeNull();
		expect(view.getByRole('button', { name: 'GPT 5 모델 선택' })).toBeTruthy();
	});

	it('keeps name and provider search filtering available', async () => {
		const view = renderPicker();

		await fireEvent.input(view.getByPlaceholderText('모델 검색 (이름·API ID·프로바이더)'), {
			target: { value: 'Anthropic' }
		});

		expect(view.getByRole('button', { name: 'Claude Sonnet 모델 선택' })).toBeTruthy();
		expect(view.queryByRole('button', { name: 'GPT 5 모델 선택' })).toBeNull();
	});

	it('searches and copies the canonical API ID instead of the internal route key', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			configurable: true,
			value: { writeText }
		});
		const view = renderPicker();

		await fireEvent.input(view.getByPlaceholderText('모델 검색 (이름·API ID·프로바이더)'), {
			target: { value: 'perplexity/sonar' }
		});
		expect(view.getByText('perplexity/sonar')).toBeTruthy();
		expect(view.getByText('perplexity', { selector: 'code' })).toBeTruthy();
		expect(view.queryByText('perplexity/perplexity/sonar')).toBeNull();

		await fireEvent.click(view.getByRole('button', { name: 'perplexity/sonar API 모델 ID 복사' }));
		expect(writeText).toHaveBeenCalledWith('perplexity/sonar');
	});
	it('keeps the catalog provider and model order instead of sorting display labels', async () => {
		const ordered = [
			{ ...models[2], id: 13, provider_id: 4, provider_type: 'openai', api_provider: 'nvidia', provider: 'NVIDIA', display_name: 'Z model', model_name: 'nim/z', provider_sort_order: 1, sort_order: 1 },
			{ ...models[0], id: 12, provider_id: 4, provider_type: 'openai', api_provider: 'nvidia', provider: 'NVIDIA', display_name: 'A model', model_name: 'nim/a', provider_sort_order: 1, sort_order: 2 },
			{ ...models[0], provider_sort_order: 2 },
			{ ...models[1], provider_sort_order: 3 }
		];
		const view = renderPicker(ordered);
		const navigation = view.getByRole('navigation', { name: '모델 프로바이더' });
		expect(Array.from(navigation.querySelectorAll('button > span:first-child'), (node) => node.textContent)).toEqual(['전체 모델', 'NVIDIA', 'OpenAI', 'Anthropic']);
		expect(Array.from(view.container.querySelectorAll('.group-label'), (node) => node.textContent)).toEqual(['NVIDIA', 'OpenAI', 'Anthropic']);
		expect(view.getAllByRole('button', { name: /모델 선택$/ }).map((button) => button.getAttribute('aria-label'))).toEqual(['Z model 모델 선택', 'A model 모델 선택', 'GPT 5 모델 선택', 'Claude Sonnet 모델 선택']);

		await fireEvent.click(view.getByRole('button', { name: /NVIDIA/ }));
		expect(view.getAllByRole('button', { name: /모델 선택$/ }).map((button) => button.getAttribute('aria-label'))).toEqual(['Z model 모델 선택', 'A model 모델 선택']);
		expect(view.getAllByText('nvidia', { selector: 'code' })).toHaveLength(2);
	});

	it('retains provider filtering and the selected model when refreshed catalog order changes', async () => {
		const onSelect = vi.fn();
		const view = render(ModelPickerOverlay, { open: true, models, value: 'gpt-5', onSelect, onClose: vi.fn() });
		await fireEvent.click(view.getByRole('button', { name: /OpenAI/ }));
		await view.rerender({ models: [models[3], models[2], models[0], models[1]] });

		expect(view.getByRole('button', { name: /OpenAI/ }).getAttribute('aria-pressed')).toBe('true');
		expect(view.getByRole('button', { name: 'GPT 5 모델 선택' }).getAttribute('aria-pressed')).toBe('true');
		expect(view.getAllByRole('button', { name: /모델 선택$/ }).map((button) => button.getAttribute('aria-label'))).toEqual(['GPT 4.1 모델 선택', 'GPT 5 모델 선택']);
		expect(view.queryByRole('button', { name: 'Sonar 모델 선택' })).toBeNull();
		expect(onSelect).not.toHaveBeenCalled();
	});
	it('keeps a provider filter bound to its ID when its label and API selector change', async () => {
		const view = renderPicker();
		await fireEvent.click(view.getByRole('button', { name: /Anthropic/ }));
		await view.rerender({ models: models.map((model) => model.provider_id === 2 ? { ...model, provider: 'Claude', api_provider: 'claude' } : model) });

		expect(view.getByRole('button', { name: /Claude 1/ }).getAttribute('aria-pressed')).toBe('true');
		expect(view.getByRole('button', { name: 'Claude Sonnet 모델 선택' })).toBeTruthy();
		expect(view.getByText('claude', { selector: 'code' })).toBeTruthy();
		expect(view.queryByRole('button', { name: 'GPT 5 모델 선택' })).toBeNull();
	});
});

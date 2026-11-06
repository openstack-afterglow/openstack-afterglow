import { fireEvent, render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import ModelSelector from '../ModelSelector.svelte';

const models = [
	{ id: 1, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'route/alpha', api_model_name: 'alpha-v1', api_provider: 'openai', display_name: 'Alpha', provider: 'Provider A' },
	{ id: 2, provider_id: 2, provider_type: 'anthropic', provider_sort_order: 0, sort_order: 0, model_name: 'route/beta', api_model_name: 'beta-v1', api_provider: 'anthropic', display_name: 'Beta', provider: 'Provider B' }
];

describe('ModelSelector regex resource matching', () => {
	it('matches independent anchored fields and never changes selection when filtering or refreshing', async () => {
		const onSelect = vi.fn();
		const view = render(ModelSelector, { models, value: models[0].model_name, onSelect });
		await fireEvent.click(view.getByRole('button', { expanded: false }));
		const input = view.getByRole('textbox');
		expect(document.activeElement).toBe(input);
		await fireEvent.input(input, { target: { value: '^(BETA-V1|anthropic)$' } });
		expect(view.queryByRole('option', { name: /Alpha/ })).toBeNull();
		expect(view.getByRole('option', { name: /Beta/ })).toBeTruthy();
		await view.rerender({ models: [...models].reverse() });
		expect((input as HTMLInputElement).value).toBe('^(BETA-V1|anthropic)$');
		expect(onSelect).not.toHaveBeenCalled();
		await fireEvent.click(view.getByRole('option', { name: /Beta/ }));
		expect(onSelect).toHaveBeenCalledWith(models[1].model_name);
	});

	it('shows an inline error and no options for malformed patterns', async () => {
		const onSelect = vi.fn();
		const view = render(ModelSelector, { models, value: models[0].model_name, onSelect });
		await fireEvent.click(view.getByRole('button', { expanded: false }));
		const input = view.getByRole('textbox');
		await fireEvent.input(input, { target: { value: '[' } });
		expect(input.getAttribute('aria-invalid')).toBe('true');
		expect(view.getByRole('alert')).toBeTruthy();
		expect(view.queryAllByRole('option')).toHaveLength(0);
		expect(onSelect).not.toHaveBeenCalled();
	});
});

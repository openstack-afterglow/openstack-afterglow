import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/chat-studio';
import ProviderModelSelect from '../ProviderModelSelect.svelte';
import AgentBuilderForm from '../AgentBuilderForm.svelte';
import { emptyAgentForm } from '$lib/api/chatAgents';

const rows = [
	{ id: 1, provider_id: 1, provider: 'OpenAI', provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'gpt-a', display_name: 'GPT A', domain_billing: { ready: false, reason_code: 'pricing_unavailable' as const } },
	{ id: 2, provider_id: 1, provider: 'OpenAI', provider_type: 'openai', provider_sort_order: 0, sort_order: 1, model_name: 'gpt-b', display_name: 'GPT B' }
];

describe('ProviderModelSelect domain billing', () => {
	it('keeps unready rows visible but disabled with their reason', async () => {
		const onSelect = vi.fn();
		render(ProviderModelSelect, { models: rows, value: null, onSelect, modelLabel: 'Model' });
		const unready = screen.getByRole('option', { name: t('modelBilling.option', { name: 'GPT A', reason: t('modelBilling.pricing') }) }) as HTMLOptionElement;
		expect(unready.disabled).toBe(true);
		expect((screen.getByRole('option', { name: 'GPT B' }) as HTMLOptionElement).disabled).toBe(false);
		await fireEvent.change(screen.getByRole('combobox', { name: 'Model' }), { target: { value: '1' } });
		expect(onSelect).toHaveBeenLastCalledWith(null);
		await fireEvent.change(screen.getByRole('combobox', { name: 'Model' }), { target: { value: '2' } });
		expect(onSelect).toHaveBeenLastCalledWith(rows[1]);
	});

	it('shows the reason for an agent pinned to an unready model', () => {
		const form = { ...emptyAgentForm(), name: 'Pinned', model_row_id: 1, model_name: 'gpt-a' };
		render(AgentBuilderForm, { form, models: rows, mcps: [], tools: [], onSubmit: vi.fn(), onCancel: vi.fn() });
		expect(screen.getByRole('status').textContent).toBe(t('modelBilling.pricing'));
	});
});
